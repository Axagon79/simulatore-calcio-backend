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
          'matches.real_score': 1, 'matches.status': 1
        }
      })
      .toArray();

    const resultsMap = {};
    for (const doc of docs) {
      if (!doc.matches) continue;
      for (const m of doc.matches) {
        if (m.status === 'Finished' && m.real_score) {
          resultsMap[`${m.home}|||${m.away}`] = m.real_score;
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
      const realScore = resultsMap[`${pred.home}|||${pred.away}`] || null;
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
      const realScore = resultsMap[`${bomb.home}|||${bomb.away}`] || null;
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

module.exports = router;