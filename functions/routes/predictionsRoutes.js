// 📁 functions/routes/predictionsRoutes.js
const express = require('express');
const router = express.Router();

// --- CACHE: Track Record (TTL 5 minuti) ---
const trackRecordCache = new Map();
const CACHE_TTL = 5 * 60 * 1000; // 5 minuti

// --- HELPER: Parse real_score → { home, away, total, sign } ---
function parseScore(realScore) {
  if (!realScore || typeof realScore !== 'string') return null;
  const parts = realScore.split(':');
  if (parts.length !== 2) return null;
  const home = parseInt(parts[0]);
  const away = parseInt(parts[1]);
  if (isNaN(home) || isNaN(away)) return null;
  let sign;
  if (home > away) sign = '1';
  else if (home < away) sign = '2';
  else sign = 'X';
  return { home, away, total: home + away, sign, btts: home > 0 && away > 0 };
}

// --- HELPER: Verifica un singolo pronostico contro il risultato ---
function checkPronostico(pronostico, tipo, parsed) {
  if (!parsed || !pronostico) return null;
  const p = pronostico.trim();

  // SEGNO FISSO: 1, X, 2
  if (tipo === 'SEGNO') {
    return p === parsed.sign;
  }

  // DOPPIA CHANCE: 1X, X2, 12
  if (tipo === 'DOPPIA_CHANCE') {
    if (p === '1X') return parsed.sign === '1' || parsed.sign === 'X';
    if (p === 'X2') return parsed.sign === 'X' || parsed.sign === '2';
    if (p === '12') return parsed.sign === '1' || parsed.sign === '2';
    return null;
  }

  // GOL: Over X.X, Under X.X, Goal, NoGoal
  if (tipo === 'GOL') {
    // Over/Under
    const overMatch = p.match(/^Over\s+(\d+\.?\d*)$/i);
    if (overMatch) {
      const threshold = parseFloat(overMatch[1]);
      return parsed.total > threshold;
    }
    const underMatch = p.match(/^Under\s+(\d+\.?\d*)$/i);
    if (underMatch) {
      const threshold = parseFloat(underMatch[1]);
      return parsed.total < threshold;
    }
    // Goal (entrambe segnano) / NoGoal
    if (p.toLowerCase() === 'goal') return parsed.btts;
    if (p.toLowerCase() === 'nogoal') return !parsed.btts;
    // Multigol: MG X-Y
    const mgMatch = p.match(/^MG\s+(\d+)-(\d+)$/i);
    if (mgMatch) {
      return parsed.total >= parseInt(mgMatch[1]) && parsed.total <= parseInt(mgMatch[2]);
    }
    return null;
  }

  // X FACTOR: pronostico è 'X', hit se risultato è pareggio
  if (tipo === 'X_FACTOR') {
    return p === parsed.sign;
  }

  // RISULTATO ESATTO: pronostico è "1:1" o "1-1", hit se risultato reale matcha
  if (tipo === 'RISULTATO_ESATTO') {
    const realScore = `${parsed.home}:${parsed.away}`;
    return p.replace('-', ':') === realScore;
  }

  return null;
}

// --- HELPER: Deriva quota per pronostici GOL dal campo odds padre ---
function getQuotaForPronostico(pronostico, tipo, parentOdds) {
  if (tipo !== 'GOL') return null;
  if (!parentOdds || typeof parentOdds !== 'object') return null;
  const p = (pronostico || '').trim().toLowerCase();
  const MAPPING = {
    'over 1.5': 'over_15', 'over 2.5': 'over_25', 'over 3.5': 'over_35',
    'under 1.5': 'under_15', 'under 2.5': 'under_25', 'under 3.5': 'under_35',
    'goal': 'gg', 'nogoal': 'ng',
  };
  const key = MAPPING[p];
  if (!key) return null;
  const val = parseFloat(parentOdds[key]);
  return isNaN(val) ? null : val;
}

// --- HELPER: Recupera risultati reali da h2h_by_round (filtrato per data) ---
async function getFinishedResults(db, dateFilter) {
  try {
    const matchCondition = {
      'matches.status': 'Finished',
      'matches.real_score': { $ne: null }
    };

    // Filtro per data: stringa "YYYY-MM-DD" o oggetto { from, to }
    if (typeof dateFilter === 'string') {
      const startOfDay = new Date(dateFilter + 'T00:00:00.000Z');
      const endOfDay = new Date(dateFilter + 'T23:59:59.999Z');
      matchCondition['matches.date_obj'] = { $gte: startOfDay, $lte: endOfDay };
    } else if (dateFilter && dateFilter.from && dateFilter.to) {
      matchCondition['matches.date_obj'] = {
        $gte: new Date(dateFilter.from + 'T00:00:00.000Z'),
        $lte: new Date(dateFilter.to + 'T23:59:59.999Z')
      };
    }

    const pipeline = [
      { $unwind: '$matches' },
      { $match: matchCondition },
      { $project: {
        _id: 0,
        home: '$matches.home',
        away: '$matches.away',
        real_score: '$matches.real_score',
        date_obj: '$matches.date_obj'
      }}
    ];

    const results = await db.collection('h2h_by_round').aggregate(pipeline).toArray();

    const resultsMap = {};
    for (const r of results) {
      const dateStr = new Date(r.date_obj).toISOString().split('T')[0];
      resultsMap[`${r.home}|||${r.away}|||${dateStr}`] = r.real_score;
    }
    return resultsMap;
  } catch (err) {
    console.error('⚠️ Errore lettura h2h_by_round:', err.message);
    return {};
  }
}

