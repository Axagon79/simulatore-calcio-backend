const express = require('express');
const router = express.Router();

// GET /wallet/balance — Saldo crediti e shield
router.get('/balance', async (req, res) => {
  try {
    const db = req.db;
    const userId = req.user.uid;

    let userDoc = await db.collection('users').findOne({ firebaseUid: userId });

    // Se il documento non esiste, crealo con saldo 0
    if (!userDoc) {
      userDoc = {
        firebaseUid: userId,
        credits: 0,
        shields: 0,
        subscription: null,
        subscription_expires_at: null,
        created_at: new Date()
      };
      await db.collection('users').insertOne(userDoc);
    }

    // Se i campi non esistono, inizializzali
    if (userDoc.credits === undefined || userDoc.shields === undefined) {
      await db.collection('users').updateOne(
        { firebaseUid: userId },
        {
          $set: {
            credits: userDoc.credits ?? 0,
            shields: userDoc.shields ?? 0,
            subscription: userDoc.subscription ?? null,
            subscription_expires_at: userDoc.subscription_expires_at ?? null
          }
        }
      );
    }

    res.json({
      credits: userDoc.credits ?? 0,
      shields: userDoc.shields ?? 0,
      subscription: userDoc.subscription ?? null,
      subscription_expires_at: userDoc.subscription_expires_at ?? null
    });
  } catch (err) {
    console.error('Errore GET /wallet/balance:', err);
    res.status(500).json({ error: 'Errore nel recupero saldo' });
  }
});

// GET /wallet/transactions — Storico transazioni
router.get('/transactions', async (req, res) => {
  try {
    const db = req.db;
    const userId = req.user.uid;
    const limit = parseInt(req.query.limit) || 50;
    const skip = parseInt(req.query.skip) || 0;

    const transactions = await db.collection('wallet_transactions')
      .find({ user_id: userId })
      .sort({ created_at: -1 })
      .skip(skip)
      .limit(limit)
      .toArray();

    // Riepilogo mese corrente
    const now = new Date();
    const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);

    const monthTransactions = await db.collection('wallet_transactions')
      .find({
        user_id: userId,
        created_at: { $gte: startOfMonth }
      })
      .toArray();

    const summary = {
      credits_acquired: 0,
      credits_spent: 0,
      credits_refunded: 0,
      shields_current: 0,
      total_eur: 0,
    };

    for (const t of monthTransactions) {
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

    // Saldo shield attuale
    const userDoc = await db.collection('users').findOne({ firebaseUid: userId });
    summary.shields_current = userDoc?.shields ?? 0;

    res.json({ transactions, summary });
  } catch (err) {
    console.error('Errore GET /wallet/transactions:', err);
    res.status(500).json({ error: 'Errore nel recupero transazioni' });
  }
});

// GET /wallet/purchases — Acquisti pronostici per data
router.get('/purchases', async (req, res) => {
  try {
    const db = req.db;
    const userId = req.user.uid;
    const date = req.query.date;

    const filter = { user_id: userId, type: 'pronostico_sbloccato' };
    if (date) filter['metadata.date'] = date;

    const purchases = await db.collection('wallet_transactions')
      .find(filter)
      .project({ 'metadata.match_key': 1, created_at: 1 })
      .toArray();

    res.json({
      purchases: purchases.map(p => ({
        match_key: p.metadata?.match_key,
        purchased_at: p.created_at,
      })),
    });
  } catch (err) {
    console.error('Errore GET /wallet/purchases:', err);
    res.status(500).json({ error: 'Errore nel recupero acquisti' });
  }
});

// POST /wallet/transaction — Registra transazione (uso interno + acquisto pacchetti beta)
router.post('/transaction', async (req, res) => {
  try {
    const db = req.db;
    const userId = req.user.uid;
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

    // Controlla crediti sufficienti per sblocco pronostico
    if (type === 'pronostico_sbloccato' && credits_delta < 0) {
      const currentUser = await db.collection('users').findOne({ firebaseUid: userId });
      const currentCredits = currentUser?.credits ?? 0;
      if (currentCredits + credits_delta < 0) {
        return res.status(400).json({ error: 'Crediti insufficienti' });
      }
    }

    // Aggiorna saldo utente
    const updateFields = {};
    if (credits_delta) updateFields.credits = credits_delta;
    if (shields_delta) updateFields.shields = shields_delta;

    let userDoc;
    if (Object.keys(updateFields).length > 0) {
      userDoc = await db.collection('users').findOneAndUpdate(
        { firebaseUid: userId },
        { $inc: updateFields },
        { returnDocument: 'after', upsert: true }
      );
    } else {
      userDoc = await db.collection('users').findOne({ firebaseUid: userId });
    }

    const balanceAfter = {
      credits: userDoc?.credits ?? userDoc?.value?.credits ?? 0,
      shields: userDoc?.shields ?? userDoc?.value?.shields ?? 0,
    };

    // Salva transazione
    const transaction = {
      user_id: userId,
      type,
      description: description || type,
      credits_delta: credits_delta || 0,
      shields_delta: shields_delta || 0,
      amount_eur: amount_eur || 0,
      balance_after: balanceAfter,
      metadata: metadata || {},
      created_at: new Date()
    };

    await db.collection('wallet_transactions').insertOne(transaction);

    res.json({
      success: true,
      transaction,
      balance: balanceAfter
    });
  } catch (err) {
    console.error('Errore POST /wallet/transaction:', err);
    res.status(500).json({ error: 'Errore nel salvataggio transazione' });
  }
});

module.exports = router;
