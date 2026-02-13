/**
 * contextBuilder.js — Costruisce contesto testuale da 4 sorgenti DB per il Coach AI
 * Sorgenti: daily_predictions, h2h_by_round, matches_champions_league, matches_europa_league
 */

// Mappa nomi interni → nomi leggibili (il LLM non deve mai vedere "bvs" o "lucifero")
const NOMI_SEGNALI = {
  bvs: 'valore_scommessa',
  quote: 'quote',
  lucifero: 'forma_recente',
  affidabilita: 'affidabilita',
  dna: 'dna_tecnico',
  motivazioni: 'motivazioni',
  h2h: 'scontri_diretti',
  campo: 'fattore_campo',
  strisce: 'strisce',
};

// ── Ricerca in daily_predictions ──
async function findInDailyPredictions(db, home, away, date) {
  const query = { home, away };
  if (date) query.date = date;
  return db.collection('daily_predictions').findOne(query, { sort: { date: -1 } });
}

// ── Ricerca in h2h_by_round ──
async function findInH2hByRound(db, home, away) {
  const pipeline = [
    { $unwind: '$matches' },
    { $match: { 'matches.home': home, 'matches.away': away } },
    { $sort: { 'matches.date_obj': -1 } },
    { $limit: 1 },
    { $project: { _id: 0, league: '$league', round_name: '$round_name', match: '$matches' } }
  ];
  const results = await db.collection('h2h_by_round').aggregate(pipeline).toArray();
  return results.length > 0 ? results[0] : null;
}

// ── Ricerca nelle coppe (UCL + UEL) ──
async function findInCups(db, home, away) {
  const ucl = await db.collection('matches_champions_league')
    .findOne({ home_team: home, away_team: away }, { sort: { match_date: -1 } });
  if (ucl) return { ...ucl, cup: 'Champions League' };

  const uel = await db.collection('matches_europa_league')
    .findOne({ home_team: home, away_team: away }, { sort: { match_date: -1 } });
  if (uel) return { ...uel, cup: 'Europa League' };

  return null;
}