// 🔮 ENDPOINT: Pronostici del giorno
router.get('/daily-predictions', async (req, res) => {
  const { date } = req.query;
  if (!date) return res.status(400).json({ error: 'Parametro date mancante' });

  console.log('🔮 [PREDICTIONS] Richiesta per:', date);

  try {
    const [predictions, resultsMap] = await Promise.all([
      req.db.collection('daily_predictions')
        .find({ date, decision: { $ne: 'SCARTA' } }, { projection: { _id: 0 } })
        .toArray(),
      getFinishedResults(req.db, date)
    ]);

    // Cross-match con risultati reali
    for (const pred of predictions) {
      const realScore = resultsMap[`${pred.home}|||${pred.away}|||${pred.date}`] || null;
      pred.real_score = realScore;

      if (realScore) {
        const parsed = parseScore(realScore);
        pred.real_sign = parsed ? parsed.sign : null;

        // Verifica ogni pronostico nell'array
        if (pred.pronostici && pred.pronostici.length > 0) {
          for (const p of pred.pronostici) {
            p.hit = checkPronostico(p.pronostico, p.tipo, parsed);
          }
          // hit globale: true se almeno uno dei pronostici è corretto
          pred.hit = pred.pronostici.some(p => p.hit === true);
        } else {
          pred.hit = null;
        }
      } else {
        pred.real_sign = null;
        pred.hit = null;
      }
    }

    predictions.sort((a, b) => (a.match_time || '').localeCompare(b.match_time || ''));

    // Backward compatibility: assicura campi Kelly sempre presenti
    for (const pred of predictions) {
      if (pred.pronostici) {
        for (const p of pred.pronostici) {
          p.probabilita_stimata = p.probabilita_stimata ?? null;
          p.stake = p.stake ?? 0;
          p.edge = p.edge ?? 0;
          p.profit_loss = p.profit_loss ?? null;
          p.prob_mercato = p.prob_mercato ?? null;
          p.prob_modello = p.prob_modello ?? null;
          p.has_odds = p.has_odds ?? true;
        }
      }
    }

    // Conteggio per singolo pronostico (non per partita)
    const allP = predictions.flatMap(p => p.pronostici || []);
    const verifiedP = allP.filter(p => p.hit === true || p.hit === false);
    const hitsP = allP.filter(p => p.hit === true).length;

    // Conteggio HR per partita (almeno 1 pronostico corretto = match hit)
    const matchesWithResult = predictions.filter(p => p.real_score);
    const matchHits = matchesWithResult.filter(p => p.hit === true).length;

    console.log(`✅ [PREDICTIONS] ${predictions.length} partite, ${allP.length} pronostici, ${hitsP}/${verifiedP.length} azzeccati, HR partite: ${matchHits}/${matchesWithResult.length}`);

    return res.json({
      success: true, date, predictions, count: predictions.length,
      stats: {
        total: allP.length,
        total_matches: predictions.length,
        finished: verifiedP.length,
        hits: hitsP,
        misses: verifiedP.length - hitsP,
        pending: allP.length - verifiedP.length,
        hit_rate: verifiedP.length > 0 ? Math.round((hitsP / verifiedP.length) * 1000) / 10 : null,
        // HR Partite
        matches_finished: matchesWithResult.length,
        matches_hits: matchHits,
        matches_hit_rate: matchesWithResult.length > 0 ? Math.round((matchHits / matchesWithResult.length) * 1000) / 10 : null
      }
    });
  } catch (error) {
    console.error('❌ [PREDICTIONS] Errore:', error);
    return res.status(500).json({ error: 'Errore nel recupero pronostici', details: error.message });
  }
});

// 💣 ENDPOINT: Bombe del giorno
router.get('/daily-bombs', async (req, res) => {
  const { date } = req.query;
  if (!date) return res.status(400).json({ error: 'Parametro date mancante' });

  console.log('💣 [BOMBS] Richiesta per:', date);

  try {
    const [bombs, resultsMap] = await Promise.all([
      req.db.collection('daily_bombs')
        .find({ date }, { projection: { _id: 0 } })
        .toArray(),
      getFinishedResults(req.db, date)
    ]);

    for (const bomb of bombs) {
      const realScore = resultsMap[`${bomb.home}|||${bomb.away}|||${bomb.date}`] || null;
      bomb.real_score = realScore;
      if (realScore) {
        const parsed = parseScore(realScore);
        bomb.real_sign = parsed ? parsed.sign : null;
        bomb.hit = bomb.segno_bomba ? (bomb.segno_bomba === (parsed ? parsed.sign : null)) : null;
      } else {
        bomb.real_sign = null;
        bomb.hit = null;
      }
    }

    bombs.sort((a, b) => (b.stars || 0) - (a.stars || 0));

    const finished = bombs.filter(b => b.real_score !== null);
    const hits = finished.filter(b => b.hit === true).length;

    console.log(`✅ [BOMBS] ${bombs.length} bombe, ${hits}/${finished.length} azzeccate`);

    return res.json({
      success: true, date, bombs, count: bombs.length,
      stats: {
        total: bombs.length,
        finished: finished.length,
        hits,
        misses: finished.filter(b => b.hit === false).length,
        pending: bombs.length - finished.length,
        hit_rate: finished.length > 0 ? Math.round((hits / finished.length) * 1000) / 10 : null
      }
    });
  } catch (error) {
    console.error('❌ [BOMBS] Errore:', error);
    return res.status(500).json({ error: 'Errore nel recupero bombe', details: error.message });
  }
});

// 🧪 ENDPOINT: Pronostici SANDBOX del giorno
router.get('/daily-predictions-sandbox', async (req, res) => {
  const { date } = req.query;
  if (!date) return res.status(400).json({ error: 'Parametro date mancante' });

  console.log('🧪 [PREDICTIONS SANDBOX] Richiesta per:', date);

  try {
    const [predictions, resultsMap] = await Promise.all([
      req.db.collection('daily_predictions_sandbox')
        .find({ date, decision: { $ne: 'SCARTA' } }, { projection: { _id: 0 } })
        .toArray(),
      getFinishedResults(req.db, date)
    ]);

    for (const pred of predictions) {
      const realScore = resultsMap[`${pred.home}|||${pred.away}|||${pred.date}`] || null;
      pred.real_score = realScore;

      if (realScore) {
        const parsed = parseScore(realScore);
        pred.real_sign = parsed ? parsed.sign : null;

        if (pred.pronostici && pred.pronostici.length > 0) {
          for (const p of pred.pronostici) {
            p.hit = checkPronostico(p.pronostico, p.tipo, parsed);
          }
          pred.hit = pred.pronostici.some(p => p.hit === true);
        } else {
          pred.hit = null;
        }
      } else {
        pred.real_sign = null;
        pred.hit = null;
      }
    }

    predictions.sort((a, b) => (a.match_time || '').localeCompare(b.match_time || ''));

    // Conteggio per singolo pronostico (non per partita)
    const allP = predictions.flatMap(p => p.pronostici || []);
    const verifiedP = allP.filter(p => p.hit === true || p.hit === false);
    const hitsP = allP.filter(p => p.hit === true).length;

    console.log(`✅ [PREDICTIONS SANDBOX] ${predictions.length} partite, ${allP.length} pronostici, ${hitsP}/${verifiedP.length} azzeccati`);

    return res.json({
      success: true, date, predictions, count: predictions.length,
      stats: {
        total: allP.length,
        total_matches: predictions.length,
        finished: verifiedP.length,
        hits: hitsP,
        misses: verifiedP.length - hitsP,
        pending: allP.length - verifiedP.length,
        hit_rate: verifiedP.length > 0 ? Math.round((hitsP / verifiedP.length) * 1000) / 10 : null
      }
    });
  } catch (error) {
    console.error('❌ [PREDICTIONS SANDBOX] Errore:', error);
    return res.status(500).json({ error: 'Errore nel recupero pronostici sandbox', details: error.message });
  }
});

