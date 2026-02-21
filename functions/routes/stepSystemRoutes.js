const express = require('express');
const router = express.Router();
const { ObjectId } = require('mongodb');

// ============================================
// ALGORITMO STEP SYSTEM (da ELEVATORBET.ods)
// ============================================

/**
 * Calcola il prossimo step: quota consigliata, importo, range
 * Formula chiave: daily_target = (budget + target_gain - current_balance) / remaining_steps
 *                 suggested_odds = 1 + daily_target / max_bet
 */
function calculateNextStep(session) {
  const {
    budget, target_multiplier, current_balance,
    total_steps, current_step,
    daily_exposure_pct, single_bet_pct, odds_range
  } = session;

  const target_gain = target_multiplier * budget;
  const final_target = budget + target_gain;
  const remaining_target = final_target - current_balance;
  const remaining_steps = total_steps - current_step;

  // Sessione completata?
  if (remaining_steps <= 0 || remaining_target <= 0) {
    return { completed: true, reason: remaining_target <= 0 ? 'target_reached' : 'steps_exhausted' };
  }

  // Budget esaurito?
  if (current_balance <= 0) {
    return { completed: true, reason: 'budget_depleted' };
  }

  const daily_target = remaining_target / remaining_steps;
  const max_daily = daily_exposure_pct * current_balance;
  const max_single = single_bet_pct * current_balance;
  const max_bet = Math.min(max_daily, max_single);

  // Quota consigliata = 1 + daily_target / max_bet
  let suggested_odds = 1 + (daily_target / max_bet);

  // Clamp al range quote se enforce attivo
  const [min_odds, max_odds] = odds_range;
  if (session.enforce_odds_range) {
    suggested_odds = Math.max(min_odds, Math.min(max_odds, suggested_odds));
  }

  // Range quota (±15% della parte decimale)
  const decimal_part = suggested_odds - 1;
  const delta = decimal_part * 0.15;
  const odds_low = Math.max(min_odds, +(suggested_odds - delta).toFixed(2));
  const odds_high = Math.min(max_odds, +(suggested_odds + delta).toFixed(2));

  // Importo consigliato range
  const amount_at_high_odds = odds_high > 1 ? daily_target / (odds_high - 1) : max_bet;
  const amount_at_low_odds = odds_low > 1 ? daily_target / (odds_low - 1) : max_bet;
  const amount_min = Math.max(1, Math.min(amount_at_high_odds, max_bet));
  const amount_max = Math.min(amount_at_low_odds, max_bet);
  const suggested_amount = Math.min(max_bet, +(daily_target / (suggested_odds - 1)).toFixed(2));

  return {
    step_number: current_step + 1,
    remaining_steps,
    remaining_target: +remaining_target.toFixed(2),
    daily_target: +daily_target.toFixed(2),
    max_bet: +max_bet.toFixed(2),
    max_daily_exposure: +max_daily.toFixed(2),
    suggested_odds: +suggested_odds.toFixed(2),
    odds_range_suggested: [odds_low, odds_high],
    suggested_amount: +Math.max(1, suggested_amount).toFixed(2),
    amount_range: [+Math.max(1, amount_min).toFixed(2), +Math.max(1, amount_max).toFixed(2)],
    potential_win: +(suggested_amount * (suggested_odds - 1)).toFixed(2),
    progress_pct: +((current_balance - budget) / target_gain * 100).toFixed(1)
  };
}

// ============================================
// 1. GET /sessions — Lista sessioni utente
// ============================================
router.get('/sessions', async (req, res) => {
  try {
    const db = req.db;
    const userId = req.userId;
    const sessions = await db.collection('step_system_sessions')
      .find({ user_id: userId })
      .sort({ created_at: -1 })
      .project({
        steps: 0 // Escludi array steps nella lista
      })
      .toArray();

    res.json({ sessions });
  } catch (err) {
    console.error('GET /sessions error:', err);
    res.status(500).json({ error: 'Errore server' });
  }
});

