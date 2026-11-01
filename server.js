import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';
import { handleScriptExecution } from './controllers/execution.controller.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT || 5000;

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Static frontend serving
app.use(express.static(path.join(__dirname, 'public')));

// API Routes
app.get('/api/scripts/run-stream', handleScriptExecution);

// Root Fallback
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.listen(PORT, () => {
  console.log(`🚀 Server running on http://localhost:${PORT}`);
});