// ══════════════════════════════════════════════
// Contesto da daily_predictions (il più ricco)
// ══════════════════════════════════════════════
function buildDailyPredictionsContext(doc) {
  const { home, away } = doc;
  const lines = [];

  lines.push(`PARTITA: ${home} vs ${away}`);
  lines.push(`Campionato: ${doc.league} | Data: ${doc.date} ore ${doc.match_time || '?'}`);
  lines.push(`Decisione algoritmo: ${doc.decision}`);

  // Pronostici
  for (const p of (doc.pronostici || [])) {
    lines.push(`  Pronostico: ${p.tipo} -> ${p.pronostico} (confidence ${p.confidence}%, stelle ${p.stars}, quota ${p.quota || '?'})`);
  }

  // Confidence
  lines.push(`Confidence SEGNO: ${doc.confidence_segno ?? '?'}% | Confidence GOL: ${doc.confidence_gol ?? '?'}%`);

  // Quote
  const odds = doc.odds || {};
  lines.push(`Quote 1X2: 1=${odds['1'] || '?'} X=${odds['X'] || '?'} 2=${odds['2'] || '?'}`);
  lines.push(`Quote O/U: Over1.5=${odds.over_15 || '?'} Over2.5=${odds.over_25 || '?'} Over3.5=${odds.over_35 || '?'} Under2.5=${odds.under_25 || '?'}`);
  lines.push(`Quote GG/NG: GG=${odds.gg || '?'} NG=${odds.ng || '?'}`);

  // Segnali SEGNO (0-100)
  const sd = doc.segno_dettaglio || {};
  lines.push(`\nSEGNALI SEGNO (0-100, dove >50 = favore ${home}, <50 = favore ${away}):`);
  for (const [k, v] of Object.entries(sd)) {
    const nome = NOMI_SEGNALI[k] || k;
    lines.push(`  ${nome}: ${typeof v === 'number' ? v.toFixed(1) : v}`);
  }

  // Segnali SEGNO raw (valori grezzi bidirezionali)
  const raw = doc.segno_dettaglio_raw || {};
  lines.push(`\nDETTAGLI RAW SEGNO:`);
  for (const [k, v] of Object.entries(raw)) {
    if (v && typeof v === 'object') {
      const nome = NOMI_SEGNALI[k] || k;
      const parts = Object.entries(v).map(([kk, vv]) => `${kk}=${vv}`);
      lines.push(`  ${nome}: ${parts.join(', ')}`);
    }
  }

  // Segnali GOL (0-100)
  const gd = doc.gol_dettaglio || {};
  const gdir = doc.gol_directions || {};
  lines.push(`\nSEGNALI GOL (0-100):`);
  for (const [k, v] of Object.entries(gd)) {
    const d = gdir[k] || '?';
    lines.push(`  ${k}: ${typeof v === 'number' ? v.toFixed(1) : v} (direzione: ${d})`);
  }

  lines.push(`\nGol attesi: ${doc.expected_total_goals ?? '?'} | Media lega: ${doc.league_avg_goals ?? '?'}`);

  // Strisce
  const sh = doc.streak_home || {};
  const sa = doc.streak_away || {};
  lines.push(`\nSTRISCE ${home} (generali): ${JSON.stringify(sh)}`);
  lines.push(`STRISCE ${away} (generali): ${JSON.stringify(sa)}`);
  if (doc.streak_home_context) {
    lines.push(`STRISCE ${home} (solo casa): ${JSON.stringify(doc.streak_home_context)}`);
  }
  if (doc.streak_away_context) {
    lines.push(`STRISCE ${away} (solo trasferta): ${JSON.stringify(doc.streak_away_context)}`);
  }
  lines.push(`Adj SEGNO: ${(doc.streak_adjustment_segno || 0).toFixed(2)}% | Adj GOL: ${(doc.streak_adjustment_gol || 0).toFixed(2)}% | Adj GG/NG: ${(doc.streak_adjustment_ggng || 0).toFixed(2)}%`);

  // Commenti
  const comment = doc.comment || {};
  if (comment.segno) lines.push(`\nCommento SEGNO: ${comment.segno}`);
  if (comment.gol) lines.push(`Commento GOL: ${comment.gol}`);
  if (comment.gol_extra) lines.push(`Commento GG/NG: ${comment.gol_extra}`);

  return lines.join('\n');
}