// ============================================
// 2. POST /sessions — Crea nuova sessione
// ============================================
router.post('/sessions', async (req, res) => {
  try {
    const db = req.db;
    const userId = req.userId;

    const {
      name = 'Sessione',
      budget = 200,
      target_multiplier = 2,
      total_steps = 15,
      odds_range = [1.25, 2.50],
      daily_exposure_pct = 0.20,
      single_bet_pct = 0.15,
      enforce_odds_range = false
    } = req.body;

    // Validazione
    if (budget < 1) return res.status(400).json({ error: 'Budget deve essere >= 1€' });
    if (target_multiplier <= 0) return res.status(400).json({ error: 'Moltiplicatore deve essere > 0' });
    if (total_steps < 1 || total_steps > 365) return res.status(400).json({ error: 'Step deve essere tra 1 e 365' });
    if (daily_exposure_pct < 0.01 || daily_exposure_pct > 1) return res.status(400).json({ error: 'Esposizione giornaliera tra 1% e 100%' });
    if (single_bet_pct < 0.01 || single_bet_pct > 1) return res.status(400).json({ error: 'Limite singola tra 1% e 100%' });

    const session = {
      user_id: userId,
      name: String(name).trim() || 'Sessione',
      status: 'active',
      budget: +budget,
      target_multiplier: +target_multiplier,
      total_steps: +total_steps,
      odds_range: [+(odds_range[0] || 1.25), +(odds_range[1] || 2.50)],
      daily_exposure_pct: +daily_exposure_pct,
      single_bet_pct: +single_bet_pct,
      enforce_odds_range: !!enforce_odds_range,
      current_balance: +budget,
      current_step: 0,
      steps_won: 0,
      steps_lost: 0,
      steps: [],
      created_at: new Date(),
      updated_at: new Date()
    };

    const result = await db.collection('step_system_sessions').insertOne(session);
    session._id = result.insertedId;

    // Calcola subito il primo step
    const nextStep = calculateNextStep(session);

    res.json({ session, nextStep });
  } catch (err) {
    console.error('POST /sessions error:', err);
    res.status(500).json({ error: 'Errore server' });
  }
});

// ============================================
// 3. GET /sessions/:id — Dettaglio sessione
// ============================================
router.get('/sessions/:id', async (req, res) => {
  try {
    const db = req.db;
    const userId = req.userId;
    const sessionId = req.params.id;

    if (!ObjectId.isValid(sessionId)) {
      return res.status(400).json({ error: 'ID sessione non valido' });
    }

    const session = await db.collection('step_system_sessions')
      .findOne({ _id: new ObjectId(sessionId), user_id: userId });

    if (!session) {
      return res.status(404).json({ error: 'Sessione non trovata' });
    }

    res.json({ session });
  } catch (err) {
    console.error('GET /sessions/:id error:', err);
    res.status(500).json({ error: 'Errore server' });
  }
});

// ============================================
// 4. GET /sessions/:id/calculate — Calcola prossimo step
// ============================================
router.get('/sessions/:id/calculate', async (req, res) => {
  try {
    const db = req.db;
    const userId = req.userId;
    const sessionId = req.params.id;

    if (!ObjectId.isValid(sessionId)) {
      return res.status(400).json({ error: 'ID sessione non valido' });
    }

    const session = await db.collection('step_system_sessions')
      .findOne({ _id: new ObjectId(sessionId), user_id: userId });

    if (!session) {
      return res.status(404).json({ error: 'Sessione non trovata' });
    }

    if (session.status !== 'active') {
      return res.status(400).json({ error: 'Sessione non attiva' });
    }

    const nextStep = calculateNextStep(session);
    res.json({ nextStep, session_status: session.status });
  } catch (err) {
    console.error('GET /calculate error:', err);
    res.status(500).json({ error: 'Errore server' });
  }
});

