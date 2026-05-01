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

// ============================================================
// POST /wallet/process-shield-refunds
// ============================================================
// Job batch chiamato dalla pipeline notturna locale (process_shield_refunds.py).
// Trova tutte le transazioni `shield_attivato` non ancora processate, verifica
// se la partita e' finita e se almeno uno dei pronostici sbloccati e' sbagliato.
// Se sì, accredita all'utente esattamente i crediti che aveva pagato per
// `pronostico_sbloccato` (1 se abbonato, 3 se gratuito — letto da metadata.cost
// della transazione di sblocco originale).
//
// Schema transazione `shield_attivato`:
//   { user_id, type: 'shield_attivato', metadata: { match_key } }
//
// Schema transazione `pronostico_sbloccato` correlata (stesso user + match_key):
//   { user_id, type: 'pronostico_sbloccato', metadata: { match_key, cost, snapshot_at_purchase } }
//
// Idempotenza: marca la transazione `shield_attivato` con `refund_processed: true`
// dopo l'elaborazione (sia in caso di refund che in caso di pronostico centrato).
// Nessun rimborso doppio possibile.
//
// Output JSON: { processed, credits_refunded, errors[] }

function _parseScore(realScore) {
  if (!realScore) return null;
  const parts = String(realScore).trim().split(/[:\-]/);
  if (parts.length !== 2) return null;
  const h = parseInt(parts[0]);
  const a = parseInt(parts[1]);
  if (isNaN(h) || isNaN(a)) return null;
  const sign = h > a ? '1' : (h === a ? 'X' : '2');
  const btts = h > 0 && a > 0;
  return { home: h, away: a, total: h + a, sign, btts };
}

function _checkPronostico(pronostico, tipo, parsed) {
  if (!parsed || !pronostico) return null;
  const p = String(pronostico).trim();
  const t = (tipo || '').toUpperCase();
  if (t === 'SEGNO' || t === '1X2 ESITO FINALE' || t === '1X2') {
    return parsed.sign === p;
  }
  if (t === 'DOPPIA_CHANCE' || t === 'DOPPIA CHANCE') {
    if (p === '1X') return parsed.sign === '1' || parsed.sign === 'X';
    if (p === 'X2') return parsed.sign === 'X' || parsed.sign === '2';
    if (p === '12') return parsed.sign === '1' || parsed.sign === '2';
    return null;
  }
  if (t === 'GOL' || t === 'GOAL' || t === 'GOAL/NOGOAL' || t === 'U/O') {
    const m = p.match(/^(Over|Under)\s+([\d.]+)/i);
    if (m) {
      const thr = parseFloat(m[2]);
      return m[1].toLowerCase() === 'over' ? parsed.total > thr : parsed.total < thr;
    }
    const lp = p.toLowerCase();
    if (lp === 'goal' || lp === 'si') return parsed.btts;
    if (lp === 'nogoal' || lp === 'no') return !parsed.btts;
    const mg = p.match(/^MG\s+(\d+)-(\d+)/i);
    if (mg) return parsed.total >= parseInt(mg[1]) && parsed.total <= parseInt(mg[2]);
  }
  if (t === 'RISULTATO_ESATTO' || t === 'RISULTATO ESATTO') {
    return `${parsed.home}:${parsed.away}` === p.replace('-', ':');
  }
  return null;
}

