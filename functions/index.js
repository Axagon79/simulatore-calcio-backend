require('dotenv').config();
const { onRequest } = require("firebase-functions/v2/https");
const simulationRoutes = require('./routes/simulationRoutes');
const express = require('express');
const cors = require('cors');
const { MongoClient } = require('mongodb');

const app = express();
app.use(cors({ origin: true }));
app.use(express.json());

// Invece di: const MONGO_URI = process.env.MONGO_URI;
const MONGO_URI="mongodb+srv://Database_User:LPmYAZkzEVxjSaAd@pup-pals-cluster.y1h2r.mongodb.net/football_simulator_db?retryWrites=true&w=majority&appName=pup-pals-cluster"

let client;
let db;

// Funzione per ottenere il database (si connette solo se necessario)
async function getDatabase() {
  if (db) return db;
  if (!client) {
    client = new MongoClient(MONGO_URI);
    await client.connect();
  }
  const db_name = MONGO_URI.split('/').pop()?.split('?')[0] || 'football_simulator_db';
  db = client.db(db_name);
  console.log(`✅ DB connesso: ${db_name}`);
  return db;
}

// Middleware: invece di dare errore 503, aspetta la connessione
app.use(async (req, res, next) => {
  try {
    req.db = await getDatabase();
    next();
  } catch (err) {
    console.error('❌ Errore connessione DB:', err);
    res.status(500).send("Errore di connessione al database");
  }
});

app.use('/simulation', simulationRoutes);

const predictionsRoutes = require('./routes/predictionsRoutes');
app.use('/simulation', predictionsRoutes.router);

const chatRoutes = require('./routes/chatRoutes');
app.use('/chat', chatRoutes);

const authenticate = require('./middleware/auth');
const moneyTrackerRoutes = require('./routes/moneyTrackerRoutes');
app.use('/money-tracker', authenticate, moneyTrackerRoutes);

const stepSystemRoutes = require('./routes/stepSystemRoutes');
app.use('/step-system', authenticate, stepSystemRoutes);

const standingsRoutes = require('./routes/standingsRoutes');
app.use('/standings', standingsRoutes);

// ============================================
// UTILITY FUNCTIONS
// ============================================

function getRoundNumber(roundName) {
  if (!roundName) return 0;
  const match = String(roundName).match(/^(\d+)/);
  return match ? parseInt(match[1], 10) : 0;
}

function hasScheduledMatches(round) {
  const matches = round.matches || [];
  return matches.some(m => m.status === 'Scheduled' || m.status === 'Timed');
}

function hasFinishedMatches(round) {
  const matches = round.matches || [];
  return matches.some(m => m.status === 'Finished' && m.real_score);
}

// ============================================
// ENDPOINT: /rounds - LOGICA INTELLIGENTE
// ============================================

