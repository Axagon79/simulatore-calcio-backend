/**
 * dbTools.js — Tool definitions per Mistral function calling (accesso DB)
 * Mistral può interrogare il database autonomamente per rispondere alle domande
 */

const { buildMatchContext, searchMatch } = require('./contextBuilder');
const { parseScore, checkPronostico, getQuotaForPronostico, getFinishedResults } = require('../routes/predictionsRoutes');

// ── Tool Definitions (formato Mistral function calling) ──

const DB_TOOLS = [
  {
    type: 'function',
    function: {
      name: 'get_today_matches',
      description: "Ottieni le partite programmate per una data specifica da TUTTE le leghe o da una lega specifica. Usa quando l'utente chiede 'che partite ci sono oggi/domani', 'partite Serie A oggi', 'calendario di oggi', ecc. Restituisce: lista partite con squadre, lega, orario e pronostici se disponibili.",
      parameters: {
        type: 'object',
        properties: {
          date: { type: 'string', description: 'Data in formato YYYY-MM-DD. Se non specificata, usa la data di oggi.' },
          league: { type: 'string', description: "Filtro opzionale per lega (es. 'Serie A', 'Premier League', 'La Liga', 'Bundesliga', 'Ligue 1'). Se vuoto, restituisce tutte le leghe." }
        },
        required: []
      }
    }
  },
  {
    type: 'function',
    function: {
      name: 'search_matches',
      description: "Cerca partite nel database per nome squadra. Usa quando l'utente menziona una squadra specifica (es. 'Milan', 'Juventus', 'Real Madrid'). Cerca in tutte le fonti: pronostici giornalieri, campionati, Champions League, Europa League.",
      parameters: {
        type: 'object',
        properties: {
          query: { type: 'string', description: 'Nome della squadra o parte del nome' }
        },
        required: ['query']
      }
    }
  },
  {
    type: 'function',
    function: {
      name: 'get_match_details',
      description: "Ottieni l'analisi dettagliata completa di una partita specifica: tutti i segnali (0-100), quote, strisce, DNA tecnico, forma recente, valore scommessa, affidabilità, pronostici. Usa DOPO aver identificato la partita esatta con get_today_matches o search_matches.",
      parameters: {
        type: 'object',
        properties: {
          home: { type: 'string', description: 'Nome esatto della squadra di casa' },
          away: { type: 'string', description: 'Nome esatto della squadra ospite' },
          date: { type: 'string', description: 'Data partita YYYY-MM-DD (opzionale, migliora la precisione)' }
        },
        required: ['home', 'away']
      }
    }
  }
  ,
  {
    type: 'function',
    function: {
      name: 'get_standings',
      description: "Ottieni la classifica di un campionato o la posizione di una squadra specifica. Usa quando l'utente chiede 'quanti punti ha la Juve?', 'classifica Serie A', 'chi e primo in Premier League?', 'distacco dalla prima', ecc. Restituisce: classifica completa con posizione, squadra, punti.",
      parameters: {
        type: 'object',
        properties: {
          league: { type: 'string', description: "Nome del campionato (es. 'Serie A', 'Premier League', 'La Liga', 'Bundesliga', 'Ligue 1'). Se non specificato e team e fornito, viene individuato automaticamente." },
          team: { type: 'string', description: "Nome squadra per filtrare/evidenziare (es. 'Juventus', 'Milan'). Se fornito senza league, cerca la lega della squadra." }
        },
        required: []
      }
    }
  },
  {
    type: 'function',
    function: {
      name: 'get_track_record',
      description: "Ottieni le statistiche del track record dei pronostici: percentuale di successo globale, per mercato (SEGNO, Over/Under, GG/NG), per campionato, per fascia di quota (con ROI), e trend temporale. Usa quando l'utente chiede 'come vanno i pronostici?', 'percentuale di successo', 'track record', 'hit rate', 'quanti ne azzecchiamo?', 'ROI', 'rendimento quote', ecc.",
      parameters: {
        type: 'object',
        properties: {
          days: { type: 'number', description: "Numero di giorni indietro da analizzare (default 30). Es. 7 = ultima settimana, 30 = ultimo mese." },
          league: { type: 'string', description: "Filtro opzionale per campionato (es. 'Serie A', 'Premier League')." },
          market: { type: 'string', description: "Filtro opzionale per mercato: 'SEGNO', 'OVER_UNDER', 'GG_NG'." }
        },
        required: []
      }
    }
  }
];

