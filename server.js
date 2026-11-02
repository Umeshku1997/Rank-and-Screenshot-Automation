const express = require('express');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = process.env.PORT || 10000;

app.use(express.static(path.join(__dirname, 'public')));
app.use(express.json());

// Helper function to setup proper SSE headers
function setupSSEHeaders(res) {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache, no-transform');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no'); // Disable proxy buffering for Render
    res.flushHeaders();
}

// Route to run desktop & mobile processes together with live SSE stream
app.get('/api/stream/together', (req, res) => {
    setupSSEHeaders(res);

    const pythonExecutable = process.env.PYTHON_BIN || 'python3';
    const scriptPath = path.join(__dirname, 'run_both.py');

    // Send initial log message to terminal UI
    res.write(`data: ${JSON.stringify({ type: 'stdout', message: 'Starting automation process...\n' })}\n\n`);

    // Spawn python process with unbuffered output (-u)
    const child = spawn(pythonExecutable, ['-u', scriptPath, 'together'], {
        cwd: __dirname,
        env: { ...process.env, PYTHONUNBUFFERED: '1' }
    });

    child.stdout.on('data', (data) => {
        const lines = data.toString().split('\n');
        lines.forEach(line => {
            if (line.trim()) {
                res.write(`data: ${JSON.stringify({ type: 'stdout', message: line })}\n\n`);
            }
        });
    });

    child.stderr.on('data', (data) => {
        const lines = data.toString().split('\n');
        lines.forEach(line => {
            if (line.trim()) {
                res.write(`data: ${JSON.stringify({ type: 'stderr', message: line })}\n\n`);
            }
        });
    });

    child.on('close', (code) => {
        res.write(`data: ${JSON.stringify({ type: 'end', message: `[Task Complete] (Exit Code: ${code})` })}\n\n`);
        res.end();
    });

    child.on('error', (err) => {
        res.write(`data: ${JSON.stringify({ type: 'stderr', message: `Failed to start subprocess: ${err.message}` })}\n\n`);
        res.end();
    });

    req.on('close', () => {
        child.kill();
    });
});

// Generic fall-back stream endpoint for dynamic script routes
app.get('/api/stream', (req, res) => {
    setupSSEHeaders(res);
    
    const scriptName = req.query.script || 'run_both.py';
    const scriptPath = path.join(__dirname, scriptName);

    if (!fs.existsSync(scriptPath)) {
        res.write(`data: ${JSON.stringify({ type: 'stderr', message: `Error: Script ${scriptName} not found.` })}\n\n`);
        res.end();
        return;
    }

    const pythonExecutable = process.env.PYTHON_BIN || 'python3';
    const child = spawn(pythonExecutable, ['-u', scriptPath], {
        cwd: __dirname,
        env: { ...process.env, PYTHONUNBUFFERED: '1' }
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

// Fallback for SPA/Dashboard index
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
