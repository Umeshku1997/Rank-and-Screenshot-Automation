import express from 'express';
import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT || 10000;

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Sirf ye scripts chalane ki permission hai (security: koi bhi file run na ho)
const ALLOWED_SCRIPTS = new Set(['run_both.py', 'desktop_rank.py', 'mobile_rank.py']);

// Download ke liye allowed file types
const ALLOWED_DOWNLOAD_EXT = new Set(['.xlsx', '.csv', '.png']);

// Dynamic Windows Path Mapper for Linux Container (Python Script Path Dependency Fix)
function setupWindowsVirtualPath() {
    try {
        const rootKeywords = path.join(__dirname, 'keywords.txt');
        if (!fs.existsSync(rootKeywords)) return;

        const targetPaths = [
            path.join('/D:', 'Python code', 'New Rank Automation', 'keywords.txt'),
            path.join(__dirname, 'D:', 'Python code', 'New Rank Automation', 'keywords.txt')
        ];

        targetPaths.forEach(targetFile => {
            const dir = path.dirname(targetFile);
            if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
            fs.copyFileSync(rootKeywords, targetFile);
        });
    } catch (err) {
        // Safe catch for environment restrictions
    }
}

// Initial Sync on boot
setupWindowsVirtualPath();

function setSSEHeaders(res) {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache, no-transform');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no');
    if (res.flushHeaders) res.flushHeaders();
}

function runScript(req, res, forceScript) {
    setSSEHeaders(res);
    setupWindowsVirtualPath(); // Always keep paths synced before execution

    let scriptFile = forceScript || req.query.path || req.query.script || 'run_both.py';
    scriptFile = path.basename(String(scriptFile));
    const scriptPath = path.join(__dirname, scriptFile);

    res.write(`data: [System] Starting live script execution: ${scriptFile}...\n\n`);

    if (!ALLOWED_SCRIPTS.has(scriptFile) || !fs.existsSync(scriptPath)) {
        res.write(`data: [Error] Script not allowed or file missing: ${scriptFile}\n\n`);
        res.write(`data: [Task Complete]\n\n`);
        return res.end();
    }

    const scriptArgs = ['-u', scriptPath];
    if (scriptFile === 'run_both.py') {
        scriptArgs.push(req.query.mode || 'together');
    }

    const child = spawn('python3', scriptArgs, {
        cwd: __dirname,
        env: {
            ...process.env,
            PYTHONUNBUFFERED: '1',
            PYTHONIOENCODING: 'utf-8',
            DISPLAY: process.env.DISPLAY || ':99'
        }
    });

    let finished = false;

    // Heartbeat: Render/proxy idle connection band na kare
    const heartbeat = setInterval(() => {
        if (!finished) res.write(': keep-alive\n\n');
    }, 15000);

    const sendLines = (data, prefix = '') => {
        data.toString().split('\n').forEach(line => {
            if (line.trim()) res.write(`data: ${prefix}${line}\n\n`);
        });
    };

    child.stdout.on('data', (data) => sendLines(data));
    child.stderr.on('data', (data) => sendLines(data, '[LOG] '));

    child.on('close', (code) => {
        finished = true;
        clearInterval(heartbeat);
        res.write(`data: [Task Complete] Exit code: ${code}\n\n`);
        res.end();
    });

    child.on('error', (err) => {
        finished = true;
        clearInterval(heartbeat);
        res.write(`data: [EXEC ERROR] ${err.message}\n\n`);
        res.write(`data: [Task Complete]\n\n`);
        res.end();
    });

    // Browser band/minimize hone par script rok do
    res.on('close', () => {
        clearInterval(heartbeat);
        if (!finished) child.kill();
    });
}

// ---------- Script routes ----------
app.get('/run-stream', (req, res) => runScript(req, res));
app.get('/api/stream', (req, res) => runScript(req, res));
app.get('/api/stream/together', (req, res) => runScript(req, res, 'run_both.py'));
app.get('/api/stream/desktop', (req, res) => runScript(req, res, 'desktop_rank.py'));
app.get('/api/stream/mobile', (req, res) => runScript(req, res, 'mobile_rank.py'));

// ---------- Result files (Excel / CSV / Screenshots) ----------
function listFiles(dir, base = dir, out = []) {
    if (!fs.existsSync(dir)) return out;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        if (entry.name === 'node_modules' || entry.name.startsWith('.')) continue;
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
            // Sirf root aur Screenshots folder me dekho
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

// Saari generated files ki list (JSON)
app.get('/api/files', (req, res) => {
    res.json(listFiles(__dirname));
});

// File download: /download?file=google_rank_combined.xlsx
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

// ---------- UI ----------
app.use(express.static(path.join(__dirname, 'public'), { index: false }));

app.get('/', (req, res) => {
    const indexPath = path.join(__dirname, 'public', 'index.html');
    if (fs.existsSync(indexPath)) {
        res.sendFile(indexPath);
    } else {
        res.status(404).send('UI Index Missing');
    }
});

app.listen(PORT, () => console.log(`🚀 Server active on port ${PORT}`));