// ============================================
// 5. POST /sessions/:id/steps — Registra un nuovo step
// ============================================
router.post('/sessions/:id/steps', async (req, res) => {
  try {
    const db = req.db;
    const userId = req.userId;
    const sessionId = req.params.id;

    if (!ObjectId.isValid(sessionId)) {
      return res.status(400).json({ error: 'ID sessione non valido' });
    }

    const session = await db.collection('step_system_sessions')
      .findOne({ _id: new ObjectId(sessionId), user_id: userId });

    if (!session) return res.status(404).json({ error: 'Sessione non trovata' });
    if (session.status !== 'active') return res.status(400).json({ error: 'Sessione non attiva' });

    const { odds_entered, amount_bet, outcome, match_info } = req.body;

    if (!odds_entered || odds_entered <= 1) {
      return res.status(400).json({ error: 'Quota deve essere > 1' });
    }
    if (!amount_bet || amount_bet <= 0) {
      return res.status(400).json({ error: 'Importo deve essere > 0' });
    }

    // Calcola suggerimenti per salvare nello step
    const calc = calculateNextStep(session);
    if (calc.completed) {
      return res.status(400).json({ error: 'Sessione già completata' });
    }

    // Calcola P/L
    let actual_pl = 0;
    if (outcome === 'won') {
      actual_pl = +(amount_bet * (odds_entered - 1)).toFixed(2);
    } else if (outcome === 'lost') {
      actual_pl = +(-amount_bet).toFixed(2);
    }

    const new_balance = +(session.current_balance + actual_pl).toFixed(2);

    const step = {
      step_number: session.current_step + 1,
      date: new Date(),
      match_info: match_info || null,
      odds_entered: +odds_entered,
      suggested_odds: calc.suggested_odds,
      suggested_amount: calc.suggested_amount,
      amount_bet: +amount_bet,
      potential_win: +(amount_bet * (odds_entered - 1)).toFixed(2),
      outcome: outcome || null,  // null = pending
      actual_pl,
      balance_after: new_balance,
      created_at: new Date()
    };

    // Aggiorna sessione
    const update = {
      $push: { steps: step },
      $set: {
        updated_at: new Date()
      }
    };

    // Se c'è un esito, aggiorna contatori
    if (outcome) {
      update.$set.current_balance = new_balance;
      update.$set.current_step = session.current_step + 1;
      update.$inc = {};
      if (outcome === 'won') update.$inc.steps_won = 1;
      if (outcome === 'lost') update.$inc.steps_lost = 1;

      // Check completamento
      const target_gain = session.target_multiplier * session.budget;
      if (new_balance >= session.budget + target_gain) {
        update.$set.status = 'completed';
      } else if (new_balance <= 0) {
        update.$set.status = 'completed';
      }
    }

    await db.collection('step_system_sessions').updateOne(
      { _id: new ObjectId(sessionId) },
      update
    );

    // Ritorna sessione aggiornata + prossimo step
    const updated = await db.collection('step_system_sessions')
      .findOne({ _id: new ObjectId(sessionId) });

    let nextStep = null;
    if (updated.status === 'active') {
      nextStep = calculateNextStep(updated);
    }

    res.json({ step, session: updated, nextStep });
  } catch (err) {
    console.error('POST /steps error:', err);
    res.status(500).json({ error: 'Errore server' });
  }
});

