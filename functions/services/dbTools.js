/**
 * dbTools.js — Tool definitions per Mistral function calling (accesso DB)
 * Mistral può interrogare il database autonomamente per rispondere alle domande
 */

const { buildMatchContext, searchMatch } = require('./contextBuilder');

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
    dpQuery.league = { $regex: new RegExp(leagueFilter, 'i') };
  }
  const predictions = await db.collection('daily_predictions')
    .find(dpQuery)
    .project({ home: 1, away: 1, league: 1, date: 1, match_time: 1, decision: 1, pronostici: 1, confidence_segno: 1, confidence_gol: 1, stelle_segno: 1, stelle_gol: 1 })
    .sort({ match_time: 1 })
    .toArray();

  for (const p of predictions) {
    const pronostici = (p.pronostici || []).map(pr => `${pr.tipo}: ${pr.segno} @${pr.quota}`).join(', ');
    results.push({
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
    });
  }

  // 2. h2h_by_round — partite senza pronostici (complemento)
  const h2hPipeline = [
    { $unwind: '$matches' },
    { $match: { 'matches.date_obj': { $regex: new RegExp(`^${date}`) } } },
    { $project: { _id: 0, league: '$league', home: '$matches.home', away: '$matches.away', time: '$matches.match_time', date_obj: '$matches.date_obj' } }
  ];
  if (leagueFilter) {
    h2hPipeline.unshift({ $match: { league: { $regex: new RegExp(leagueFilter, 'i') } } });
  }
  const h2hMatches = await db.collection('h2h_by_round').aggregate(h2hPipeline).toArray();

  for (const m of h2hMatches) {
    // Evita duplicati già presenti da daily_predictions
    const isDup = results.some(r => r.home === m.home && r.away === m.away);
    if (!isDup) {
      results.push({
        home: m.home,
        away: m.away,
        league: m.league,
        date,
        time: m.time || '?',
        decision: 'NO_PRONOSTICO',
        pronostici: 'non analizzata',
        source: 'h2h_by_round'
      });
    }
  }

  // Ordina per orario
  results.sort((a, b) => (a.time || '').localeCompare(b.time || ''));

  if (results.length === 0) {
    return JSON.stringify({ message: `Nessuna partita trovata per il ${date}${leagueFilter ? ' in ' + leagueFilter : ''}.` });
  }

  return JSON.stringify({
    date,
    league_filter: leagueFilter || 'tutte',
    total: results.length,
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
  const result = await buildMatchContext(db, args.home, args.away, args.date || undefined);
  if (!result) {
    return JSON.stringify({ message: `Partita ${args.home} vs ${args.away} non trovata nel database.` });
  }
  return result.context; // Già una stringa di testo formattata
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
    default:
      return JSON.stringify({ error: `Tool sconosciuto: ${toolName}` });
  }
}

module.exports = { DB_TOOLS, executeDbTool };
