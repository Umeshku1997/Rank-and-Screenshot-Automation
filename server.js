import express from 'express';
import http from 'http';
import httpProxy from 'http-proxy';
import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';
import crypto from 'crypto';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT || 10000;

// Optional: Render Environment me APP_PASSWORD set karoge to poori site par password lagega
// (browser ka popup aayega: username kuch bhi, password = APP_PASSWORD)
const APP_PASSWORD = process.env.APP_PASSWORD || '';

const ALLOWED_SCRIPTS = new Set(['run_both.py', 'desktop_rank.py', 'mobile_rank.py']);
const ALLOWED_DOWNLOAD_EXT = new Set(['.xlsx', '.csv', '.png']);
const NOVNC_DIR = '/usr/share/novnc';

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// ------------------------------------------------------------
// AUTH (optional)
// ------------------------------------------------------------
function isAuthorized(req) {
    if (!APP_PASSWORD) return true;
    const header = req.headers['authorization'] || '';
    if (!header.startsWith('Basic ')) return false;
    const decoded = Buffer.from(header.slice(6), 'base64').toString('utf8');
    const given = decoded.slice(decoded.indexOf(':') + 1);
    const a = Buffer.from(given);
    const b = Buffer.from(APP_PASSWORD);
    return a.length === b.length && crypto.timingSafeEqual(a, b);
}

app.get('/healthz', (req, res) => res.send('ok'));

app.use((req, res, next) => {
    if (isAuthorized(req)) return next();
    res.setHeader('WWW-Authenticate', 'Basic realm="Gempundit Catalog"');
    res.status(401).send('Password required');
});

// ------------------------------------------------------------
// JOB MANAGER  (script background me chalti hai, browser band hone par bhi)
// ------------------------------------------------------------
const MAX_LOG_LINES = 5000;

const job = {
    running: false,
    script: null,
    mode: null,
    startedAt: null,
    endedAt: null,
    exitCode: null,
    lines: [],
    clients: new Set(),
    child: null
};

function emit(line) {
    job.lines.push(line);
    if (job.lines.length > MAX_LOG_LINES) job.lines.shift();
    for (const res of job.clients) res.write(`data: ${line}\n\n`);
}

function killChromeLeftovers() {
    for (const name of ['chromium', 'chromedriver']) {
        try { spawn('pkill', ['-f', name], { stdio: 'ignore' }); } catch (e) { /* ignore */ }
    }
}

function finishJob(code) {
    if (!job.running) return;
    job.running = false;
    job.endedAt = new Date().toISOString();
    job.exitCode = code;
    job.child = null;
    killChromeLeftovers();
    emit(`[Task Complete] Exit code: ${code}`);
    for (const res of job.clients) res.end();
    job.clients.clear();
}

function startJob(scriptFile, mode) {
    job.running = true;
    job.script = scriptFile;
    job.mode = mode;
    job.startedAt = new Date().toISOString();
    job.endedAt = null;
    job.exitCode = null;
    job.lines = [];

    const args = ['-u', path.join(__dirname, scriptFile)];
    if (scriptFile === 'run_both.py') args.push(mode || 'together');

    emit(`[System] Starting live script execution: ${scriptFile}...`);

    const child = spawn('python3', args, {
        cwd: __dirname,
        detached: true, // alag process group, taaki Stop par sab band ho
        stdio: ['ignore', 'pipe', 'pipe'],
        env: {
            ...process.env,
            PYTHONUNBUFFERED: '1',
            PYTHONIOENCODING: 'utf-8',
            DISPLAY: ':99' // virtual screen (Xvfb)
        }
    });
    job.child = child;

    const pump = (prefix) => (data) => {
        data.toString().split('\n').forEach(line => {
            if (line.trim()) emit(`${prefix}${line}`);
        });
    };
    child.stdout.on('data', pump(''));
    child.stderr.on('data', pump('[LOG] '));

    child.on('close', (code) => finishJob(code));
    child.on('error', (err) => {
        emit(`[EXEC ERROR] ${err.message}`);
        finishJob(-1);
    });
}

function stopJob() {
    if (!job.running || !job.child) return false;
    emit('[System] Stop requested...');
    const pid = job.child.pid;
    try { process.kill(-pid, 'SIGTERM'); } catch (e) { /* ignore */ }
    setTimeout(() => {
        if (job.running) {
            try { process.kill(-pid, 'SIGKILL'); } catch (e) { /* ignore */ }
        }
    }, 8000);
    return true;
}

function setSSEHeaders(res) {
    res.setHeader('Content-Type', 'text/event-stream; charset=utf-8');
    res.setHeader('Cache-Control', 'no-cache, no-transform');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no');
    if (res.flushHeaders) res.flushHeaders();
}

// Client ko stream se jodo (purani lines replay + live)
function attachClient(req, res) {
    job.lines.forEach(line => res.write(`data: ${line}\n\n`));

    if (!job.running) {
        res.write('data: [Task Complete]\n\n');
        return res.end();
    }

    job.clients.add(res);
    const heartbeat = setInterval(() => res.write(': keep-alive\n\n'), 15000);
    res.on('close', () => {
        clearInterval(heartbeat);
        job.clients.delete(res); // sirf viewer hata, script chalti rahegi
    });
}

