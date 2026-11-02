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

// 1. Explicit SSE Route Handling (Placed FIRST to block static fallback)
app.get(['/run-stream', '/api/stream', '/api/stream/together'], (req, res) => {
    // Force SSE Headers
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache, no-transform');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no');
    if (res.flushHeaders) res.flushHeaders();

    const scriptFile = req.query.path || req.query.script || 'run_both.py';
    const scriptPath = path.join(__dirname, scriptFile);
    const pythonBin = process.env.PYTHON_BIN || 'python3';

    res.write(`data: ${JSON.stringify({ type: 'stdout', message: `[System] Starting script: ${scriptFile}...\n` })}\n\n`);

    if (!fs.existsSync(scriptPath)) {
        res.write(`data: ${JSON.stringify({ type: 'stderr', message: `[Error] Script file '${scriptFile}' not found in root directory!\n` })}\n\n`);
        res.write(`data: ${JSON.stringify({ type: 'end', message: '[Task Complete]' })}\n\n`);
        return res.end();
    }

    const child = spawn(pythonBin, ['-u', scriptPath], {
        cwd: __dirname,
        env: {
            ...process.env,
            PYTHONUNBUFFERED: '1',
            DISPLAY: process.env.DISPLAY || ':99'
        }
    });

    child.stdout.on('data', (data) => {
        const text = data.toString();
        res.write(`data: ${JSON.stringify({ type: 'stdout', message: text })}\n\n`);
    });

    child.stderr.on('data', (data) => {
        const text = data.toString();
        res.write(`data: ${JSON.stringify({ type: 'stdout', message: `[LOG] ${text}` })}\n\n`);
    });

    child.on('close', (code) => {
        res.write(`data: ${JSON.stringify({ type: 'end', message: `[Task Complete] Exit Code: ${code}` })}\n\n`);
        res.end();
    });

    child.on('error', (err) => {
        res.write(`data: ${JSON.stringify({ type: 'stdout', message: `[EXEC ERROR] ${err.message}\n` })}\n\n`);
        res.end();
    });

    req.on('close', () => {
        child.kill();
    });
});

// 2. Static File Serving (No automatic index.html resolution)
app.use(express.static(path.join(__dirname, 'public'), { index: false }));

// 3. Page Route for Front-end UI
app.get('/', (req, res) => {
    const indexPath = path.join(__dirname, 'public', 'index.html');
    if (fs.existsSync(indexPath)) {
        res.sendFile(indexPath);
    } else {
        res.status(404).send('Index HTML not found');
    }
});

app.listen(PORT, () => {
    console.log(`🚀 Server running on port ${PORT}`);
});