// ── Funzioni Esecutrici ──

/**
 * Partite di oggi (o di una data specifica)
 * Cerca in daily_predictions (ha pronostici) + h2h_by_round (tutte le partite)
 */
async function executeTodayMatches(db, args) {
  const date = args.date || new Date().toISOString().split('T')[0];
  const leagueFilter = args.league || null;

  const results = [];

  // 1. daily_predictions — partite con pronostici
  const dpQuery = { date };
  if (leagueFilter) {
    // Match esatto con word boundary — evita "Serie A" che matcha "Brasileirão Serie A"
    dpQuery.league = { $regex: new RegExp(`^${leagueFilter}$`, 'i') };
  }
  const predictions = await db.collection('daily_predictions')
    .find(dpQuery)
    .project({ home: 1, away: 1, league: 1, date: 1, match_time: 1, decision: 1, pronostici: 1, confidence_segno: 1, confidence_gol: 1, stelle_segno: 1, stelle_gol: 1, odds: 1, real_score: 1, status: 1 })
    .sort({ match_time: 1 })
    .toArray();

  // Mapping pronostico GOL → chiave quota (le quote GOL non sono nel sub-doc pronostici, ma in odds)
  const golQuotaMap = (pronostico, odds) => {
    if (!odds || !pronostico) return null;
    return { 'Over 1.5': odds.over_15, 'Over 2.5': odds.over_25, 'Over 3.5': odds.over_35,
      'Under 1.5': odds.under_15, 'Under 2.5': odds.under_25, 'Under 3.5': odds.under_35,
      'Goal': odds.gg, 'NoGoal': odds.ng }[pronostico] || null;
  };

  for (const p of predictions) {
    const odds = p.odds || {};
    const pronostici = (p.pronostici || []).map(pr => {
      const quota = pr.quota || golQuotaMap(pr.pronostico, odds);
      return `${pr.tipo}: ${pr.pronostico} @${quota || '?'} (${pr.confidence}%)`;
    }).join(', ');
    const entry = {
      home: p.home,
      away: p.away,
      league: p.league,
      date: p.date,
      time: p.match_time || '?',
      decision: p.decision || 'ANALISI',
      pronostici: pronostici || 'nessuno',
      confidence_segno: p.confidence_segno,
      confidence_gol: p.confidence_gol,
      stelle_segno: p.stelle_segno,
      stelle_gol: p.stelle_gol,
      source: 'daily_predictions'
    };
    if (p.real_score) entry.risultato = p.real_score;
    if (p.status) entry.status = p.status;
    results.push(entry);
  }

  // 2. h2h_by_round — risultati + partite extra (stessa logica di predictionsRoutes.js)
  const startOfDay = new Date(date + 'T00:00:00.000Z');
  const endOfDay = new Date(date + 'T23:59:59.999Z');
  const h2hMatchCondition = {
    'matches.date_obj': { $gte: startOfDay, $lte: endOfDay }
  };
  if (leagueFilter) {
    h2hMatchCondition.league = { $regex: new RegExp(`^${leagueFilter}$`, 'i') };
  }
  const h2hMatches = await db.collection('h2h_by_round').aggregate([
    { $unwind: '$matches' },
    { $match: h2hMatchCondition },
    { $project: { _id: 0, league: '$league', home: '$matches.home', away: '$matches.away', time: '$matches.match_time', real_score: '$matches.real_score', status: '$matches.status' } }
  ]).toArray();

  // Mappa risultati h2h per lookup veloce (home|||away → real_score)
  const resultsMap = {};
  for (const m of h2hMatches) {
    const key = `${m.home}|||${m.away}`;
    resultsMap[key] = { real_score: m.real_score, status: m.status };
  }

  // Arricchisci pronostici con risultati da h2h_by_round
  for (const r of results) {
    if (!r.risultato) {
      const h2h = resultsMap[`${r.home}|||${r.away}`];
      if (h2h && h2h.real_score) {
        r.risultato = h2h.real_score;
        if (h2h.status) r.status = h2h.status;
      }
    }
  }

  // Aggiungi partite h2h senza pronostici (complemento)
  for (const m of h2hMatches) {
    const isDup = results.some(r => r.home === m.home && r.away === m.away);
    if (!isDup) {
      const entry = {
        home: m.home,
        away: m.away,
        league: m.league,
        date,
        time: m.time || '?',
        decision: 'NO_PRONOSTICO',
        pronostici: 'non analizzata',
        source: 'h2h_by_round'
      };
      if (m.real_score) entry.risultato = m.real_score;
      if (m.status) entry.status = m.status;
      results.push(entry);
    }
  }

  // Ordina per orario
  results.sort((a, b) => (a.time || '').localeCompare(b.time || ''));

  if (results.length === 0) {
    return JSON.stringify({ message: `Nessuna partita trovata per il ${date}${leagueFilter ? ' in ' + leagueFilter : ''}.` });
  }

  // Conta pronostici totali (una partita può averne più di uno, es. SEGNO + GOL)
  const totalPronostici = predictions.reduce((sum, p) => sum + (p.pronostici || []).length, 0);

  return JSON.stringify({
    date,
    league_filter: leagueFilter || 'tutte',
    total_matches: results.length,
    total_pronostici: totalPronostici,
    matches: results
  });
}

