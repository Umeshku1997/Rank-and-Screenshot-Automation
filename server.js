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

// Set mandatory SSE headers for real-time log streaming
function setupSSEHeaders(res) {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache, no-transform');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no');
    if (res.flushHeaders) res.flushHeaders();
}

// Handler to spawn Python script and stream terminal output live
function executePythonScript(req, res, scriptFileName) {
    setupSSEHeaders(res);

    const targetScript = scriptFileName || req.query.path || req.query.script || 'run_both.py';
    const scriptPath = path.join(__dirname, targetScript);
    const pythonBin = process.env.PYTHON_BIN || 'python3';

    res.write(`data: ${JSON.stringify({ type: 'stdout', message: `[System] Starting script: ${targetScript}...\n` })}\n\n`);

    if (!fs.existsSync(scriptPath)) {
        res.write(`data: ${JSON.stringify({ type: 'stderr', message: `[Error] Script file '${targetScript}' not found on server root!\n` })}\n\n`);
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
        res.write(`data: ${JSON.stringify({ type: 'stderr', message: text })}\n\n`);
    });

    child.on('close', (code) => {
        res.write(`data: ${JSON.stringify({ type: 'end', message: `[Task Complete] (Exit Code: ${code})` })}\n\n`);
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

// 1. Primary Endpoint matching exact Frontend request (/run-stream)
app.get('/run-stream', (req, res) => {
    executePythonScript(req, res);
});

// 2. Auxiliary Endpoints matching secondary or dynamic calls
app.get(['/api/stream', '/api/stream/together', '/run', '/api/run'], (req, res) => {
    executePythonScript(req, res);
});

// 3. Static fallback for Dashboard UI
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