app.get('/rounds', async (req, res) => {
  try {
    const leagueId = req.query.league;

    const leagueMap = {
      SERIE_A: 'Serie A',
      SERIE_B: 'Serie B',
      SERIE_C_A: 'Serie C - Girone A',
      SERIE_C_B: 'Serie C - Girone B',
      SERIE_C_C: 'Serie C - Girone C',
      PREMIER_LEAGUE: 'Premier League',
      LA_LIGA: 'La Liga',
      BUNDESLIGA: 'Bundesliga',
      LIGUE_1: 'Ligue 1',
      EREDIVISIE: 'Eredivisie',
      LIGA_PORTUGAL: 'Liga Portugal',
      // 🆕 EUROPA SERIE B
      CHAMPIONSHIP: 'Championship',
      LA_LIGA_2: 'LaLiga 2',
      BUNDESLIGA_2: '2. Bundesliga',
      LIGUE_2: 'Ligue 2',

      // 🆕 NORDICI + EXTRA
      SCOTTISH_PREMIERSHIP: 'Scottish Premiership',
      ALLSVENSKAN: 'Allsvenskan',
      ELITESERIEN: 'Eliteserien',
      SUPERLIGAEN: 'Superligaen',
      JUPILER_PRO_LEAGUE: 'Jupiler Pro League',
      SUPER_LIG: 'Süper Lig',
      LEAGUE_OF_IRELAND: 'League of Ireland Premier Division',

      // 🆕 AMERICHE
      BRASILEIRAO: 'Brasileirão Serie A',
      PRIMERA_DIVISION_ARG: 'Primera División',
      MLS: 'Major League Soccer',

      // 🆕 ASIA
      J1_LEAGUE: 'J1 League'
    };

    const leagueName = leagueMap[leagueId];
    if (!leagueName) return res.json({ rounds: [], anchor: null });

    // Recupera TUTTE le giornate (solo campi necessari per calcolo anchor)
    const docs = await db.collection('h2h_by_round')
      .find({ league: leagueName })
      .project({ round_name: 1, 'matches.status': 1, 'matches.date_obj': 1 })
      .toArray();

    if (docs.length === 0) {
      return res.json({ rounds: [], anchor: null });
    }

    // Ordina per numero giornata
    const sortedRounds = docs.sort((a, b) => {
      return getRoundNumber(a.round_name) - getRoundNumber(b.round_name);
    });

    // TROVA L'ANCHOR (giornata di riferimento) - Logica blindata: scarta passate e recuperi lontani
    let anchorIndex = -1;
    const oggi = new Date();

    // --- TUA LOGICA CORRETTA: CONTROLLO SUI POSTICIPI ---
    for (let i = 0; i < sortedRounds.length; i++) {
      const currentRound = sortedRounds[i];
      const matches = currentRound.matches || [];
      
      // 1. Identifichiamo le partite NON terminate (senza risultato)
      const openMatches = matches.filter(m => m.status === 'Scheduled' || m.status === 'Timed');

      // Se sono tutte finite, passiamo alla prossima giornata
      if (openMatches.length === 0) continue;

      // 2. Identifichiamo le partite già FINITE per trovare il "fine turno regolare"
      const finishedMatches = matches.filter(m => m.status === 'Finished');
      
      if (finishedMatches.length > 0) {
        const finishedDates = finishedMatches.map(m => new Date(m.date_obj).getTime());
        const lastRegularDate = new Date(Math.max(...finishedDates));

        // 3. Creiamo il limite di 7 giorni dalla fine delle partite regolari
        const limitDate = new Date(lastRegularDate);
        limitDate.setDate(limitDate.getDate() + 7);

        // 4. Verifichiamo se tra le partite NON terminate ce n'è almeno una "attuale" (entro 7gg)
        const hasValidUpcomingMatch = openMatches.some(m => {
          const matchDate = new Date(m.date_obj);
          return matchDate >= oggi && matchDate <= limitDate;
        });

        if (hasValidUpcomingMatch) {
          anchorIndex = i;
          break; 
        }
        // Se le partite non terminate sono tutte oltre i 7gg, il ciclo prosegue alla giornata dopo
      } else {
        // Se non è finita nemmeno una partita (giornata totalmente futura), la prendiamo come attuale
        anchorIndex = i;
        break;
      }
    }

    // STEP DI RISERVA: Se tutte le partite sono "scadute" o finite, prendiamo l'ultima con risultati
    if (anchorIndex === -1) {
      for (let i = sortedRounds.length - 1; i >= 0; i--) {
        if (hasFinishedMatches(sortedRounds[i])) {
          anchorIndex = i;
          break;
        }
      }
    }

    // STEP 3: Se ancora non trova nulla, prende l'ultima disponibile
    if (anchorIndex === -1) {
      anchorIndex = sortedRounds.length - 1;
    }

    // Calcola PRECEDENTE, ATTUALE, SUCCESSIVA
    const rounds = [];
    
    // PRECEDENTE (anchor - 1)
    if (anchorIndex > 0) {
      rounds.push({
        name: sortedRounds[anchorIndex - 1].round_name,
        label: 'PRECEDENTE',
        type: 'previous'
      });
    }

    // ATTUALE (anchor)
    rounds.push({
      name: sortedRounds[anchorIndex].round_name,
      label: 'ATTUALE',
      type: 'current'
    });

    // SUCCESSIVA (anchor + 1)
    if (anchorIndex < sortedRounds.length - 1) {
      rounds.push({
        name: sortedRounds[anchorIndex + 1].round_name,
        label: 'SUCCESSIVA',
        type: 'next'
      });
    }

    console.log(`✅ Rounds ${leagueId}: anchor=${sortedRounds[anchorIndex].round_name}, count=${rounds.length}`);
    
    return res.json({
      rounds: rounds,
      anchor: sortedRounds[anchorIndex].round_name
    });

  } catch (err) {
    console.error('Rounds error:', err);
    return res.status(500).json({ error: err.message });
  }
});

// ============================================
// ENDPOINT: /matches
// ============================================

app.get('/matches', async (req, res) => {
  try {
    const leagueId = req.query.league;
    const roundName = req.query.round;
    
    const leagueMap = {
      'SERIE_A': 'Serie A',
      'SERIE_B': 'Serie B',
      'SERIE_C_A': 'Serie C - Girone A',
      'SERIE_C_B': 'Serie C - Girone B',
      'SERIE_C_C': 'Serie C - Girone C',
      'PREMIER_LEAGUE': 'Premier League',
      'LA_LIGA': 'La Liga',
      'BUNDESLIGA': 'Bundesliga',
      'LIGUE_1': 'Ligue 1',
      'EREDIVISIE': 'Eredivisie',
      'LIGA_PORTUGAL': 'Liga Portugal',
      // 🆕 EUROPA SERIE B
      'CHAMPIONSHIP': 'Championship',
      'LA_LIGA_2': 'LaLiga 2',
      'BUNDESLIGA_2': '2. Bundesliga',
      'LIGUE_2': 'Ligue 2',

      // 🆕 NORDICI + EXTRA
      'SCOTTISH_PREMIERSHIP': 'Scottish Premiership',
      'ALLSVENSKAN': 'Allsvenskan',
      'ELITESERIEN': 'Eliteserien',
      'SUPERLIGAEN': 'Superligaen',
      'JUPILER_PRO_LEAGUE': 'Jupiler Pro League',
      'SUPER_LIG': 'Süper Lig',
      'LEAGUE_OF_IRELAND': 'League of Ireland Premier Division',

      // 🆕 AMERICHE
      'BRASILEIRAO': 'Brasileirão Serie A',
      'PRIMERA_DIVISION_ARG': 'Primera División',
      'MLS': 'Major League Soccer',

      // 🆕 ASIA
      'J1_LEAGUE': 'J1 League'
    };
    
    const leagueName = leagueMap[leagueId];
    if (!leagueName) return res.json([]);

    // Query: cerca per league + round_name (se specificato)
    let query = { league: leagueName };
    if (roundName) query.round_name = roundName;

    const docs = await db.collection('h2h_by_round')
      .find(query)
      .toArray();

    if (docs.length === 0) return res.json([]);

    // Estrai tutte le partite includendo TUTTI i dati presenti nel database
    const matches = docs.flatMap(doc => 
      (doc.matches || []).map((m, i) => ({
        ...m,                  // <--- Questa è la "magia": prende TUTTO quello che c'è nel DB (inclusi odds e altro)
        id: `${doc._id}_${i}`, // Mantiene l'ID che avevi creato
        status: m.status || 'Finished' // Mantiene il default per lo status
      }))
    );

    console.log(`✅ Matches ${leagueId} ${roundName || 'all'}: ${matches.length} partite`);
    res.json(matches);
  } catch (error) {
    console.error('Matches error:', error);
    res.status(500).json({ error: error.message });
  }
});