// 🧪 ENDPOINT: Bombe SANDBOX del giorno
router.get('/daily-bombs-sandbox', async (req, res) => {
  const { date } = req.query;
  if (!date) return res.status(400).json({ error: 'Parametro date mancante' });

  console.log('🧪 [BOMBS SANDBOX] Richiesta per:', date);

  try {
    const [bombs, resultsMap] = await Promise.all([
      req.db.collection('daily_bombs_sandbox')
        .find({ date }, { projection: { _id: 0 } })
        .toArray(),
      getFinishedResults(req.db, date)
    ]);

    for (const bomb of bombs) {
      const realScore = resultsMap[`${bomb.home}|||${bomb.away}|||${bomb.date}`] || null;
      bomb.real_score = realScore;
      if (realScore) {
        const parsed = parseScore(realScore);
        bomb.real_sign = parsed ? parsed.sign : null;
        bomb.hit = bomb.segno_bomba ? (bomb.segno_bomba === (parsed ? parsed.sign : null)) : null;
      } else {
        bomb.real_sign = null;
        bomb.hit = null;
      }
    }

    bombs.sort((a, b) => (b.stars || 0) - (a.stars || 0));

    const finished = bombs.filter(b => b.real_score !== null);
    const hits = finished.filter(b => b.hit === true).length;

    console.log(`✅ [BOMBS SANDBOX] ${bombs.length} bombe, ${hits}/${finished.length} azzeccate`);

    return res.json({
      success: true, date, bombs, count: bombs.length,
      stats: {
        total: bombs.length,
        finished: finished.length,
        hits,
        misses: finished.filter(b => b.hit === false).length,
        pending: bombs.length - finished.length,
        hit_rate: finished.length > 0 ? Math.round((hits / finished.length) * 1000) / 10 : null
      }
    });
  } catch (error) {
    console.error('❌ [BOMBS SANDBOX] Errore:', error);
    return res.status(500).json({ error: 'Errore nel recupero bombe sandbox', details: error.message });
  }
});

