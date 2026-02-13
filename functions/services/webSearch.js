/**
 * webSearch.js — Ricerca web on-demand via Brave Search API
 * Mistral decide autonomamente SE cercare sul web (function calling)
 * Brave Search: 2000 query/mese gratis, no carta di credito
 */

const BRAVE_API_KEY = process.env.BRAVE_API_KEY || '';
const BRAVE_URL = 'https://api.search.brave.com/res/v1/web/search';

// Tool definition per Mistral function calling
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

/**
 * Esegue ricerca web via Brave Search API
 */
async function searchWeb(query) {
  if (!BRAVE_API_KEY) {
    return [{ title: 'Ricerca web non configurata', snippet: 'API key Brave Search non impostata. Configurare BRAVE_API_KEY.' }];
  }

  const url = `${BRAVE_URL}?q=${encodeURIComponent(query)}&count=3&search_lang=it`;

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

    if (!resp.ok) {
      throw new Error(`Brave Search API ${resp.status}`);
    }

    const data = await resp.json();
    return (data.web?.results || []).slice(0, 3).map(r => ({
      title: r.title,
      snippet: r.description,
      url: r.url,
    }));
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * Gestisce il ciclo tool_call con Mistral
 * Supporta: web_search + tool DB (get_today_matches, search_matches, get_match_details)
 * @param {object} reply - Risposta Mistral con tool_calls
 * @param {Array} messages - Storia messaggi
 * @param {object} db - Istanza MongoDB (per tool DB)
 */
async function handleToolCalls(reply, messages, db) {
  if (!reply.tool_calls || reply.tool_calls.length === 0) {
    return reply.content;
  }

  const { callMistral } = require('./llmService');
  const { executeDbTool } = require('./dbTools');
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
          const results = await searchWeb(args.query);
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

    // Richiama Mistral con i risultati dei tool
    currentReply = await callMistral(messages);

    // Se non ci sono altre tool_calls, abbiamo la risposta finale
    if (!currentReply.tool_calls || currentReply.tool_calls.length === 0) {
      return currentReply.content || '(risposta vuota)';
    }
  }

  // Raggiunto il limite di round
  return currentReply.content || '(limite round tool raggiunto)';
}

module.exports = { WEB_SEARCH_TOOL, searchWeb, handleToolCalls };
