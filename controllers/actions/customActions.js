import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';

function resolveSmartPath(inputPath) {
  if (!inputPath) return { file: '', cwd: process.cwd() };

  // Sanitize path separators across cross-platform environments
  let cleanInput = String(inputPath).trim().replace(/^["']|["']$/g, '');
  cleanInput = path.normalize(cleanInput);

  // Direct File Exists Check
  if (fs.existsSync(cleanInput)) {
    try {
      const stat = fs.statSync(cleanInput);
      if (stat.isFile()) {
        return { file: path.resolve(cleanInput), cwd: path.dirname(cleanInput) };
      }
    } catch (e) {}
  }

  // Recursive Deep File Search Engine
  const targetFileName = path.basename(cleanInput);

  function searchFolder(dir, depth = 0) {
    if (depth > 6) return null;
    try {
      const list = fs.readdirSync(dir);
      for (const item of list) {
        if (item === 'node_modules' || item === '.git' || item === '.venv') continue;
        const fullPath = path.join(dir, item);
        const stat = fs.statSync(fullPath);

        if (stat && stat.isDirectory()) {
          const res = searchFolder(fullPath, depth + 1);
          if (res) return res;
        } else if (item.toLowerCase() === targetFileName.toLowerCase()) {
          return { file: fullPath, cwd: dir };
        }
      }
    } catch (err) {
      return null;
    }
    return null;
  }

  // Search inside server root directory
  const cwdSearch = searchFolder(process.cwd());
  if (cwdSearch) return cwdSearch;

  // Search inside parent directory
  const parentDir = path.resolve(process.cwd(), '..');
  const parentSearch = searchFolder(parentDir);
  if (parentSearch) return parentSearch;

  return { file: cleanInput, cwd: process.cwd() };
}

export const runCustomScript = (scriptInputPath, sendLog, taskId, onComplete) => {
  const resolved = resolveSmartPath(scriptInputPath);
  const actualFileName = path.basename(resolved.file).toLowerCase();

  sendLog(`[${new Date().toLocaleTimeString()}] Cloud Execution Pipeline Active...`);
  sendLog(`Executing Script: ${path.basename(resolved.file)}`);
  sendLog(`Resolved Target Path: ${resolved.file}`);
  sendLog(`Working Directory (CWD): ${resolved.cwd}`);
  sendLog(`--------------------------------------------------`);

  // Support both python3 (Render/Linux) and python (Windows local fallback)
  const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';
  const scriptArgs = ['-u', resolved.file];

  if (actualFileName === 'run_both.py') {
    scriptArgs.push('together');
  }

  const child = spawn(pythonCmd, scriptArgs, {
    cwd: resolved.cwd,
    encoding: 'utf-8',
    env: {
      ...process.env,
      PYTHONUNBUFFERED: '1',
      PYTHONIOENCODING: 'utf-8',
      PYTHONUTF8: '1'
    }
  });

  child.stdout.on('data', (data) => {
    const lines = data.toString('utf-8').split('\n');
    lines.forEach(line => line.trim() && sendLog(line));
  });

  child.stderr.on('data', (data) => {
    const lines = data.toString('utf-8').split('\n');
    lines.forEach(line => line.trim() && sendLog(`[ERROR] ${line}`));
  });

  child.on('close', () => {
    onComplete();
  });
};