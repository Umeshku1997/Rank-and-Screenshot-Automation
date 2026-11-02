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

// Global script runner logic
function executeScript(req, res, forceScript) {
    setSSEHeaders(res);

    const scriptName = forceScript || req.query.path || req.query.script || req.query.file || 'run_both.py';
    const scriptPath = path.join(__dirname, scriptName);
    const mode = req.query.mode || '';

    res.write(`data: ${JSON.stringify({ type: 'stdout', message: `[System] Initializing ${scriptName} ${mode}...\n` })}\n\n`);

    if (!fs.existsSync(scriptPath)) {
        res.write(`data: ${JSON.stringify({ type: 'stderr', message: `[Error] Script file '${scriptName}' not found!\n` })}\n\n`);
        res.write(`data: ${JSON.stringify({ type: 'end', message: '[Task Complete]' })}\n\n`);
        return res.end();
    }

    const args = ['-u', scriptPath];
    if (mode) args.push(mode);

    const child = spawn('python3', args, {
        cwd: __dirname,
        env: {
            ...process.env,
            PYTHONUNBUFFERED: '1',
            DISPLAY: process.env.DISPLAY || ':99'
        }
    });

    child.stdout.on('data', (data) => {
        res.write(`data: ${JSON.stringify({ type: 'stdout', message: data.toString() })}\n\n`);
    });

    child.stderr.on('data', (data) => {
        res.write(`data: ${JSON.stringify({ type: 'stdout', message: `[LOG] ${data.toString()}` })}\n\n`);
    });

    child.on('close', (code) => {
        res.write(`data: ${JSON.stringify({ type: 'end', message: `[Task Complete] Exit code: ${code}` })}\n\n`);
        res.end();
    });

    child.on('error', (err) => {
        res.write(`data: ${JSON.stringify({ type: 'stdout', message: `[EXEC ERROR] ${err.message}\n` })}\n\n`);
        res.end();
    });

    req.on('close', () => {
        child.kill();
    });
}

// EventSource Routes
app.get('/run-stream', (req, res) => executeScript(req, res));
app.get('/api/stream', (req, res) => executeScript(req, res));
app.get('/api/stream/desktop', (req, res) => executeScript(req, res, 'desktop_rank.py'));
app.get('/api/stream/mobile', (req, res) => executeScript(req, res, 'mobile_rank.py'));

// Serve Static Frontend Assets (bypassing route collisions)
app.use(express.static(path.join(__dirname, 'public'), { index: false }));

app.get('/', (req, res) => {
    const indexPath = path.join(__dirname, 'public', 'index.html');
    if (fs.existsSync(indexPath)) {
        res.sendFile(indexPath);
    } else {
        res.status(404).send('Dashboard HTML missing');
    }
});

app.listen(PORT, () => {
    console.log(`🚀 Server running on port ${PORT}`);
});