/**
 * Cerca partite per nome squadra (wrapper di searchMatch)
 */
async function executeSearchMatches(db, args) {
  const matches = await searchMatch(db, args.query);
  if (matches.length === 0) {
    return JSON.stringify({ message: `Nessuna partita trovata per "${args.query}".` });
  }
  return JSON.stringify({ total: matches.length, matches });
}

/**
 * Dettagli completi di una partita (wrapper di buildMatchContext)
 */
async function executeMatchDetails(db, args) {
  // Fallback: Mistral a volte manda {"match": "Home vs Away"} invece di {"home", "away"} separati
  let home = args.home;
  let away = args.away;
  if (!home && !away && args.match) {
    const parts = args.match.split(/\s+vs\s+/i);
    if (parts.length === 2) {
      home = parts[0].trim();
      away = parts[1].trim();
    }
  }
  if (!home || !away) {
    return JSON.stringify({ message: `Parametri mancanti: serve home e away (ricevuto: ${JSON.stringify(args)})` });
  }
  const result = await buildMatchContext(db, home, away, args.date || undefined);
  if (!result) {
    return JSON.stringify({ message: `Partita ${home} vs ${away} non trovata nel database.` });
  }
  return result.context; // Già una stringa di testo formattata
}

/**
 * Classifica di un campionato o posizione di una squadra
 * Collezione: classifica (un doc per lega con array table[])
 */
async function executeGetStandings(db, args) {
  const { league, team } = args;

  // Se team fornito senza league, cerca in quale lega gioca
  let leagueQuery = league;
  if (!leagueQuery && team) {
    const regex = new RegExp(team, 'i');
    const found = await db.collection('classifiche').findOne(
      { 'table.team': regex },
      { projection: { league: 1 } }
    );
    if (found) leagueQuery = found.league;
  }

  if (!leagueQuery) {
    return JSON.stringify({ error: 'Specifica un campionato (es. Serie A) o una squadra.' });
  }

  const doc = await db.collection('classifiche').findOne(
    { league: { $regex: new RegExp(leagueQuery, 'i') } }
  );

  if (!doc || !doc.table) {
    return JSON.stringify({ message: `Classifica non trovata per "${leagueQuery}".` });
  }

  // Calcola round corrente da h2h_by_round (played nel DB potrebbe essere 0)
  // NOTA: h2h_by_round NON ha "round_number" — ha "round_name" (es. "Giornata 24")
  let currentRound = 0;
  let totalRounds = 38; // default Serie A/top 5
  try {
    const today = new Date().toISOString().split('T')[0]; // "2026-02-13"
    // Match ESATTO sulla league (non regex — evita "Serie A" che matcha "Brasileirão Serie A")
    const exactLeague = doc.league; // nome esatto dalla classifica
    // Aggregation: estrae round_name + prima data di ogni giornata, ordina per data DESC
    const roundDates = await db.collection('h2h_by_round').aggregate([
      { $match: { league: exactLeague } },
      { $project: { round_name: 1, first_date: { $arrayElemAt: ['$matches.date_obj', 0] } } },
      { $sort: { first_date: -1 } }
    ]).toArray();
    if (roundDates.length > 0) {
      // Funzione helper: "Giornata 24" → 24, "Round 5" → 5
      const parseRoundNum = (name) => parseInt((name || '').replace(/\D/g, '')) || 0;
      // totalRounds = numero più alto tra tutti i round_name
      totalRounds = Math.max(...roundDates.map(rd => parseRoundNum(rd.round_name))) || roundDates.length;
      // Trova il round più recente con partite già giocate (data ≤ oggi)
      // roundDates è ordinato per first_date DESC → il primo con data ≤ oggi è il round corrente
      for (const rd of roundDates) {
        if (rd.first_date) {
          const dateStr = rd.first_date instanceof Date
            ? rd.first_date.toISOString().substring(0, 10)
            : String(rd.first_date).substring(0, 10);
          if (dateStr && dateStr <= today) {
            currentRound = parseRoundNum(rd.round_name);
            break;
          }
        }
      }
    }
  } catch (e) { /* ignora errore calcolo round */ }

  const remainingRounds = totalRounds - currentRound;

  const result = {
    league: doc.league,
    country: doc.country,
    total_teams: doc.table.length,
    current_round: currentRound,
    total_rounds: totalRounds,
    remaining_rounds: remainingRounds,
    remaining_points_available: remainingRounds * 3,
    table: doc.table.map(t => ({
      rank: t.rank,
      team: t.team,
      points: t.points,
      played: t.played || currentRound
    }))
  };

  // Se team specificato, evidenzia la posizione
  if (team) {
    const regex = new RegExp(team, 'i');
    const teamRow = doc.table.find(t => regex.test(t.team));
    if (teamRow) {
      const leader = doc.table[0];
      const gap = leader.points - teamRow.points;
      result.highlighted_team = {
        team: teamRow.team,
        rank: teamRow.rank,
        points: teamRow.points,
        played: teamRow.played || currentRound,
        gap_from_first: gap,
        leader: leader.team,
        leader_points: leader.points,
        can_catch_leader: gap <= remainingRounds * 3,
        min_points_needed_to_catch: gap + 1
      };
    }
  }

  return JSON.stringify(result);
}

