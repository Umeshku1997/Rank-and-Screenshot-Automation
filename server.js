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

// Ensure keywords.txt directory exists for Windows path fallbacks
const windowsDirPath = path.join(__dirname, 'D:', 'Python code', 'New Rank Automation');
if (!fs.existsSync(windowsDirPath)) {
    fs.mkdirSync(windowsDirPath, { recursive: true });
}

// Copy local keywords.txt to Windows path fallback if present in root
const rootKeywords = path.join(__dirname, 'keywords.txt');
const fallbackKeywords = path.join(windowsDirPath, 'keywords.txt');
if (fs.existsSync(rootKeywords) && !fs.existsSync(fallbackKeywords)) {
    fs.copyFileSync(rootKeywords, fallbackKeywords);
}

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

    // Initial log line
    const initMsg = `[System] Executing ${scriptFile}...\n`;
    res.write(`data: ${initMsg}\n\n`);
    res.write(`data: ${JSON.stringify({ type: 'stdout', message: initMsg })}\n\n`);

    if (!fs.existsSync(scriptPath)) {
        const errorMsg = `[Error] File missing: ${scriptFile}\n`;
        res.write(`data: ${errorMsg}\n\n`);
        res.write(`data: ${JSON.stringify({ type: 'stderr', message: errorMsg })}\n\n`);
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
        const rawText = data.toString();
        // Send both plain string and structured JSON for maximum frontend UI compatibility
        res.write(`data: ${rawText}\n\n`);
        res.write(`data: ${JSON.stringify({ type: 'stdout', message: rawText })}\n\n`);
    });

    child.stderr.on('data', (data) => {
        const rawText = data.toString();
        res.write(`data: ${rawText}\n\n`);
        res.write(`data: ${JSON.stringify({ type: 'stdout', message: `[LOG] ${rawText}` })}\n\n`);
    });

    child.on('close', (code) => {
        const endMsg = `[Task Complete] Exit code: ${code}`;
        res.write(`data: ${endMsg}\n\n`);
        res.write(`data: ${JSON.stringify({ type: 'end', message: endMsg })}\n\n`);
        res.end();
    });

    child.on('error', (err) => {
        const errStr = `[EXEC ERROR] ${err.message}\n`;
        res.write(`data: ${errStr}\n\n`);
        res.write(`data: ${JSON.stringify({ type: 'stderr', message: errStr })}\n\n`);
        res.end();
    });

    req.on('close', () => {
        child.kill();
    });
}

// EventSource endpoints mapping
app.get('/run-stream', (req, res) => runPythonProcess(req, res));
app.get('/api/stream', (req, res) => runPythonProcess(req, res));
app.get('/api/stream/together', (req, res) => runPythonProcess(req, res, 'run_both.py', 'together'));
app.get('/api/stream/desktop', (req, res) => runPythonProcess(req, res, 'desktop_rank.py'));
app.get('/api/stream/mobile', (req, res) => runPythonProcess(req, res, 'mobile_rank.py'));

// Serve UI Static Assets
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