// ============================================
// 6. PUT /sessions/:id/steps/:stepNum/result — Aggiorna esito
// ============================================
router.put('/sessions/:id/steps/:stepNum/result', async (req, res) => {
  try {
    const db = req.db;
    const userId = req.userId;
    const sessionId = req.params.id;
    const stepNum = parseInt(req.params.stepNum);

    if (!ObjectId.isValid(sessionId)) {
      return res.status(400).json({ error: 'ID sessione non valido' });
    }

    const { outcome } = req.body;
    if (!['won', 'lost'].includes(outcome)) {
      return res.status(400).json({ error: 'Esito deve essere won o lost' });
    }

    const session = await db.collection('step_system_sessions')
      .findOne({ _id: new ObjectId(sessionId), user_id: userId });

    if (!session) return res.status(404).json({ error: 'Sessione non trovata' });

    // Trova lo step
    const stepIdx = session.steps.findIndex(s => s.step_number === stepNum);
    if (stepIdx === -1) return res.status(404).json({ error: 'Step non trovato' });

    const step = session.steps[stepIdx];
    if (step.outcome) return res.status(400).json({ error: 'Step ha già un esito' });

    // Calcola P/L
    let actual_pl = 0;
    if (outcome === 'won') {
      actual_pl = +(step.amount_bet * (step.odds_entered - 1)).toFixed(2);
    } else {
      actual_pl = +(-step.amount_bet).toFixed(2);
    }

    const new_balance = +(session.current_balance + actual_pl).toFixed(2);

    // Aggiorna lo step nell'array
    const setFields = {
      [`steps.${stepIdx}.outcome`]: outcome,
      [`steps.${stepIdx}.actual_pl`]: actual_pl,
      [`steps.${stepIdx}.balance_after`]: new_balance,
      current_balance: new_balance,
      current_step: session.current_step + 1,
      updated_at: new Date()
    };

    // Check completamento
    const target_gain = session.target_multiplier * session.budget;
    if (new_balance >= session.budget + target_gain) {
      setFields.status = 'completed';
    } else if (new_balance <= 0) {
      setFields.status = 'completed';
    }

    const incFields = {};
    if (outcome === 'won') incFields.steps_won = 1;
    if (outcome === 'lost') incFields.steps_lost = 1;

    await db.collection('step_system_sessions').updateOne(
      { _id: new ObjectId(sessionId) },
      { $set: setFields, $inc: incFields }
    );

    const updated = await db.collection('step_system_sessions')
      .findOne({ _id: new ObjectId(sessionId) });

    let nextStep = null;
    if (updated.status === 'active') {
      nextStep = calculateNextStep(updated);
    }

    res.json({ session: updated, nextStep });
  } catch (err) {
    console.error('PUT /steps/:stepNum/result error:', err);
    res.status(500).json({ error: 'Errore server' });
  }
});

// ============================================
// 7. POST /sessions/:id/close — Chiudi sessione
// ============================================
router.post('/sessions/:id/close', async (req, res) => {
  try {
    const db = req.db;
    const userId = req.userId;
    const sessionId = req.params.id;

    if (!ObjectId.isValid(sessionId)) {
      return res.status(400).json({ error: 'ID sessione non valido' });
    }

    const session = await db.collection('step_system_sessions')
      .findOne({ _id: new ObjectId(sessionId), user_id: userId });

    if (!session) return res.status(404).json({ error: 'Sessione non trovata' });
    if (session.status !== 'active') return res.status(400).json({ error: 'Sessione già chiusa' });

    const { reason } = req.body; // 'completed' o 'abandoned'

    await db.collection('step_system_sessions').updateOne(
      { _id: new ObjectId(sessionId) },
      {
        $set: {
          status: reason === 'completed' ? 'completed' : 'abandoned',
          updated_at: new Date()
        }
      }
    );

    res.json({ success: true, status: reason === 'completed' ? 'completed' : 'abandoned' });
  } catch (err) {
    console.error('POST /close error:', err);
    res.status(500).json({ error: 'Errore server' });
  }
});

// ============================================
// 8. DELETE /sessions/:id — Elimina sessione
// ============================================
router.delete('/sessions/:id', async (req, res) => {
  try {
    const db = req.db;
    const userId = req.userId;
    const sessionId = req.params.id;

    if (!ObjectId.isValid(sessionId)) {
      return res.status(400).json({ error: 'ID sessione non valido' });
    }

    const result = await db.collection('step_system_sessions')
      .deleteOne({ _id: new ObjectId(sessionId), user_id: userId });

    if (result.deletedCount === 0) {
      return res.status(404).json({ error: 'Sessione non trovata' });
    }

    res.json({ success: true });
  } catch (err) {
    console.error('DELETE /sessions/:id error:', err);
    res.status(500).json({ error: 'Errore server' });
  }
});

module.exports = router;
