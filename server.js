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

// Windows Virtual Path Mapper for unmodified Python Scripts
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
        console.log("Path mapping notice:", e.message);
    }
}

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(projectRoot, 'public')));

// Run Automation Trigger API
app.get('/api/run-automation', (req, res) => {
    const pythonExecutable = process.platform === 'win32' ? 'python' : 'python3';
    
    console.log("🚀 Spawning Python Automation Process...");
    
    // Environment variables pass headless mode to Selenium
    const customEnv = {
        ...process.env,
        PYTHONUNBUFFERED: "1",
        SELENIUM_HEADLESS: "true"
    };

    const pythonProcess = spawn(pythonExecutable, ['run_both.py'], {
        cwd: projectRoot,
        env: customEnv
    });

    pythonProcess.stdout.on('data', (data) => {
        console.log(`[LOG]: ${data.toString()}`);
    });

    pythonProcess.stderr.on('data', (data) => {
        console.error(`[ERROR]: ${data.toString()}`);
    });

    pythonProcess.on('close', (code) => {
        console.log(`Process finished with exit code ${code}`);
        if (code === 0) {
            res.json({ status: 'success', message: 'Automation finished successfully!' });
        } else {
            res.status(500).json({ status: 'error', message: 'Script execution failed' });
        }
    });
});

// Download Endpoint
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
        res.status(404).json({ error: 'Report file generate nahi hui.' });
    }
});

app.get('*', (req, res) => {
    res.sendFile(path.join(projectRoot, 'public', 'index.html'));
});

app.listen(PORT, () => console.log(`🚀 Server running on port ${PORT}`));