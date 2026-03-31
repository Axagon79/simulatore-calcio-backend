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

module.exports = router;
