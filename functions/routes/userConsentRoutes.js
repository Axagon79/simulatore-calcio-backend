const express = require('express');
const router = express.Router();

// Versione corrente dei termini — aggiornare quando cambiano T&C
const CURRENT_VERSION = '1.1';

// GET /user-consent/status — controlla se l'utente ha accettato i termini
router.get('/status', async (req, res) => {
  try {
    const db = req.db;
    const doc = await db.collection('user_consents').findOne(
      { userId: req.userId, accountStatus: { $ne: 'deleted' } },
      { projection: { _id: 0, termsAccepted: 1, privacyAccepted: 1, disclaimerAccepted: 1 } }
    );

    if (!doc) {
      return res.json({ accepted: false });
    }

    const accepted = !!(
      doc.termsAccepted?.version === CURRENT_VERSION &&
      doc.privacyAccepted &&
      doc.disclaimerAccepted
    );
    res.json({ accepted, consents: doc });
  } catch (err) {
    console.error('Errore GET /user-consent/status:', err);
    res.status(500).json({ error: 'Errore server' });
  }
});

// POST /user-consent/accept — salva accettazione dei 3 consensi
router.post('/accept', async (req, res) => {
  try {
    const db = req.db;
    const now = new Date().toISOString();
    const ip = req.headers['x-forwarded-for'] || req.socket?.remoteAddress || 'unknown';
    const version = CURRENT_VERSION;

    const update = {
      $set: {
        userId: req.userId,
        email: req.userEmail,
        termsAccepted: { version, acceptedAt: now, ip },
        privacyAccepted: { version, acceptedAt: now, ip },
        disclaimerAccepted: { version, acceptedAt: now, ip },
        accountStatus: 'active',
        updatedAt: now
      },
      $setOnInsert: {
        createdAt: now
      }
    };

    await db.collection('user_consents').updateOne(
      { userId: req.userId },
      update,
      { upsert: true }
    );

    res.json({ success: true });
  } catch (err) {
    console.error('Errore POST /user-consent/accept:', err);
    res.status(500).json({ error: 'Errore server' });
  }
});

// POST /user-consent/delete-account — soft delete
router.post('/delete-account', async (req, res) => {
  try {
    const db = req.db;
    const now = new Date().toISOString();

    const result = await db.collection('user_consents').updateOne(
      { userId: req.userId },
      {
        $set: {
          accountStatus: 'deleted',
          deletedAt: now,
          deletionRequestedAt: now,
          email: `deleted_user_${req.userId}`,
          updatedAt: now
        }
      }
    );

    if (result.matchedCount === 0) {
      return res.status(404).json({ error: 'Utente non trovato' });
    }

    res.json({ success: true });
  } catch (err) {
    console.error('Errore POST /user-consent/delete-account:', err);
    res.status(500).json({ error: 'Errore server' });
  }
});

module.exports = router;
