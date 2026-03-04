/**
 * webSearch.js — Ricerca web con rotazione a 4 provider gratuiti
 * Ordine: Tavily (1000/mese) → Brave (1000/mese) → Google CSE (100/giorno, 3000/mese) → Serper (2500 lifetime)
 * Contatori salvati in MongoDB (collection web_search_counters)
 * Mistral decide autonomamente SE cercare sul web (function calling)
 */

// --- API Keys ---
const TAVILY_API_KEY = process.env.TAVILY_API_KEY || '';
const BRAVE_API_KEY = process.env.BRAVE_API_KEY || '';
const GOOGLE_CSE_API_KEY = process.env.GOOGLE_CSE_API_KEY || '';
const GOOGLE_CSE_CX = process.env.GOOGLE_CSE_CX || '';
const SERPER_API_KEY = process.env.SERPER_API_KEY || '';

// --- Limiti ---
const LIMITS = {
  tavily: 1000,
  brave: 1000,
  google_daily: 100,
  google_monthly: 3000,
  serper_lifetime: 2500,
};

// Tool definition per Mistral function calling (invariata)
const WEB_SEARCH_TOOL = {
  type: 'function',
  function: {
    name: 'web_search',
    description: "Cerca informazioni aggiornate sul web riguardo calcio, squadre, giocatori, infortunati, notizie recenti. Usalo quando l'utente chiede informazioni che NON sono presenti nei dati della partita.",
    parameters: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description: 'La query di ricerca in italiano o inglese',
        },
      },
      required: ['query'],
    },
  },
};

// ===================== LEAGUE DOMAINS (per Tavily include_domains) =====================
const LEAGUE_DOMAINS = {
  // Italia
  'Serie A': ['gazzetta.it', 'corrieredellosport.it', 'tuttosport.com', 'tuttomercatoweb.com', 'calciomercato.com', 'skysport.it', 'sportsgambler.com'],
  'Serie B': ['gazzetta.it', 'corrieredellosport.it', 'tuttosport.com', 'tuttomercatoweb.com', 'calciomercato.com', 'skysport.it', 'sportsgambler.com'],
  'Serie C': ['tuttoc.com', 'trivenetogoal.it', 'notiziariocalcio.com', 'tsportinthecity.it', 'tuttocampo.it', 'news.bet365.it', 'forebet.com', 'windrawwin.com', 'sportsgambler.com'],
  // Europa Top 5
  'Premier League': ['premierleague.com', 'bbc.com', 'skysports.com', '90min.com', 'football365.com', 'sportsgambler.com'],
  'Championship': ['skysports.com', 'bbc.com', 'football365.com', 'sportsmole.co.uk', 'sportsgambler.com'],
  'La Liga': ['as.com', 'marca.com', 'mundodeportivo.com', 'footballespana.net', 'sportsgambler.com'],
  'LaLiga 2': ['as.com', 'marca.com', 'sportsmole.co.uk', 'sportsgambler.com'],
  'Bundesliga': ['bundesliga.com', 'bulinews.com', '90min.com', 'sportsgambler.com'],
  '2. Bundesliga': ['bundesliga.com', 'bulinews.com', 'sportsmole.co.uk', 'sportsgambler.com'],
  'Ligue 1': ['gffn.com', 'sofoot.com', 'footmercato.net', 'sportsgambler.com'],
  'Ligue 2': ['gffn.com', 'sofoot.com', 'footmercato.net', 'sportsgambler.com'],
  // Europa altri
  'Eredivisie': ['vi.nl', 'voetbalzone.nl', 'sportsgambler.com', 'sofascore.com'],
  'Liga Portugal': ['maisfutebol.iol.pt', 'record.pt', 'sportsgambler.com'],
  'Scottish Premiership': ['bbc.com', 'dailyrecord.co.uk', 'scotsman.com', 'sportsgambler.com'],
  'Allsvenskan': ['sofascore.com', 'sportsgambler.com', 'injuriesandsuspensions.com'],
  'Eliteserien': ['sofascore.com', 'sportsgambler.com', 'injuriesandsuspensions.com'],
  'Superligaen': ['sofascore.com', 'sportsgambler.com', 'injuriesandsuspensions.com'],
  'Jupiler Pro League': ['sofascore.com', 'sportsgambler.com', 'injuriesandsuspensions.com'],
  'Süper Lig': ['trtspor.com', 'sporx.com', 'sportsgambler.com'],
  'League of Ireland': ['extratime.com', 'sportsgambler.com', 'sofascore.com'],
  // Americhe
  'Brasileirão': ['ge.globo.com', 'sofascore.com', 'sportsgambler.com'],
  'Primera División': ['infobae.com', 'ole.com.ar', 'sportsgambler.com'],
  'MLS': ['mlssoccer.com', 'rotowire.com', 'sportsgambler.com'],
  // Asia
  'J1 League': ['jsgoal.jp', 'japantimes.co.jp', 'sportsgambler.com'],
  // Coppe
  'Champions League': ['uefa.com', 'goal.com', 'skysports.com', '90min.com', 'sportsgambler.com'],
  'Europa League': ['uefa.com', 'goal.com', 'skysports.com', '90min.com', 'sportsgambler.com'],
};

