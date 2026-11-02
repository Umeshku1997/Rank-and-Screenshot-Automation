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

// Ensure keywords file is copied everywhere Python might check
function syncKeywordsFile() {
    const rootKeywords = path.join(__dirname, 'keywords.txt');
    if (!fs.existsSync(rootKeywords)) return;

    const targetPaths = [
        path.join('/D:', 'Python code', 'New Rank Automation', 'keywords.txt'),
        path.join(__dirname, 'D:', 'Python code', 'New Rank Automation', 'keywords.txt')
    ];

    targetPaths.forEach(targetFile => {
        try {
            const dir = path.dirname(targetFile);
            if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
            fs.copyFileSync(rootKeywords, targetFile);
        } catch (e) {
            // ignore OS system dir warnings
        }
    });
}

syncKeywordsFile();

function setSSEHeaders(res) {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache, no-transform');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no');
    if (res.flushHeaders) res.flushHeaders();
}

function runScript(req, res, forceScript) {
    setSSEHeaders(res);
    syncKeywordsFile();

    const scriptFile = forceScript || req.query.path || req.query.script || 'run_both.py';
    const scriptPath = path.join(__dirname, scriptFile);

    res.write(`data: [System] Starting live script execution: ${scriptFile}...\n\n`);

    if (!fs.existsSync(scriptPath)) {
        res.write(`data: [Error] File missing: ${scriptFile}\n\n`);
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
            DISPLAY: process.env.DISPLAY || ':99'
        }
    });

    child.stdout.on('data', (data) => {
        const lines = data.toString().split('\n');
        lines.forEach(line => {
            if (line.trim()) res.write(`data: ${line}\n\n`);
        });
    });

    child.stderr.on('data', (data) => {
        const lines = data.toString().split('\n');
        lines.forEach(line => {
            if (line.trim()) res.write(`data: [LOG] ${line}\n\n`);
        });
    });

    child.on('close', (code) => {
        res.write(`data: [Task Complete] Exit code: ${code}\n\n`);
        res.end();
    });

    child.on('error', (err) => {
        res.write(`data: [EXEC ERROR] ${err.message}\n\n`);
        res.end();
    });

    req.on('close', () => {
        child.kill();
    });
}

app.get('/run-stream', (req, res) => runScript(req, res));
app.get('/api/stream', (req, res) => runScript(req, res));
app.get('/api/stream/together', (req, res) => runScript(req, res, 'run_both.py'));
app.get('/api/stream/desktop', (req, res) => runScript(req, res, 'desktop_rank.py'));
app.get('/api/stream/mobile', (req, res) => runScript(req, res, 'mobile_rank.py'));

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
