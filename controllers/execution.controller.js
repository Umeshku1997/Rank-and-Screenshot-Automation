import { runCustomScript } from './actions/customActions.js';

export const handleScriptExecution = (req, res) => {
  // Query se raw encoded path receive karke decode karna
  const rawPath = req.query.path ? decodeURIComponent(req.query.path) : '';
  const taskId = req.query.task_id || `task_${Date.now()}`;

  // SSE Headers Setup
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  const sendLog = (data) => {
    res.write(`data: ${data}\n\n`);
  };

  runCustomScript(rawPath, sendLog, taskId, () => {
    sendLog(`✅ Task completed with status code 0`);
    res.end();
  });

  req.on('close', () => {
    res.end();
  });
};