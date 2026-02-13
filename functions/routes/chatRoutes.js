/**
 * chatRoutes.js — Endpoint Express per il Coach AI
 * 3 endpoint: /chat/context, /chat/message, /chat/search-match
 */
const express = require('express');
const router = express.Router();
const { generateAnalysis, chatWithContext, SYSTEM_PROMPT } = require('../services/llmService');
const { buildMatchContext, searchMatch } = require('../services/contextBuilder');
const { WEB_SEARCH_TOOL, handleToolCalls } = require('../services/webSearch');
const { DB_TOOLS } = require('../services/dbTools');

// ── GET /chat/context?home=X&away=Y&date=Z ──
// Genera analisi iniziale per una partita
router.get('/context', async (req, res) => {
  try {
    const { home, away, date } = req.query;
    if (!home || !away) {
      return res.status(400).json({ success: false, error: 'Missing home or away parameter' });
    }

    const result = await buildMatchContext(req.db, home, away, date || undefined);
    if (!result) {
      return res.json({ success: false, error: 'Match not found' });
    }

    const analysis = await generateAnalysis(result.context);

    res.json({
      success: true,
      analysis,
      source: result.source,
      match_info: result.match_info,
    });
  } catch (error) {
    console.error('[CHAT/CONTEXT]', error.message);
    res.status(500).json({ success: false, error: error.message });
  }
});

// ── POST /chat/message ──
// Messaggio follow-up nella chat (con web search opzionale)
// Funziona anche SENZA home/away — in quel caso risponde come domanda generica
router.post('/message', async (req, res) => {
  try {
    const { home, away, date, message, history } = req.body;
    if (!message) {
      return res.status(400).json({ success: false, error: 'Missing message' });
    }

    // Se home/away forniti, cerca contesto partita
    let contextText = '';
    if (home && away) {
      const result = await buildMatchContext(req.db, home, away, date || undefined);
      if (result) {
        contextText = result.context;
      }
    }

    // Chiama LLM con tutti i tool disponibili (web + DB)
    const tools = [WEB_SEARCH_TOOL, ...DB_TOOLS];
    const reply = await chatWithContext(contextText, message, history || [], tools);

    // Se Mistral ha richiesto tool calls, gestisci il ciclo
    let finalReply;
    if (reply.tool_calls && reply.tool_calls.length > 0) {
      const messages = [{ role: 'system', content: SYSTEM_PROMPT }];
      for (const msg of (history || [])) {
        messages.push({ role: msg.role, content: msg.content });
      }
      const userContent = contextText
        ? `Contesto partita:\n${contextText}\n\nDomanda utente: ${message}`
        : `Domanda utente: ${message}`;
      messages.push({ role: 'user', content: userContent });
      finalReply = await handleToolCalls(reply, messages, req.db);
    } else {
      finalReply = reply.content;
    }

    res.json({ success: true, reply: finalReply });
  } catch (error) {
    console.error('[CHAT/MESSAGE]', error.message);
    res.status(500).json({ success: false, error: error.message });
  }
});

// ── GET /chat/search-match?q=inter ──
// Ricerca fuzzy per nome squadra in tutte le sorgenti
router.get('/search-match', async (req, res) => {
  try {
    const q = req.query.q;
    if (!q || q.length < 2) {
      return res.status(400).json({ success: false, error: 'Query too short (min 2 chars)' });
    }

    const matches = await searchMatch(req.db, q);
    res.json({ success: true, matches });
  } catch (error) {
    console.error('[CHAT/SEARCH]', error.message);
    res.status(500).json({ success: false, error: error.message });
  }
});

module.exports = router;
