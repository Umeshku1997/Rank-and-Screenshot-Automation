import express from 'express';
import { handleScriptExecution } from '../controllers/execution.controller.js';

const router = express.Router();

// Real-time EventSource Stream Route
router.get('/run-stream', handleScriptExecution);

export default router;
