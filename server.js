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

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(projectRoot, 'public')));

// Run Automation Route: Triggering run_both.py together
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

    res.write(`data: ${JSON.stringify({ log: "[DESKTOP] 🚀 Spawning run_both.py script...\n[MOBILE] 🚀 Spawning run_both.py script...\n" })}\n\n`);

    // Spawning run_both.py directly just like VS Code
    const pyProc = spawn(pythonExecutable, ['run_both.py', 'together'], { cwd: projectRoot, env: customEnv });

    const handleData = (data) => {
        const text = data.toString();
        const lines = text.split('\n');
        lines.forEach(line => {
            if (line.trim()) {
                console.log(line);
                // Smart Routing for split terminals in index.html
                if (line.includes('MOBILE') || line.includes('Mobile')) {
                    res.write(`data: ${JSON.stringify({ log: `[MOBILE] ${line}` })}\n\n`);
                } else {
                    res.write(`data: ${JSON.stringify({ log: `[DESKTOP] ${line}` })}\n\n`);
                }
            }
        });
    };

    pyProc.stdout.on('data', handleData);
    pyProc.stderr.on('data', (d) => {
        const errText = d.toString();
        console.error("STDERR:", errText);
        res.write(`data: ${JSON.stringify({ log: `[DESKTOP ERROR] ${errText}` })}\n\n`);
    });

    pyProc.on('close', (code) => {
        console.log(`run_both.py finished with code ${code}`);
        res.write(`data: ${JSON.stringify({ log: `\n[DESKTOP] [Task Complete]\n[MOBILE] [Task Complete]\n` })}\n\n`);
        res.end();
    });

    pyProc.on('error', (err) => {
        res.write(`data: ${JSON.stringify({ log: `[DESKTOP ERROR] CRITICAL: ${err.message}` })}\n\n`);
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