// ============================================
// ENDPOINT: /matches-today
// ============================================

app.get('/matches-today', async (req, res) => {
  try {
    const dateParam = req.query.date; // "YYYY-MM-DD" oppure omesso → oggi
    const targetDate = dateParam || new Date().toISOString().split('T')[0];

    const startOfDay = new Date(targetDate + 'T00:00:00.000Z');
    const endOfDay   = new Date(targetDate + 'T23:59:59.999Z');

    // Mappa inversa: nome DB → { id frontend, country }
    const reverseLeagueMap = {
      'Serie A': { id: 'SERIE_A', country: 'Italy' },
      'Serie B': { id: 'SERIE_B', country: 'Italy' },
      'Serie C - Girone A': { id: 'SERIE_C_A', country: 'Italy' },
      'Serie C - Girone B': { id: 'SERIE_C_B', country: 'Italy' },
      'Serie C - Girone C': { id: 'SERIE_C_C', country: 'Italy' },
      'Premier League': { id: 'PREMIER_LEAGUE', country: 'England' },
      'La Liga': { id: 'LA_LIGA', country: 'Spain' },
      'Bundesliga': { id: 'BUNDESLIGA', country: 'Germany' },
      'Ligue 1': { id: 'LIGUE_1', country: 'France' },
      'Eredivisie': { id: 'EREDIVISIE', country: 'Netherlands' },
      'Liga Portugal': { id: 'LIGA_PORTUGAL', country: 'Portugal' },
      'Championship': { id: 'CHAMPIONSHIP', country: 'England' },
      'LaLiga 2': { id: 'LA_LIGA_2', country: 'Spain' },
      '2. Bundesliga': { id: 'BUNDESLIGA_2', country: 'Germany' },
      'Ligue 2': { id: 'LIGUE_2', country: 'France' },
      'Scottish Premiership': { id: 'SCOTTISH_PREMIERSHIP', country: 'Scotland' },
      'Allsvenskan': { id: 'ALLSVENSKAN', country: 'Sweden' },
      'Eliteserien': { id: 'ELITESERIEN', country: 'Norway' },
      'Superligaen': { id: 'SUPERLIGAEN', country: 'Denmark' },
      'Jupiler Pro League': { id: 'JUPILER_PRO_LEAGUE', country: 'Belgium' },
      'Süper Lig': { id: 'SUPER_LIG', country: 'Turkey' },
      'League of Ireland Premier Division': { id: 'LEAGUE_OF_IRELAND', country: 'Ireland' },
      'Brasileirão Serie A': { id: 'BRASILEIRAO', country: 'Brazil' },
      'Primera División': { id: 'PRIMERA_DIVISION_ARG', country: 'Argentina' },
      'Major League Soccer': { id: 'MLS', country: 'USA' },
      'J1 League': { id: 'J1_LEAGUE', country: 'Japan' },
    };

    const pipeline = [
      { $unwind: '$matches' },
      { $match: {
        'matches.date_obj': { $gte: startOfDay, $lte: endOfDay }
      }},
      { $project: {
        _id: 0,
        league: '$league',
        match: '$matches'
      }},
      { $sort: { 'match.match_time': 1 } }
    ];

    const rawResults = await db.collection('h2h_by_round').aggregate(pipeline).toArray();

    // Raggruppa per lega
    const grouped = {};
    for (const r of rawResults) {
      const leagueName = r.league;
      if (!grouped[leagueName]) {
        const meta = reverseLeagueMap[leagueName] || { id: leagueName, country: 'Altro' };
        grouped[leagueName] = {
          league_name: leagueName,
          league_id: meta.id,
          country: meta.country,
          matches: []
        };
      }
      const m = r.match;
      grouped[leagueName].matches.push({
        ...m,
        id: `today_${grouped[leagueName].league_id}_${grouped[leagueName].matches.length}`,
        status: m.status || 'Finished'
      });
    }

    const result = Object.values(grouped);
    // Ordina: Italia prima, poi per numero di partite desc
    result.sort((a, b) => {
      if (a.country === 'Italy' && b.country !== 'Italy') return -1;
      if (b.country === 'Italy' && a.country !== 'Italy') return 1;
      return b.matches.length - a.matches.length;
    });

    console.log(`✅ Matches today ${targetDate}: ${rawResults.length} partite in ${result.length} leghe`);
    res.json({ success: true, date: targetDate, leagues: result, total: rawResults.length });
  } catch (error) {
    console.error('Matches-today error:', error);
    res.status(500).json({ error: error.message });
  }
});

// ============================================
// ENDPOINT: /live-scores
// ============================================

