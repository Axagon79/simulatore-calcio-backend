const express = require('express');
const admin = require('../config/firebaseAdmin');
const router = express.Router();

const firestore = admin.firestore();

router.get('/status', async (req, res) => {
  try {
    const userId = req.userId;

    const userDoc = await firestore.collection('users').doc(userId).get();
    const data = userDoc.exists ? userDoc.data() : null;

    res.json({
      onboarding_completed: !!(data?.onboarding_completed)
    });
  } catch (err) {
    console.error('Errore GET /onboarding/status:', err);
    res.status(500).json({ error: 'Errore server' });
  }
});

router.post('/complete', async (req, res) => {
  try {
    const userId = req.userId;

    await firestore.collection('users').doc(userId).set(
      {
        onboarding_completed: true,
        onboarding_completed_at: admin.firestore.FieldValue.serverTimestamp()
      },
      { merge: true }
    );

    res.json({ success: true });
  } catch (err) {
    console.error('Errore POST /onboarding/complete:', err);
    res.status(500).json({ error: 'Errore server' });
  }
});

module.exports = router;
