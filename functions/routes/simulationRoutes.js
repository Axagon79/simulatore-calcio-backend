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


// 🏆 ENDPOINT SIMULAZIONE COPPE
router.post('/simulate-cup', async (req, res) => {
  const {
    competition = 'UCL',
    home = null,
    away = null,
    algo_id = 5,
    cycles = 100
  } = req.body;

  console.log('🏆 [CUPS] Simulazione coppa:', {
    competition, home, away, algo_id, cycles
  });

  try {
    // Chiama la Cloud Function Python via HTTP (come i campionati!)
    const response = await fetch('https://run-simulation-6b34yfzjia-uc.a.run.app', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        main_mode: 4,
        league: competition,  // 'UCL' o 'UEL'
        home: home,
        away: away,
        round: 'null',
        algo_id: algo_id,
        cycles: cycles,
        is_cup: true
      })
    });

    const data = await response.json();
    return res.json(data);

  } catch (error) {
    console.error('❌ [CUPS] Errore:', error);
    return res.status(500).json({
      error: 'Simulazione coppa fallita',
      details: error.message
    });
  }
});

// 🏆 ENDPOINT: Lista squadre coppe
router.get('/cup-teams', async (req, res) => {
  const { competition } = req.query;
  
  if (!competition || !['UCL', 'UEL'].includes(competition)) {
    return res.status(400).json({
      error: 'Parametro competition mancante o non valido',
      hint: 'Usa ?competition=UCL o ?competition=UEL'
    });
  }

  console.log('🏆 [CUPS] Richiesta teams per:', competition);

  try {
    const response = await fetch(
      `https://get-cup-teams-6b34yfzjia-uc.a.run.app?competition=${competition}`
    );
    
    const data = await response.json();
    return res.json(data);
  } catch (error) {
    console.error('❌ [CUPS-TEAMS] Errore:', error);
    return res.status(500).json({
      error: 'Errore nel recupero teams',
      details: error.message
    });
  }
});


// 🏆 ENDPOINT: Lista partite coppe
router.get('/cup-matches', async (req, res) => {
  const { competition } = req.query;
  
  if (!competition || !['UCL', 'UEL'].includes(competition)) {
    return res.status(400).json({
      error: 'Parametro competition mancante o non valido',
      hint: 'Usa ?competition=UCL o ?competition=UEL'
    });
  }

  console.log('🏆 [CUPS] Richiesta matches per:', competition);

  try {
    const collectionMap = {
      'UCL': 'matches_champions_league',
      'UEL': 'matches_europa_league'
    };
    
    const collectionName = collectionMap[competition];
    
    // Query DIRETTA MongoDB (come i campionati!)
    const matches = await req.db.collection(collectionName)
      .find(
        { season: "2025-2026" },
        {
          projection: {
            _id: 0,
            home_team: 1,
            away_team: 1,
            home_mongo_id: 1,
            away_mongo_id: 1,
            match_date: 1,
            status: 1,
            result: 1,
            odds: 1
          }
        }
      )
      .toArray();

    // Separa e filtra: ultima giocata + prossima per squadra
    const played = matches.filter(m => m.status === 'finished');
    const upcoming = matches.filter(m => m.status === 'scheduled');

    // Ordina per data
    played.sort((a, b) => {
      const dateA = a.match_date?.split(' ')[0].split('-').reverse().join('-') || '';
      const dateB = b.match_date?.split(' ')[0].split('-').reverse().join('-') || '';
      return dateB.localeCompare(dateA); // Più recente prima
    });

    upcoming.sort((a, b) => {
      const dateA = a.match_date?.split(' ')[0].split('-').reverse().join('-') || '';
      const dateB = b.match_date?.split(' ')[0].split('-').reverse().join('-') || '';
      return dateA.localeCompare(dateB); // Più vicina prima
    });

    // Filtra: 1 partita per squadra
    const teamsPlayed = new Set();
    const finalPlayed = [];
    for (const match of played) {
      if (!teamsPlayed.has(match.home_team) || !teamsPlayed.has(match.away_team)) {
        finalPlayed.push(match);
        teamsPlayed.add(match.home_team);
        teamsPlayed.add(match.away_team);
      }
    }

    const teamsUpcoming = new Set();
    const finalUpcoming = [];
    for (const match of upcoming) {
      if (!teamsUpcoming.has(match.home_team) || !teamsUpcoming.has(match.away_team)) {
        finalUpcoming.push(match);
        teamsUpcoming.add(match.home_team);
        teamsUpcoming.add(match.away_team);
      }
    }

    console.log(`✅ Cup matches ${competition}: ${matches.length} partite`);
    
    return res.json({
      success: true,
      matches: { played: finalPlayed, upcoming: finalUpcoming },
      count: { played: finalPlayed.length, upcoming: finalUpcoming.length, total: finalPlayed.length + finalUpcoming.length }
    });
    
  } catch (error) {
    console.error('❌ [CUPS-MATCHES] Errore:', error);
    return res.status(500).json({
      error: 'Errore nel recupero matches',
      details: error.message
    });
  }
});


// 🏆 ENDPOINT: Info competizioni disponibili
router.get('/cups-info', async (req, res) => {
  res.json({
    success: true,
    competitions: [
      {
        code: 'UCL',
        name: 'Champions League',
        teams_count: 36,
        teams_collection: 'teams_champions_league',
        matches_collection: 'matches_champions_league'
      },
      {
        code: 'UEL',
        name: 'Europa League',
        teams_count: 36,
        teams_collection: 'teams_europa_league',
        matches_collection: 'matches_europa_league'
      }
    ]
  });
});

module.exports = router;