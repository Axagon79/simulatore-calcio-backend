const express = require('express');
const router = express.Router();

/**
 * GET /patterns
 * Aggregation pipeline per pattern recognition sugli errori pronostici
 */
router.get('/patterns', async (req, res) => {
  try {
    const db = req.db;
    const days = parseInt(req.query.days) || 30;
    const minCount = parseInt(req.query.min_count) || 3;
    const league = req.query.league || null;
    const source = req.query.source || null;

    const fromDate = new Date();
    fromDate.setDate(fromDate.getDate() - days);
    const toDate = new Date();

    // Filtro base
    const matchFilter = { match_date: { $gte: fromDate, $lte: toDate } };
    if (league) matchFilter.league = league;
    if (source) matchFilter.source = source;

    const coll = db.collection('prediction_errors');

    // 1. Conteggio totale
    const totalErrors = await coll.countDocuments(matchFilter);

    if (totalErrors === 0) {
      return res.json({
        period: { from: fromDate.toISOString().split('T')[0], to: toDate.toISOString().split('T')[0], days },
        total_errors: 0, patterns: [], avg_variables_impact: {},
        by_source: [], by_league: [], severity: {}, weekly_trend: [],
      });
    }

    // 2. Pattern più frequenti (unwind pattern_tags)
    const patternsAgg = await coll.aggregate([
      { $match: matchFilter },
      { $unwind: '$pattern_tags' },
      { $group: { _id: '$pattern_tags', count: { $sum: 1 } } },
      { $match: { count: { $gte: minCount } } },
      { $sort: { count: -1 } },
      { $limit: 20 },
    ]).toArray();
    const patterns = patternsAgg.map(p => ({
      tag: p._id,
      count: p.count,
      pct: Math.round((p.count / totalErrors) * 1000) / 10,
    }));

    // 3. Media variables_impact
    const avgAgg = await coll.aggregate([
      { $match: matchFilter },
      { $group: {
        _id: null,
        form: { $avg: '$variables_impact.form' },
        motivation: { $avg: '$variables_impact.motivation' },
        home_advantage: { $avg: '$variables_impact.home_advantage' },
        market_odds: { $avg: '$variables_impact.market_odds' },
        h2h: { $avg: '$variables_impact.h2h' },
        fatigue: { $avg: '$variables_impact.fatigue' },
        streaks: { $avg: '$variables_impact.streaks' },
        tactical_dna: { $avg: '$variables_impact.tactical_dna' },
      }},
    ]).toArray();
    const avg = avgAgg[0] || {};
    delete avg._id;
    const avgRounded = {};
    for (const [k, v] of Object.entries(avg)) {
      avgRounded[k] = Math.round((v || 0) * 100) / 100;
    }

    // 4. Per source
    const sourceAgg = await coll.aggregate([
      { $match: matchFilter },
      { $group: { _id: '$source', errors: { $sum: 1 } } },
      { $sort: { errors: -1 } },
    ]).toArray();
    const bySource = sourceAgg.map(s => ({
      source: s._id || 'unknown',
      errors: s.errors,
      pct: Math.round((s.errors / totalErrors) * 1000) / 10,
    }));

    // 5. Per league
    const leagueAgg = await coll.aggregate([
      { $match: matchFilter },
      { $group: { _id: '$league', errors: { $sum: 1 } } },
      { $sort: { errors: -1 } },
      { $limit: 15 },
    ]).toArray();
    const byLeague = leagueAgg.map(l => ({ league: l._id, errors: l.errors }));

    // 6. Severity distribution
    const sevAgg = await coll.aggregate([
      { $match: matchFilter },
      { $group: { _id: '$severity', count: { $sum: 1 } } },
    ]).toArray();
    const severity = {};
    for (const s of sevAgg) severity[s._id || 'unknown'] = s.count;

    // 7. Trend settimanale
    const weeklyAgg = await coll.aggregate([
      { $match: matchFilter },
      { $group: {
        _id: { $dateToString: { format: '%G-W%V', date: '$match_date' } },
        errors: { $sum: 1 },
      }},
      { $sort: { _id: 1 } },
    ]).toArray();
    const weeklyTrend = weeklyAgg.map(w => ({ week: w._id, errors: w.errors }));

    res.json({
      period: { from: fromDate.toISOString().split('T')[0], to: toDate.toISOString().split('T')[0], days },
      total_errors: totalErrors,
      patterns,
      avg_variables_impact: avgRounded,
      by_source: bySource,
      by_league: byLeague,
      severity,
      weekly_trend: weeklyTrend,
    });
  } catch (err) {
    console.error('Feedback patterns error:', err);
    res.status(500).json({ error: err.message });
  }
});

module.exports = router;
