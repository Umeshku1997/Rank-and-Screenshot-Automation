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

// Automatic Windows path creation on Linux container
function ensureVirtualKeywordsPath() {
    try {
        const virtualDir = path.join(__dirname, 'D:', 'Python code', 'New Rank Automation');
        if (!fs.existsSync(virtualDir)) {
            fs.mkdirSync(virtualDir, { recursive: true });
        }
        const sourceFile = path.join(__dirname, 'keywords.txt');
        const targetFile = path.join(virtualDir, 'keywords.txt');

        if (fs.existsSync(sourceFile)) {
            fs.copyFileSync(sourceFile, targetFile);
        }
    } catch (err) {
        console.error("Virtual path mapping failed:", err.message);
    }
}

function handleExecution(req, res, forceScript) {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache, no-transform');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no');
    if (res.flushHeaders) res.flushHeaders();

    ensureVirtualKeywordsPath();

    const scriptFile = forceScript || req.query.path || req.query.script || 'run_both.py';
    const scriptPath = path.join(__dirname, scriptFile);

    res.write(`data: [System] Initializing script: ${scriptFile}...\n\n`);

    if (!fs.existsSync(scriptPath)) {
        res.write(`data: [Error] Script missing in container: ${scriptFile}\n\n`);
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

// Routes Mapping
app.get('/run-stream', (req, res) => handleExecution(req, res));
app.get('/api/stream', (req, res) => handleExecution(req, res));
app.get('/api/stream/together', (req, res) => handleExecution(req, res, 'run_both.py'));
app.get('/api/stream/desktop', (req, res) => handleExecution(req, res, 'desktop_rank.py'));
app.get('/api/stream/mobile', (req, res) => handleExecution(req, res, 'mobile_rank.py'));

app.use(express.static(path.join(__dirname, 'public'), { index: false }));

app.get('/', (req, res) => {
    const indexPath = path.join(__dirname, 'public', 'index.html');
    if (fs.existsSync(indexPath)) {
        res.sendFile(indexPath);
    } else {
        res.status(404).send('Dashboard UI Index Missing');
    }
});

app.listen(PORT, () => console.log(`🚀 Server running on port ${PORT}`));