app.get('/live-scores', async (req, res) => {
  try {
    const dateParam = req.query.date;
    const targetDate = dateParam || new Date().toISOString().split('T')[0];

    const startOfDay = new Date(targetDate + 'T00:00:00.000Z');
    const endOfDay   = new Date(targetDate + 'T23:59:59.999Z');

    const pipeline = [
      { $unwind: '$matches' },
      { $match: {
        'matches.date_obj': { $gte: startOfDay, $lte: endOfDay },
        'matches.live_status': { $in: ['Live', 'HT', 'Finished'] }
      }},
      { $project: {
        _id: 0,
        home: '$matches.home',
        away: '$matches.away',
        live_score: '$matches.live_score',
        live_status: '$matches.live_status',
        live_minute: '$matches.live_minute',
        match_time: '$matches.match_time'
      }}
    ];

    const scores = await db.collection('h2h_by_round').aggregate(pipeline).toArray();

    // Coppe europee (documenti singoli, struttura diversa)
    const [y, m, d] = targetDate.split('-');
    const cupDatePrefix = `${d}-${m}-${y}`;  // "17-02-2026"

    for (const cupColl of ['matches_champions_league', 'matches_europa_league']) {
      const cupMatches = await db.collection(cupColl).find({
        match_date: { $regex: `^${cupDatePrefix}` },
        live_status: { $in: ['Live', 'HT', 'Finished'] }
      }).toArray();

      for (const cm of cupMatches) {
        scores.push({
          home: cm.home_team,
          away: cm.away_team,
          live_score: cm.live_score || null,
          live_status: cm.live_status || null,
          live_minute: cm.live_minute || null,
          match_time: cm.match_date ? cm.match_date.split(' ')[1] : null
        });
      }
    }

    res.json({ success: true, scores });
  } catch (error) {
    console.error('Live-scores error:', error);
    res.status(500).json({ error: error.message });
  }
});

// ============================================
// ENDPOINT: /streaks
// ============================================

const ALL_STREAK_TYPES = [
  'vittorie', 'sconfitte', 'imbattibilita', 'pareggi', 'senza_vittorie',
  'over25', 'under25', 'gg', 'clean_sheet', 'senza_segnare', 'gol_subiti'
];

const STREAK_CURVES = {
  vittorie:       {1: 0, 2: 0, 3: 2, 4: 3, 5: 0, 6: -1, 7: -3, 8: -6, '9+': -10},
  sconfitte:      {1: 0, 2: 0, 3: 0, 4: -1, 5: -2, '6+': -5},
  imbattibilita:  {'1-4': 0, '5-7': 2, '8-10': 0, '11+': -3},
  pareggi:        {1: 0, 2: 0, 3: -1, 4: 0, 5: 1, '6+': -3},
  senza_vittorie: {1: 0, 2: 0, 3: -1, 4: -2, 5: 0, 6: 1, '7+': 2},
  over25:         {1: 0, 2: 0, 3: 3, 4: 3, 5: 0, 6: -1, '7+': -4},
  under25:        {1: 0, 2: 0, 3: 3, 4: 3, 5: 0, 6: -1, '7+': -4},
  gg:             {1: 0, 2: 0, 3: 2, 4: 2, 5: 0, '6+': -3},
  clean_sheet:    {1: 0, 2: 0, 3: 2, 4: 3, 5: 0, 6: -1, '7+': -4},
  senza_segnare:  {1: 0, 2: 1, 3: 2, 4: 0, 5: -1, '6+': -3},
  gol_subiti:     {1: 0, 2: 0, 3: 2, 4: 3, 5: 2, 6: 1, '7+': -2},
};

function curveLookup(streakType, n) {
  if (n <= 0) return 0;
  const curve = STREAK_CURVES[streakType];
  if (!curve) return 0;
  if (curve[n] !== undefined) return curve[n];
  for (const [key, value] of Object.entries(curve)) {
    if (typeof key === 'string' && key.includes('+')) {
      const minVal = parseInt(key.replace('+', ''));
      if (n >= minVal) return value;
    } else if (typeof key === 'string' && key.includes('-')) {
      const [lo, hi] = key.split('-').map(Number);
      if (n >= lo && n <= hi) return value;
    }
  }
  return 0;
}

function checkStreakCondition(teamName, match, streakType) {
  const score = match.real_score;
  if (!score || !score.includes(':')) return false;
  const parts = score.split(':');
  const homeGoals = parseInt(parts[0].trim());
  const awayGoals = parseInt(parts[1].trim());
  if (isNaN(homeGoals) || isNaN(awayGoals)) return false;

  const isHome = match.home === teamName;
  const teamGoals = isHome ? homeGoals : awayGoals;
  const oppGoals = isHome ? awayGoals : homeGoals;
  const totalGoals = homeGoals + awayGoals;

  switch (streakType) {
    case 'vittorie':       return teamGoals > oppGoals;
    case 'sconfitte':      return teamGoals < oppGoals;
    case 'imbattibilita':  return teamGoals >= oppGoals;
    case 'pareggi':        return teamGoals === oppGoals;
    case 'senza_vittorie': return teamGoals <= oppGoals;
    case 'over25':         return totalGoals >= 3;
    case 'under25':        return totalGoals <= 2;
    case 'gg':             return homeGoals > 0 && awayGoals > 0;
    case 'clean_sheet':    return oppGoals === 0;
    case 'senza_segnare':  return teamGoals === 0;
    case 'gol_subiti':     return oppGoals > 0;
    default: return false;
  }
}

function calculateTeamStreaks(teamName, matches) {
  const result = {};
  for (const st of ALL_STREAK_TYPES) {
    let count = 0;
    for (const m of matches) {
      if (checkStreakCondition(teamName, m, st)) {
        count++;
      } else {
        break;
      }
    }
    result[st] = count;
  }
  return result;
}