// Top league dove include_domains è utile (siti prevedibili e affidabili)
const TOP_LEAGUES_FOR_DOMAINS = new Set([
  'Serie A', 'Serie B', 'Serie C', 'Premier League', 'La Liga', 'Bundesliga', 'Ligue 1',
  'Champions League', 'Europa League',
]);

// Trova i domini per un campionato — solo top league, per le altre ricerca libera
function getLeagueDomains(league) {
  if (!league) return [];
  const key = Object.keys(LEAGUE_DOMAINS).find(k =>
    k.toLowerCase() === league.toLowerCase() || league.toLowerCase().includes(k.toLowerCase())
  );
  if (!key || !TOP_LEAGUES_FOR_DOMAINS.has(key)) return [];
  return LEAGUE_DOMAINS[key];
}

// ===================== PROVIDER FUNCTIONS =====================

/**
 * Tavily Search — POST https://api.tavily.com/search
 */
async function searchTavily(query, domains = []) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const body = {
      api_key: TAVILY_API_KEY,
      query,
      max_results: 3,
      search_depth: 'advanced',
      topic: 'news',
      time_range: 'week',
      days: 5,
    };
    // include_domains solo per top league — per Serie C e minori troppo restrittivo
    if (domains.length > 0) body.include_domains = domains;
    const resp = await fetch('https://api.tavily.com/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!resp.ok) throw new Error(`Tavily API ${resp.status}`);
    const data = await resp.json();
    return (data.results || []).slice(0, 3).map(r => ({
      title: r.title,
      snippet: (r.content || r.snippet || '').substring(0, 1500),
      url: r.url,
      published_date: r.published_date || null,
    }));
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * Brave Search — GET https://api.search.brave.com/res/v1/web/search
 */
async function searchBrave(query) {
  const url = `https://api.search.brave.com/res/v1/web/search?q=${encodeURIComponent(query)}&count=3&search_lang=it`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const resp = await fetch(url, {
      headers: {
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip',
        'X-Subscription-Token': BRAVE_API_KEY,
      },
      signal: controller.signal,
    });
    if (!resp.ok) throw new Error(`Brave Search API ${resp.status}`);
    const data = await resp.json();
    return (data.web?.results || []).slice(0, 3).map(r => ({
      title: r.title,
      snippet: (r.description || '').substring(0, 1500),
      url: r.url,
    }));
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * Google Custom Search — GET https://www.googleapis.com/customsearch/v1
 */
async function searchGoogle(query) {
  const url = `https://www.googleapis.com/customsearch/v1?key=${GOOGLE_CSE_API_KEY}&cx=${GOOGLE_CSE_CX}&q=${encodeURIComponent(query)}&num=3`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const resp = await fetch(url, { signal: controller.signal });
    if (!resp.ok) throw new Error(`Google CSE API ${resp.status}`);
    const data = await resp.json();
    return (data.items || []).slice(0, 3).map(r => ({
      title: r.title,
      snippet: (r.snippet || '').substring(0, 1500),
      url: r.link,
    }));
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * Serper — POST https://google.serper.dev/search
 */
async function searchSerper(query) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const resp = await fetch('https://google.serper.dev/search', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-KEY': SERPER_API_KEY,
      },
      body: JSON.stringify({ q: query, num: 3 }),
      signal: controller.signal,
    });
    if (!resp.ok) throw new Error(`Serper API ${resp.status}`);
    const data = await resp.json();
    return (data.organic || []).slice(0, 3).map(r => ({
      title: r.title,
      snippet: (r.snippet || '').substring(0, 1500),
      url: r.link,
    }));
  } finally {
    clearTimeout(timeout);
  }
}

// ===================== CONTATORI MONGODB =====================

const PROVIDER_ORDER = ['tavily', 'brave', 'google', 'serper'];
const PROVIDER_FN = { tavily: searchTavily, brave: searchBrave, google: searchGoogle, serper: searchSerper };
const PROVIDER_KEY = { tavily: TAVILY_API_KEY, brave: BRAVE_API_KEY, google: GOOGLE_CSE_API_KEY, serper: SERPER_API_KEY };

/**
 * Struttura contatori di default (primo uso)
 */
