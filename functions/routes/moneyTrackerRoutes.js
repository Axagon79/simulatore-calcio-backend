const express = require('express');
const router = express.Router();
const { ObjectId } = require('mongodb');

// ============================================
// COSTANTI
// ============================================

const TIER_LIMITS = {
  free:    { monthly_bets: 15 },
  mini:    { monthly_bets: 50 },
  medium:  { monthly_bets: 150 },
  premium: { monthly_bets: 9999 },
};

const AGGRESSIVENESS_PCT = {
  conservative: 0.015,
  moderate: 0.03,
  aggressive: 0.05
};

const BET_TYPE_MULT = {
  singola: 1.0,
  doppia: 0.75,
  tripla: 0.55,
  quadrupla: 0.40,
  quintupla: 0.30
};

function getOddsBandMult(totalOdds) {
  if (totalOdds < 1.5) return 1.10;
  if (totalOdds < 2.5) return 1.00;
  if (totalOdds < 5) return 0.80;
  if (totalOdds < 10) return 0.60;
  if (totalOdds < 50) return 0.40;
  return 0.25;
}

// ============================================
// HELPER: profilo utente (crea se non esiste)
// ============================================

async function getOrCreateProfile(db, userId, userEmail) {
  let profile = await db.collection('user_profiles').findOne({ firebase_uid: userId });
  if (!profile) {
    profile = {
      firebase_uid: userId,
      email: userEmail || '',
      display_name: '',
      tier: 'free',
      tier_expires_at: null,
      created_at: new Date(),
      updated_at: new Date()
    };
    await db.collection('user_profiles').insertOne(profile);
  }
  return profile;
}

// ============================================
// HELPER: conta bet del mese corrente
// ============================================

async function countMonthlyBets(db, userId) {
  const now = new Date();
  const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
  const endOfMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString().slice(0, 10);
  return db.collection('money_tracker_bets').countDocuments({
    user_id: userId,
    date: { $gte: startOfMonth, $lte: endOfMonth }
  });
}

// ============================================
// HELPER: calcola striscia recente
// ============================================

async function getRecentStreak(db, userId) {
  const recentBets = await db.collection('money_tracker_bets')
    .find({ user_id: userId, status: { $in: ['won', 'lost'] } })
    .sort({ settled_at: -1 })
    .limit(10)
    .toArray();

  let winStreak = 0, lossStreak = 0;
  for (const bet of recentBets) {
    if (bet.status === 'won') {
      if (lossStreak > 0) break;
      winStreak++;
    } else {
      if (winStreak > 0) break;
      lossStreak++;
    }
  }
  return { winStreak, lossStreak };
}

// ============================================
// GET /settings — Legge impostazioni utente
// ============================================

router.get('/settings', async (req, res) => {
  try {
    const settings = await req.db.collection('money_tracker_settings')
      .findOne({ user_id: req.userId });

    const profile = await getOrCreateProfile(req.db, req.userId, req.userEmail);

    res.json({
      success: true,
      settings: settings || null,
      tier: profile.tier || 'free'
    });
  } catch (error) {
    console.error('MT settings GET error:', error);
    res.status(500).json({ error: error.message });
  }
});

// ============================================
// POST /settings — Crea/aggiorna (upsert)
// ============================================

router.post('/settings', async (req, res) => {
  try {
    const { initial_capital, max_bet_pct, aggressiveness } = req.body;

    if (!initial_capital || initial_capital < 10) {
      return res.status(400).json({ error: 'Capitale iniziale minimo 10€' });
    }
    if (!['conservative', 'moderate', 'aggressive'].includes(aggressiveness)) {
      return res.status(400).json({ error: 'Aggressività non valida' });
    }
    const maxPct = Math.max(1, Math.min(10, Number(max_bet_pct) || 5));

    const existing = await req.db.collection('money_tracker_settings')
      .findOne({ user_id: req.userId });

    if (existing) {
      await req.db.collection('money_tracker_settings').updateOne(
        { user_id: req.userId },
        {
          $set: {
            initial_capital: Number(initial_capital),
            max_bet_pct: maxPct,
            aggressiveness,
            updated_at: new Date()
          }
        }
      );
    } else {
      await req.db.collection('money_tracker_settings').insertOne({
        user_id: req.userId,
        initial_capital: Number(initial_capital),
        current_balance: Number(initial_capital),
        max_bet_pct: maxPct,
        aggressiveness,
        created_at: new Date(),
        updated_at: new Date()
      });
    }

    // Crea profilo se non esiste
    await getOrCreateProfile(req.db, req.userId, req.userEmail);

    const updated = await req.db.collection('money_tracker_settings')
      .findOne({ user_id: req.userId });

    res.json({ success: true, settings: updated });
  } catch (error) {
    console.error('MT settings POST error:', error);
    res.status(500).json({ error: error.message });
  }
});

