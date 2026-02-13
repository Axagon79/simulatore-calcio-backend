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
 * Se Mistral vuole cercare sul web, esegue la ricerca e ritorna la risposta finale
 */
async function handleToolCalls(reply, messages) {
  if (!reply.tool_calls || reply.tool_calls.length === 0) {
    return reply.content;
  }

  const { callMistral } = require('./llmService');

  // Aggiungi la risposta del modello con le tool calls
  messages.push(reply);

  for (const tc of reply.tool_calls) {
    if (tc.function.name === 'web_search') {
      let args;
      try {
        args = JSON.parse(tc.function.arguments);
      } catch {
        args = { query: tc.function.arguments };
      }

      let results;
      try {
        results = await searchWeb(args.query);
      } catch (err) {
        results = [{ title: 'Errore ricerca', snippet: err.message }];
      }

      messages.push({
        role: 'tool',
        tool_call_id: tc.id,
        name: 'web_search',
        content: JSON.stringify(results),
      });
    }
  }

  // Richiama Mistral con i risultati della ricerca
  const finalReply = await callMistral(messages);
  return finalReply.content;
}

module.exports = { WEB_SEARCH_TOOL, searchWeb, handleToolCalls };
