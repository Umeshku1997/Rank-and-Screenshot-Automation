import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';
import { spawn } from 'child_process';
import fs from 'fs';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 10000;

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, './');

// Compatibility setup for local folder references & keywords placement
if (process.platform !== 'win32') {
    const winPath = '/app/D:/Python code/New Rank Automation';
    try {
        if (!fs.existsSync(winPath)) {
            fs.mkdirSync(winPath, { recursive: true });
        }
        const srcKeywords = path.join(projectRoot, 'keywords.txt');
        const destKeywords = path.join(winPath, 'keywords.txt');
        if (fs.existsSync(srcKeywords) && !fs.existsSync(destKeywords)) {
            fs.copyFileSync(srcKeywords, destKeywords);
        }
    } catch (e) {
        console.log("Path mapping note:", e.message);
    }
}

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(projectRoot, 'public')));

// Run Automation Route with Parallel Execution of Desktop & Mobile
app.get('/api/run-automation', (req, res) => {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');

    const pythonExecutable = process.platform === 'win32' ? 'python' : 'python3';
    
    const customEnv = {
        ...process.env,
        PYTHONUNBUFFERED: "1",
        PYTHONIOENCODING: "utf-8",
        CHROME_BIN: process.env.CHROME_BIN || "/usr/bin/chromium",
        CHROMEDRIVER_PATH: process.env.CHROMEDRIVER_PATH || "/usr/bin/chromedriver"
    };

    // Send startup markers to both streams
    res.write(`data: ${JSON.stringify({ log: "[DESKTOP] 🚀 Initializing Desktop Automation Task...\n" })}\n\n`);
    res.write(`data: ${JSON.stringify({ log: "[MOBILE] 🚀 Initializing Mobile Automation Task...\n" })}\n\n`);

    // Direct Parallel Spawning of Desktop and Mobile Trackers
    const desktopProc = spawn(pythonExecutable, ['desktop_rank.py'], { cwd: projectRoot, env: customEnv });
    const mobileProc = spawn(pythonExecutable, ['mobile_rank.py'], { cwd: projectRoot, env: customEnv });

    let activeProcesses = 2;

    const handleData = (data, prefix) => {
        const text = data.toString();
        const lines = text.split('\n');
        lines.forEach(line => {
            if (line.trim()) {
                console.log(`${prefix} ${line}`);
                res.write(`data: ${JSON.stringify({ log: `${prefix} ${line}` })}\n\n`);
            }
        });
    };

    // Forward standard output & error logs with explicit UI tags
    desktopProc.stdout.on('data', (d) => handleData(d, '[DESKTOP]'));
    desktopProc.stderr.on('data', (d) => handleData(d, '[DESKTOP ERROR]'));

    mobileProc.stdout.on('data', (d) => handleData(d, '[MOBILE]'));
    mobileProc.stderr.on('data', (d) => handleData(d, '[MOBILE ERROR]'));

    const checkDone = (code, scriptName, prefix) => {
        const finishMsg = `${prefix} [${scriptName} Finished] Exit Code: ${code}`;
        console.log(finishMsg);
        res.write(`data: ${JSON.stringify({ log: finishMsg })}\n\n`);
        activeProcesses--;
        if (activeProcesses === 0) {
            res.write(`data: ${JSON.stringify({ log: "[DESKTOP] [Task Complete]\n[MOBILE] [Task Complete]\n" })}\n\n`);
            res.end();
        }
    };

    desktopProc.on('close', (code) => checkDone(code, 'DESKTOP', '[DESKTOP]'));
    mobileProc.on('close', (code) => checkDone(code, 'MOBILE', '[MOBILE]'));

    desktopProc.on('error', (err) => handleData(`CRITICAL ERROR: ${err.message}`, '[DESKTOP ERROR]'));
    mobileProc.on('error', (err) => handleData(`CRITICAL ERROR: ${err.message}`, '[MOBILE ERROR]'));
});

app.get('/download-report', (req, res) => {
    const candidatePaths = [
        path.join(projectRoot, 'google_rank_combined.xlsx'),
        path.join(projectRoot, 'outputs', 'google_rank_combined.xlsx'),
        '/app/google_rank_combined.xlsx'
    ];

    const targetFile = candidatePaths.find(p => fs.existsSync(p));

    if (targetFile) {
        res.download(targetFile, 'google_rank_combined.xlsx');
    } else {
        res.status(404).json({ error: 'Report file not found.' });
    }
});

app.get('*', (req, res) => {
    res.sendFile(path.join(projectRoot, 'public', 'index.html'));
});

app.listen(PORT, () => console.log(`🚀 Server running on port ${PORT}`));