// ============================================
// GET /bets?month=2026-02 — Scommesse del mese
// ============================================

router.get('/bets', async (req, res) => {
  try {
    const month = req.query.month; // "2026-02"
    if (!month || !/^\d{4}-\d{2}$/.test(month)) {
      return res.status(400).json({ error: 'Formato mese: YYYY-MM' });
    }

    const [y, m] = month.split('-').map(Number);
    const startDate = `${month}-01`;
    const endDate = `${month}-${new Date(y, m, 0).getDate()}`;

    const bets = await req.db.collection('money_tracker_bets')
      .find({
        user_id: req.userId,
        date: { $gte: startDate, $lte: endDate }
      })
      .sort({ date: -1, created_at: -1 })
      .toArray();

    // Stats del mese
    let totalStake = 0, totalProfit = 0, won = 0, lost = 0, pending = 0;
    for (const b of bets) {
      totalStake += b.stake_amount || 0;
      if (b.status === 'won') {
        won++;
        totalProfit += (b.net_profit || 0);
      } else if (b.status === 'lost') {
        lost++;
        totalProfit -= (b.stake_amount || 0);
      } else if (b.status === 'pending') {
        pending++;
      }
    }

    res.json({
      success: true,
      bets,
      stats: {
        total: bets.length,
        won, lost, pending,
        totalStake: Math.round(totalStake * 100) / 100,
        totalProfit: Math.round(totalProfit * 100) / 100,
        roi: totalStake > 0 ? Math.round((totalProfit / totalStake) * 10000) / 100 : 0
      }
    });
  } catch (error) {
    console.error('MT bets GET error:', error);
    res.status(500).json({ error: error.message });
  }
});

// ============================================
// POST /bets — Nuova scommessa
// ============================================

router.post('/bets', async (req, res) => {
  try {
    const { bet_type, selections, stake_amount, date } = req.body;

    if (!bet_type || !selections || !Array.isArray(selections) || selections.length === 0) {
      return res.status(400).json({ error: 'Dati scommessa non validi' });
    }
    if (!stake_amount || stake_amount <= 0) {
      return res.status(400).json({ error: 'Stake non valido' });
    }

    // Controlla limite tier
    const profile = await getOrCreateProfile(req.db, req.userId, req.userEmail);
    const tier = profile.tier || 'free';
    const limit = TIER_LIMITS[tier]?.monthly_bets || 15;
    const monthlyCount = await countMonthlyBets(req.db, req.userId);
    if (monthlyCount >= limit) {
      return res.status(403).json({
        error: `Limite mensile raggiunto (${limit} scommesse per tier "${tier}")`,
        limit, current: monthlyCount, tier
      });
    }

    // Controlla saldo
    const settings = await req.db.collection('money_tracker_settings')
      .findOne({ user_id: req.userId });
    if (!settings) {
      return res.status(400).json({ error: 'Completa prima l\'onboarding (impostazioni)' });
    }
    if (stake_amount > settings.current_balance) {
      return res.status(400).json({ error: 'Saldo insufficiente' });
    }

    // Calcola quota totale
    const totalOdds = selections.reduce((acc, s) => acc * (Number(s.odds) || 1), 1);
    const potentialWin = Math.round(stake_amount * totalOdds * 100) / 100;

    const betDate = date || new Date().toISOString().slice(0, 10);

    const newBet = {
      user_id: req.userId,
      date: betDate,
      bet_type,
      selections: selections.map(s => ({
        home: s.home || '',
        away: s.away || '',
        market: s.market || '',
        prediction: s.prediction || '',
        odds: Number(s.odds) || 1,
        result: null
      })),
      total_odds: Math.round(totalOdds * 100) / 100,
      stake_amount: Number(stake_amount),
      potential_win: potentialWin,
      status: 'pending',
      net_profit: null,
      settled_at: null,
      created_at: new Date()
    };

    const insertResult = await req.db.collection('money_tracker_bets').insertOne(newBet);

    // Scala saldo
    await req.db.collection('money_tracker_settings').updateOne(
      { user_id: req.userId },
      {
        $inc: { current_balance: -Number(stake_amount) },
        $set: { updated_at: new Date() }
      }
    );

    newBet._id = insertResult.insertedId;
    res.json({ success: true, bet: newBet });
  } catch (error) {
    console.error('MT bets POST error:', error);
    res.status(500).json({ error: error.message });
  }
});

