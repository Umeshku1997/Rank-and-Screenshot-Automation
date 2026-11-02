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

// Ensure keywords.txt exists before running
const keywordsPath = path.join(projectRoot, 'keywords.txt');
if (!fs.existsSync(keywordsPath)) {
    console.log("Creating default keywords.txt...");
    fs.writeFileSync(keywordsPath, "Pukhraj Stone Price\nHessonite Garnet Natural Srilanka\n");
}

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(projectRoot, 'public')));

app.get('/api/run-automation', (req, res) => {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');

    const pythonExecutable = process.platform === 'win32' ? 'python' : 'python3';
    
    // Explicit environment variables for Linux Chromium Execution
    const customEnv = {
        ...process.env,
        PYTHONUNBUFFERED: "1",
        PYTHONIOENCODING: "utf-8",
        CHROME_BIN: process.env.CHROME_BIN || "/usr/bin/chromium",
        CHROMEDRIVER_PATH: process.env.CHROMEDRIVER_PATH || "/usr/bin/chromedriver",
        HEADLESS_MODE: "true"
    };

    res.write(`data: ${JSON.stringify({ log: "[DESKTOP] 🚀 Initializing Rank Automation Tasks...\n[MOBILE] 🚀 Initializing Rank Automation Tasks...\n" })}\n\n`);

    // Force run_both.py in 'together' mode with unbuffered output (-u)
    const pyProc = spawn(pythonExecutable, ['-u', 'run_both.py', 'together'], { cwd: projectRoot, env: customEnv });

    const sendLog = (text) => {
        const lines = text.split('\n');
        lines.forEach(line => {
            if (line.trim()) {
                console.log(line);
                if (line.toLowerCase().includes('mobile')) {
                    res.write(`data: ${JSON.stringify({ log: `[MOBILE] ${line}` })}\n\n`);
                } else {
                    res.write(`data: ${JSON.stringify({ log: `[DESKTOP] ${line}` })}\n\n`);
                }
            }
        });
    };

    pyProc.stdout.on('data', (d) => sendLog(d.toString()));
    pyProc.stderr.on('data', (d) => sendLog(`[ERROR] ${d.toString()}`));

    pyProc.on('close', (code) => {
        console.log(`Automation finished with exit code ${code}`);
        res.write(`data: ${JSON.stringify({ log: `\n[DESKTOP] [Task Complete - Code ${code}]\n[MOBILE] [Task Complete - Code ${code}]\n` })}\n\n`);
        res.end();
    });

    pyProc.on('error', (err) => {
        sendLog(`[CRITICAL ERROR] Failed to start Python process: ${err.message}`);
    });
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
