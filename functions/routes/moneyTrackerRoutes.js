const express = require('express');
const admin = require('../config/firebaseAdmin');
const router = express.Router();

const firestore = admin.firestore();
const FV = admin.firestore.FieldValue;

const TIER_LIMITS = {
  free:    { monthly_bets: 15 },
  mini:    { monthly_bets: 50 },
  medium:  { monthly_bets: 150 },
  premium: { monthly_bets: 9999 },
};

const AGGRESSIVENESS_PCT = {
  conservative: 0.02,
  moderate: 0.035,
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
  if (totalOdds < 1.5) return 1.30;
  if (totalOdds < 2.5) return 1.00;
  if (totalOdds < 5) return 0.80;
  if (totalOdds < 10) return 0.60;
  if (totalOdds < 50) return 0.40;
  return 0.25;
}

function getSystemStakeMult(sysStake) {
  if (sysStake == null || sysStake <= 0) return 1.0;
  if (sysStake <= 3) return 0.50;
  if (sysStake <= 6) return 1.00;
  if (sysStake <= 8) return 1.30;
  return 1.50;
}

function quarterKelly(probStimata, odds) {
  if (!probStimata || !odds || odds <= 1) return null;
  const p = probStimata / 100;
  const q = 1 - p;
  const b = odds - 1;
  const kelly = (p * b - q) / b;
  if (kelly <= 0) return null;
  return kelly * 0.25;
}

async function getOrCreateProfile(userId, userEmail) {
  const ref = firestore.collection('user_profiles').doc(userId);
  const snap = await ref.get();
  if (!snap.exists) {
    const data = {
      email: userEmail || '',
      display_name: '',
      tier: 'free',
      tier_expires_at: null,
      created_at: FV.serverTimestamp(),
      updated_at: FV.serverTimestamp()
    };
    await ref.set(data);
    return data;
  }
  return snap.data();
}

async function countMonthlyBets(userId) {
  const now = new Date();
  const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
  const endOfMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString().slice(0, 10);
  const snap = await firestore.collection('money_tracker_bets')
    .where('user_id', '==', userId)
    .where('date', '>=', startOfMonth)
    .where('date', '<=', endOfMonth)
    .get();
  return snap.size;
}