// 📊 ENDPOINT: Track Record — Aggregazione storica accuratezza pronostici
router.get('/track-record', async (req, res) => {
  const { from, to, league, market, min_confidence, min_quota, max_quota, sezione } = req.query;

  if (!from || !to) {
    return res.status(400).json({ error: 'Parametri from e to (YYYY-MM-DD) obbligatori' });
  }

  console.log(`📊 [TRACK-RECORD] Richiesta: ${from} → ${to} | league=${league || 'tutte'} | market=${market || 'tutti'} | sezione=${sezione || 'tutto'}`);

  try {
    // Cache check (chiave = tutti i parametri della richiesta)
    const cacheKey = `${from}|${to}|${league || ''}|${market || ''}|${min_confidence || ''}|${min_quota || ''}|${max_quota || ''}|${sezione || ''}`;
    const cached = trackRecordCache.get(cacheKey);
    if (cached && (Date.now() - cached.ts) < CACHE_TTL) {
      console.log(`⚡ [TRACK-RECORD] Cache hit (${Math.round((Date.now() - cached.ts) / 1000)}s old)`);
      return res.json(cached.data);
    }

    // 1. Query da daily_predictions_unified (MoE — sistema attuale)
    const query = { date: { $gte: from, $lte: to } };
    if (league) query.league = { $regex: new RegExp(league, 'i') };

    const predictions = await req.db.collection('daily_predictions_unified')
      .find(query, { projection: { _id: 0, date: 1, league: 1, pronostici: 1, odds: 1 } }).toArray();

    // 2. Estrai pronostici verificati (con esito già calcolato dal P/L)
    const verified = [];
    const allVerified = []; // tutti senza filtro sezione, per split_sezione
    for (const pred of predictions) {
      if (!pred.pronostici || pred.pronostici.length === 0) continue;

      for (const p of pred.pronostici) {
        // Solo pronostici con esito verificato
        if (p.esito === undefined || p.esito === null) continue;

        // Ignora tipi deprecati (sicurezza — unified non dovrebbe averli)
        if (p.tipo === 'X_FACTOR' || p.tipo === 'RISULTATO_ESATTO') continue;

        // Splitta tipo "GOL" in OVER_UNDER vs GG_NG
        let tipoEffettivo = p.tipo;
        if (p.tipo === 'GOL') {
          const pLower = (p.pronostico || '').toLowerCase();
          if (pLower.startsWith('over') || pLower.startsWith('under')) {
            tipoEffettivo = 'OVER_UNDER';
          } else if (pLower === 'goal' || pLower === 'nogoal') {
            tipoEffettivo = 'GG_NG';
          } else if (pLower.startsWith('mg ')) {
            tipoEffettivo = 'MULTI_GOAL';
          }
        }

        // Filtro per mercato se specificato
        if (market && tipoEffettivo.toUpperCase() !== market.toUpperCase()) continue;
        // Filtro per confidence minima
        if (min_confidence && (p.confidence || 0) < parseFloat(min_confidence)) continue;

        // Risolvi quota — STESSA logica del frontend (UnifiedPredictions.getPronosticoQuota)
        let quota = p.quota != null ? parseFloat(p.quota) : null;
        if (quota === null || isNaN(quota)) {
          quota = getQuotaForPronostico(p.pronostico, p.tipo, pred.odds);
        }
        // Fallback SEGNO / DOPPIA_CHANCE: estrai da pred.odds[pronostico]
        if ((quota === null || isNaN(quota)) && pred.odds) {
          if (p.tipo === 'SEGNO' || p.tipo === 'DOPPIA_CHANCE') {
            const oddsVal = pred.odds[p.pronostico];
            if (oddsVal != null && !isNaN(parseFloat(String(oddsVal)))) {
              quota = parseFloat(String(oddsVal));
            }
          }
        }
        // Filtro per range quota
        if (min_quota && (quota === null || quota < parseFloat(min_quota))) continue;
        if (max_quota && (quota === null || quota > parseFloat(max_quota))) continue;

        // Classificazione Pronostici vs Alto Rendimento
        // DC: soglia >= 2.00 (copre 2 esiti, quota 2.00 = 50% prob implicita), altri: > 2.50
        const sogliaAR = (p.tipo === 'DOPPIA_CHANCE') ? 2.00 : 2.51;
        const sez = (quota != null && quota >= sogliaAR) ? 'alto_rendimento' : 'pronostici';

        const item = {
          date: pred.date,
          league: pred.league || 'N/A',
          tipo: tipoEffettivo,
          pronostico: p.pronostico,
          confidence: p.confidence || 0,
          stars: p.stars || 0,
          quota,
          probabilita_stimata: p.probabilita_stimata != null ? parseFloat(String(p.probabilita_stimata)) : null,
          hit: p.esito === true,
          sezione: sez,
          source: p.source || 'unknown'
        };

        // Salva in allVerified PRIMA del filtro sezione (per split_sezione)
        allVerified.push(item);

        // Filtro per sezione se specificato
        if (sezione && sezione !== sez) continue;

        verified.push(item);
      }
    }

    // 3. Aggregazioni
    const hitRate = (items) => {
      const total = items.length;
      const hits = items.filter(i => i.hit).length;
      return {
        total, hits, misses: total - hits,
        hit_rate: total > 0 ? Math.round((hits / total) * 1000) / 10 : null
      };
    };

    // Stats estese per sezione (hitRate + dati finanziari)
    const sectionStats = (items) => {
      const base = hitRate(items);
      const withQuota = items.filter(v => v.quota != null);
      let profit = 0;
      for (const v of withQuota) {
        profit += v.hit ? (v.quota - 1) : -1;
      }
      return {
        ...base,
        roi: withQuota.length > 0 ? Math.round((profit / withQuota.length) * 1000) / 10 : null,
        profit: Math.round(profit * 100) / 100,
        avg_quota: withQuota.length > 0 ? Math.round(withQuota.reduce((s, v) => s + v.quota, 0) / withQuota.length * 100) / 100 : null,
      };
    };

    // Globale
    const globale = hitRate(verified);

    // Per mercato (tipo)
    const byMarket = {};
    for (const v of verified) {
      if (!byMarket[v.tipo]) byMarket[v.tipo] = [];
      byMarket[v.tipo].push(v);
    }
    const breakdown_mercato = {};
    for (const [tipo, items] of Object.entries(byMarket)) {
      breakdown_mercato[tipo] = hitRate(items);
    }

    // Per source (algoritmo di provenienza)
    const bySource = {};
    for (const v of verified) {
      if (!bySource[v.source]) bySource[v.source] = [];
      bySource[v.source].push(v);
    }
    const breakdown_source = {};
    for (const [src, items] of Object.entries(bySource)) {
      const hr = hitRate(items);
      const withQuota = items.filter(i => i.quota && i.quota > 1);
      const profit = withQuota.reduce((sum, i) => sum + (i.hit ? (i.quota - 1) : -1), 0);
      const avgQuota = withQuota.length > 0 ? Math.round(withQuota.reduce((s, i) => s + i.quota, 0) / withQuota.length * 100) / 100 : null;
      const roi = withQuota.length > 0 ? Math.round((profit / withQuota.length) * 1000) / 10 : null;
      breakdown_source[src] = { ...hr, profit: Math.round(profit * 100) / 100, avg_quota: avgQuota, roi };
    }

    // Per campionato
    const byLeague = {};
    for (const v of verified) {
      if (!byLeague[v.league]) byLeague[v.league] = [];
      byLeague[v.league].push(v);
    }
    const breakdown_campionato = {};
    for (const [lg, items] of Object.entries(byLeague)) {
      breakdown_campionato[lg] = hitRate(items);
    }

    // Per fascia confidence
    const confBands = { '60-70': [], '70-80': [], '80-90': [], '90+': [] };
    for (const v of verified) {
      if (v.confidence >= 90) confBands['90+'].push(v);
      else if (v.confidence >= 80) confBands['80-90'].push(v);
      else if (v.confidence >= 70) confBands['70-80'].push(v);
      else confBands['60-70'].push(v);
    }
    const breakdown_confidence = {};
    for (const [band, items] of Object.entries(confBands)) {
      breakdown_confidence[band] = hitRate(items);
    }

    // Per fascia stelle
    const starBands = { '2.5-3': [], '3-4': [], '4-5': [] };
    for (const v of verified) {
      if (v.stars >= 4) starBands['4-5'].push(v);
      else if (v.stars >= 3) starBands['3-4'].push(v);
      else starBands['2.5-3'].push(v);
    }
    const breakdown_stelle = {};
    for (const [band, items] of Object.entries(starBands)) {
      breakdown_stelle[band] = hitRate(items);
    }

    // Per fascia quota (fasce strette)
    const quotaBands = {
      '1.01-1.20': [], '1.21-1.40': [], '1.41-1.60': [], '1.61-1.80': [],
      '1.81-2.00': [], '2.01-2.20': [], '2.21-2.50': [], '2.51-3.00': [],
      '3.01-3.50': [], '3.51-4.00': [], '4.01-5.00': [], '5.00+': [], 'N/D': []
    };
    for (const v of verified) {
      if (v.quota === null || v.quota === undefined) { quotaBands['N/D'].push(v); continue; }
      if (v.quota <= 1.20) quotaBands['1.01-1.20'].push(v);
      else if (v.quota <= 1.40) quotaBands['1.21-1.40'].push(v);
      else if (v.quota <= 1.60) quotaBands['1.41-1.60'].push(v);
      else if (v.quota <= 1.80) quotaBands['1.61-1.80'].push(v);
      else if (v.quota <= 2.00) quotaBands['1.81-2.00'].push(v);
      else if (v.quota <= 2.20) quotaBands['2.01-2.20'].push(v);
      else if (v.quota <= 2.50) quotaBands['2.21-2.50'].push(v);
      else if (v.quota <= 3.00) quotaBands['2.51-3.00'].push(v);
      else if (v.quota <= 3.50) quotaBands['3.01-3.50'].push(v);
      else if (v.quota <= 4.00) quotaBands['3.51-4.00'].push(v);
      else if (v.quota <= 5.00) quotaBands['4.01-5.00'].push(v);
      else quotaBands['5.00+'].push(v);
    }
    // Helper: classifica quota in band
    const getQuotaBand = (q) => {
      if (q === null || q === undefined) return 'N/D';
      if (q <= 1.20) return '1.01-1.20';
      if (q <= 1.40) return '1.21-1.40';
      if (q <= 1.60) return '1.41-1.60';
      if (q <= 1.80) return '1.61-1.80';
      if (q <= 2.00) return '1.81-2.00';
      if (q <= 2.20) return '2.01-2.20';
      if (q <= 2.50) return '2.21-2.50';
      if (q <= 3.00) return '2.51-3.00';
      if (q <= 3.50) return '3.01-3.50';
      if (q <= 4.00) return '3.51-4.00';
      if (q <= 5.00) return '4.01-5.00';
      return '5.00+';
    };

    // Breakdown quota esteso con ROI
    const breakdown_quota = {};
    for (const [band, items] of Object.entries(quotaBands)) {
      if (items.length === 0) continue;
      const base = hitRate(items);
      let totalProfit = 0;
      const hitQuotas = [];
      const missQuotas = [];
      for (const v of items) {
        if (v.hit && v.quota != null) { totalProfit += (v.quota - 1); hitQuotas.push(v.quota); }
        else if (!v.hit) { totalProfit -= 1; if (v.quota != null) missQuotas.push(v.quota); }
      }
      breakdown_quota[band] = {
        ...base,
        roi: items.length > 0 ? Math.round((totalProfit / items.length) * 1000) / 10 : null,
        profit: Math.round(totalProfit * 100) / 100,
        avg_quota: items.filter(v => v.quota != null).length > 0
          ? Math.round(items.filter(v => v.quota != null).reduce((s, v) => s + v.quota, 0) / items.filter(v => v.quota != null).length * 100) / 100
          : null
      };
    }

    // Stats globali quote
    const quotaVerified = verified.filter(v => v.quota != null);
    const quotaHits = quotaVerified.filter(v => v.hit);
    const quotaMisses = quotaVerified.filter(v => !v.hit);
    let roiGlobale = 0;
    for (const v of quotaVerified) {
      roiGlobale += v.hit ? (v.quota - 1) : -1;
    }
    const quota_stats = {
      total_con_quota: quotaVerified.length,
      total_senza_quota: verified.length - quotaVerified.length,
      avg_quota_tutti: quotaVerified.length > 0 ? Math.round(quotaVerified.reduce((s, v) => s + v.quota, 0) / quotaVerified.length * 100) / 100 : null,
      avg_quota_azzeccati: quotaHits.length > 0 ? Math.round(quotaHits.reduce((s, v) => s + v.quota, 0) / quotaHits.length * 100) / 100 : null,
      avg_quota_sbagliati: quotaMisses.length > 0 ? Math.round(quotaMisses.reduce((s, v) => s + v.quota, 0) / quotaMisses.length * 100) / 100 : null,
      roi_globale: quotaVerified.length > 0 ? Math.round((roiGlobale / quotaVerified.length) * 1000) / 10 : null,
      profit_globale: Math.round(roiGlobale * 100) / 100,
    };

    // Incrocio quota × mercato
    const crossQM = {};
    for (const v of verified) {
      const band = getQuotaBand(v.quota);
      const key = `${band}|||${v.tipo}`;
      if (!crossQM[key]) crossQM[key] = [];
      crossQM[key].push(v);
    }
    const cross_quota_mercato = {};
    for (const [key, items] of Object.entries(crossQM)) {
      const [band, tipo] = key.split('|||');
      if (!cross_quota_mercato[band]) cross_quota_mercato[band] = {};
      cross_quota_mercato[band][tipo] = hitRate(items);
    }

    // Serie temporale giornaliera
    const byDate = {};
    for (const v of verified) {
      if (!byDate[v.date]) byDate[v.date] = [];
      byDate[v.date].push(v);
    }
    const serie_temporale = Object.entries(byDate)
      .map(([date, items]) => {
        const withQuota = items.filter(v => v.quota != null);
        let dayProfit = 0;
        for (const v of withQuota) {
          dayProfit += v.hit ? (v.quota - 1) : -1;
        }
        // Quota media giornaliera
        const avgQuota = withQuota.length > 0
          ? Math.round(withQuota.reduce((s, v) => s + v.quota, 0) / withQuota.length * 100) / 100
          : null;
        // Edge medio giornaliero: probabilita_stimata - (1/quota)
        const withEdge = items.filter(v => v.quota != null && v.probabilita_stimata != null);
        const avgEdge = withEdge.length > 0
          ? Math.round(withEdge.reduce((s, v) => s + (v.probabilita_stimata / 100 - 1 / v.quota), 0) / withEdge.length * 1000) / 10
          : null;
        return {
          date,
          ...hitRate(items),
          profit: Math.round(dayProfit * 100) / 100,
          avg_quota: avgQuota,
          edge: avgEdge,
        };
      })
      .sort((a, b) => a.date.localeCompare(b.date));

    // Incrocio mercato × campionato
    const breakdown_mercato_campionato = {};
    for (const v of verified) {
      const key = `${v.tipo}|||${v.league}`;
      if (!breakdown_mercato_campionato[key]) breakdown_mercato_campionato[key] = [];
      breakdown_mercato_campionato[key].push(v);
    }
    const cross_mercato_campionato = {};
    for (const [key, items] of Object.entries(breakdown_mercato_campionato)) {
      const [tipo, lg] = key.split('|||');
      if (!cross_mercato_campionato[tipo]) cross_mercato_campionato[tipo] = {};
      cross_mercato_campionato[tipo][lg] = hitRate(items);
    }

    // Split Pronostici vs Alto Rendimento (da allVerified — non filtrato per sezione)
    const pronosticiItems = allVerified.filter(v => v.sezione === 'pronostici');
    const arItems = allVerified.filter(v => v.sezione === 'alto_rendimento');

    console.log(`✅ [TRACK-RECORD] ${verified.length} pronostici verificati (${pronosticiItems.length} pronostici + ${arItems.length} AR), hit rate globale: ${globale.hit_rate}%`);

    const result = {
      success: true,
      periodo: { from, to },
      filtri: { league: league || null, market: market || null, min_confidence: min_confidence || null, min_quota: min_quota || null, max_quota: max_quota || null, sezione: sezione || null },
      globale,
      split_sezione: {
        pronostici: sectionStats(pronosticiItems),
        alto_rendimento: sectionStats(arItems)
      },
      breakdown_mercato,
      breakdown_source,
      breakdown_campionato,
      breakdown_confidence,
      breakdown_stelle,
      breakdown_quota,
      quota_stats,
      cross_quota_mercato,
      cross_mercato_campionato,
      serie_temporale
    };

    // Salva in cache
    trackRecordCache.set(cacheKey, { data: result, ts: Date.now() });

    return res.json(result);
  } catch (error) {
    console.error('❌ [TRACK-RECORD] Errore:', error);
    return res.status(500).json({ error: 'Errore nel calcolo track record', details: error.message });
  }
});

