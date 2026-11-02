const express = require('express');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = process.env.PORT || 10000;

// Body parsing and static file serving
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname, 'public')));

// Set proper headers for SSE streaming
function setSSEHeaders(res) {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache, no-transform');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no');
    if (res.flushHeaders) res.flushHeaders();
}

// 1. Specific Stream Route for 'Run Desktop & Mobile Together'
app.get('/api/stream/together', (req, res) => {
    setSSEHeaders(res);

    const pythonBin = process.env.PYTHON_BIN || 'python3';
    const scriptPath = path.join(__dirname, 'run_both.py');

    res.write(`data: ${JSON.stringify({ type: 'stdout', message: 'Starting Dual Execution...\n' })}\n\n`);

    const child = spawn(pythonBin, ['-u', scriptPath, 'together'], {
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
        res.write(`data: ${JSON.stringify({ type: 'end', message: `[Task Complete]` })}\n\n`);
        res.end();
    });

    child.on('error', (err) => {
        res.write(`data: ${JSON.stringify({ type: 'stderr', message: `Execution Error: ${err.message}` })}\n\n`);
        res.end();
    });

    req.on('close', () => {
        child.kill();
    });
});

// 2. Generic Dynamic Stream Endpoint (For individual desktop_rank.py or mobile_rank.py)
app.get('/api/stream', (req, res) => {
    setSSEHeaders(res);

    const scriptFile = req.query.script || 'run_both.py';
    const scriptPath = path.join(__dirname, scriptFile);

    if (!fs.existsSync(scriptPath)) {
        res.write(`data: ${JSON.stringify({ type: 'stderr', message: `File not found: ${scriptFile}` })}\n\n`);
        res.end();
        return;
    }

    const pythonBin = process.env.PYTHON_BIN || 'python3';
    const child = spawn(pythonBin, ['-u', scriptPath], {
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
        res.write(`data: ${JSON.stringify({ type: 'end', message: `[Task Complete]` })}\n\n`);
        res.end();
    });

    req.on('close', () => {
        child.kill();
    });
});

// 3. Fallback Route for Front-end Dashboard SPA
app.get('*', (req, res) => {
    const indexPath = path.join(__dirname, 'public', 'index.html');
    if (fs.existsSync(indexPath)) {
        res.sendFile(indexPath);
    } else {
        res.status(404).send('Dashboard UI Index File Not Found');
    }
});

app.listen(PORT, () => {
    console.log(`🚀 Server running on port ${PORT}`);
});