// ══════════════════════════════════════════════
// Contesto da h2h_by_round (dati grezzi)
// ══════════════════════════════════════════════
function buildH2hContext(result) {
  const { league, round_name, match: m } = result;
  const hd = m.h2h_data || {};
  const lines = [];

  lines.push(`PARTITA: ${m.home} vs ${m.away}`);
  lines.push(`Campionato: ${league} | Giornata: ${round_name} | Orario: ${m.match_time || '?'}`);
  lines.push(`Stato: ${m.status || '?'}`);
  if (m.real_score) lines.push(`Risultato: ${m.real_score}`);

  // Quote
  const odds = m.odds || {};
  if (odds['1'] || odds.qt_1) {
    lines.push(`Quote 1X2: 1=${odds['1'] || odds.qt_1 || '?'} X=${odds['X'] || odds.qt_x || '?'} 2=${odds['2'] || odds.qt_2 || '?'}`);
  }
  if (odds.over_25) lines.push(`Quote O/U: Over2.5=${odds.over_25} Under2.5=${odds.under_25 || '?'}`);
  if (odds.gg) lines.push(`Quote GG/NG: GG=${odds.gg} NG=${odds.ng || '?'}`);

  // Scontri diretti
  if (hd.home_score !== undefined) {
    lines.push(`\nSCONTRI DIRETTI: ${m.home} ${hd.home_score}/10 vs ${m.away} ${hd.away_score}/10 (${hd.total_matches || '?'} partite)`);
    if (hd.history_summary) lines.push(`  Storico: ${hd.history_summary}`);
    if (hd.avg_goals_home !== undefined) {
      lines.push(`  Media gol H2H: ${m.home} ${hd.avg_goals_home} - ${m.away} ${hd.avg_goals_away} (totale: ${hd.avg_total_goals || '?'})`);
    }
  }

  // Valore Scommessa (ex BVS)
  if (hd.bvs_match_index !== undefined) {
    lines.push(`\nVALORE SCOMMESSA: indice=${hd.bvs_match_index} (scala +/-7), classificazione=${hd.classification || '?'}, lineare=${hd.is_linear}, tip=${hd.tip_sign || 'nessuno'}`);
  }

  // Forma Recente (ex Lucifero)
  if (hd.lucifero_home !== undefined) {
    lines.push(`FORMA RECENTE: ${m.home} ${hd.lucifero_home}/25, ${m.away} ${hd.lucifero_away}/25`);
    if (hd.lucifero_trend_home) lines.push(`  Trend ${m.home}: [${hd.lucifero_trend_home.join(', ')}]`);
    if (hd.lucifero_trend_away) lines.push(`  Trend ${m.away}: [${hd.lucifero_trend_away.join(', ')}]`);
  }

  // Affidabilita
  if (hd.trust_home_letter) {
    lines.push(`AFFIDABILITA: ${m.home} ${hd.trust_home_letter} (${hd['affidabilità_casa'] ?? '?'}/10), ${m.away} ${hd.trust_away_letter} (${hd['affidabilità_trasferta'] ?? '?'}/10)`);
  }

  // Fattore Campo
  const fc = hd.fattore_campo || {};
  if (fc.field_home !== undefined) {
    lines.push(`FATTORE CAMPO: ${m.home} ${fc.field_home}/7, ${m.away} ${fc.field_away}/7`);
  }

  // DNA Tecnico
  const hDna = hd.home_dna || (hd.h2h_dna && hd.h2h_dna.home_dna) || {};
  const aDna = hd.away_dna || (hd.h2h_dna && hd.h2h_dna.away_dna) || {};
  if (hDna.att !== undefined) {
    lines.push(`DNA TECNICO ${m.home}: att=${hDna.att} def=${hDna.def} tec=${hDna.tec} val=${hDna.val} (scala /100)`);
    lines.push(`DNA TECNICO ${m.away}: att=${aDna.att} def=${aDna.def} tec=${aDna.tec} val=${aDna.val}`);
  }

  // Classifica
  if (hd.home_rank !== undefined) {
    lines.push(`CLASSIFICA: ${m.home} ${hd.home_rank} posto, ${m.away} ${hd.away_rank} posto`);
  }

  // Formazioni
  if (hd.formazioni) {
    lines.push(`\nFORMAZIONI: disponibili nel database`);
  }

  // Live score
  if (m.live_status) {
    lines.push(`\nLIVE: ${m.live_score || '?'} (${m.live_status}, minuto ${m.live_minute || '?'})`);
  }

  return lines.join('\n');
}

// ══════════════════════════════════════════════
// Contesto da coppe (UCL/UEL)
// ══════════════════════════════════════════════
function buildCupContext(doc) {
  const lines = [];

  lines.push(`PARTITA: ${doc.home_team} vs ${doc.away_team}`);
  lines.push(`Competizione: ${doc.cup} | Data: ${doc.match_date || '?'}`);
  lines.push(`Stato: ${doc.status || '?'}`);

  if (doc.result && doc.result.home_goals != null) {
    lines.push(`Risultato: ${doc.result.home_goals}-${doc.result.away_goals}`);
  }

  const odds = doc.odds || {};
  if (odds['1']) lines.push(`Quote 1X2: 1=${odds['1']} X=${odds['X'] || '?'} 2=${odds['2'] || '?'}`);
  if (odds.over_25) lines.push(`Quote O/U: Over2.5=${odds.over_25} Under2.5=${odds.under_25 || '?'}`);
  if (odds.gg) lines.push(`Quote GG/NG: GG=${odds.gg} NG=${odds.ng || '?'}`);

  if (doc.home_elo) lines.push(`ELO: ${doc.home_team} ${doc.home_elo}, ${doc.away_team} ${doc.away_elo}`);
  if (doc.home_value) lines.push(`Valore Rosa: ${doc.home_team} ${doc.home_value}, ${doc.away_team} ${doc.away_value}`);

  lines.push(`\nNota: dati limitati per partite di coppa (ELO, valore rosa, quote). Analisi meno dettagliata rispetto ai campionati.`);

  return lines.join('\n');
}

