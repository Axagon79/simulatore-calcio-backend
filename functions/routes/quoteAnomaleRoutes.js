const express = require('express');
const router = express.Router();

// GET /quote-anomale/matches?date=YYYY-MM-DD&league=...
// Lista partite con tutti gli indicatori
router.get('/matches', async (req, res) => {
  try {
    const { date, league } = req.query;
    if (!date) {
      return res.json({ success: false, message: 'Parametro date richiesto (YYYY-MM-DD)' });
    }

    const filtro = { date };
    if (league) {
      filtro.league = league;
    }

    // Escludi storico dalla lista (pesante) — si carica solo nel dettaglio
    const docs = await req.db.collection('quote_anomale')
      .find(filtro, { projection: { _id: 0, storico: 0 } })
      .sort({ league: 1, match_time: 1 })
      .toArray();

    res.json({ success: true, data: docs, count: docs.length });
  } catch (err) {
    console.error('Errore GET /quote-anomale/matches:', err);
    res.status(500).json({ success: false, message: err.message });
  }
});

// GET /quote-anomale/leagues?date=YYYY-MM-DD
// Campionati disponibili per il dropdown
router.get('/leagues', async (req, res) => {
  try {
    const { date } = req.query;
    if (!date) {
      return res.json({ success: false, message: 'Parametro date richiesto (YYYY-MM-DD)' });
    }

    const leagues = await req.db.collection('quote_anomale').distinct('league', { date });

    res.json({ success: true, data: leagues.sort() });
  } catch (err) {
    console.error('Errore GET /quote-anomale/leagues:', err);
    res.status(500).json({ success: false, message: err.message });
  }
});

// GET /quote-anomale/detail?date=YYYY-MM-DD&match_key=...
// Dettaglio singola partita CON storico completo (per grafici)
router.get('/detail', async (req, res) => {
  try {
    const { date, match_key } = req.query;
    if (!date || !match_key) {
      return res.json({ success: false, message: 'Parametri date e match_key richiesti' });
    }

    const doc = await req.db.collection('quote_anomale')
      .findOne({ date, match_key }, { projection: { _id: 0 } });

    if (!doc) {
      return res.json({ success: false, message: 'Partita non trovata' });
    }

    res.json({ success: true, data: doc });
  } catch (err) {
    console.error('Errore GET /quote-anomale/detail:', err);
    res.status(500).json({ success: false, message: err.message });
  }
});