// 💰 ENDPOINT: Statistiche Bankroll (ROI, Yield, P/L)
router.get('/bankroll-stats', async (req, res) => {
  console.log('💰 [BANKROLL] Richiesta statistiche');

  try {
    const today = new Date().toISOString().split('T')[0];
    const dateFilter = { $lt: today };
    if (req.query.from) dateFilter.$gte = req.query.from;
    const docs = await req.db.collection('daily_predictions_unified')
      .find({ date: dateFilter })
      .project({ date: 1, league: 1, pronostici: 1 })
      .toArray();

    // Filtro quota: low (<=2.50), high (>2.50), omesso = tutti
    const quotaFilter = req.query.quotaFilter; // 'low' | 'high' | undefined

    // Raccogli tutti i pronostici con profit_loss
    const allBets = [];
    for (const doc of docs) {
      for (const p of (doc.pronostici || [])) {
        if (p.profit_loss === undefined || p.profit_loss === null) continue;
        if (p.stake === undefined || p.stake === 0) continue;
        // Applica filtro quota se richiesto (DC soglia 2.00, altri 2.50)
        const sogliaAR_bk = (p.tipo === 'DOPPIA_CHANCE') ? 2.00 : 2.51;
        if (quotaFilter === 'low' && p.quota && p.quota >= sogliaAR_bk) continue;
        if (quotaFilter === 'high' && (!p.quota || p.quota < sogliaAR_bk)) continue;
        allBets.push({
          date: doc.date,
          league: doc.league,
          tipo: p.tipo,
          pronostico: p.pronostico,
          quota: p.quota,
          probabilita_stimata: p.probabilita_stimata,
          stake: p.stake,
          edge: p.edge,
          esito: p.esito,
          profit_loss: p.profit_loss,
        });
      }
    }

    if (allBets.length === 0) {
      return res.json({ success: true, message: 'Nessun dato disponibile. Esegui prima il backfill.', data: null });
    }

    // Helper
    const calcStats = (bets) => {
      const total = bets.length;
      const won = bets.filter(b => b.esito === true).length;
      const totalStake = bets.reduce((s, b) => s + (b.stake || 0), 0);
      const totalPL = bets.reduce((s, b) => s + (b.profit_loss || 0), 0);
      return {
        count: total,
        won,
        lost: total - won,
        hr: total > 0 ? Math.round((won / total) * 1000) / 10 : 0,
        total_stake: Math.round(totalStake * 100) / 100,
        profit_loss: Math.round(totalPL * 100) / 100,
        yield: totalStake > 0 ? Math.round((totalPL / totalStake) * 1000) / 10 : 0,
      };
    };

    // Globale
    const globale = calcStats(allBets);

    // Per mercato
    const mercati = {};
    for (const b of allBets) {
      let m = b.tipo;
      if (m === 'GOL') {
        const p = (b.pronostico || '').toLowerCase();
        if (p.includes('over') || p.includes('under')) m = 'OVER_UNDER';
        else if (p.startsWith('mg ')) m = 'MULTI_GOAL';
        else m = 'GG_NG';
      }
      if (!mercati[m]) mercati[m] = [];
      mercati[m].push(b);
    }
    const byMercato = {};
    for (const [m, bets] of Object.entries(mercati)) {
      byMercato[m] = calcStats(bets);
    }

    // Per stake level
    const stakeLevels = { '0': [], '1': [], '2': [], '3': [], '4-5': [], '6+': [] };
    for (const b of allBets) {
      const s = b.stake || 0;
      if (s === 0) stakeLevels['0'].push(b);
      else if (s === 1) stakeLevels['1'].push(b);
      else if (s === 2) stakeLevels['2'].push(b);
      else if (s === 3) stakeLevels['3'].push(b);
      else if (s <= 5) stakeLevels['4-5'].push(b);
      else stakeLevels['6+'].push(b);
    }
    const byStake = {};
    for (const [level, bets] of Object.entries(stakeLevels)) {
      if (bets.length > 0) byStake[level] = calcStats(bets);
    }

    // Per campionato
    const campionati = {};
    for (const b of allBets) {
      const lg = b.league || 'Altro';
      if (!campionati[lg]) campionati[lg] = [];
      campionati[lg].push(b);
    }
    const byLeague = {};
    for (const [lg, bets] of Object.entries(campionati)) {
      byLeague[lg] = calcStats(bets);
    }

    // Temporale: ultimi 7/30/90 giorni
    const now = new Date();
    const daysAgo = (n) => {
      const d = new Date(now);
      d.setDate(d.getDate() - n);
      return d.toISOString().split('T')[0];
    };
    const last7 = calcStats(allBets.filter(b => b.date >= daysAgo(7)));
    const last30 = calcStats(allBets.filter(b => b.date >= daysAgo(30)));
    const last90 = calcStats(allBets.filter(b => b.date >= daysAgo(90)));

    // Per mese
    const mesi = {};
    for (const b of allBets) {
      const ym = b.date ? b.date.substring(0, 7) : '????-??';
      if (!mesi[ym]) mesi[ym] = [];
      mesi[ym].push(b);
    }
    const byMonth = {};
    for (const [ym, bets] of Object.entries(mesi)) {
      byMonth[ym] = calcStats(bets);
    }

    // Profitto cumulativo per data (per chart)
    const dateMap = {};
    for (const b of allBets) {
      if (!dateMap[b.date]) dateMap[b.date] = 0;
      dateMap[b.date] += b.profit_loss || 0;
    }
    const sortedDates = Object.keys(dateMap).sort();
    let cumulative = 0;
    const cumulativeChart = sortedDates.map(d => {
      cumulative += dateMap[d];
      return { date: d, pl: Math.round(cumulative * 100) / 100 };
    });

    console.log(`✅ [BANKROLL] ${allBets.length} pronostici, P/L: ${globale.profit_loss}, Yield: ${globale.yield}%`);

    return res.json({
      success: true,
      data: {
        globale,
        byMercato,
        byStake,
        byLeague,
        temporal: { last7, last30, last90, byMonth },
        cumulativeChart,
      }
    });
  } catch (error) {
    console.error('❌ [BANKROLL] Errore:', error);
    return res.status(500).json({ error: 'Errore nel calcolo bankroll stats', details: error.message });
  }
});