app.get('/streaks', async (req, res) => {
  try {
    const { home, away, league: leagueId } = req.query;
    if (!home || !away || !leagueId) {
      return res.status(400).json({ error: 'Missing home, away, or league parameter' });
    }

    // Converti ID lega → nome nel DB (stessa mappa di /matches)
    const leagueMap = {
      'SERIE_A': 'Serie A', 'SERIE_B': 'Serie B',
      'SERIE_C_A': 'Serie C - Girone A', 'SERIE_C_B': 'Serie C - Girone B', 'SERIE_C_C': 'Serie C - Girone C',
      'PREMIER_LEAGUE': 'Premier League', 'LA_LIGA': 'La Liga', 'BUNDESLIGA': 'Bundesliga',
      'LIGUE_1': 'Ligue 1', 'EREDIVISIE': 'Eredivisie', 'LIGA_PORTUGAL': 'Liga Portugal',
      'CHAMPIONSHIP': 'Championship', 'LA_LIGA_2': 'LaLiga 2', 'BUNDESLIGA_2': '2. Bundesliga', 'LIGUE_2': 'Ligue 2',
      'SCOTTISH_PREMIERSHIP': 'Scottish Premiership', 'ALLSVENSKAN': 'Allsvenskan', 'ELITESERIEN': 'Eliteserien',
      'SUPERLIGAEN': 'Superligaen', 'JUPILER_PRO_LEAGUE': 'Jupiler Pro League', 'SUPER_LIG': 'Süper Lig',
      'LEAGUE_OF_IRELAND': 'League of Ireland Premier Division',
      'BRASILEIRAO': 'Brasileirão Serie A', 'PRIMERA_DIVISION_ARG': 'Primera División', 'MLS': 'Major League Soccer',
      'J1_LEAGUE': 'J1 League'
    };
    const leagueName = leagueMap[leagueId];
    if (!leagueName) return res.json({ success: false, error: 'Unknown league: ' + leagueId });

    const pipeline = [
      { $match: { league: leagueName } },
      { $unwind: '$matches' },
      { $match: {
        'matches.real_score': { $exists: true, $nin: ['-:-', '', null] }
      }},
      { $sort: { 'matches.date_obj': -1 } },
      { $project: {
        _id: 0,
        home: '$matches.home',
        away: '$matches.away',
        real_score: '$matches.real_score',
        date_obj: '$matches.date_obj'
      }}
    ];

    const allMatches = await db.collection('h2h_by_round').aggregate(pipeline).toArray();

    // Separa partite per squadra e contesto
    const homeTotal = allMatches.filter(m => m.home === home || m.away === home);
    const awayTotal = allMatches.filter(m => m.home === away || m.away === away);
    const homeContext = allMatches.filter(m => m.home === home); // solo partite IN CASA
    const awayContext = allMatches.filter(m => m.away === away); // solo partite IN TRASFERTA

    const streak_home = calculateTeamStreaks(home, homeTotal);
    const streak_away = calculateTeamStreaks(away, awayTotal);
    const streak_home_context = calculateTeamStreaks(home, homeContext);
    const streak_away_context = calculateTeamStreaks(away, awayContext);

    res.json({
      success: true,
      streak_home,
      streak_away,
      streak_home_context,
      streak_away_context
    });
  } catch (error) {
    console.error('Streaks error:', error);
    res.status(500).json({ error: error.message });
  }
});