// ============================================
// PUT /bets/:id/result — Segna risultato
// ============================================

router.put('/bets/:id/result', async (req, res) => {
  try {
    const betId = req.params.id;
    const { status, selection_results } = req.body;

    if (!['won', 'lost', 'void', 'partial'].includes(status)) {
      return res.status(400).json({ error: 'Status non valido (won/lost/void/partial)' });
    }

    const bet = await req.db.collection('money_tracker_bets')
      .findOne({ _id: new ObjectId(betId), user_id: req.userId });
    if (!bet) {
      return res.status(404).json({ error: 'Scommessa non trovata' });
    }
    if (bet.status !== 'pending') {
      return res.status(400).json({ error: 'Scommessa già chiusa' });
    }

    // Aggiorna risultati singole selezioni se forniti
    let updatedSelections = bet.selections;
    if (selection_results && Array.isArray(selection_results)) {
      updatedSelections = bet.selections.map((s, i) => ({
        ...s,
        result: selection_results[i] || s.result
      }));
    }

    // Calcola P/L
    let netProfit = 0;
    let balanceChange = 0;

    if (status === 'won') {
      netProfit = bet.potential_win - bet.stake_amount;
      balanceChange = bet.potential_win; // restituisce stake + profitto
    } else if (status === 'lost') {
      netProfit = -bet.stake_amount;
      balanceChange = 0; // stake già scalato
    } else if (status === 'void') {
      netProfit = 0;
      balanceChange = bet.stake_amount; // rimborso totale
    } else if (status === 'partial') {
      // Partial: calcola in base alle selezioni vinte
      const wonSelections = updatedSelections.filter(s => s.result === 'won');
      if (wonSelections.length > 0) {
        const partialOdds = wonSelections.reduce((acc, s) => acc * s.odds, 1);
        const partialWin = Math.round(bet.stake_amount * partialOdds * 100) / 100;
        netProfit = partialWin - bet.stake_amount;
        balanceChange = partialWin;
      } else {
        netProfit = -bet.stake_amount;
        balanceChange = 0;
      }
    }

    netProfit = Math.round(netProfit * 100) / 100;
    balanceChange = Math.round(balanceChange * 100) / 100;

    // Aggiorna bet
    await req.db.collection('money_tracker_bets').updateOne(
      { _id: new ObjectId(betId) },
      {
        $set: {
          status,
          selections: updatedSelections,
          net_profit: netProfit,
          settled_at: new Date()
        }
      }
    );

    // Aggiorna saldo
    if (balanceChange > 0) {
      await req.db.collection('money_tracker_settings').updateOne(
        { user_id: req.userId },
        {
          $inc: { current_balance: balanceChange },
          $set: { updated_at: new Date() }
        }
      );
    }

    res.json({
      success: true,
      status,
      net_profit: netProfit,
      balance_change: balanceChange
    });
  } catch (error) {
    console.error('MT result PUT error:', error);
    res.status(500).json({ error: error.message });
  }
});

// ============================================
// DELETE /bets/:id — Cancella bet pending
// ============================================

router.delete('/bets/:id', async (req, res) => {
  try {
    const betId = req.params.id;
    const bet = await req.db.collection('money_tracker_bets')
      .findOne({ _id: new ObjectId(betId), user_id: req.userId });

    if (!bet) {
      return res.status(404).json({ error: 'Scommessa non trovata' });
    }
    if (bet.status !== 'pending') {
      return res.status(400).json({ error: 'Solo scommesse pending possono essere cancellate' });
    }

    // Rimborsa stake
    await req.db.collection('money_tracker_settings').updateOne(
      { user_id: req.userId },
      {
        $inc: { current_balance: bet.stake_amount },
        $set: { updated_at: new Date() }
      }
    );

    await req.db.collection('money_tracker_bets').deleteOne({ _id: new ObjectId(betId) });

    res.json({ success: true, refunded: bet.stake_amount });
  } catch (error) {
    console.error('MT delete error:', error);
    res.status(500).json({ error: error.message });
  }
});

// ============================================
// POST /suggest-stake — Stake suggerito
// ============================================