// 🎲 ENDPOINT: Pronostici Sistema C (Monte Carlo)
router.get('/daily-predictions-engine-c', async (req, res) => {
  const { date } = req.query;
  if (!date) return res.status(400).json({ error: 'Parametro date mancante' });

  console.log('🎲 [ENGINE C] Richiesta per:', date);

  try {
    const [predictions, resultsMap] = await Promise.all([
      req.db.collection('daily_predictions_engine_c')
        .find({ date }, { projection: { _id: 0 } })
        .toArray(),
      getFinishedResults(req.db, date)
    ]);

    for (const pred of predictions) {
      const realScore = resultsMap[`${pred.home}|||${pred.away}|||${pred.date}`] || null;
      pred.real_score = realScore;

      if (realScore) {
        const parsed = parseScore(realScore);
        pred.real_sign = parsed ? parsed.sign : null;

        if (pred.pronostici && pred.pronostici.length > 0) {
          for (const p of pred.pronostici) {
            p.hit = checkPronostico(p.pronostico, p.tipo, parsed);
          }
          pred.hit = pred.pronostici.some(p => p.hit === true);
        } else {
          pred.hit = null;
        }
      } else {
        pred.real_sign = null;
        pred.hit = null;
      }
    }

    predictions.sort((a, b) => (a.match_time || '').localeCompare(b.match_time || ''));

    // Backward compatibility: assicura campi Kelly sempre presenti
    for (const pred of predictions) {
      if (pred.pronostici) {
        for (const p of pred.pronostici) {
          p.probabilita_stimata = p.probabilita_stimata ?? null;
          p.stake = p.stake ?? 0;
          p.edge = p.edge ?? 0;
          p.prob_mercato = p.prob_mercato ?? null;
          p.prob_modello = p.prob_modello ?? null;
          p.has_odds = p.has_odds ?? true;
        }
      }
    }

    const allP = predictions.flatMap(p => (p.pronostici || []).filter(pr => pr.tipo !== 'RISULTATO_ESATTO'));
    const verifiedP = allP.filter(p => p.hit === true || p.hit === false);
    const hitsP = allP.filter(p => p.hit === true).length;

    const matchesWithResult = predictions.filter(p => p.real_score);
    const matchHits = matchesWithResult.filter(p => p.hit === true).length;

    console.log(`✅ [ENGINE C] ${predictions.length} partite, ${allP.length} pronostici (no RE), ${hitsP}/${verifiedP.length} azzeccati`);

    return res.json({
      success: true, date, predictions, count: predictions.length,
      stats: {
        total: allP.length,
        total_matches: predictions.length,
        finished: verifiedP.length,
        hits: hitsP,
        misses: verifiedP.length - hitsP,
        pending: allP.length - verifiedP.length,
        hit_rate: verifiedP.length > 0 ? Math.round((hitsP / verifiedP.length) * 1000) / 10 : null,
        matches_finished: matchesWithResult.length,
        matches_hits: matchHits,
        matches_hit_rate: matchesWithResult.length > 0 ? Math.round((matchHits / matchesWithResult.length) * 1000) / 10 : null
      }
    });
  } catch (error) {
    console.error('❌ [ENGINE C] Errore:', error);
    return res.status(500).json({ error: 'Errore nel recupero pronostici Engine C', details: error.message });
  }
});