// ============================================
// ENDPOINT: /gauge-data
// 1. Cerca in daily_predictions (path veloce)
// 2. Se non trova, calcola on-demand da h2h_by_round + teams
// ============================================
app.get('/gauge-data', async (req, res) => {
  try {
    const { home, away, league: leagueId } = req.query;
    if (!home || !away) {
      return res.status(400).json({ error: 'Missing home or away parameter' });
    }

    // --- PATH 1: Cerca in daily_predictions ---
    const existing = await req.db.collection('daily_predictions')
      .find(
        { home, away },
        {
          projection: {
            _id: 0,
            segno_dettaglio: 1,
            segno_dettaglio_raw: 1,
            gol_dettaglio: 1,
            gol_directions: 1,
            expected_total_goals: 1,
            date: 1
          }
        }
      )
      .sort({ date: -1 })
      .limit(1)
      .toArray();

    if (existing.length > 0 && existing[0].segno_dettaglio_raw) {
      return res.json(existing[0]);
    }

    // --- PATH 2: Calcolo on-demand ---
    if (!leagueId) {
      return res.json(null); // Senza lega non possiamo cercare nel DB
    }

    const leagueMap = {
      'SERIE_A': 'Serie A', 'SERIE_B': 'Serie B',
      'SERIE_C_GIRONE_A': 'Serie C - Girone A', 'SERIE_C_GIRONE_B': 'Serie C - Girone B', 'SERIE_C_GIRONE_C': 'Serie C - Girone C',
      'PREMIER_LEAGUE': 'Premier League', 'LA_LIGA': 'La Liga', 'BUNDESLIGA': 'Bundesliga',
      'LIGUE_1': 'Ligue 1', 'EREDIVISIE': 'Eredivisie', 'LIGA_PORTUGAL': 'Liga Portugal',
      'CHAMPIONSHIP': 'Championship', 'LA_LIGA_2': 'LaLiga 2', 'BUNDESLIGA_2': '2. Bundesliga', 'LIGUE_2': 'Ligue 2',
      'SCOTTISH_PREMIERSHIP': 'Scottish Premiership', 'ALLSVENSKAN': 'Allsvenskan', 'ELITESERIEN': 'Eliteserien',
      'SUPERLIGAEN': 'Superligaen', 'JUPILER_PRO_LEAGUE': 'Jupiler Pro League', 'SUPER_LIG': 'Süper Lig',
      'LEAGUE_OF_IRELAND': 'League of Ireland Premier Division',
      'BRASILEIRAO': 'Brasileirão Serie A', 'PRIMERA_DIVISION_ARG': 'Primera División', 'MLS': 'Major League Soccer',
      'J1_LEAGUE': 'J1 League'
    };
    const leagueName = leagueMap[leagueId];

    // Cerca la partita in h2h_by_round
    const matchPipeline = [
      { $match: { league: leagueName } },
      { $unwind: '$matches' },
      { $match: { 'matches.home': home, 'matches.away': away } },
      { $sort: { 'matches.date_obj': -1 } },
      { $limit: 1 },
      { $replaceRoot: { newRoot: '$matches' } }
    ];
    const matchDocs = await req.db.collection('h2h_by_round').aggregate(matchPipeline).toArray();
    if (matchDocs.length === 0) return res.json(null);

    const m = matchDocs[0];
    const hd = m.h2h_data || {};
    const odds = m.odds || {};

    // Cerca team docs per dati GOL
    const [homeTeamDocs, awayTeamDocs] = await Promise.all([
      req.db.collection('teams').find({ name: home }).limit(1).toArray(),
      req.db.collection('teams').find({ name: away }).limit(1).toArray()
    ]);
    const homeTeam = homeTeamDocs[0] || {};
    const awayTeam = awayTeamDocs[0] || {};

    // ===== CALCOLO SEGNO =====

    // BVS raw
    const bvsHome = Number(hd.bvs_index || 0);
    const bvsAway = Number(hd.bvs_away || 0);

    // Quote raw (probabilità implicite normalizzate)
    const q1 = Number(odds['1'] || odds.qt_1 || 99);
    const qx = Number(odds['X'] || odds.qt_x || 99);
    const q2 = Number(odds['2'] || odds.qt_2 || 99);
    let quoteHome = 50, quoteAway = 50;
    if (q1 < 90 && q2 < 90) {
      const p1 = 1 / q1, px = 1 / qx, p2 = 1 / q2;
      const tot = p1 + px + p2;
      const n1 = (p1 / tot) * 100, nx = (px / tot) * 100, n2 = (p2 / tot) * 100;
      quoteHome = Math.round((n1 + nx / 2) * 10) / 10;
      quoteAway = Math.round((n2 + nx / 2) * 10) / 10;
    }

    // Lucifero raw
    const lucHome = Number(hd.lucifero_home || 0);
    const lucAway = Number(hd.lucifero_away || 0);

    // Affidabilità raw
    const trustHL = hd.trust_home_letter || 'C';
    const trustAL = hd.trust_away_letter || 'C';
    const trustMap = { 'A': 10, 'B': 7, 'C': 4, 'D': 1 };
    const trustHN = trustMap[trustHL] || 4;
    const trustAN = trustMap[trustAL] || 4;

    // DNA raw (35%att + 25%def + 25%tec + 15%val)
    const hDna = hd.home_dna || hd.h2h_dna?.home_dna || {};
    const aDna = hd.away_dna || hd.h2h_dna?.away_dna || {};
    const dnaCalc = (d) => (Number(d.att || 50) * 0.35 + Number(d.def || 50) * 0.25 + Number(d.tec || 50) * 0.25 + Number(d.val || 50) * 0.15);
    const dnaHome = Math.round(dnaCalc(hDna) * 10) / 10;
    const dnaAway = Math.round(dnaCalc(aDna) * 10) / 10;

    // Motivazioni raw (da teams collection)
    const motHome = Number(homeTeam?.stats?.motivation || 7);
    const motAway = Number(awayTeam?.stats?.motivation || 7);

    // H2H raw
    const h2hHome = Number(hd.home_score || 5);
    const h2hAway = Number(hd.away_score || 5);
    const h2hMatches = Number(hd.total_matches || 0);

    // Campo raw
    const fc = hd.fattore_campo || {};
    const campoHome = Number(fc.field_home || hd.field_home || 3.5);
    const campoAway = Number(fc.field_away || hd.field_away || 3.5);

    // Score functions per SEGNO (0-100)
    const scoreBvs = (() => {
      const cls = hd.classification || 'NON_BVS';
      const bmi = Number(hd.bvs_match_index || 0);
      const lin = hd.is_linear;
      if (cls === 'NON_BVS') return 40;
      let base = 50 + (bmi / 7) * 40;
      if (cls === 'PURO' && lin) base = Math.min(base + 10, 100);
      if (cls === 'SEMI') base *= 0.85;
      return Math.max(0, Math.min(100, Math.round(base * 10) / 10));
    })();

    const scoreQuote = (() => {
      if (q1 >= 90 || q2 >= 90) return 50;
      const diff = Math.abs(quoteHome - quoteAway);
      return Math.max(0, Math.min(100, Math.round((50 + diff * 0.8) * 10) / 10));
    })();

    const scoreLucifero = (() => {
      const diff = Math.abs(lucHome - lucAway);
      return Math.max(0, Math.min(100, Math.round((50 + diff * 3) * 10) / 10));
    })();

    const scoreAffidabilita = (() => {
      const diff = Math.abs(trustHN - trustAN);
      return Math.max(0, Math.min(100, Math.round((50 + diff * 8) * 10) / 10));
    })();

    const scoreDna = (() => {
      const diff = Math.abs(dnaHome - dnaAway);
      return Math.max(0, Math.min(100, Math.round((50 + diff * 0.5) * 10) / 10));
    })();

    const scoreMot = (() => {
      const diff = Math.abs(motHome - motAway);
      return Math.max(0, Math.min(100, Math.round((50 + diff * 5) * 10) / 10));
    })();

    const scoreH2h = (() => {
      if (h2hMatches < 2) return 50;
      const diff = Math.abs(h2hHome - h2hAway);
      const weight = Math.min(h2hMatches / 10, 1);
      return Math.max(0, Math.min(100, Math.round((50 + diff * 5 * weight) * 10) / 10));
    })();

    const scoreCampo = (() => {
      const diff = Math.abs(campoHome - campoAway);
      return Math.max(0, Math.min(100, Math.round((50 + diff * 10) * 10) / 10));
    })();

    const segno_dettaglio = {
      bvs: scoreBvs, quote: scoreQuote, lucifero: scoreLucifero,
      affidabilita: scoreAffidabilita, dna: scoreDna, motivazioni: scoreMot,
      h2h: scoreH2h, campo: scoreCampo
    };

    const segno_dettaglio_raw = {
      bvs: { home: bvsHome, away: bvsAway, scala: '±7' },
      quote: { home: quoteHome, away: quoteAway, scala: '%' },
      lucifero: { home: lucHome, away: lucAway, scala: '±7' },
      affidabilita: { home: trustHL, away: trustAL, home_num: trustHN, away_num: trustAN, scala: 'A-D' },
      dna: { home: dnaHome, away: dnaAway, scala: '%' },
      motivazioni: { home: motHome, away: motAway, scala: '%' },
      h2h: { home: h2hHome, away: h2hAway, matches: h2hMatches, scala: '%' },
      campo: { home: campoHome, away: campoAway, scala: '%' }
    };

    // ===== CALCOLO GOL =====

    // Media gol da ranking stats
    const hStats = homeTeam?.ranking?.homeStats || {};
    const aStats = awayTeam?.ranking?.awayStats || {};
    const hPlayed = Number(hStats.played || 1);
    const aPlayed = Number(aStats.played || 1);
    const hGfAvg = Number(hStats.goalsFor || 0) / hPlayed;
    const hGaAvg = Number(hStats.goalsAgainst || 0) / hPlayed;
    const aGfAvg = Number(aStats.goalsFor || 0) / aPlayed;
    const aGaAvg = Number(aStats.goalsAgainst || 0) / aPlayed;

    const expHome = (hGfAvg + aGaAvg) / 2;
    const expAway = (aGfAvg + hGaAvg) / 2;
    const expected_total_goals = Math.round((expHome + expAway) * 100) / 100 || 2.5;

    // Direzione da expected total
    const dirFromExp = (et) => et >= 2.5 ? 'over' : et <= 2.0 ? 'under' : 'neutro';

    // Score media gol
    const scoreMediaGol = (() => {
      const et = expected_total_goals;
      if (et >= 3.0) return Math.min(100, 80 + (et - 3.0) * 20);
      if (et >= 2.5) return 60 + (et - 2.5) * 40;
      if (et <= 1.8) return Math.min(100, 80 + (1.8 - et) * 30);
      if (et <= 2.2) return 55 + (2.2 - et) * 62;
      return 45;
    })();
    const dirMediaGol = dirFromExp(expected_total_goals);

    // Att vs Def
    const attHome = Number(homeTeam?.scores?.attack_home || 7);
    const defAway = Number(awayTeam?.scores?.defense_away || 5);
    const attAway = Number(awayTeam?.scores?.attack_away || 7);
    const defHome = Number(homeTeam?.scores?.defense_home || 5);
    const attHN = (attHome / 15) * 100;
    const defAN = (defAway / 10) * 100;
    const attAN = (attAway / 15) * 100;
    const defHN = (defHome / 10) * 100;
    const mismatch = Math.max(0, attHN - defAN) + Math.max(0, attAN - defHN);
    const scoreAttVsDef = Math.max(0, Math.min(100, Math.round((35 + mismatch * 0.5) * 10) / 10));
    const dirAttVsDef = mismatch > 30 ? 'over' : mismatch < 10 ? 'under' : 'neutro';

    // DNA off/def
    const dnaAttComb = ((Number(hDna.att || 50) + Number(aDna.att || 50)) / 2);
    const dnaDefComb = ((Number(hDna.def || 50) + Number(aDna.def || 50)) / 2);
    const scoreDnaOffDef = Math.max(0, Math.min(100, Math.round((dnaAttComb - dnaDefComb + 50) * 10) / 10));
    const dirDnaOffDef = dnaAttComb > dnaDefComb + 10 ? 'over' : dnaAttComb < dnaDefComb - 10 ? 'under' : 'neutro';

    // xG (default se non disponibile)
    const scoreXg = 50;
    const dirXg = 'neutro';

    // H2H gol (default se non disponibile)
    const scoreH2hGol = 50;
    const dirH2hGol = 'neutro';

    // Media lega (default 2.5)
    const scoreMediaLega = 50;
    const dirMediaLega = 'neutro';

    const gol_dettaglio = {
      media_gol: scoreMediaGol,
      att_vs_def: scoreAttVsDef,
      xg: scoreXg,
      h2h_gol: scoreH2hGol,
      media_lega: scoreMediaLega,
      dna_off_def: scoreDnaOffDef
    };

    const gol_directions = {
      media_gol: dirMediaGol,
      att_vs_def: dirAttVsDef,
      xg: dirXg,
      h2h_gol: dirH2hGol,
      media_lega: dirMediaLega,
      dna_off_def: dirDnaOffDef
    };

    res.json({
      segno_dettaglio,
      segno_dettaglio_raw,
      gol_dettaglio,
      gol_directions,
      expected_total_goals,
      source: 'calculated' // Per distinguere dai dati daily_predictions
    });

  } catch (error) {
    console.error('❌ [GAUGE-DATA] Errore:', error.message);
    res.status(500).json({ error: error.message });
  }
});