async function getRecentStreak(userId) {
  const wonSnap = await firestore.collection('money_tracker_bets')
    .where('user_id', '==', userId)
    .where('status', 'in', ['won', 'lost'])
    .orderBy('settled_at', 'desc')
    .limit(10)
    .get();

  let winStreak = 0, lossStreak = 0;
  for (const doc of wonSnap.docs) {
    const bet = doc.data();
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

router.get('/settings', async (req, res) => {
  try {
    const settingsSnap = await firestore.collection('money_tracker_settings').doc(req.userId).get();
    const profile = await getOrCreateProfile(req.userId, req.userEmail);
    res.json({
      success: true,
      settings: settingsSnap.exists ? settingsSnap.data() : null,
      tier: profile.tier || 'free'
    });
  } catch (error) {
    console.error('MT settings GET error:', error);
    res.status(500).json({ error: error.message });
  }
});

router.post('/settings', async (req, res) => {
  try {
    const { initial_capital, max_bet_pct, daily_exposure_pct, aggressiveness } = req.body;

    if (!initial_capital || initial_capital < 10) {
      return res.status(400).json({ error: 'Capitale iniziale minimo 10€' });
    }
    const validAggr = ['conservative', 'moderate', 'aggressive'].includes(aggressiveness) ? aggressiveness : 'moderate';
    const maxPct = Math.max(1, Math.min(20, Number(max_bet_pct) || 4));
    const dailyPct = Math.max(5, Math.min(50, Number(daily_exposure_pct) || 15));

    const ref = firestore.collection('money_tracker_settings').doc(req.userId);
    const existing = await ref.get();

    if (existing.exists) {
      await ref.update({
        initial_capital: Number(initial_capital),
        max_bet_pct: maxPct,
        daily_exposure_pct: dailyPct,
        aggressiveness: validAggr,
        updated_at: FV.serverTimestamp()
      });
    } else {
      await ref.set({
        initial_capital: Number(initial_capital),
        current_balance: Number(initial_capital),
        max_bet_pct: maxPct,
        daily_exposure_pct: dailyPct,
        aggressiveness: validAggr,
        created_at: FV.serverTimestamp(),
        updated_at: FV.serverTimestamp()
      });
    }

    await getOrCreateProfile(req.userId, req.userEmail);
    const updated = (await ref.get()).data();
    res.json({ success: true, settings: updated });
  } catch (error) {
    console.error('MT settings POST error:', error);
    res.status(500).json({ error: error.message });
  }
});

router.get('/bets', async (req, res) => {
  try {
    const month = req.query.month;
    if (!month || !/^\d{4}-\d{2}$/.test(month)) {
      return res.status(400).json({ error: 'Formato mese: YYYY-MM' });
    }

    const [y, m] = month.split('-').map(Number);
    const startDate = `${month}-01`;
    const endDate = `${month}-${new Date(y, m, 0).getDate()}`;

    const snap = await firestore.collection('money_tracker_bets')
      .where('user_id', '==', req.userId)
      .where('date', '>=', startDate)
      .where('date', '<=', endDate)
      .orderBy('date', 'desc')
      .orderBy('created_at', 'desc')
      .get();

    const bets = snap.docs.map(d => ({ id: d.id, ...d.data() }));

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

router.post('/bets', async (req, res) => {
  try {
    const { bet_type, selections, stake_amount, date } = req.body;

    if (!bet_type || !selections || !Array.isArray(selections) || selections.length === 0) {
      return res.status(400).json({ error: 'Dati scommessa non validi' });
    }
    if (!stake_amount || stake_amount <= 0) {
      return res.status(400).json({ error: 'Stake non valido' });
    }

    const profile = await getOrCreateProfile(req.userId, req.userEmail);
    const tier = profile.tier || 'free';
    const limit = TIER_LIMITS[tier]?.monthly_bets || 15;
    const monthlyCount = await countMonthlyBets(req.userId);
    if (monthlyCount >= limit) {
      return res.status(403).json({
        error: `Limite mensile raggiunto (${limit} scommesse per tier "${tier}")`,
        limit, current: monthlyCount, tier
      });
    }

    const settingsRef = firestore.collection('money_tracker_settings').doc(req.userId);
    const totalOdds = selections.reduce((acc, s) => acc * (Number(s.odds) || 1), 1);
    const potentialWin = Math.round(stake_amount * totalOdds * 100) / 100;
    const betDate = date || new Date().toISOString().slice(0, 10);

    const newBetRef = firestore.collection('money_tracker_bets').doc();

    const newBet = await firestore.runTransaction(async (tx) => {
      const sSnap = await tx.get(settingsRef);
      if (!sSnap.exists) {
        throw new Error('NO_ONBOARDING');
      }
      const settings = sSnap.data();
      if (stake_amount > settings.current_balance) {
        throw new Error('SALDO_INSUFFICIENTE');
      }

      const bet = {
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
        created_at: FV.serverTimestamp()
      };

      tx.set(newBetRef, bet);
      tx.update(settingsRef, {
        current_balance: FV.increment(-Number(stake_amount)),
        updated_at: FV.serverTimestamp()
      });
      return bet;
    });

    res.json({ success: true, bet: { id: newBetRef.id, ...newBet } });
  } catch (error) {
    if (error.message === 'NO_ONBOARDING') {
      return res.status(400).json({ error: 'Completa prima l\'onboarding (impostazioni)' });
    }
    if (error.message === 'SALDO_INSUFFICIENTE') {
      return res.status(400).json({ error: 'Saldo insufficiente' });
    }
    console.error('MT bets POST error:', error);
    res.status(500).json({ error: error.message });
  }
});

router.put('/bets/:id/result', async (req, res) => {
  try {
    const betId = req.params.id;
    const { status, selection_results } = req.body;

    if (!['won', 'lost', 'void', 'partial'].includes(status)) {
      return res.status(400).json({ error: 'Status non valido (won/lost/void/partial)' });
    }

    const betRef = firestore.collection('money_tracker_bets').doc(betId);
    const settingsRef = firestore.collection('money_tracker_settings').doc(req.userId);

    const result = await firestore.runTransaction(async (tx) => {
      const bSnap = await tx.get(betRef);
      if (!bSnap.exists || bSnap.data().user_id !== req.userId) {
        throw new Error('NOT_FOUND');
      }
      const bet = bSnap.data();
      if (bet.status !== 'pending') {
        throw new Error('ALREADY_CLOSED');
      }

      let updatedSelections = bet.selections;
      if (selection_results && Array.isArray(selection_results)) {
        updatedSelections = bet.selections.map((s, i) => ({
          ...s,
          result: selection_results[i] || s.result
        }));
      }

      let netProfit = 0;
      let balanceChange = 0;

      if (status === 'won') {
        netProfit = bet.potential_win - bet.stake_amount;
        balanceChange = bet.potential_win;
      } else if (status === 'lost') {
        netProfit = -bet.stake_amount;
        balanceChange = 0;
      } else if (status === 'void') {
        netProfit = 0;
        balanceChange = bet.stake_amount;
      } else if (status === 'partial') {
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

      tx.update(betRef, {
        status,
        selections: updatedSelections,
        net_profit: netProfit,
        settled_at: FV.serverTimestamp()
      });

      if (balanceChange > 0) {
        tx.update(settingsRef, {
          current_balance: FV.increment(balanceChange),
          updated_at: FV.serverTimestamp()
        });
      }

      return { netProfit, balanceChange };
    });

    res.json({
      success: true,
      status,
      net_profit: result.netProfit,
      balance_change: result.balanceChange
    });
  } catch (error) {
    if (error.message === 'NOT_FOUND') {
      return res.status(404).json({ error: 'Scommessa non trovata' });
    }
    if (error.message === 'ALREADY_CLOSED') {
      return res.status(400).json({ error: 'Scommessa già chiusa' });
    }
    console.error('MT result PUT error:', error);
    res.status(500).json({ error: error.message });
  }
});

router.delete('/bets/:id', async (req, res) => {
  try {
    const betId = req.params.id;
    const betRef = firestore.collection('money_tracker_bets').doc(betId);
    const settingsRef = firestore.collection('money_tracker_settings').doc(req.userId);

    const refunded = await firestore.runTransaction(async (tx) => {
      const bSnap = await tx.get(betRef);
      if (!bSnap.exists || bSnap.data().user_id !== req.userId) {
        throw new Error('NOT_FOUND');
      }
      const bet = bSnap.data();
      if (bet.status !== 'pending') {
        throw new Error('NOT_PENDING');
      }
      tx.update(settingsRef, {
        current_balance: FV.increment(bet.stake_amount),
        updated_at: FV.serverTimestamp()
      });
      tx.delete(betRef);
      return bet.stake_amount;
    });

    res.json({ success: true, refunded });
  } catch (error) {
    if (error.message === 'NOT_FOUND') {
      return res.status(404).json({ error: 'Scommessa non trovata' });
    }
    if (error.message === 'NOT_PENDING') {
      return res.status(400).json({ error: 'Solo scommesse pending possono essere cancellate' });
    }
    console.error('MT delete error:', error);
    res.status(500).json({ error: error.message });
  }
});

router.post('/suggest-stake', async (req, res) => {
  try {
    const { bet_type, total_odds, confidence, probabilita_stimata, system_stake } = req.body;

    const settingsSnap = await firestore.collection('money_tracker_settings').doc(req.userId).get();
    if (!settingsSnap.exists) {
      return res.status(400).json({ error: 'Completa prima l\'onboarding' });
    }
    const settings = settingsSnap.data();

    const balance = settings.current_balance || 0;
    const aggressiveness = settings.aggressiveness || 'moderate';
    const maxBetPct = (settings.max_bet_pct || 5) / 100;
    const odds = Number(total_odds) || 2.0;

    const { winStreak, lossStreak } = await getRecentStreak(req.userId);
    let streakMult = 1.0;
    if (lossStreak >= 5) streakMult = 0.60;
    else if (lossStreak >= 3) streakMult = 0.80;
    else if (winStreak >= 5) streakMult = 1.15;
    else if (winStreak >= 3) streakMult = 1.10;

    const maxBet = balance * maxBetPct;
    let suggested;
    let method;

    const kellyFraction = quarterKelly(probabilita_stimata, odds);
    const sysStakeMult = getSystemStakeMult(system_stake);

    if (kellyFraction != null && probabilita_stimata > 0) {
      suggested = balance * kellyFraction * sysStakeMult * streakMult;
      method = 'kelly';
    } else {
      const basePct = AGGRESSIVENESS_PCT[aggressiveness] || 0.03;
      const typeMult = BET_TYPE_MULT[bet_type] || 1.0;
      const oddsMult = getOddsBandMult(odds);
      suggested = balance * basePct * typeMult * oddsMult * streakMult;
      method = 'classic';
    }

    suggested = Math.max(1, Math.min(suggested, maxBet));
    suggested = Math.round(suggested * 100) / 100;

    res.json({
      success: true,
      suggested_stake: suggested,
      method,
      details: {
        balance,
        max_bet: Math.round(maxBet * 100) / 100,
        streak_mult: streakMult,
        win_streak: winStreak,
        loss_streak: lossStreak,
        ...(method === 'kelly' ? {
          kelly_fraction: kellyFraction ? Math.round(kellyFraction * 10000) / 100 : null,
          probabilita_stimata,
          system_stake,
          sys_stake_mult: sysStakeMult
        } : {
          base_pct: AGGRESSIVENESS_PCT[aggressiveness] || 0.03,
          type_mult: BET_TYPE_MULT[bet_type] || 1.0,
          odds_mult: getOddsBandMult(odds)
        })
      }
    });
  } catch (error) {
    console.error('MT suggest-stake error:', error);
    res.status(500).json({ error: error.message });
  }
});

router.get('/stats', async (req, res) => {
  try {
    const settingsSnap = await firestore.collection('money_tracker_settings').doc(req.userId).get();
    const settings = settingsSnap.exists ? settingsSnap.data() : null;

    const allSnap = await firestore.collection('money_tracker_bets')
      .where('user_id', '==', req.userId)
      .get();

    let totalStake = 0, totalWon = 0, totalLost = 0;
    let won = 0, lost = 0, pending = 0, voided = 0;
    let bestWin = 0, worstLoss = 0;

    for (const doc of allSnap.docs) {
      const b = doc.data();
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
        total_bets: allSnap.size,
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

router.post('/reset', async (req, res) => {
  try {
    const allSnap = await firestore.collection('money_tracker_bets')
      .where('user_id', '==', req.userId)
      .get();

    const batch = firestore.batch();
    allSnap.docs.forEach(doc => batch.delete(doc.ref));
    await batch.commit();

    const settingsRef = firestore.collection('money_tracker_settings').doc(req.userId);
    const settingsSnap = await settingsRef.get();
    let resetTo = 0;
    if (settingsSnap.exists) {
      const initial = settingsSnap.data().initial_capital || 0;
      resetTo = initial;
      await settingsRef.update({
        current_balance: initial,
        updated_at: FV.serverTimestamp()
      });
    }

    res.json({
      success: true,
      deleted_bets: allSnap.size,
      balance_reset_to: resetTo
    });
  } catch (error) {
    console.error('MT reset error:', error);
    res.status(500).json({ error: error.message });
  }
});

router.get('/summary', async (req, res) => {
  try {
    const year = Number(req.query.year) || new Date().getFullYear();

    const snap = await firestore.collection('money_tracker_bets')
      .where('user_id', '==', req.userId)
      .where('date', '>=', `${year}-01-01`)
      .where('date', '<=', `${year}-12-31`)
      .get();

    const months = {};
    for (let m = 1; m <= 12; m++) {
      const key = String(m).padStart(2, '0');
      months[key] = { count: 0, won: 0, lost: 0, pending: 0, stake: 0, wins: 0, profit: 0 };
    }

    for (const doc of snap.docs) {
      const bet = doc.data();
      const m = bet.date.substring(5, 7);
      if (!months[m]) continue;
      months[m].count++;
      months[m].stake += bet.stake_amount || 0;

      if (bet.status === 'won') {
        months[m].won++;
        months[m].wins += bet.potential_win || 0;
        months[m].profit += (bet.net_profit || 0);
      } else if (bet.status === 'lost') {
        months[m].lost++;
        months[m].profit -= (bet.stake_amount || 0);
      } else if (bet.status === 'pending') {
        months[m].pending++;
      }
    }

    for (const k of Object.keys(months)) {
      months[k].stake = Math.round(months[k].stake * 100) / 100;
      months[k].wins = Math.round(months[k].wins * 100) / 100;
      months[k].profit = Math.round(months[k].profit * 100) / 100;
    }

    let totalStake = 0, totalWins = 0, totalProfit = 0, totalCount = 0, totalWon = 0, totalLost = 0;
    for (const m of Object.values(months)) {
      totalStake += m.stake;
      totalWins += m.wins;
      totalProfit += m.profit;
      totalCount += m.count;
      totalWon += m.won;
      totalLost += m.lost;
    }

    res.json({
      success: true,
      year,
      months,
      totals: {
        count: totalCount,
        won: totalWon,
        lost: totalLost,
        stake: Math.round(totalStake * 100) / 100,
        wins: Math.round(totalWins * 100) / 100,
        profit: Math.round(totalProfit * 100) / 100,
        yield: totalStake > 0 ? Math.round((totalProfit / totalStake) * 10000) / 100 : 0
      }
    });
  } catch (error) {
    console.error('MT summary error:', error);
    res.status(500).json({ error: error.message });
  }
});

module.exports = router;