function defaultCounters() {
  const now = new Date();
  const nextMonth = new Date(now);
  nextMonth.setMonth(nextMonth.getMonth() + 1);

  const tomorrow = new Date(now);
  tomorrow.setUTCHours(0, 0, 0, 0);
  tomorrow.setUTCDate(tomorrow.getUTCDate() + 1);

  const nextMonthFirst = new Date(now);
  nextMonthFirst.setUTCDate(1);
  nextMonthFirst.setUTCMonth(nextMonthFirst.getUTCMonth() + 1);
  nextMonthFirst.setUTCHours(0, 0, 0, 0);

  return {
    _id: 'counters',
    tavily: { count: 0, reset_date: nextMonth.toISOString() },
    brave: { count: 0, reset_date: nextMonth.toISOString() },
    google: {
      daily_count: 0,
      daily_reset: tomorrow.toISOString(),
      monthly_count: 0,
      monthly_reset: nextMonthFirst.toISOString(),
    },
    serper: { lifetime_count: 0 },
    updated_at: now.toISOString(),
  };
}

/**
 * Reset contatori scaduti
 */
function checkAndReset(counters) {
  const now = new Date();

  // Reset Tavily (mensile dalla data iscrizione)
  if (now >= new Date(counters.tavily.reset_date)) {
    counters.tavily.count = 0;
    const next = new Date(counters.tavily.reset_date);
    next.setMonth(next.getMonth() + 1);
    counters.tavily.reset_date = next.toISOString();
  }

  // Reset Brave (mensile dalla data iscrizione)
  if (now >= new Date(counters.brave.reset_date)) {
    counters.brave.count = 0;
    const next = new Date(counters.brave.reset_date);
    next.setMonth(next.getMonth() + 1);
    counters.brave.reset_date = next.toISOString();
  }

  // Reset Google giornaliero (mezzanotte UTC)
  if (now >= new Date(counters.google.daily_reset)) {
    counters.google.daily_count = 0;
    const tomorrow = new Date(now);
    tomorrow.setUTCHours(0, 0, 0, 0);
    tomorrow.setUTCDate(tomorrow.getUTCDate() + 1);
    counters.google.daily_reset = tomorrow.toISOString();
  }

  // Reset Google mensile (1° del mese)
  if (now >= new Date(counters.google.monthly_reset)) {
    counters.google.monthly_count = 0;
    const next = new Date(now);
    next.setUTCDate(1);
    next.setUTCMonth(next.getUTCMonth() + 1);
    next.setUTCHours(0, 0, 0, 0);
    counters.google.monthly_reset = next.toISOString();
  }

  return counters;
}

/**
 * Controlla se un provider è disponibile (ha key + quota)
 */
function isProviderAvailable(provider, counters) {
  if (!PROVIDER_KEY[provider]) return false;

  switch (provider) {
    case 'tavily':
      return counters.tavily.count < LIMITS.tavily;
    case 'brave':
      return counters.brave.count < LIMITS.brave;
    case 'google':
      return counters.google.daily_count < LIMITS.google_daily &&
             counters.google.monthly_count < LIMITS.google_monthly;
    case 'serper':
      return counters.serper.lifetime_count < LIMITS.serper_lifetime;
    default:
      return false;
  }
}

/**
 * Incrementa contatore atomico su MongoDB
 */
async function incrementCounter(db, provider) {
  const inc = {};
  if (provider === 'tavily') inc['tavily.count'] = 1;
  else if (provider === 'brave') inc['brave.count'] = 1;
  else if (provider === 'google') {
    inc['google.daily_count'] = 1;
    inc['google.monthly_count'] = 1;
  } else if (provider === 'serper') {
    inc['serper.lifetime_count'] = 1;
  }

  await db.collection('web_search_counters').updateOne(
    { _id: 'counters' },
    { $inc: inc, $set: { updated_at: new Date().toISOString() } }
  );
}

/**
 * Carica contatori da MongoDB (crea se non esistono)
 */
async function loadCounters(db) {
  const col = db.collection('web_search_counters');
  let doc = await col.findOne({ _id: 'counters' });
  if (!doc) {
    doc = defaultCounters();
    await col.insertOne(doc);
  }
  return checkAndReset(doc);
}

// ===================== SEARCH CON ROTAZIONE =====================

/**
 * Esegue ricerca web con rotazione automatica tra 4 provider
 * @param {string} query - La query di ricerca
 * @param {object} db - Istanza MongoDB (per contatori)
 */
