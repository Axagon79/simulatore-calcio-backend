const express = require('express');
const router = express.Router();

// GET /onboarding/status — controlla se l'utente ha completato l'onboarding
router.get('/status', async (req, res) => {
  try {
    const db = req.db;
    const userId = req.userId;

    const userDoc = await db.collection('users').findOne(
      { firebaseUid: userId },
      { projection: { onboarding_completed: 1 } }
    );

    res.json({
      onboarding_completed: !!(userDoc?.onboarding_completed)
    });
  } catch (err) {
    console.error('Errore GET /onboarding/status:', err);
    res.status(500).json({ error: 'Errore server' });
  }
});

// POST /onboarding/complete — segna l'onboarding come completato
router.post('/complete', async (req, res) => {
  try {
    const db = req.db;
    const userId = req.userId;

    await db.collection('users').updateOne(
      { firebaseUid: userId },
      {
        $set: {
          onboarding_completed: true,
          onboarding_completed_at: new Date()
        }
      },
      { upsert: true }
    );

    res.json({ success: true });
  } catch (err) {
    console.error('Errore POST /onboarding/complete:', err);
    res.status(500).json({ error: 'Errore server' });
  }
});

module.exports = router;
