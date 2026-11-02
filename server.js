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
app.use(express.static(path.join(__dirname, 'public')));

function setupSSEHeaders(res) {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache, no-transform');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no');
    if (res.flushHeaders) res.flushHeaders();
}

// Handler function for executing Python scripts safely
function handlePythonExecution(req, res, targetScript) {
    setupSSEHeaders(res);

    const scriptPath = path.join(__dirname, targetScript);
    const pythonBin = process.env.PYTHON_BIN || 'python3';

    res.write(`data: ${JSON.stringify({ type: 'stdout', message: `[System] Executing ${targetScript} on Render...\n` })}\n\n`);

    if (!fs.existsSync(scriptPath)) {
        res.write(`data: ${JSON.stringify({ type: 'stderr', message: `[Error] Script file '${targetScript}' not found on server!\n` })}\n\n`);
        res.write(`data: ${JSON.stringify({ type: 'end', message: '[Task Complete]' })}\n\n`);
        return res.end();
    }

    const child = spawn(pythonBin, ['-u', targetScript], {
        cwd: __dirname,
        env: { ...process.env, PYTHONUNBUFFERED: '1', DISPLAY: process.env.DISPLAY || ':99' }
    });

    child.stdout.on('data', (data) => {
        res.write(`data: ${JSON.stringify({ type: 'stdout', message: data.toString() })}\n\n`);
    });

    child.stderr.on('data', (data) => {
        res.write(`data: ${JSON.stringify({ type: 'stderr', message: data.toString() })}\n\n`);
    });

    child.on('close', (code) => {
        res.write(`data: ${JSON.stringify({ type: 'end', message: `[Task Complete] (Code: ${code})` })}\n\n`);
        res.end();
    });

    child.on('error', (err) => {
        res.write(`data: ${JSON.stringify({ type: 'stderr', message: `[Process Error] ${err.message}\n` })}\n\n`);
        res.end();
    });

    req.on('close', () => {
        child.kill();
    });
}

// 1. Dual stream / Together route handlers
app.get(['/api/stream/together', '/run-together', '/api/run-together'], (req, res) => {
    handlePythonExecution(req, res, 'run_both.py');
});

// 2. Generic API stream handler (catches query params like ?script=run_both.py or ?file=desktop_rank.py)
app.get(['/api/stream', '/stream', '/api/run', '/run'], (req, res) => {
    const scriptFile = req.query.script || req.query.file || req.query.name || 'run_both.py';
    handlePythonExecution(req, res, scriptFile);
});

// 3. Static fallback
app.get('*', (req, res) => {
    const indexPath = path.join(__dirname, 'public', 'index.html');
    if (fs.existsSync(indexPath)) {
        res.sendFile(indexPath);
    } else {
        res.status(404).send('UI Index File Not Found');
    }
});

app.listen(PORT, () => {
    console.log(`🚀 Server running on port ${PORT}`);
});