// ============================================
// ENDPOINT: /leagues
// ============================================

app.get('/leagues', (req, res) => {
  const country = req.query.country;
  const leaguesData = {
    'Italy': [
      { id: 'SERIE_A', name: 'Serie A' },
      { id: 'SERIE_B', name: 'Serie B' },
      { id: 'SERIE_C_A', name: 'Serie C - Girone A' },
      { id: 'SERIE_C_B', name: 'Serie C - Girone B' },
      { id: 'SERIE_C_C', name: 'Serie C - Girone C' }
    ],
    'England': [
      { id: 'PREMIER_LEAGUE', name: 'Premier League' },
      { id: 'CHAMPIONSHIP', name: 'Championship' }
    ],
    'Spain': [
      { id: 'LA_LIGA', name: 'La Liga' },
      { id: 'LA_LIGA_2', name: 'LaLiga 2' }
    ],
    'Germany': [
      { id: 'BUNDESLIGA', name: 'Bundesliga' },
      { id: 'BUNDESLIGA_2', name: '2. Bundesliga' }
    ],
    'France': [
      { id: 'LIGUE_1', name: 'Ligue 1' },
      { id: 'LIGUE_2', name: 'Ligue 2' }
    ],
    'Netherlands': [{ id: 'EREDIVISIE', name: 'Eredivisie' }],
    'Portugal': [{ id: 'LIGA_PORTUGAL', name: 'Liga Portugal' }],
    'Scotland': [{ id: 'SCOTTISH_PREMIERSHIP', name: 'Scottish Premiership' }],
    'Sweden': [{ id: 'ALLSVENSKAN', name: 'Allsvenskan' }],
    'Norway': [{ id: 'ELITESERIEN', name: 'Eliteserien' }],
    'Denmark': [{ id: 'SUPERLIGAEN', name: 'Superligaen' }],
    'Belgium': [{ id: 'JUPILER_PRO_LEAGUE', name: 'Jupiler Pro League' }],
    'Turkey': [{ id: 'SUPER_LIG', name: 'Süper Lig' }],
    'Ireland': [{ id: 'LEAGUE_OF_IRELAND', name: 'League of Ireland Premier Division' }],
    'Brazil': [{ id: 'BRASILEIRAO', name: 'Brasileirão Serie A' }],
    'Argentina': [{ id: 'PRIMERA_DIVISION_ARG', name: 'Primera División' }],
    'USA': [{ id: 'MLS', name: 'Major League Soccer' }],
    'Japan': [{ id: 'J1_LEAGUE', name: 'J1 League' }]
  };
  res.json(leaguesData[country] || []);
});