router.post('/suggest-stake', async (req, res) => {
  try {
    const { bet_type, total_odds } = req.body;

    const settings = await req.db.collection('money_tracker_settings')
      .findOne({ user_id: req.userId });
    if (!settings) {
      return res.status(400).json({ error: 'Completa prima l\'onboarding' });
    }

    const balance = settings.current_balance || 0;
    const aggressiveness = settings.aggressiveness || 'moderate';
    const maxBetPct = (settings.max_bet_pct || 5) / 100;

    const basePct = AGGRESSIVENESS_PCT[aggressiveness] || 0.03;
    const typeMult = BET_TYPE_MULT[bet_type] || 1.0;
    const oddsMult = getOddsBandMult(Number(total_odds) || 2.0);

    // Striscia
    const { winStreak, lossStreak } = await getRecentStreak(req.db, req.userId);
    let streakMult = 1.0;
    if (lossStreak >= 5) streakMult = 0.60;
    else if (lossStreak >= 3) streakMult = 0.80;
    else if (winStreak >= 5) streakMult = 1.15;
    else if (winStreak >= 3) streakMult = 1.10;

    let suggested = balance * basePct * typeMult * oddsMult * streakMult;
    const maxBet = balance * maxBetPct;
    suggested = Math.max(1, Math.min(suggested, maxBet));
    suggested = Math.round(suggested * 100) / 100;

    res.json({
      success: true,
      suggested_stake: suggested,
      details: {
        balance,
        base_pct: basePct,
        type_mult: typeMult,
        odds_mult: oddsMult,
        streak_mult: streakMult,
        win_streak: winStreak,
        loss_streak: lossStreak,
        max_bet: Math.round(maxBet * 100) / 100
      }
    });
  } catch (error) {
    console.error('MT suggest-stake error:', error);
    res.status(500).json({ error: error.message });
  }
});

// ============================================
// GET /stats — Statistiche globali
// ============================================

router.get('/stats', async (req, res) => {
  try {
    const settings = await req.db.collection('money_tracker_settings')
      .findOne({ user_id: req.userId });

    const allBets = await req.db.collection('money_tracker_bets')
      .find({ user_id: req.userId })
      .toArray();

    let totalStake = 0, totalWon = 0, totalLost = 0;
    let won = 0, lost = 0, pending = 0, voided = 0;
    let bestWin = 0, worstLoss = 0;

    for (const b of allBets) {
      totalStake += b.stake_amount || 0;
      if (b.status === 'won') {
        won++;
        const profit = b.net_profit || 0;
        totalWon += profit;
        if (profit > bestWin) bestWin = profit;
      } else if (b.status === 'lost') {
        lost++;
        totalLost += b.stake_amount || 0;
        if (b.stake_amount > worstLoss) worstLoss = b.stake_amount;
      } else if (b.status === 'pending') {
        pending++;
      } else if (b.status === 'void') {
        voided++;
      }
    }

    const netProfit = totalWon - totalLost;
    const roi = totalStake > 0 ? Math.round((netProfit / totalStake) * 10000) / 100 : 0;

    res.json({
      success: true,
      stats: {
        initial_capital: settings?.initial_capital || 0,
        current_balance: settings?.current_balance || 0,
        total_bets: allBets.length,
        won, lost, pending, voided,
        win_rate: (won + lost) > 0 ? Math.round((won / (won + lost)) * 10000) / 100 : 0,
        total_stake: Math.round(totalStake * 100) / 100,
        total_won: Math.round(totalWon * 100) / 100,
        total_lost: Math.round(totalLost * 100) / 100,
        net_profit: Math.round(netProfit * 100) / 100,
        roi,
        best_win: Math.round(bestWin * 100) / 100,
        worst_loss: Math.round(worstLoss * 100) / 100
      }
    });
  } catch (error) {
    console.error('MT stats error:', error);
    res.status(500).json({ error: error.message });
  }
});

// ============================================
// POST /reset — Reset totale
// ============================================

router.post('/reset', async (req, res) => {
  try {
    // Cancella tutte le bet
    const deleteResult = await req.db.collection('money_tracker_bets')
      .deleteMany({ user_id: req.userId });

    // Resetta saldo al capitale iniziale
    const settings = await req.db.collection('money_tracker_settings')
      .findOne({ user_id: req.userId });

    if (settings) {
      await req.db.collection('money_tracker_settings').updateOne(
        { user_id: req.userId },
        {
          $set: {
            current_balance: settings.initial_capital,
            updated_at: new Date()
          }
        }
      );
    }

    res.json({
      success: true,
      deleted_bets: deleteResult.deletedCount,
      balance_reset_to: settings?.initial_capital || 0
    });
  } catch (error) {
    console.error('MT reset error:', error);
    res.status(500).json({ error: error.message });
  }
});

module.exports = router;