/**
 * Track Record — statistiche accuratezza pronostici
 * Restituisce: globale, per mercato, per campionato (top/bottom), per fascia quota (con ROI), trend
 */
async function executeTrackRecord(db, args) {
  const days = args.days || 30;
  const leagueFilter = args.league || null;
  const marketFilter = args.market || null;

  const to = new Date().toISOString().split('T')[0];
  const fromDate = new Date();
  fromDate.setDate(fromDate.getDate() - days);
  const from = fromDate.toISOString().split('T')[0];

  // 1. Query predictions + risultati
  const query = { date: { $gte: from, $lte: to } };
  if (leagueFilter) query.league = { $regex: new RegExp(leagueFilter, 'i') };

  const [predictions, resultsMap] = await Promise.all([
    db.collection('daily_predictions').find(query, { projection: { _id: 0 } }).toArray(),
    getFinishedResults(db, { from, to })
  ]);

  // 2. Cross-match e verifica hit/miss
  const verified = [];
  for (const pred of predictions) {
    const realScore = resultsMap[`${pred.home}|||${pred.away}|||${pred.date}`] || null;
    if (!realScore) continue;
    const parsed = parseScore(realScore);
    if (!parsed || !pred.pronostici || pred.pronostici.length === 0) continue;

    for (const p of pred.pronostici) {
      const hit = checkPronostico(p.pronostico, p.tipo, parsed);
      if (hit === null) continue;

      let tipoEffettivo = p.tipo;
      if (p.tipo === 'GOL') {
        const pLower = (p.pronostico || '').toLowerCase();
        if (pLower.startsWith('over') || pLower.startsWith('under')) tipoEffettivo = 'OVER_UNDER';
        else if (pLower === 'goal' || pLower === 'nogoal') tipoEffettivo = 'GG_NG';
      }
      if (marketFilter && tipoEffettivo.toUpperCase() !== marketFilter.toUpperCase()) continue;

      let quota = p.quota != null ? parseFloat(p.quota) : null;
      if (quota === null || isNaN(quota)) quota = getQuotaForPronostico(p.pronostico, p.tipo, pred.odds);

      verified.push({ date: pred.date, league: pred.league || 'N/A', tipo: tipoEffettivo, quota, hit });
    }
  }

  // 3. Aggregazioni
  const hitRate = (items) => {
    const total = items.length;
    const hits = items.filter(i => i.hit).length;
    return { total, hits, misses: total - hits, hit_rate: total > 0 ? Math.round((hits / total) * 1000) / 10 : null };
  };

  // Globale
  const globale = hitRate(verified);

  // Per mercato
  const byMarket = {};
  for (const v of verified) { if (!byMarket[v.tipo]) byMarket[v.tipo] = []; byMarket[v.tipo].push(v); }
  const breakdown_mercato = {};
  for (const [tipo, items] of Object.entries(byMarket)) breakdown_mercato[tipo] = hitRate(items);

  // Per campionato (top 5 + bottom 5 per hit rate, min 3 pronostici)
  const byLeague = {};
  for (const v of verified) { if (!byLeague[v.league]) byLeague[v.league] = []; byLeague[v.league].push(v); }
  const leagueStats = Object.entries(byLeague)
    .map(([lg, items]) => ({ league: lg, ...hitRate(items) }))
    .filter(l => l.total >= 3)
    .sort((a, b) => (b.hit_rate || 0) - (a.hit_rate || 0));
  const top_campionati = leagueStats.slice(0, 5);
  const bottom_campionati = leagueStats.slice(-5).reverse();

  // Per fascia quota (con ROI)
  const getQuotaBand = (q) => {
    if (q === null || q === undefined) return 'N/D';
    if (q <= 1.20) return '1.01-1.20'; if (q <= 1.40) return '1.21-1.40';
    if (q <= 1.60) return '1.41-1.60'; if (q <= 1.80) return '1.61-1.80';
    if (q <= 2.00) return '1.81-2.00'; if (q <= 2.50) return '2.01-2.50';
    if (q <= 3.00) return '2.51-3.00'; if (q <= 4.00) return '3.01-4.00';
    return '4.00+';
  };
  const quotaBands = {};
  for (const v of verified) {
    const band = getQuotaBand(v.quota);
    if (!quotaBands[band]) quotaBands[band] = [];
    quotaBands[band].push(v);
  }
  const breakdown_quota = {};
  for (const [band, items] of Object.entries(quotaBands)) {
    if (items.length === 0 || band === 'N/D') continue;
    const base = hitRate(items);
    let profit = 0;
    for (const v of items) profit += v.hit && v.quota != null ? (v.quota - 1) : -1;
    const quotaItems = items.filter(v => v.quota != null);
    breakdown_quota[band] = {
      ...base,
      roi: items.length > 0 ? Math.round((profit / items.length) * 1000) / 10 : null,
      profit: Math.round(profit * 100) / 100,
      avg_quota: quotaItems.length > 0 ? Math.round(quotaItems.reduce((s, v) => s + v.quota, 0) / quotaItems.length * 100) / 100 : null
    };
  }

  // Quote stats globali
  const quotaVerified = verified.filter(v => v.quota != null);
  let roiGlobale = 0;
  for (const v of quotaVerified) roiGlobale += v.hit ? (v.quota - 1) : -1;
  const quota_stats = {
    total_con_quota: quotaVerified.length,
    avg_quota: quotaVerified.length > 0 ? Math.round(quotaVerified.reduce((s, v) => s + v.quota, 0) / quotaVerified.length * 100) / 100 : null,
    roi_globale: quotaVerified.length > 0 ? Math.round((roiGlobale / quotaVerified.length) * 1000) / 10 : null,
    profit_globale: Math.round(roiGlobale * 100) / 100
  };

  // Trend ultimi 7 giorni
  const byDate = {};
  for (const v of verified) { if (!byDate[v.date]) byDate[v.date] = []; byDate[v.date].push(v); }
  const trend = Object.entries(byDate)
    .map(([date, items]) => ({ date, ...hitRate(items) }))
    .sort((a, b) => a.date.localeCompare(b.date))
    .slice(-7);

  return JSON.stringify({
    periodo: { from, to, giorni: days },
    filtri: { league: leagueFilter, market: marketFilter },
    globale,
    breakdown_mercato,
    top_campionati,
    bottom_campionati,
    breakdown_quota,
    quota_stats,
    trend_ultimi_7_giorni: trend
  });
}

/**
 * Esegue un tool DB dato il nome e gli argomenti
 * @returns {string} Risultato serializzato
 */
async function executeDbTool(db, toolName, args) {
  switch (toolName) {
    case 'get_today_matches':
      return executeTodayMatches(db, args);
    case 'search_matches':
      return executeSearchMatches(db, args);
    case 'get_match_details':
      return executeMatchDetails(db, args);
    case 'get_standings':
      return executeGetStandings(db, args);
    case 'get_track_record':
      return executeTrackRecord(db, args);
    default:
      return JSON.stringify({ error: `Tool sconosciuto: ${toolName}` });
  }
}

module.exports = { DB_TOOLS, executeDbTool };