// Start (agar khali ho) + attach
function startAndStream(req, res, forceScript) {
    setSSEHeaders(res);

    let scriptFile = forceScript || req.query.path || req.query.script || 'run_both.py';
    scriptFile = path.basename(String(scriptFile));

    if (!ALLOWED_SCRIPTS.has(scriptFile) || !fs.existsSync(path.join(__dirname, scriptFile))) {
        res.write(`data: [Error] Script not allowed or file missing: ${scriptFile}\n\n`);
        res.write('data: [Task Complete]\n\n');
        return res.end();
    }

    if (job.running) {
        res.write(`data: [System] Ek run pehle se chal raha hai (${job.script}). Usi se jud rahe hain...\n\n`);
    } else {
        startJob(scriptFile, req.query.mode);
    }
    attachClient(req, res);
}

app.get('/run-stream', (req, res) => startAndStream(req, res));
app.get('/api/stream', (req, res) => startAndStream(req, res));
app.get('/api/stream/together', (req, res) => startAndStream(req, res, 'run_both.py'));
app.get('/api/stream/desktop', (req, res) => startAndStream(req, res, 'desktop_rank.py'));
app.get('/api/stream/mobile', (req, res) => startAndStream(req, res, 'mobile_rank.py'));

// Sirf jud jao (naya run start nahi hoga)
app.get('/api/job/stream', (req, res) => {
    setSSEHeaders(res);
    attachClient(req, res);
});

app.get('/api/job/status', (req, res) => {
    res.json({
        running: job.running,
        script: job.script,
        startedAt: job.startedAt,
        endedAt: job.endedAt,
        exitCode: job.exitCode,
        lines: job.lines.length
    });
});

app.all('/api/job/stop', (req, res) => {
    res.json({ stopped: stopJob() });
});

// ------------------------------------------------------------
// RESULT FILES  (Excel / CSV / Screenshots)
// ------------------------------------------------------------
function listFiles(dir, base = dir, out = []) {
    if (!fs.existsSync(dir)) return out;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        if (entry.name === 'node_modules' || entry.name.startsWith('.')) continue;
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
            if (dir === base && entry.name !== 'Screenshots') continue;
            listFiles(full, base, out);
        } else if (ALLOWED_DOWNLOAD_EXT.has(path.extname(entry.name).toLowerCase())) {
            const stat = fs.statSync(full);
            out.push({
                path: path.relative(base, full).split(path.sep).join('/'),
                size: stat.size,
                modified: stat.mtime
            });
        }
    }
    return out;
}

app.get('/api/files', (req, res) => res.json(listFiles(__dirname)));

app.get('/download', (req, res) => {
    const rel = String(req.query.file || '');
    const full = path.resolve(__dirname, rel);
    const insideApp = full.startsWith(__dirname + path.sep);
    const okExt = ALLOWED_DOWNLOAD_EXT.has(path.extname(full).toLowerCase());
    const notModules = !full.includes(`${path.sep}node_modules${path.sep}`);
    if (!insideApp || !okExt || !notModules || !fs.existsSync(full)) {
        return res.status(404).send('File not found');
    }
    res.download(full);
});

// Sab kuch ek zip me: Excel + CSV + Screenshots
app.get('/download/results.zip', (req, res) => {
    const items = fs.readdirSync(__dirname).filter(n => {
        const ext = path.extname(n).toLowerCase();
        return (ext === '.xlsx' || ext === '.csv') && !n.startsWith('.');
    });
    if (fs.existsSync(path.join(__dirname, 'Screenshots'))) items.push('Screenshots');

    if (items.length === 0) return res.status(404).send('Abhi koi result file nahi hai.');

    const stamp = new Date().toISOString().slice(0, 10);
    res.setHeader('Content-Type', 'application/zip');
    res.setHeader('Content-Disposition', `attachment; filename="rank-results-${stamp}.zip"`);

    const zip = spawn('zip', ['-r', '-q', '-', ...items], { cwd: __dirname });
    zip.stdout.pipe(res);
    zip.on('error', () => res.end());
    res.on('close', () => zip.kill());
});

// ------------------------------------------------------------
// LIVE BROWSER (noVNC)  ->  /novnc/vnc.html  +  websocket /websockify
// ------------------------------------------------------------
if (fs.existsSync(NOVNC_DIR)) {
    app.use('/novnc', express.static(NOVNC_DIR));
}

const proxy = httpProxy.createProxyServer({ target: 'ws://127.0.0.1:6080', ws: true });
proxy.on('error', () => { /* VNC abhi ready nahi, ignore */ });

// ------------------------------------------------------------
// UI
// ------------------------------------------------------------
app.use(express.static(path.join(__dirname, 'public'), { index: false }));

app.get('/', (req, res) => {
    const indexPath = path.join(__dirname, 'public', 'index.html');
    if (fs.existsSync(indexPath)) {
        res.sendFile(indexPath);
    } else {
        res.status(404).send('UI Index Missing');
    }
});

const server = http.createServer(app);

server.on('upgrade', (req, socket, head) => {
    if (req.url.startsWith('/websockify') && isAuthorized(req)) {
        proxy.ws(req, socket, head);
    } else {
        socket.destroy();
    }
});

server.listen(PORT, () => console.log(`🚀 Server active on port ${PORT}`));
