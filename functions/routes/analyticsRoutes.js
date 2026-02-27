const express = require('express');
const router = express.Router();

// GET /analytics/reports — lista report mensili (mese + performance)
router.get('/reports', async (req, res) => {
  try {
    const reports = await req.db.collection('analisi_mensili')
      .find({}, { projection: { mese: 1, created_at: 1, performance: 1 } })
      .sort({ mese: -1 })
      .toArray();
    res.json({ success: true, reports });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

// GET /analytics/report/:mese — dettaglio completo di un mese (es. 2026-02)
router.get('/report/:mese', async (req, res) => {
  try {
    const doc = await req.db.collection('analisi_mensili').findOne(
      { mese: req.params.mese },
      { projection: { _id: 0 } }
    );
    if (!doc) return res.json({ success: false, message: 'Report non trovato' });
    res.json({ success: true, report: doc });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

module.exports = router;
