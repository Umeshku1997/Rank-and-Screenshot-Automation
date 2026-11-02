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

function setSSEHeaders(res) {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache, no-transform');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no');
    if (res.flushHeaders) res.flushHeaders();
}

function runPythonProcess(req, res, targetScript, modeArg) {
    setSSEHeaders(res);

    const scriptFile = targetScript || req.query.path || req.query.script || req.query.file || 'run_both.py';
    const scriptPath = path.join(__dirname, scriptFile);

    res.write(`data: ${JSON.stringify({ type: 'stdout', message: `[System] Executing ${scriptFile}...\n` })}\n\n`);

    if (!fs.existsSync(scriptPath)) {
        res.write(`data: ${JSON.stringify({ type: 'stderr', message: `[Error] File standard missing: ${scriptFile}\n` })}\n\n`);
        res.write(`data: ${JSON.stringify({ type: 'end', message: '[Task Complete]' })}\n\n`);
        return res.end();
    }

    const scriptArgs = ['-u', scriptPath];
    if (scriptFile === 'run_both.py') {
        scriptArgs.push(modeArg || req.query.mode || 'together');
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
            if (line.trim()) {
                res.write(`data: ${JSON.stringify({ type: 'stdout', message: `${line}\n` })}\n\n`);
            }
        });
    });

    child.stderr.on('data', (data) => {
        const lines = data.toString().split('\n');
        lines.forEach(line => {
            if (line.trim()) {
                res.write(`data: ${JSON.stringify({ type: 'stdout', message: `[LOG] ${line}\n` })}\n\n`);
            }
        });
    });

    child.on('close', (code) => {
        res.write(`data: ${JSON.stringify({ type: 'end', message: `[Task Complete] Exit code: ${code}` })}\n\n`);
        res.end();
    });

    child.on('error', (err) => {
        res.write(`data: ${JSON.stringify({ type: 'stderr', message: `[EXEC ERROR] ${err.message}\n` })}\n\n`);
        res.end();
    });

    req.on('close', () => {
        child.kill();
    });
}

// 1. All Endpoints map to process runner cleanly
app.get('/run-stream', (req, res) => runPythonProcess(req, res));
app.get('/api/stream', (req, res) => runPythonProcess(req, res));
app.get('/api/stream/together', (req, res) => runPythonProcess(req, res, 'run_both.py', 'together'));
app.get('/api/stream/desktop', (req, res) => runPythonProcess(req, res, 'desktop_rank.py'));
app.get('/api/stream/mobile', (req, res) => runPythonProcess(req, res, 'mobile_rank.py'));

// 2. Serve public static assets
app.use(express.static(path.join(__dirname, 'public'), { index: false }));

app.get('/', (req, res) => {
    const indexPath = path.join(__dirname, 'public', 'index.html');
    if (fs.existsSync(indexPath)) {
        res.sendFile(indexPath);
    } else {
        res.status(404).send('Dashboard UI Index Missing');
    }
});

app.listen(PORT, () => {
    console.log(`🚀 Server running on port ${PORT}`);
});