// 🎼 ENDPOINT: Pronostici Unified (Mixture of Experts)
router.get('/daily-predictions-unified', async (req, res) => {
  const { date } = req.query;
  if (!date) return res.status(400).json({ error: 'Parametro date mancante' });

  console.log('🎼 [UNIFIED] Richiesta per:', date);

  try {
    const [predictions, resultsMap] = await Promise.all([
      req.db.collection('daily_predictions_unified')
        .find({ date }, { projection: { _id: 0 } })
        .toArray(),
      getFinishedResults(req.db, date)
    ]);

    for (const pred of predictions) {
      const realScore = resultsMap[`${pred.home}|||${pred.away}|||${pred.date}`] || null;
      pred.real_score = realScore;

      if (realScore) {
        const parsed = parseScore(realScore);
        pred.real_sign = parsed ? parsed.sign : null;

        if (pred.pronostici && pred.pronostici.length > 0) {
          for (const p of pred.pronostici) {
            p.hit = checkPronostico(p.pronostico, p.tipo, parsed);
          }
          pred.hit = pred.pronostici.some(p => p.hit === true);
        } else {
          pred.hit = null;
        }
      } else {
        pred.real_sign = null;
        pred.hit = null;
      }
    }

    predictions.sort((a, b) => (a.match_time || '').localeCompare(b.match_time || ''));

    // Assicura campi sempre presenti
    for (const pred of predictions) {
      if (pred.pronostici) {
        for (const p of pred.pronostici) {
          p.probabilita_stimata = p.probabilita_stimata ?? null;
          p.stake = p.stake ?? 0;
          p.edge = p.edge ?? 0;
          p.prob_mercato = p.prob_mercato ?? null;
          p.prob_modello = p.prob_modello ?? null;
          p.has_odds = p.has_odds ?? true;
          p.source = p.source ?? null;
          p.routing_rule = p.routing_rule ?? null;
        }
      }
    }

    const allP = predictions.flatMap(p => p.pronostici || []);
    const verifiedP = allP.filter(p => p.hit === true || p.hit === false);
    const hitsP = allP.filter(p => p.hit === true).length;

    const matchesWithResult = predictions.filter(p => p.real_score);
    const matchHits = matchesWithResult.filter(p => p.hit === true).length;

    // Stats per source (da quale sistema viene ogni pronostico)
    const bySource = {};
    for (const p of allP) {
      const src = p.source || 'unknown';
      if (!bySource[src]) bySource[src] = { total: 0, hits: 0, verified: 0 };
      bySource[src].total++;
      if (p.hit === true || p.hit === false) {
        bySource[src].verified++;
        if (p.hit === true) bySource[src].hits++;
      }
    }

    console.log(`✅ [UNIFIED] ${predictions.length} partite, ${allP.length} pronostici, ${hitsP}/${verifiedP.length} azzeccati`);

    return res.json({
      success: true, date, predictions, count: predictions.length,
      stats: {
        total: allP.length,
        total_matches: predictions.length,
        finished: verifiedP.length,
        hits: hitsP,
        misses: verifiedP.length - hitsP,
        pending: allP.length - verifiedP.length,
        hit_rate: verifiedP.length > 0 ? Math.round((hitsP / verifiedP.length) * 1000) / 10 : null,
        matches_finished: matchesWithResult.length,
        matches_hits: matchHits,
        matches_hit_rate: matchesWithResult.length > 0 ? Math.round((matchHits / matchesWithResult.length) * 1000) / 10 : null,
        by_source: bySource
      }
    });
  } catch (error) {
    console.error('❌ [UNIFIED] Errore:', error);
    return res.status(500).json({ error: 'Errore nel recupero pronostici unified', details: error.message });
  }
});

// --- CACHE: Totale storico P/L (TTL 10 minuti) ---
const totalePLCache = new Map();
const TOTALE_CACHE_TTL = 10 * 60 * 1000;

