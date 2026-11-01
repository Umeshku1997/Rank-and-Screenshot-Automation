import { runCustomScript } from './customActions.js';

export const runSEOBoth = (sendLog, taskId, onComplete) => {
  runCustomScript('run_both.py', sendLog, taskId, onComplete);
};

export const runSEODesktop = (sendLog, taskId, onComplete) => {
  runCustomScript('desktop_rank.py', sendLog, taskId, onComplete);
};

export const runSEOMobile = (sendLog, taskId, onComplete) => {
  runCustomScript('mobile_rank.py', sendLog, taskId, onComplete);
};