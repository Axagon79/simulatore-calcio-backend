const functions = require('firebase-functions');
const express = require('express');
const cors = require('cors');
const { MongoClient } = require('mongodb');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '../.env') });

const app = express();
app.use(cors({ origin: true }));
app.use(express.json());

let dbReady = false;
let db;

// Connetti e ASPETTA
const MONGO_URI = process.env.MONGO_URI;
const client = new MongoClient(MONGO_URI);

async function connectDB() {
  try {
    await client.connect();
    const db_name = MONGO_URI.split('/').pop()?.split('?')[0] || 'football_simulator_db';
    db = client.db(db_name);
    dbReady = true;
    console.log(`✅ DB connesso: ${db_name}`);
  } catch (err) {
    console.error('❌ Mongo errore:', err);
  }
}

connectDB();

// Aspetta DB pronto
app.use((req, res, next) => {
  if (!dbReady) {
    return res.status(503).json({ error: 'DB non pronto, riprova tra 2 secondi' });
  }
  next();
});

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
      LIGA_PORTUGAL: 'Liga Portugal'
    };

    const leagueName = leagueMap[leagueId];
    if (!leagueName) return res.json({ rounds: [], anchor: null });

    // Recupera TUTTE le giornate
    const docs = await db.collection('h2h_by_round')
      .find({ league: leagueName })
      .toArray();

    if (docs.length === 0) {
      return res.json({ rounds: [], anchor: null });
    }

    // Ordina per numero giornata
    const sortedRounds = docs.sort((a, b) => {
      return getRoundNumber(a.round_name) - getRoundNumber(b.round_name);
    });

    // TROVA L'ANCHOR (giornata di riferimento)
    let anchorIndex = -1;

    // STEP 1: Cerca la prima giornata con partite "Scheduled"
    for (let i = 0; i < sortedRounds.length; i++) {
      if (hasScheduledMatches(sortedRounds[i])) {
        anchorIndex = i;
        break;
      }
    }

    // STEP 2: Se non trova Scheduled, prende l'ultima con "Finished"
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
      'LIGA_PORTUGAL': 'Liga Portugal'
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

    // Estrai tutte le partite dal documento trovato
    const matches = docs.flatMap(doc => 
      (doc.matches || []).map((m, i) => ({
        id: `${doc._id}_${i}`,
        home: m.home,
        away: m.away,
        real_score: m.real_score,
        score: m.score,
        status: m.status || 'Finished',
        match_time: m.match_time,
        date_obj: m.date_obj,
        h2h_data: m.h2h_data
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
    'England': [{ id: 'PREMIER_LEAGUE', name: 'Premier League' }],
    'Spain': [{ id: 'LA_LIGA', name: 'La Liga' }],
    'Germany': [{ id: 'BUNDESLIGA', name: 'Bundesliga' }],
    'France': [{ id: 'LIGUE_1', name: 'Ligue 1' }],
    'Netherlands': [{ id: 'EREDIVISIE', name: 'Eredivisie' }],
    'Portugal': [{ id: 'LIGA_PORTUGAL', name: 'Liga Portugal' }]
  };
  res.json(leaguesData[country] || []);
});

// ============================================
// ROOT
// ============================================

app.get('/', (req, res) => {
  res.send('Simulatore Calcio API is running... ⚽');
});

exports.api = functions.https.onRequest(app);