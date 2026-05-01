const express = require('express');
const admin = require('../config/firebaseAdmin');
const router = express.Router();

const firestore = admin.firestore();

router.get('/balance', async (req, res) => {
  try {
    const userId = req.userId;
    const userRef = firestore.collection('users').doc(userId);
    const snap = await userRef.get();

    if (!snap.exists) {
      const initial = {
        credits: 0,
        shields: 0,
        subscription: null,
        subscription_expires_at: null,
        created_at: admin.firestore.FieldValue.serverTimestamp()
      };
      await userRef.set(initial, { merge: true });
      return res.json({
        credits: 0,
        shields: 0,
        subscription: null,
        subscription_expires_at: null
      });
    }

    const data = snap.data();
    const patch = {};
    if (data.credits === undefined) patch.credits = 0;
    if (data.shields === undefined) patch.shields = 0;
    if (data.subscription === undefined) patch.subscription = null;
    if (data.subscription_expires_at === undefined) patch.subscription_expires_at = null;
    if (Object.keys(patch).length > 0) {
      await userRef.set(patch, { merge: true });
    }

    res.json({
      credits: data.credits ?? 0,
      shields: data.shields ?? 0,
      subscription: data.subscription ?? null,
      subscription_expires_at: data.subscription_expires_at ?? null
    });
  } catch (err) {
    console.error('Errore GET /wallet/balance:', err);
    res.status(500).json({ error: 'Errore nel recupero saldo' });
  }
});

router.get('/transactions', async (req, res) => {
  try {
    const userId = req.userId;
    const limit = parseInt(req.query.limit) || 50;
    const skip = parseInt(req.query.skip) || 0;

    const txCol = firestore.collection('wallet_transactions');

    const allSnap = await txCol
      .where('user_id', '==', userId)
      .orderBy('created_at', 'desc')
      .limit(skip + limit)
      .get();

    const transactions = allSnap.docs.slice(skip).map(d => ({ id: d.id, ...d.data() }));

    const now = new Date();
    const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);

    const monthSnap = await txCol
      .where('user_id', '==', userId)
      .where('created_at', '>=', startOfMonth)
      .get();

    const summary = {
      credits_acquired: 0,
      credits_spent: 0,
      credits_refunded: 0,
      shields_current: 0,
      total_eur: 0,
    };

    for (const doc of monthSnap.docs) {
      const t = doc.data();
      if (t.credits_delta > 0 && t.type !== 'rimborso') {
        summary.credits_acquired += t.credits_delta;
      }
      if (t.credits_delta < 0) {
        summary.credits_spent += Math.abs(t.credits_delta);
      }
      if (t.type === 'rimborso' && t.credits_delta > 0) {
        summary.credits_refunded += t.credits_delta;
      }
      summary.total_eur += t.amount_eur || 0;
    }

    const userSnap = await firestore.collection('users').doc(userId).get();
    summary.shields_current = userSnap.exists ? (userSnap.data().shields ?? 0) : 0;

    res.json({ transactions, summary });
  } catch (err) {
    console.error('Errore GET /wallet/transactions:', err);
    res.status(500).json({ error: 'Errore nel recupero transazioni' });
  }
});

router.get('/shielded-matches', async (req, res) => {
  try {
    const userId = req.userId;

    const snap = await firestore.collection('wallet_transactions')
      .where('user_id', '==', userId)
      .where('type', '==', 'shield_attivato')
      .get();

    const matchKeys = snap.docs
      .map(d => d.data().metadata?.match_key)
      .filter(Boolean);

    res.json({ match_keys: Array.from(new Set(matchKeys)) });
  } catch (err) {
    console.error('Errore GET /wallet/shielded-matches:', err);
    res.status(500).json({ error: 'Errore nel recupero shield attivi' });
  }
});

router.get('/purchases', async (req, res) => {
  try {
    const userId = req.userId;
    const date = req.query.date;

    let q = firestore.collection('wallet_transactions')
      .where('user_id', '==', userId)
      .where('type', '==', 'pronostico_sbloccato');

    if (date) q = q.where('metadata.date', '==', date);

    const snap = await q.get();

    res.json({
      purchases: snap.docs.map(d => {
        const data = d.data();
        return {
          match_key: data.metadata?.match_key,
          purchased_at: data.created_at,
        };
      }),
    });
  } catch (err) {
    console.error('Errore GET /wallet/purchases:', err);
    res.status(500).json({ error: 'Errore nel recupero acquisti' });
  }
});

router.post('/transaction', async (req, res) => {
  try {
    const userId = req.userId;
    const { type, credits_delta, shields_delta, amount_eur, description, metadata } = req.body;

    if (!type) {
      return res.status(400).json({ error: 'Campo type obbligatorio' });
    }

    const validTypes = [
      'acquisto_pacchetto',
      'pronostico_sbloccato',
      'rimborso',
      'shield_attivato',
      'shield_restituito',
      'crediti_bonus_abbonamento'
    ];

    if (!validTypes.includes(type)) {
      return res.status(400).json({ error: `Tipo non valido. Valori: ${validTypes.join(', ')}` });
    }

    const userRef = firestore.collection('users').doc(userId);
    const txRef = firestore.collection('wallet_transactions').doc();

    const balanceAfter = await firestore.runTransaction(async (tx) => {
      const snap = await tx.get(userRef);
      const current = snap.exists ? snap.data() : {};
      const currentCredits = current.credits ?? 0;
      const currentShields = current.shields ?? 0;

      if (type === 'pronostico_sbloccato' && credits_delta < 0) {
        if (currentCredits + credits_delta < 0) {
          throw new Error('CREDITI_INSUFFICIENTI');
        }
      }

      const newCredits = currentCredits + (credits_delta || 0);
      const newShields = currentShields + (shields_delta || 0);

      const userPatch = {};
      if (credits_delta) userPatch.credits = newCredits;
      if (shields_delta) userPatch.shields = newShields;

      if (Object.keys(userPatch).length > 0) {
        tx.set(userRef, userPatch, { merge: true });
      }

      const transaction = {
        user_id: userId,
        type,
        description: description || type,
        credits_delta: credits_delta || 0,
        shields_delta: shields_delta || 0,
        amount_eur: amount_eur || 0,
        balance_after: { credits: newCredits, shields: newShields },
        metadata: metadata || {},
        created_at: admin.firestore.FieldValue.serverTimestamp()
      };
      tx.set(txRef, transaction);

      return { credits: newCredits, shields: newShields };
    });

    const txSnap = await txRef.get();
    res.json({
      success: true,
      transaction: { id: txRef.id, ...txSnap.data() },
      balance: balanceAfter
    });
  } catch (err) {
    if (err.message === 'CREDITI_INSUFFICIENTI') {
      return res.status(400).json({ error: 'Crediti insufficienti' });
    }
    console.error('Errore POST /wallet/transaction:', err);
    res.status(500).json({ error: 'Errore nel salvataggio transazione' });
  }
});

module.exports = router;
