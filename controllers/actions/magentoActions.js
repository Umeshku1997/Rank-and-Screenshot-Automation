import { spawn } from 'child_process';

export const runMagentoMobile = (sendLog, taskId, onComplete) => {
  sendLog(`Starting Magento Mobile Overview Script...`);

  const child = spawn('python', ['Ai Overview\\MOBILE.py'], { 
    cwd: process.cwd(),
    env: { 
      ...process.env, 
      PYTHONUNBUFFERED: '1',
      PYTHONIOENCODING: 'utf-8',
      PYTHONUTF8: '1'
    }
  });

  child.stdout.on('data', (data) => sendLog(`[MAGENTO] ${data.toString('utf-8')}`));
  child.stderr.on('data', (data) => sendLog(`[ERROR] ${data.toString('utf-8')}`));
  child.on('close', () => onComplete());
};