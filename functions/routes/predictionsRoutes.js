// 📁 functions/routes/predictionsRoutes.js
const express = require('express');
const router = express.Router();

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
    return null;
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
        .find({ date }, { projection: { _id: 0 } })
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

    // Conteggio per singolo pronostico (non per partita)
    const allP = predictions.flatMap(p => p.pronostici || []);
    const verifiedP = allP.filter(p => p.hit === true || p.hit === false);
    const hitsP = allP.filter(p => p.hit === true).length;

    console.log(`✅ [PREDICTIONS] ${predictions.length} partite, ${allP.length} pronostici, ${hitsP}/${verifiedP.length} azzeccati`);

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
  const { from, to, league, market, min_confidence, min_quota, max_quota } = req.query;

  if (!from || !to) {
    return res.status(400).json({ error: 'Parametri from e to (YYYY-MM-DD) obbligatori' });
  }

  console.log(`📊 [TRACK-RECORD] Richiesta: ${from} → ${to} | league=${league || 'tutte'} | market=${market || 'tutti'}`);

  try {
    // 1. Query predictions nel range di date
    const query = { date: { $gte: from, $lte: to } };
    if (league) query.league = { $regex: new RegExp(league, 'i') };

    const [predictions, resultsMap] = await Promise.all([
      req.db.collection('daily_predictions').find(query, { projection: { _id: 0 } }).toArray(),
      getFinishedResults(req.db, { from, to })
    ]);

    // 2. Cross-match con risultati reali + verifica hit/miss
    const verified = [];
    for (const pred of predictions) {
      const realScore = resultsMap[`${pred.home}|||${pred.away}|||${pred.date}`] || null;
      if (!realScore) continue; // solo partite finite

      const parsed = parseScore(realScore);
      if (!parsed || !pred.pronostici || pred.pronostici.length === 0) continue;

      for (const p of pred.pronostici) {
        const hit = checkPronostico(p.pronostico, p.tipo, parsed);
        if (hit === null) continue; // pronostico non verificabile

        // Splitta tipo "GOL" in OVER_UNDER vs GG_NG
        let tipoEffettivo = p.tipo;
        if (p.tipo === 'GOL') {
          const pLower = (p.pronostico || '').toLowerCase();
          if (pLower.startsWith('over') || pLower.startsWith('under')) {
            tipoEffettivo = 'OVER_UNDER';
          } else if (pLower === 'goal' || pLower === 'nogoal') {
            tipoEffettivo = 'GG_NG';
          }
        }

        // Filtro per mercato se specificato
        if (market && tipoEffettivo.toUpperCase() !== market.toUpperCase()) continue;
        // Filtro per confidence minima
        if (min_confidence && (p.confidence || 0) < parseFloat(min_confidence)) continue;

        // Risolvi quota: prima dal pronostico, poi dal parent odds (GOL)
        let quota = p.quota != null ? parseFloat(p.quota) : null;
        if (quota === null || isNaN(quota)) {
          quota = getQuotaForPronostico(p.pronostico, p.tipo, pred.odds);
        }
        // Filtro per range quota
        if (min_quota && (quota === null || quota < parseFloat(min_quota))) continue;
        if (max_quota && (quota === null || quota > parseFloat(max_quota))) continue;

        verified.push({
          date: pred.date,
          league: pred.league || 'N/A',
          tipo: tipoEffettivo,
          pronostico: p.pronostico,
          confidence: p.confidence || 0,
          stars: p.stars || 0,
          quota,
          hit
        });
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
      .map(([date, items]) => ({ date, ...hitRate(items) }))
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

    console.log(`✅ [TRACK-RECORD] ${verified.length} pronostici verificati, hit rate globale: ${globale.hit_rate}%`);

    return res.json({
      success: true,
      periodo: { from, to },
      filtri: { league: league || null, market: market || null, min_confidence: min_confidence || null, min_quota: min_quota || null, max_quota: max_quota || null },
      globale,
      breakdown_mercato,
      breakdown_campionato,
      breakdown_confidence,
      breakdown_stelle,
      breakdown_quota,
      quota_stats,
      cross_quota_mercato,
      cross_mercato_campionato,
      serie_temporale
    });
  } catch (error) {
    console.error('❌ [TRACK-RECORD] Errore:', error);
    return res.status(500).json({ error: 'Errore nel calcolo track record', details: error.message });
  }
});

module.exports = router;