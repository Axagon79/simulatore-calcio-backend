const express = require('express');
const router = express.Router();

// GET /standings/:league — classifica completa (totale + casa + trasferta)
router.get('/:league', async (req, res) => {
  try {
    const doc = await req.db.collection('classifiche').findOne({ league: req.params.league });
    if (!doc) return res.json({ success: false, message: 'Classifica non trovata' });
    res.json({
      success: true,
      league: doc.league,
      country: doc.country,
      table: doc.table || [],
      table_home: doc.table_home || [],
      table_away: doc.table_away || [],
      last_updated: doc.last_updated
    });
  } catch (err) {
    res.status(500).json({ success: false, message: err.message });
  }
});

module.exports = router;