// ============================================
// ENDPOINT: /cups
// ============================================

app.get('/cups', (req, res) => {
  const cupsData = [
    { id: 'UCL', name: 'UEFA Champions League' },
    { id: 'UEL', name: 'UEFA Europa League' }
  ];
  
  console.log('✅ Cups list requested');
  res.json(cupsData);
});


// ============================================
// ENDPOINT: /cup-matches
// ============================================

app.get('/cup-matches', async (req, res) => {
  try {
    const cupId = req.query.cup;
    
    const cupMap = {
      'UCL': { matches: 'matches_champions_league', teams: 'teams_champions_league' },
      'UEL': { matches: 'matches_europa_league', teams: 'teams_europa_league' }
    };
    
    const collections = cupMap[cupId];
    if (!collections) {
      return res.json([]);
    }

    // Carica tutte le squadre per creare una mappa nome -> _id
    const teams = await db.collection(collections.teams).find({}).toArray();
    
    // Mappa: nome squadra (e aliases) -> MongoDB _id
    const teamIdMap = {};
    teams.forEach(team => {
      teamIdMap[team.name.toLowerCase()] = team._id.toString();
      // Aggiungi anche gli aliases
      if (team.aliases && Array.isArray(team.aliases)) {
        team.aliases.forEach(alias => {
          teamIdMap[alias.toLowerCase()] = team._id.toString();
        });
      }
    });

    // Carica i match e aggiungi gli ID MongoDB
    const matches = await db.collection(collections.matches)
      .find({})
      .toArray();

    // Aggiungi home_team_id e away_team_id
    const matchesWithIds = matches.map(match => ({
      ...match,
      home_team_id: teamIdMap[match.home_team.toLowerCase()] || null,
      away_team_id: teamIdMap[match.away_team.toLowerCase()] || null
    }));

    console.log(`✅ Cup matches ${cupId}: ${matchesWithIds.length} partite`);
    res.json(matchesWithIds);
    
  } catch (error) {
    console.error('Cup matches error:', error);
    res.status(500).json({ error: error.message });
  }
});


// =============================================
// ROOT E ESPORTAZIONE
// =============================================

app.get('/', (req, res) => {
  res.send('Simulatore Calcio API is running... ⚽');
});

// NON ri-dichiarare onRequest qui! È già dichiarata alla riga 1.
exports.api = onRequest({
  region: "us-central1",
  memory: "256MiB",
  timeoutSeconds: 60,
  cors: true,
  invoker: 'public'
}, app);