// ── GET /predictions/monthly-pl?date=2026-03-20 ──
// P/L mensile accumulato dal primo del mese fino alla data selezionata
router.get('/monthly-pl', async (req, res) => {
  try {
    const { date } = req.query;
    const selectedDate = date || new Date().toISOString().slice(0, 10);
    const monthStart = selectedDate.slice(0, 8) + '01';

    // Cross-match solo ultimi 3 giorni (le partite più vecchie hanno già esito nel DB dallo step 29)
    const recentStart = new Date(selectedDate + 'T00:00:00Z');
    recentStart.setDate(recentStart.getDate() - 2);
    const recentFrom = recentStart.toISOString().slice(0, 10);

    const projFull = { pronostici: 1, live_score: 1, live_status: 1, match_time: 1, date: 1, home: 1, away: 1 };

    const [dayDocs, monthDocs, resultsMap] = await Promise.all([
      req.db.collection('daily_predictions_unified')
        .find({ date: selectedDate }, { projection: projFull }).toArray(),
      req.db.collection('daily_predictions_unified')
        .find({ date: { $gte: monthStart, $lte: selectedDate } }, { projection: projFull }).toArray(),
      getFinishedResults(req.db, { from: recentFrom, to: selectedDate }),
    ]);

    function calcSezioni(docs) {
      const sez = {
        tutti: { pl: 0, bets: 0, wins: 0, staked: 0 },
        pronostici: { pl: 0, bets: 0, wins: 0, staked: 0 },
        elite: { pl: 0, bets: 0, wins: 0, staked: 0 },
        alto_rendimento: { pl: 0, bets: 0, wins: 0, staked: 0 },
      };
      for (const doc of docs) {
        const realScore = resultsMap[`${doc.home}|||${doc.away}|||${doc.date}`] || null;
        const score = realScore || doc.live_score || null;
        const matchOver = realScore ? true : (() => {
          if (doc.live_status === 'Finished') return true;
          if (doc.date && doc.match_time) {
            const kickoff = new Date(`${doc.date}T${doc.match_time}:00`);
            const elapsed = (Date.now() - kickoff.getTime()) / (1000 * 60);
            if (elapsed > 130) return true;
          }
          return false;
        })();

        for (const p of (doc.pronostici || [])) {
          let esito = p.esito;
          if ((esito === undefined || esito === null) && score && matchOver) {
            const parsed = parseScore(score);
            if (parsed) {
              esito = checkPronostico(p.pronostico, p.tipo, parsed);
            }
          }
          if (esito === undefined || esito === null || esito === 'void') continue;
          const quota = p.quota || 0;
          const stake = p.stake || 1;
          if (quota <= 1) continue;
          if (p.pronostico === 'NO BET') continue;

          const profit = esito === true ? (quota - 1) * stake : -stake;
          const isHit = esito === true;

          const soglia = p.tipo === 'DOPPIA_CHANCE' ? 2.00 : 2.51;
          const isAltoRendimento = p.tipo === 'RISULTATO_ESATTO' || quota >= soglia;
          const isPronostici = !isAltoRendimento && p.tipo !== 'RISULTATO_ESATTO';

          sez.tutti.bets++; sez.tutti.staked += stake; sez.tutti.pl += profit;
          if (isHit) sez.tutti.wins++;

          if (isPronostici) {
            sez.pronostici.bets++; sez.pronostici.staked += stake; sez.pronostici.pl += profit;
            if (isHit) sez.pronostici.wins++;
          }

          if (p.elite) {
            sez.elite.bets++; sez.elite.staked += stake; sez.elite.pl += profit;
            if (isHit) sez.elite.wins++;
          }

          if (isAltoRendimento) {
            sez.alto_rendimento.bets++; sez.alto_rendimento.staked += stake; sez.alto_rendimento.pl += profit;
            if (isHit) sez.alto_rendimento.wins++;
          }
        }
      }
      for (const s of Object.values(sez)) {
        s.pl = Math.round(s.pl * 100) / 100;
        s.staked = Math.round(s.staked * 100) / 100;
        s.hr = s.bets > 0 ? Math.round((s.wins / s.bets) * 1000) / 10 : 0;
        s.roi = s.staked > 0 ? Math.round((s.pl / s.staked) * 1000) / 10 : 0;
      }
      return sez;
    }

    // Calcolo totale storico con cache (10 min TTL)
    const totaleCacheKey = selectedDate;
    const cachedTotale = totalePLCache.get(totaleCacheKey);
    let totale;
    if (cachedTotale && (Date.now() - cachedTotale.ts) < TOTALE_CACHE_TTL) {
      totale = cachedTotale.data;
    } else {
      // Aggregation MongoDB: calcola P/L direttamente nel DB senza scaricare tutti i documenti
      const totaleAgg = await req.db.collection('daily_predictions_unified').aggregate([
        { $match: { date: { $lte: selectedDate } } },
        { $unwind: '$pronostici' },
        { $match: {
          'pronostici.esito': { $in: [true, false] },
          'pronostici.quota': { $gt: 1 },
          'pronostici.pronostico': { $ne: 'NO BET' }
        }},
        { $project: {
          esito: '$pronostici.esito',
          quota: '$pronostici.quota',
          stake: { $ifNull: ['$pronostici.stake', 1] },
          tipo: '$pronostici.tipo',
          elite: { $ifNull: ['$pronostici.elite', false] },
        }},
        { $group: {
          _id: null,
          tutti_bets: { $sum: 1 },
          tutti_wins: { $sum: { $cond: ['$esito', 1, 0] } },
          tutti_staked: { $sum: '$stake' },
          tutti_pl: { $sum: { $cond: ['$esito', { $multiply: [{ $subtract: ['$quota', 1] }, '$stake'] }, { $multiply: ['$stake', -1] }] } },
          // Pronostici (quota bassa): DC < 2.00, altri < 2.51, no RE
          pron_bets: { $sum: { $cond: [{ $and: [{ $ne: ['$tipo', 'RISULTATO_ESATTO'] }, { $lt: ['$quota', { $cond: [{ $eq: ['$tipo', 'DOPPIA_CHANCE'] }, 2.00, 2.51] }] }] }, 1, 0] } },
          pron_wins: { $sum: { $cond: [{ $and: ['$esito', { $ne: ['$tipo', 'RISULTATO_ESATTO'] }, { $lt: ['$quota', { $cond: [{ $eq: ['$tipo', 'DOPPIA_CHANCE'] }, 2.00, 2.51] }] }] }, 1, 0] } },
          pron_staked: { $sum: { $cond: [{ $and: [{ $ne: ['$tipo', 'RISULTATO_ESATTO'] }, { $lt: ['$quota', { $cond: [{ $eq: ['$tipo', 'DOPPIA_CHANCE'] }, 2.00, 2.51] }] }] }, '$stake', 0] } },
          pron_pl: { $sum: { $cond: [{ $and: [{ $ne: ['$tipo', 'RISULTATO_ESATTO'] }, { $lt: ['$quota', { $cond: [{ $eq: ['$tipo', 'DOPPIA_CHANCE'] }, 2.00, 2.51] }] }] }, { $cond: ['$esito', { $multiply: [{ $subtract: ['$quota', 1] }, '$stake'] }, { $multiply: ['$stake', -1] }] }, 0] } },
          // Elite
          elite_bets: { $sum: { $cond: ['$elite', 1, 0] } },
          elite_wins: { $sum: { $cond: [{ $and: ['$esito', '$elite'] }, 1, 0] } },
          elite_staked: { $sum: { $cond: ['$elite', '$stake', 0] } },
          elite_pl: { $sum: { $cond: ['$elite', { $cond: ['$esito', { $multiply: [{ $subtract: ['$quota', 1] }, '$stake'] }, { $multiply: ['$stake', -1] }] }, 0] } },
          // Alto rendimento (RE o quota alta)
          ar_bets: { $sum: { $cond: [{ $or: [{ $eq: ['$tipo', 'RISULTATO_ESATTO'] }, { $gte: ['$quota', { $cond: [{ $eq: ['$tipo', 'DOPPIA_CHANCE'] }, 2.00, 2.51] }] }] }, 1, 0] } },
          ar_wins: { $sum: { $cond: [{ $and: ['$esito', { $or: [{ $eq: ['$tipo', 'RISULTATO_ESATTO'] }, { $gte: ['$quota', { $cond: [{ $eq: ['$tipo', 'DOPPIA_CHANCE'] }, 2.00, 2.51] }] }] }] }, 1, 0] } },
          ar_staked: { $sum: { $cond: [{ $or: [{ $eq: ['$tipo', 'RISULTATO_ESATTO'] }, { $gte: ['$quota', { $cond: [{ $eq: ['$tipo', 'DOPPIA_CHANCE'] }, 2.00, 2.51] }] }] }, '$stake', 0] } },
          ar_pl: { $sum: { $cond: [{ $or: [{ $eq: ['$tipo', 'RISULTATO_ESATTO'] }, { $gte: ['$quota', { $cond: [{ $eq: ['$tipo', 'DOPPIA_CHANCE'] }, 2.00, 2.51] }] }] }, { $cond: ['$esito', { $multiply: [{ $subtract: ['$quota', 1] }, '$stake'] }, { $multiply: ['$stake', -1] }] }, 0] } },
        }}
      ]).toArray();

      const r = totaleAgg[0] || {};
      const fmt = (pl, bets, wins, staked) => ({
        pl: Math.round((pl || 0) * 100) / 100,
        bets: bets || 0,
        wins: wins || 0,
        staked: Math.round((staked || 0) * 100) / 100,
        hr: bets > 0 ? Math.round((wins / bets) * 1000) / 10 : 0,
        roi: staked > 0 ? Math.round((pl / staked) * 1000) / 10 : 0,
      });
      totale = {
        tutti: fmt(r.tutti_pl, r.tutti_bets, r.tutti_wins, r.tutti_staked),
        pronostici: fmt(r.pron_pl, r.pron_bets, r.pron_wins, r.pron_staked),
        elite: fmt(r.elite_pl, r.elite_bets, r.elite_wins, r.elite_staked),
        alto_rendimento: fmt(r.ar_pl, r.ar_bets, r.ar_wins, r.ar_staked),
      };
      totalePLCache.set(totaleCacheKey, { ts: Date.now(), data: totale });
    }

    const giorno = calcSezioni(dayDocs);
    const sezioni = calcSezioni(monthDocs);

    res.json({ success: true, from: monthStart, to: selectedDate, giorno, sezioni, totale });
  } catch (error) {
    res.status(500).json({ error: 'Errore monthly-pl', details: error.message });
  }
});

module.exports = { router, parseScore, checkPronostico, getQuotaForPronostico, getFinishedResults };