// ══════════════════════════════════════════════
// Entry point: cerca match e costruisce contesto
// ══════════════════════════════════════════════
async function buildMatchContext(db, home, away, date) {
  // 1. daily_predictions (ha segnali 0-100, strisce, pronostici)
  const dp = await findInDailyPredictions(db, home, away, date);
  if (dp) {
    return {
      context: buildDailyPredictionsContext(dp),
      source: 'daily_predictions',
      match_info: { home: dp.home, away: dp.away, league: dp.league, date: dp.date, match_time: dp.match_time }
    };
  }

  // 2. h2h_by_round (dati grezzi: DNA, BVS, Lucifero, etc.)
  const h2h = await findInH2hByRound(db, home, away);
  if (h2h) {
    const m = h2h.match;
    return {
      context: buildH2hContext(h2h),
      source: 'h2h_by_round',
      match_info: { home: m.home, away: m.away, league: h2h.league, date: m.date_obj, match_time: m.match_time }
    };
  }

  // 3. Coppe (UCL, UEL)
  const cup = await findInCups(db, home, away);
  if (cup) {
    return {
      context: buildCupContext(cup),
      source: cup.cup,
      match_info: { home: cup.home_team, away: cup.away_team, league: cup.cup, date: cup.match_date }
    };
  }

  return null;
}

// ══════════════════════════════════════════════
// Ricerca fuzzy per nome squadra (regex case-insensitive)
// ══════════════════════════════════════════════
async function searchMatch(db, query) {
  const regex = new RegExp(query, 'i');
  const results = [];

  // daily_predictions
  const dpResults = await db.collection('daily_predictions')
    .find({ $or: [{ home: regex }, { away: regex }] })
    .sort({ date: -1 })
    .limit(5)
    .project({ home: 1, away: 1, league: 1, date: 1, decision: 1 })
    .toArray();

  for (const d of dpResults) {
    results.push({ home: d.home, away: d.away, league: d.league, date: d.date, source: 'daily_predictions', decision: d.decision });
  }

  // h2h_by_round
  const h2hResults = await db.collection('h2h_by_round').aggregate([
    { $unwind: '$matches' },
    { $match: { $or: [{ 'matches.home': regex }, { 'matches.away': regex }] } },
    { $sort: { 'matches.date_obj': -1 } },
    { $limit: 5 },
    { $project: { _id: 0, home: '$matches.home', away: '$matches.away', league: '$league', date: '$matches.date_obj', match_time: '$matches.match_time' } }
  ]).toArray();

  for (const d of h2hResults) {
    const isDup = results.some(r => r.home === d.home && r.away === d.away);
    if (!isDup) results.push({ ...d, source: 'h2h_by_round' });
  }

  // Coppe
  for (const coll of ['matches_champions_league', 'matches_europa_league']) {
    const cupName = coll.includes('champions') ? 'Champions League' : 'Europa League';
    const cupResults = await db.collection(coll)
      .find({ $or: [{ home_team: regex }, { away_team: regex }] })
      .sort({ match_date: -1 })
      .limit(3)
      .toArray();

    for (const d of cupResults) {
      const isDup = results.some(r => r.home === d.home_team && r.away === d.away_team);
      if (!isDup) results.push({ home: d.home_team, away: d.away_team, league: cupName, date: d.match_date, source: coll });
    }
  }

  return results.slice(0, 10);
}

module.exports = { buildMatchContext, searchMatch };
