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

    // Normalizza: lowercase, rimuovi accenti, suffissi club, solo lettere/numeri/spazi
    function norm(s) {
      let n = s.toLowerCase().trim()
        .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-z0-9\s]/g, '')
        .replace(/\s+/g, ' ').trim();
      // Rimuovi suffissi comuni (fc, afc, sc, etc.)
      for (const suf of [' fc', ' afc', ' sc', ' ac', ' cf', ' ssc', ' calcio']) {
        if (n.endsWith(suf)) n = n.slice(0, -suf.length).trim();
      }
      // Rimuovi prefissi comuni
      for (const pre of ['fc ', 'cf ', 'ac ', 'as ', 'sc ', 'us ', 'ss ']) {
        if (n.startsWith(pre)) n = n.slice(pre.length).trim();
      }
      return n;
    }

    // 1. Carica le partite quote_anomale
    const qaMatches = await req.db.collection('quote_anomale')
      .find({ date }, { projection: { _id: 0, match_key: 1, home_raw: 1, away_raw: 1, home: 1, away: 1, league: 1 } })
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
      // Usa nome canonico (da db.teams) se disponibile, altrimenti raw
      const homeName = qa.home && qa.home !== '-' ? qa.home : qa.home_raw;
      const awayName = qa.away && qa.away !== '-' ? qa.away : qa.away_raw;
      const teamKey = `${resolve(homeName)}|||${resolve(awayName)}`;
      qaByTeams[teamKey] = qa.match_key;
      // Aggiungi anche con home_raw come fallback
      const rawKey = `${resolve(qa.home_raw)}|||${resolve(qa.away_raw)}`;
      if (rawKey !== teamKey) qaByTeams[rawKey] = qa.match_key;
      if (qa.league) {
        const nl = norm(qa.league);
        qaByLeagueTeams[`${nl}|||${teamKey}`] = qa.match_key;
        if (rawKey !== teamKey) qaByLeagueTeams[`${nl}|||${rawKey}`] = qa.match_key;
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
          const isBestPick = name === 'daily_predictions_unified';
          // Dai sistemi A/S/C solo SEGNO e DC; dalle Best Picks (MoE) passa tutto
          if (!isBestPick && p.tipo !== 'SEGNO' && p.tipo !== 'DOPPIA_CHANCE') continue;
          if (!results[mk]) results[mk] = [];
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

// POST /quote-anomale/analysis-premium
// Genera analisi AI (Mistral) per una partita — Premium only
router.post('/analysis-premium', async (req, res) => {
  try {
    const { match_key, date, isAdmin } = req.body;

    if (!match_key || !date) {
      return res.status(400).json({ success: false, error: 'Missing match_key or date' });
    }
    // Solo admin/premium
    if (isAdmin !== true && isAdmin !== 'true') {
      return res.status(403).json({ success: false, error: 'Premium analysis is admin-only' });
    }

    // 1. Leggi doc quote_anomale
    const qa = await req.db.collection('quote_anomale')
      .findOne({ date, match_key }, { projection: { _id: 0, storico: 0 } });

    if (!qa) {
      return res.json({ success: false, error: 'Partita non trovata in quote_anomale' });
    }

    // 2. Cache check
    if (qa.analysis_premium) {
      return res.json({ success: true, analysis: qa.analysis_premium, cached: true });
    }

    // 3. Cerca pronostici in daily_predictions_unified (match per home/away)
    const homeName = qa.home && qa.home !== '-' ? qa.home : qa.home_raw;
    const awayName = qa.away && qa.away !== '-' ? qa.away : qa.away_raw;

    let pronostici = [];
    const pred = await req.db.collection('daily_predictions_unified')
      .findOne(
        { date, home: { $regex: new RegExp(homeName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i') } },
        { projection: { _id: 0, pronostici: 1 } }
      );
    if (pred && pred.pronostici) {
      pronostici = pred.pronostici.map(p => ({
        tipo: p.tipo,
        pronostico: p.pronostico,
        quota: p.quota ?? null,
        confidence: p.confidence ?? null,
        stars: p.stars ?? null,
        stake: p.stake ?? null,
        edge: p.edge ?? null,
        elite: p.elite ?? false,
      }));
    }

    // 4. Componi JSON per Mistral (solo campi utili)
    const matchJson = {
      league: qa.league || qa.league_raw || '',
      match_time: qa.match_time || '',
      home: homeName,
      away: awayName,
      quote_apertura: qa.quote_apertura,
      quote_chiusura: qa.quote_chiusura || null,
      semaforo: qa.semaforo || null,
      alert_breakeven: qa.alert_breakeven || null,
      direzione: qa.direzione || null,
      v_index_abs: qa.v_index_abs || null,
      v_index_rel: qa.v_index_rel || null,
      rendimento_apertura: qa.rendimento_apertura || null,
      rendimento_chiusura: qa.rendimento_chiusura || null,
    };
    if (pronostici.length > 0) {
      matchJson.pronostici = pronostici;
    }

    // 5. Chiama Mistral
    const { generateOddsMonitorAnalysis } = require('../services/llmService');
    const analysis = await generateOddsMonitorAnalysis(matchJson);

    // 6. Salva in cache
    await req.db.collection('quote_anomale')
      .updateOne({ date, match_key }, { $set: { analysis_premium: analysis } });

    res.json({ success: true, analysis, cached: false });
  } catch (error) {
    console.error('[QUOTE-ANOMALE/ANALYSIS-PREMIUM]', error.message);
    res.status(500).json({ success: false, error: error.message });
  }
});

module.exports = router;
