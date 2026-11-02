#!/usr/bin/env node
// Smoke test: opens index.html from disk in headless Chrome and checks it against data.js.
//
//   node scripts/smoke_test.mjs            # exit code 0 = all checks passed
//   node scripts/smoke_test.mjs https://freko247.github.io/university-requirements/   # check the live site
//   CHROME=/path/to/chrome node scripts/smoke_test.mjs
//
// No npm packages needed: talks to Chrome over the DevTools protocol (Node 22+ for global WebSocket).
// Run it after `uv run scripts/build_data.py` or any change to index.html.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const pageUrl = process.argv[2] || pathToFileURL(path.join(root, 'index.html')).href;
console.log(`Testing ${pageUrl}`);
const chromePath = process.env.CHROME || [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser',
].find(p => fs.existsSync(p));
if (!chromePath) { console.error('Chrome not found; set CHROME=/path/to/chrome'); process.exit(2); }

const sleep = ms => new Promise(r => setTimeout(r, ms));
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'kot-smoke-'));
const port = 9400 + Math.floor(Math.random() * 500);
const chrome = spawn(chromePath, ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, 'about:blank'], { stdio: 'ignore' });

let failures = 0;
const check = (name, ok, detail = '') => {
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`);
    if (!ok) failures++;
};

try {
    let tabs;
    for (let i = 0; i < 50 && !tabs; i++) {
        try { tabs = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); } catch { await sleep(200); }
    }
    const ws = new WebSocket(tabs.find(t => t.type === 'page').webSocketDebuggerUrl);
    await new Promise(r => ws.onopen = r);
    let id = 0; const pending = {}; const problems = [];
    ws.onmessage = e => {
        const m = JSON.parse(e.data);
        if (m.method === 'Runtime.exceptionThrown') problems.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
        if (m.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(m.params.type)) problems.push(m.params.args.map(a => a.value ?? a.description).join(' '));
        if (pending[m.id]) { pending[m.id](m); delete pending[m.id]; }
    };
    const send = (method, params = {}) => new Promise(r => { const i = ++id; pending[i] = r; ws.send(JSON.stringify({ id: i, method, params })); });
    const ev = async expr => {
        const r = (await send('Runtime.evaluate', { expression: expr, returnByValue: true })).result;
        if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
        return r.result.value;
    };
    const load = async width => {
        await send('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: width < 600 });
        await send('Page.navigate', { url: pageUrl });
        await sleep(3000);
        await ev(`window.__set = (id, v, e) => { const el = document.getElementById(id); el.value = v; el.dispatchEvent(new Event(e)); }; true`);
    };
    await send('Page.enable'); await send('Runtime.enable');

    // --- Desktop -----------------------------------------------------------------------------
    await load(1400);
    const basics = await ev(`({
        programs: KOT_DATA.programs.length, loaded: kotData.length, rows: document.querySelectorAll('#tableBody tr').length,
        rowCount: document.getElementById('rowCount').innerText,
        years: JSON.stringify(KOT_DATA.years), yearOptions: JSON.stringify([...document.getElementById('yearFilter').options].map(o => o.value).filter(v => v !== 'median').sort()),
        insts: new Set(KOT_DATA.programs.map(p => p.institution)).size, instOptions: document.getElementById('institutionFilter').options.length - 1,
        locs: new Set(KOT_DATA.programs.map(p => p.location)).size, locOptions: document.getElementById('locationFilter').options.length - 1,
        mapped: new Set(KOT_DATA.programs.filter(p => p.lat != null).map(p => p.location)).size, markers: markers.size,
        countText: document.querySelector('[data-fill="count"]').textContent,
    })`);
    check('data.js loads and all programs are used', basics.programs > 0 && basics.loaded === basics.programs, `${basics.loaded}/${basics.programs}`);
    check('table renders rows', basics.rows > 0 && /^Showing \d+ matching programs$/.test(basics.rowCount), basics.rowCount);
    check('year dropdown matches data.years', basics.years === basics.yearOptions, basics.yearOptions);
    check('institution dropdown lists every institution', basics.insts === basics.instOptions, `${basics.instOptions}/${basics.insts}`);
    check('location dropdown lists every location', basics.locs === basics.locOptions, `${basics.locOptions}/${basics.locs}`);
    check('one map marker per location with coordinates', basics.mapped === basics.markers, `${basics.markers}/${basics.mapped}`);
    check('header count filled from data', basics.countText === basics.programs.toLocaleString('en-US'), basics.countText);

    // Eligibility counts per year at GPA 7, recomputed here independently of the page's code.
    const KIND = { cutoff: 'cutoff', all_admitted: 'eligible', quota2_only: 'other', outside_quota: 'other', not_offered: 'unavailable', none_admitted: 'unavailable', not_listed: 'unavailable' };
    const perYear = await ev(`(() => {
        const KIND = ${JSON.stringify(KIND)};
        __set('userGpaInput', '7', 'input');
        return KOT_DATA.years.map(y => {
            __set('yearFilter', y, 'change');
            const c = { eligible: 0, other: 0, unavailable: 0, unknown: 0 };
            KOT_DATA.programs.forEach(p => {
                const e = p.years[y]; const k = KIND[e.status];
                if (!k) c.unknown++;
                else if (k === 'cutoff') { if (7 >= e.cutoff) c.eligible++; }
                else c[k]++;
            });
            return { y, expected: c, shown: document.getElementById('eligibleCount').innerText };
        });
    })()`);
    for (const { y, expected: c, shown } of perYear) {
        const want = `Eligible for ${c.eligible} of ${basics.programs} programs`;
        const ok = c.unknown === 0 && shown.startsWith(want)
            && (!c.other || shown.includes(`${c.other} not decided by GPA`))
            && (!c.unavailable || shown.includes(`${c.unavailable} not offered`));
        check(`${y}: eligibility counts at GPA 7 match the data`, ok, shown + (c.unknown ? ` (${c.unknown} unknown status codes)` : ''));
    }

    const ui = await ev(`(() => {
        __set('userGpaInput', '', 'input'); __set('yearFilter', 'median', 'change');
        const first = document.querySelector('#tableBody tr');
        const sparkOk = !!first.querySelector('svg, td span');
        first.click();
        const detail = document.querySelector('#tableBody tr + tr.bg-gray-50');
        const boxes = detail ? detail.querySelectorAll('.flex > div').length : 0;
        const loc = [...markers.keys()][0];
        __set('locationFilter', loc, 'change');
        const locOk = filteredData.length > 0 && filteredData.every(p => p.location === loc);
        document.getElementById('resetFilterBtn').click();
        return { sparkOk, boxes, years: KOT_DATA.years.length, locOk, afterReset: filteredData.length, total: kotData.length };
    })()`);
    check('trend cell renders', ui.sparkOk);
    check('clicking a row shows one box per year', ui.boxes === ui.years, `${ui.boxes}/${ui.years}`);
    check('location filter narrows the table', ui.locOk);
    check('Clear Filters restores all programs', ui.afterReset === ui.total, `${ui.afterReset}/${ui.total}`);

    // --- Phone width ---------------------------------------------------------------------------
    await load(390);
    const phone = await ev(`(() => { const t = document.getElementById('programsTable'); return { table: t.scrollWidth, box: t.parentElement.clientWidth, page: document.documentElement.scrollWidth }; })()`);
    check('phone width: page and table fit without horizontal scrolling', phone.page <= 390 && phone.table <= phone.box, `page ${phone.page}px, table ${phone.table}px in ${phone.box}px`);

    check('no console errors, warnings or exceptions', problems.length === 0, problems.slice(0, 3).join(' | '));
    ws.close();
} catch (e) {
    check('smoke test ran to completion', false, e.message);
} finally {
    chrome.kill();
    await sleep(300);
    fs.rmSync(profile, { recursive: true, force: true });
}
console.log(failures ? `\n${failures} check(s) failed` : '\nAll checks passed');
process.exit(failures ? 1 : 0);
