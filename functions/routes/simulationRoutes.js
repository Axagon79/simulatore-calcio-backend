const express = require('express');
const { spawn } = require('child_process');
const path = require('path');

const router = express.Router();

// __dirname = C:\Progetti\simulatore-calcio-backend\functions\routes
// Script attuale: C:\Progetti\simulatore-calcio-backend\ai_engine\web_simulator.py
const pythonScriptBase = path.join(__dirname, '../../ai_engine/web_simulator_A.py');
// NUOVO Script DEV: C:\Progetti\simulatore-calcio-backend\ai_engine\web_simulator_A.py
const pythonScriptDev = path.join(__dirname, '../../ai_engine/web_simulator_A.py');

console.log('📂 [simulationRoutes] Base:', pythonScriptBase);
console.log('📂 [simulationRoutes] DEV:', pythonScriptDev);

// 🔸 ENDPOINT UTENTE BASE (INALTERATO)
router.post('/simulate-match', async (req, res) => {
  const {
    main_mode = 4,
    nation = 'ITALIA',
    league = 'Serie A',
    home = null,
    away = null,
    round = null,
    algo_id = 5,
    cycles = 80,
    save_db = false
  } = req.body;

  console.log('🚀 [BASE] Super simulazione:', {
    main_mode, nation, league, home, away, algo_id, cycles
  });

  const python = spawn('python', [
    pythonScriptBase,
    main_mode.toString(),
    nation,
    league,
    home || 'null',
    away || 'null',
    round || 'null',
    algo_id.toString(),
    cycles.toString(),
    save_db.toString()
  ]);

  let result = '';
  let errorOutput = '';

  python.stdout.on('data', (data) => {
    const chunk = data.toString();
    result += chunk;
  });

  python.stderr.on('data', (data) => {
    const msg = data.toString();
    errorOutput += msg;
    console.error('⚠️ [BASE] Python stderr:', msg);
  });

  python.on('close', (code) => {
    console.log('🔚 [BASE] Python exit code:', code);
    
    const lines = result.split(/\r?\n/).filter(l => l.trim() !== '');
    const lastLine = lines[lines.length - 1] || '';
    
    if (code !== 0) {
      return res.status(500).json({
        error: 'Simulazione fallita',
        details: errorOutput || lastLine || 'Errore Python',
        pythonPath: pythonScriptBase,
        params: req.body
      });
    }
    
    try {
      const json = JSON.parse(lastLine);
      return res.json(json);
    } catch (e) {
      console.error('❌ [BASE] Errore parsing JSON:', e.message);
      return res.status(500).json({
        error: 'Output Python non valido',
        details: result || '(vuoto)',
        pythonPath: pythonScriptBase,
        params: req.body
      });
    }
  });
});

// 🔥 NUOVO ENDPOINT DEV (PER TE - COMPLETO)
router.post('/dev-simulate-match', async (req, res) => {
  const {
    main_mode = 4,      // 2=Massivo, 4=Singola
    nation = 'ITALIA',
    league = 'Serie B',
    home = null,
    away = null,
    round = null,
    algo_id = 3,        // 1-6
    cycles = 1,         // Cicli personalizzati
    save_db = false
  } = req.body;

  console.log('🚀 [DEV] Super simulazione:', {
    main_mode, nation, league, home, away, algo_id, cycles
  });

  const python = spawn('python', [
    pythonScriptDev,
    main_mode.toString(),
    nation,
    league,
    home || 'null',
    away || 'null',
    round || 'null',
    algo_id.toString(),
    cycles.toString(),
    save_db.toString()
  ]);

  let result = '';
  let errorOutput = '';

  python.stdout.on('data', (data) => {
    const chunk = data.toString();
    result += chunk;
  });

  python.stderr.on('data', (data) => {
    const msg = data.toString();
    errorOutput += msg;
    console.error('⚠️ [DEV] Python stderr:', msg);
  });

  python.on('close', (code) => {
    console.log('🔚 [DEV] Python exit code:', code);
    
    const lines = result.split(/\r?\n/).filter(l => l.trim() !== '');
    const lastLine = lines[lines.length - 1] || '';
    
    if (code !== 0) {
      return res.status(500).json({
        error: 'Dev simulazione fallita',
        details: errorOutput || lastLine || 'Errore Python DEV',
        pythonPath: pythonScriptDev,
        params: req.body
      });
    }
    
    try {
      const json = JSON.parse(lastLine);
      return res.json(json);
    } catch (e) {
      console.error('❌ [DEV] Errore parsing JSON:', e.message);
      return res.status(500).json({
        error: 'Output Python DEV non valido',
        details: result || '(vuoto)',
        pythonPath: pythonScriptDev,
        params: req.body
      });
    }
  });
});

module.exports = router;
