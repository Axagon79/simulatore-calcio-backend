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

// --- HELPER: Recupera risultati reali da h2h_by_round ---
async function getFinishedResults(db) {
  try {
    const docs = await db.collection('h2h_by_round')
      .find({}, {
        projection: {
          'matches.home': 1, 'matches.away': 1,
          'matches.real_score': 1, 'matches.status': 1,
          'matches.date_obj': 1
        }
      })
      .toArray();

    const resultsMap = {};
    for (const doc of docs) {
      if (!doc.matches) continue;
      for (const m of doc.matches) {
        if (m.status === 'Finished' && m.real_score && m.date_obj) {
          const dateStr = new Date(m.date_obj).toISOString().split('T')[0];
          resultsMap[`${m.home}|||${m.away}|||${dateStr}`] = m.real_score;
        }
      }
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
      getFinishedResults(req.db)
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

    const finished = predictions.filter(p => p.real_score !== null);
    const hits = finished.filter(p => p.hit === true).length;

    console.log(`✅ [PREDICTIONS] ${predictions.length} pronostici, ${hits}/${finished.length} azzeccati`);

    return res.json({
      success: true, date, predictions, count: predictions.length,
      stats: {
        total: predictions.length,
        finished: finished.length,
        hits,
        misses: finished.filter(p => p.hit === false).length,
        pending: predictions.length - finished.length,
        hit_rate: finished.length > 0 ? Math.round((hits / finished.length) * 1000) / 10 : null
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
      getFinishedResults(req.db)
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
      getFinishedResults(req.db)
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

    const finished = predictions.filter(p => p.real_score !== null);
    const hits = finished.filter(p => p.hit === true).length;

    console.log(`✅ [PREDICTIONS SANDBOX] ${predictions.length} pronostici, ${hits}/${finished.length} azzeccati`);

    return res.json({
      success: true, date, predictions, count: predictions.length,
      stats: {
        total: predictions.length,
        finished: finished.length,
        hits,
        misses: finished.filter(p => p.hit === false).length,
        pending: predictions.length - finished.length,
        hit_rate: finished.length > 0 ? Math.round((hits / finished.length) * 1000) / 10 : null
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
      getFinishedResults(req.db)
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
  const { from, to, league, market, min_confidence } = req.query;

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
      getFinishedResults(req.db)
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

        verified.push({
          date: pred.date,
          league: pred.league || 'N/A',
          tipo: tipoEffettivo,
          pronostico: p.pronostico,
          confidence: p.confidence || 0,
          stars: p.stars || 0,
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
      filtri: { league: league || null, market: market || null, min_confidence: min_confidence || null },
      globale,
      breakdown_mercato,
      breakdown_campionato,
      breakdown_confidence,
      breakdown_stelle,
      cross_mercato_campionato,
      serie_temporale
    });
  } catch (error) {
    console.error('❌ [TRACK-RECORD] Errore:', error);
    return res.status(500).json({ error: 'Errore nel calcolo track record', details: error.message });
  }
});

module.exports = router;