async function searchWeb(query, db, league) {
  const domains = getLeagueDomains(league);

  // Chiama il provider giusto — Tavily riceve i domini, gli altri no
  const callProvider = (provider, q) =>
    provider === 'tavily' ? searchTavily(q, domains) : PROVIDER_FN[provider](q);

  // Senza DB non possiamo gestire contatori — fallback diretto
  if (!db) {
    console.warn('[WebSearch] No DB — tentativo diretto senza contatori');
    const month = new Date().toLocaleString('it-IT', { month: 'long', year: 'numeric' });
    for (const provider of PROVIDER_ORDER) {
      if (!PROVIDER_KEY[provider]) continue;
      try {
        const q = (provider === 'brave' || provider === 'google') ? `${query} ${month}` : query;
        const results = await callProvider(provider, q);
        console.log(`[WebSearch] ${provider} OK (no counter)`);
        return results;
      } catch (err) {
        console.warn(`[WebSearch] ${provider} fallito: ${err.message}`);
      }
    }
    return [{ title: 'Ricerca web non disponibile', snippet: 'Nessun provider configurato o tutti in errore.' }];
  }

  // Carica e resetta contatori
  const counters = await loadCounters(db);

  // Appendi mese+anno alla query per Brave e Google (no filtro nativo)
  const now = new Date();
  const monthYear = now.toLocaleString('it-IT', { month: 'long', year: 'numeric' });
  const queryWithDate = (provider) =>
    (provider === 'brave' || provider === 'google') ? `${query} ${monthYear}` : query;

  // Prova ogni provider in ordine
  for (const provider of PROVIDER_ORDER) {
    if (!isProviderAvailable(provider, counters)) {
      continue;
    }

    try {
      const results = await callProvider(provider, queryWithDate(provider));
      await incrementCounter(db, provider);
      console.log(`[WebSearch] ${provider} OK (query: "${query.substring(0, 50)}"${domains.length ? `, domains: ${domains.length}` : ''})`);
      return results;
    } catch (err) {
      console.warn(`[WebSearch] ${provider} errore: ${err.message} — passo al successivo`);
      // NON incrementa contatore se errore
    }
  }

  // Tutti esauriti o in errore
  console.warn('[WebSearch] Tutti i provider esauriti o in errore');
  return [{ title: 'Ricerca web temporaneamente non disponibile', snippet: 'Tutti i provider hanno raggiunto il limite. Riprova domani.' }];
}

// ===================== HANDLE TOOL CALLS =====================

/**
 * Gestisce il ciclo tool_call con LLM (Mistral o Groq)
 * Supporta: web_search + tool DB (get_today_matches, search_matches, get_match_details, get_standings)
 * @param {object} reply - Risposta LLM con tool_calls
 * @param {Array} messages - Storia messaggi
 * @param {object} db - Istanza MongoDB (per tool DB + contatori web search)
 * @param {function} [callFn] - Funzione LLM da usare nei round successivi (default: callMistral)
 * @param {string} [league] - Campionato per filtrare i domini di ricerca (opzionale)
 */
async function handleToolCalls(reply, messages, db, callFn, league) {
  if (!reply.tool_calls || reply.tool_calls.length === 0) {
    return reply.content;
  }

  const { callMistral } = require('./llmService');
  const { executeDbTool } = require('./dbTools');
  const callLLM = callFn || callMistral;
  const MAX_ROUNDS = 5;

  let currentReply = reply;

  for (let round = 0; round < MAX_ROUNDS; round++) {
    if (!currentReply.tool_calls || currentReply.tool_calls.length === 0) {
      return currentReply.content || '(risposta vuota)';
    }

    // Aggiungi la risposta del modello con le tool calls
    messages.push(currentReply);

    for (const tc of currentReply.tool_calls) {
      let args;
      try {
        args = JSON.parse(tc.function.arguments);
      } catch {
        args = typeof tc.function.arguments === 'string' ? { query: tc.function.arguments } : {};
      }

      let content;

      if (tc.function.name === 'web_search') {
        try {
          const results = await searchWeb(args.query, db, league);
          content = JSON.stringify(results);
        } catch (err) {
          content = JSON.stringify([{ title: 'Errore ricerca', snippet: err.message }]);
        }
      } else if (['get_today_matches', 'search_matches', 'get_match_details', 'get_standings'].includes(tc.function.name)) {
        try {
          content = await executeDbTool(db, tc.function.name, args);
        } catch (err) {
          content = JSON.stringify({ error: `Errore query DB: ${err.message}` });
        }
      } else {
        content = JSON.stringify({ error: `Tool non riconosciuto: ${tc.function.name}` });
      }

      messages.push({
        role: 'tool',
        tool_call_id: tc.id,
        name: tc.function.name,
        content,
      });
    }

    // Richiama LLM con i risultati dei tool (maxTokens ridotto per rispettare limiti TPM)
    currentReply = await callLLM(messages, { maxTokens: 1000 });

    // Se non ci sono altre tool_calls, abbiamo la risposta finale
    if (!currentReply.tool_calls || currentReply.tool_calls.length === 0) {
      return currentReply.content || '(risposta vuota)';
    }
  }

  // Raggiunto il limite di round
  return currentReply.content || '(limite round tool raggiunto)';
}

module.exports = { WEB_SEARCH_TOOL, searchWeb, handleToolCalls };