// GET /quote-anomale/predictions?date=YYYY-MM-DD
// Pronostici SEGNO da tutti i sistemi, matchati per match_key di quote_anomale
router.get('/predictions', async (req, res) => {
  try {
    const { date } = req.query;
    if (!date) {
      return res.json({ success: false, message: 'Parametro date richiesto (YYYY-MM-DD)' });
    }

    // Normalizza: lowercase, rimuovi accenti, solo lettere/numeri/spazi
    function norm(s) {
      return s.toLowerCase().trim()
        .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-z0-9\s]/g, '')
        .replace(/\s+/g, ' ').trim();
    }

    // 1. Carica le partite quote_anomale
    const qaMatches = await req.db.collection('quote_anomale')
      .find({ date }, { projection: { _id: 0, match_key: 1, home_raw: 1, away_raw: 1, league: 1 } })
      .toArray();

    // 2. Carica alias da db.teams (includo league per disambiguare)
    const teamsAliases = await req.db.collection('teams')
      .find({}, { projection: { _id: 0, name: 1, aliases: 1, league: 1 } })
      .toArray();

    // Mappa: norm(alias) → norm(name)
    const aliasToCanonical = {};
    for (const t of teamsAliases) {
      const canonical = norm(t.name);
      aliasToCanonical[canonical] = canonical;
      if (t.aliases) {
        for (const a of t.aliases) {
          aliasToCanonical[norm(a)] = canonical;
        }
      }
    }

    // Mappa: norm(name o alias) → league del team in db.teams
    const nameToLeague = {};
    for (const t of teamsAliases) {
      if (t.league) {
        nameToLeague[norm(t.name)] = norm(t.league);
        if (t.aliases) {
          for (const a of t.aliases) nameToLeague[norm(a)] = norm(t.league);
        }
      }
    }

    // Risolvi nome a canonical (con fallback a norm del nome stesso)
    function resolve(name) {
      const n = norm(name);
      return aliasToCanonical[n] || n;
    }

    // 3. Costruisci lookup con e senza campionato
    // Priorità: league+teams → solo teams (fallback)
    const qaByLeagueTeams = {}; // "norm_league|||canonical_home|||canonical_away" → match_key
    const qaByTeams = {};       // "canonical_home|||canonical_away" → match_key (fallback)
    const qaLeagueMap = {};     // match_key → norm(league) di quote_anomale
    for (const qa of qaMatches) {
      const teamKey = `${resolve(qa.home_raw)}|||${resolve(qa.away_raw)}`;
      qaByTeams[teamKey] = qa.match_key;
      if (qa.league) {
        const nl = norm(qa.league);
        qaByLeagueTeams[`${nl}|||${teamKey}`] = qa.match_key;
        qaLeagueMap[qa.match_key] = nl;
      }
    }

    const collections = [
      { name: 'daily_predictions_unified', source: 'MoE' },
      { name: 'daily_predictions', source: 'A' },
      { name: 'daily_predictions_sandbox', source: 'S' },
      { name: 'daily_predictions_engine_c', source: 'C' },
    ];

    const results = {};
    const debug = { qa_partite: qaMatches.length, per_source: {}, unmatched: [] };

    await Promise.all(collections.map(async ({ name, source }) => {
      const docs = await req.db.collection(name)
        .find({ date }, { projection: { _id: 0, home: 1, away: 1, league: 1, pronostici: 1, sezione: 1 } })
        .toArray();

      let matched = 0, total = 0;
      for (const doc of docs) {
        if (!doc.home || !doc.away || !doc.pronostici) continue;
        const hasSegno = doc.pronostici.some(p => p.tipo === 'SEGNO' || p.tipo === 'DOPPIA_CHANCE');
        if (!hasSegno) continue;
        total++;

        const teamKey = `${resolve(doc.home)}|||${resolve(doc.away)}`;
        // Prima prova con campionato (disambigua omonimi come Racing)
        let mk = null;
        if (doc.league) {
          const predLeague = norm(doc.league);
          mk = qaByLeagueTeams[`${predLeague}|||${teamKey}`];
          // Fallback: prova con la league del team nel db.teams
          if (!mk) {
            const teamLeague = nameToLeague[norm(doc.home)];
            if (teamLeague) {
              mk = qaByLeagueTeams[`${teamLeague}|||${teamKey}`];
            }
          }
        }
        // Fallback: solo team names (per retrocompatibilità)
        if (!mk) mk = qaByTeams[teamKey];

        if (!mk) {
          debug.unmatched.push({ source, home: doc.home, away: doc.away, league: doc.league || '?' });
          continue;
        }
        matched++;

        for (const p of doc.pronostici) {
          if (p.tipo !== 'SEGNO' && p.tipo !== 'DOPPIA_CHANCE') continue;
          if (!results[mk]) results[mk] = [];
          const isBestPick = name === 'daily_predictions_unified';
          results[mk].push({
            source: p.source || source,
            bestPick: isBestPick,
            pronostico: p.pronostico,
            tipo: p.tipo,
            confidence: p.confidence ?? null,
            sezione: doc.sezione ?? null,
            home: doc.home,
            away: doc.away,
          });
        }
      }
      debug.per_source[source] = { total_segno: total, matched, unmatched: total - matched };
    }));

    // Deduplica unmatched (stessa partita da più sources)
    const seen = new Set();
    debug.unmatched = debug.unmatched.filter(u => {
      const key = `${u.home}|||${u.away}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });

    res.json({ success: true, data: results, matched_count: Object.keys(results).length, debug });
  } catch (err) {
    console.error('Errore GET /quote-anomale/predictions:', err);
    res.status(500).json({ success: false, message: err.message });
  }
});

module.exports = router;