router.post('/process-shield-refunds', async (req, res) => {
  const summary = { processed: 0, credits_refunded: 0, errors: [] };

  try {
    // 1. Trova tutte le transazioni shield_attivato non processate
    const shieldsSnap = await firestore.collection('wallet_transactions')
      .where('type', '==', 'shield_attivato')
      .where('refund_processed', '==', null)  // null = non processata (Firestore inequality su missing field non funziona, vedi nota sotto)
      .get()
      .catch(async () => {
        // Fallback: se l'index non c'è, prendi tutte e filtra in memoria
        const all = await firestore.collection('wallet_transactions')
          .where('type', '==', 'shield_attivato')
          .get();
        return { docs: all.docs.filter(d => !d.data().refund_processed) };
      });

    const shields = shieldsSnap.docs || [];
    console.log(`[process-shield-refunds] ${shields.length} shield non processati`);

    for (const shieldDoc of shields) {
      const shield = shieldDoc.data();
      const userId = shield.user_id;
      const matchKey = shield.metadata?.match_key;

      if (!userId || !matchKey) {
        summary.errors.push(`shield ${shieldDoc.id}: mancano user_id o match_key`);
        continue;
      }

      try {
        // 2. Trova la transazione pronostico_sbloccato corrispondente
        const sbloccoSnap = await firestore.collection('wallet_transactions')
          .where('user_id', '==', userId)
          .where('type', '==', 'pronostico_sbloccato')
          .where('metadata.match_key', '==', matchKey)
          .limit(1)
          .get();

        if (sbloccoSnap.empty) {
          // Nessuno sblocco trovato — non possiamo determinare il costo.
          // Marca la shield come processata (non rimborsabile) per non riprovarci ogni notte.
          await shieldDoc.ref.update({
            refund_processed: true,
            refund_skipped_reason: 'no_pronostico_sbloccato_trovato'
          });
          summary.errors.push(`shield ${shieldDoc.id}: pronostico_sbloccato non trovato per ${matchKey}`);
          continue;
        }

        const sbloccoDoc = sbloccoSnap.docs[0];
        const sblocco = sbloccoDoc.data();
        const cost = sblocco.metadata?.cost ?? Math.abs(sblocco.credits_delta ?? 0);
        const snapshot = sblocco.metadata?.snapshot_at_purchase || [];

        // 3. Estrai (home, away, date) da match_key formato "YYYY-MM-DD_Home_Away"
        const mkMatch = matchKey.match(/^(\d{4}-\d{2}-\d{2})_(.+?)_(.+)$/);
        if (!mkMatch) {
          await shieldDoc.ref.update({
            refund_processed: true,
            refund_skipped_reason: 'match_key_formato_non_valido'
          });
          summary.errors.push(`shield ${shieldDoc.id}: match_key formato invalido "${matchKey}"`);
          continue;
        }
        const [, matchDate, home, away] = mkMatch;

        // 4. Cerca real_score in h2h_by_round (MongoDB)
        const startOfDay = new Date(matchDate + 'T00:00:00.000Z');
        const endOfDay = new Date(matchDate + 'T23:59:59.999Z');

        const pipeline = [
          { $unwind: '$matches' },
          { $match: {
            'matches.date_obj': { $gte: startOfDay, $lte: endOfDay },
            'matches.home': home,
            'matches.away': away
          }},
          { $project: {
            _id: 0,
            real_score: '$matches.real_score',
            live_score: '$matches.live_score',
            live_status: '$matches.live_status'
          }},
          { $limit: 1 }
        ];

        const docs = await req.db.collection('h2h_by_round').aggregate(pipeline).toArray();
        let matchData = docs[0];

        // Fallback coppe (formato date diverso)
        if (!matchData) {
          const [y, m, d] = matchDate.split('-');
          const cupDatePrefix = `${d}-${m}-${y}`;
          for (const cupColl of ['matches_champions_league', 'matches_europa_league']) {
            const cm = await req.db.collection(cupColl).findOne({
              match_date: { $regex: `^${cupDatePrefix}` },
              home_team: home,
              away_team: away
            });
            if (cm) {
              matchData = {
                real_score: cm.real_score || cm.live_score,
                live_status: cm.live_status
              };
              break;
            }
          }
        }

        if (!matchData) {
          // Partita non trovata — può essere appena giocata e non ancora popolata. Ritenta domani.
          summary.errors.push(`shield ${shieldDoc.id}: partita non trovata in DB (${home} vs ${away} ${matchDate})`);
          continue;
        }

        // 5. Verifica che la partita sia FINITA
        const realScore = matchData.real_score || (matchData.live_status === 'Finished' ? matchData.live_score : null);
        if (!realScore) {
          // Non finita ancora — ritenta domani
          continue;
        }

        const parsed = _parseScore(realScore);
        if (!parsed) {
          summary.errors.push(`shield ${shieldDoc.id}: score "${realScore}" non parsabile`);
          continue;
        }

        // 6. Verifica esito pronostici dello snapshot
        let almeno_uno_sbagliato = false;
        for (const p of snapshot) {
          const hit = _checkPronostico(p.pronostico, p.tipo, parsed);
          if (hit === false) {
            almeno_uno_sbagliato = true;
            break;
          }
        }

        // 7. Decisione: se almeno uno è sbagliato, rimborso
        if (almeno_uno_sbagliato && cost > 0) {
          // Crea transazione shield_restituito + aggiorna balance utente (atomica)
          const userRef = firestore.collection('users').doc(userId);
          const refundRef = firestore.collection('wallet_transactions').doc();

          await firestore.runTransaction(async (tx) => {
            const userSnap = await tx.get(userRef);
            const current = userSnap.exists ? userSnap.data() : {};
            const newCredits = (current.credits ?? 0) + cost;

            tx.set(userRef, { credits: newCredits }, { merge: true });
            tx.set(refundRef, {
              user_id: userId,
              type: 'shield_restituito',
              description: `Rimborso shield: ${home} vs ${away}`,
              credits_delta: cost,
              shields_delta: 0,
              amount_eur: 0,
              balance_after: { credits: newCredits, shields: current.shields ?? 0 },
              metadata: {
                match_key: matchKey,
                refund_for_shield_tx: shieldDoc.id,
                refund_for_sblocco_tx: sbloccoDoc.id
              },
              created_at: admin.firestore.FieldValue.serverTimestamp()
            });
            tx.update(shieldDoc.ref, {
              refund_processed: true,
              refund_amount: cost,
              refund_tx_id: refundRef.id
            });
          });

          summary.credits_refunded += cost;
          console.log(`[refund] +${cost} crediti a ${userId} per ${matchKey}`);
        } else {
          // Pronostico CENTRATO o costo 0 — niente rimborso, ma marca come processata
          await shieldDoc.ref.update({
            refund_processed: true,
            refund_amount: 0,
            refund_skipped_reason: almeno_uno_sbagliato ? 'cost_zero' : 'pronostico_centrato'
          });
        }

        summary.processed++;
      } catch (innerErr) {
        console.error(`[process-shield-refunds] errore su ${shieldDoc.id}:`, innerErr);
        summary.errors.push(`shield ${shieldDoc.id}: ${innerErr.message}`);
      }
    }

    res.json({ success: true, ...summary });
  } catch (err) {
    console.error('Errore POST /wallet/process-shield-refunds:', err);
    res.status(500).json({ error: 'Errore nel processing refund', ...summary });
  }
});

module.exports = router;
