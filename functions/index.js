const { onRequest } = require("firebase-functions/v2/https");
const simulationRoutes = require('./routes/simulationRoutes');
const express = require('express');
const cors = require('cors');
const { MongoClient } = require('mongodb');

const app = express();
app.use(cors({ origin: true }));
app.use(express.json());

const MONGO_URI = process.env.MONGO_URI;
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


app.use('/simulation', simulationRoutes);


// ============================================
// ROOT E ESPORTAZIONE
// ============================================

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