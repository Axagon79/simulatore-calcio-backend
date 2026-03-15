const express = require('express');
const router = express.Router();
const { ObjectId } = require('mongodb');
const authenticate = require('../middleware/auth');

// ============================================
// GET /bollette?date=YYYY-MM-DD
// Lista bollette per data (default: oggi). Pubblico.
// ============================================
router.get('/', async (req, res) => {
  try {
    const date = req.query.date || new Date().toISOString().split('T')[0];
    const bollette = await req.db.collection('bollette')
      .find({ date })
      .sort({ tipo: 1, quota_totale: 1 })
      .project({ reasoning: 0 }) // reasoning solo per debug
      .toArray();

    res.json({ success: true, date, bollette });
  } catch (err) {
    console.error('Errore GET /bollette:', err);
    res.status(500).json({ success: false, error: 'Errore server' });
  }
});

// ============================================
// PUT /bollette/:id/save — Toggle saved_by (auth)
// ============================================
router.put('/:id/save', authenticate, async (req, res) => {
  try {
    const bolId = new ObjectId(req.params.id);
    const uid = req.userId;

    const doc = await req.db.collection('bollette').findOne({ _id: bolId });
    if (!doc) return res.status(404).json({ success: false, error: 'Bolletta non trovata' });

    const isSaved = (doc.saved_by || []).includes(uid);

    if (isSaved) {
      await req.db.collection('bollette').updateOne(
        { _id: bolId },
        { $pull: { saved_by: uid } }
      );
    } else {
      await req.db.collection('bollette').updateOne(
        { _id: bolId },
        { $addToSet: { saved_by: uid } }
      );
    }

    res.json({ success: true, saved: !isSaved });
  } catch (err) {
    console.error('Errore PUT /bollette/:id/save:', err);
    res.status(500).json({ success: false, error: 'Errore server' });
  }
});

// ============================================
// GET /bollette/saved — Bollette salvate dall'utente (auth)
// ============================================
router.get('/saved', authenticate, async (req, res) => {
  try {
    const uid = req.userId;
    const bollette = await req.db.collection('bollette')
      .find({ saved_by: uid })
      .sort({ date: -1 })
      .project({ reasoning: 0 })
      .toArray();

    res.json({ success: true, bollette });
  } catch (err) {
    console.error('Errore GET /bollette/saved:', err);
    res.status(500).json({ success: false, error: 'Errore server' });
  }
});

module.exports = router;
