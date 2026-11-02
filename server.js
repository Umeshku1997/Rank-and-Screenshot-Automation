const express = require('express');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = process.env.PORT || 10000;

app.use(express.static(path.join(__dirname, 'public')));
app.use(express.json());

// Main EventSource Stream Endpoint
app.get('/api/stream/together', (req, res) => {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no');

    const pythonExecutable = 'python3';
    const scriptPath = path.join(__dirname, 'run_both.py');

    res.write(`data: ${JSON.stringify({ type: 'stdout', message: 'Starting Python scripts...\n' })}\n\n`);

    const child = spawn(pythonExecutable, ['-u', scriptPath, 'together'], {
        cwd: __dirname,
        env: { ...process.env, PYTHONUNBUFFERED: '1' }
    });

    child.stdout.on('data', (data) => {
        const text = data.toString();
        res.write(`data: ${JSON.stringify({ type: 'stdout', message: text })}\n\n`);
    });

    child.stderr.on('data', (data) => {
        const text = data.toString();
        res.write(`data: ${JSON.stringify({ type: 'stderr', message: text })}\n\n`);
    });

    child.on('close', (code) => {
        res.write(`data: ${JSON.stringify({ type: 'end', message: `[Task Complete] Exit code: ${code}` })}\n\n`);
        res.end();
    });

    child.on('error', (err) => {
        res.write(`data: ${JSON.stringify({ type: 'stderr', message: `Error spawning script: ${err.message}` })}\n\n`);
        res.end();
    });

    req.on('close', () => {
        child.kill();
    });
});

// Serve UI index html fallback
app.get('*', (req, res) => {
    const indexPath = path.join(__dirname, 'public', 'index.html');
    if (fs.existsSync(indexPath)) {
        res.sendFile(indexPath);
    } else {
        res.status(404).send('Dashboard UI HTML file not found.');
    }
});

app.listen(PORT, () => {
    console.log(`🚀 Server running on port ${PORT}`);
});
