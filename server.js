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

// --- AUTOMATIC WINDOWS PATH MAPPING FOR PYTHON SCRIPTS ---
function setupWindowsPathAlias() {
    try {
        const virtualDirPath = path.join(__dirname, 'D:', 'Python code', 'New Rank Automation');
        if (!fs.existsSync(virtualDirPath)) {
            fs.mkdirSync(virtualDirPath, { recursive: true });
        }

        const sourceKeywords = path.join(__dirname, 'keywords.txt');
        const targetKeywords = path.join(virtualDirPath, 'keywords.txt');

        if (fs.existsSync(sourceKeywords)) {
            fs.copyFileSync(sourceKeywords, targetKeywords);
            console.log('✅ Synchronized GitHub keywords.txt to Windows virtual path');
        } else {
            console.log('⚠️ Warning: keywords.txt missing in GitHub root repository!');
        }
    } catch (err) {
        console.error('Path alias creation error:', err.message);
    }
}

// Run path sync on boot
setupWindowsPathAlias();

function setSSEHeaders(res) {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache, no-transform');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no');
    if (res.flushHeaders) res.flushHeaders();
}

function executeProcess(req, res, targetScript, defaultMode) {
    setSSEHeaders(res);
    setupWindowsPathAlias(); // Re-sync before every run

    const scriptFile = targetScript || req.query.path || req.query.script || req.query.file || 'run_both.py';
    const scriptPath = path.join(__dirname, scriptFile);

    const sendMsg = (text) => {
        res.write(`data: ${text}\n\n`);
        res.write(`data: ${JSON.stringify({ type: 'stdout', message: text })}\n\n`);
    };

    sendMsg(`[System] Initializing execution for ${scriptFile}...`);

    if (!fs.existsSync(scriptPath)) {
        sendMsg(`[Error] Script '${scriptFile}' not found in container root.`);
        sendMsg(`[Task Complete]`);
        return res.end();
    }

    const args = ['-u', scriptPath];
    if (scriptFile === 'run_both.py') {
        args.push(defaultMode || req.query.mode || 'together');
    }

    const child = spawn('python3', args, {
        cwd: __dirname,
        env: {
            ...process.env,
            PYTHONUNBUFFERED: '1',
            DISPLAY: process.env.DISPLAY || ':99'
        }
    });

    child.stdout.on('data', (data) => {
        sendMsg(data.toString());
    });

    child.stderr.on('data', (data) => {
        sendMsg(`[LOG] ${data.toString()}`);
    });

    child.on('close', (code) => {
        sendMsg(`[Task Complete] Exit code: ${code}`);
        res.end();
    });

    child.on('error', (err) => {
        sendMsg(`[EXEC ERROR] ${err.message}`);
        res.end();
    });

    req.on('close', () => {
        child.kill();
    });
}

// Stream Routing Endpoints
app.get('/run-stream', (req, res) => executeProcess(req, res));
app.get('/api/stream', (req, res) => executeProcess(req, res));
app.get('/api/stream/together', (req, res) => executeProcess(req, res, 'run_both.py', 'together'));
app.get('/api/stream/desktop', (req, res) => executeProcess(req, res, 'desktop_rank.py'));
app.get('/api/stream/mobile', (req, res) => executeProcess(req, res, 'mobile_rank.py'));

// Public Assets
app.use(express.static(path.join(__dirname, 'public'), { index: false }));

app.get('/', (req, res) => {
    const indexPath = path.join(__dirname, 'public', 'index.html');
    if (fs.existsSync(indexPath)) {
        res.sendFile(indexPath);
    } else {
        res.status(404).send('Dashboard Index Missing');
    }
});

app.listen(PORT, () => {
    console.log(`🚀 Server running on port ${PORT}`);
});
