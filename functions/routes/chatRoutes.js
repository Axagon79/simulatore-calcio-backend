/**
 * chatRoutes.js — Endpoint Express per il Coach AI
 * 3 endpoint: /chat/context, /chat/message, /chat/search-match
 */
const express = require('express');
const router = express.Router();
const { generateAnalysis, chatWithContext, chatDashboard, generateMatchAnalysisPremium, generateMatchDeepDive, SYSTEM_PROMPT } = require('../services/llmService');
const { buildMatchContext, searchMatch, buildUnifiedContext } = require('../services/contextBuilder');
const { WEB_SEARCH_TOOL, handleToolCalls } = require('../services/webSearch');
const { DB_TOOLS } = require('../services/dbTools');
const { validateChatResponse, extractMatchDataFromContext } = require('../services/responseValidator');

// ── GET /chat/context?home=X&away=Y&date=Z ──
// Genera analisi iniziale per una partita
router.get('/context', async (req, res) => {
  try {
    const { home, away, date, pageContext, isAdmin } = req.query;
    if (!home || !away) {
      return res.status(400).json({ success: false, error: 'Missing home or away parameter' });
    }

    const result = await buildMatchContext(req.db, home, away, date || undefined);
    if (!result) {
      return res.json({ success: false, error: 'Match not found' });
    }

    const userInfo = { pageContext: pageContext || '', isAdmin: isAdmin === 'true' };
    let analysis = await generateAnalysis(result.context, userInfo);

    // Validazione post-partita: controlla la risposta e riprova se viola regole
    const matchData = extractMatchDataFromContext(result.context);
    if (matchData) {
      const MAX_RETRIES = 2;
      for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
        const validation = validateChatResponse(analysis, matchData);
        if (validation.valid) break;
        console.log(`[CHAT/CONTEXT] Validazione fallita (tentativo ${attempt + 1}): ${validation.violations.join(', ')}`);
        // Richiama Mistral con feedback di correzione
        const correctionPrompt = `${result.context}\n\n---\nLA TUA RISPOSTA PRECEDENTE:\n${analysis}\n\n${validation.feedback}`;
        analysis = await generateAnalysis(correctionPrompt, userInfo);
      }
    }

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
    const { home, away, date, message, history, pageContext, isAdmin } = req.body;
    if (!message) {
      return res.status(400).json({ success: false, error: 'Missing message' });
    }

    // ── Dashboard: bot informativo (no tools, prompt dedicato) ──
    if (pageContext === 'dashboard') {
      const reply = await chatDashboard(message, history || []);
      return res.json({ success: true, reply });
    }

    // ── Altre pagine: Coach AI completo con tools ──
    const userInfo = { pageContext: pageContext || '', isAdmin: !!isAdmin };

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
    const reply = await chatWithContext(contextText, message, history || [], tools, userInfo);

    // Se Mistral ha richiesto tool calls, gestisci il ciclo
    let finalReply;
    if (reply.tool_calls && reply.tool_calls.length > 0) {
      const messages = [{ role: 'system', content: SYSTEM_PROMPT }];
      for (const msg of (history || [])) {
        messages.push({ role: msg.role, content: msg.content });
      }
      const pageLine = userInfo.pageContext ? `\n[Pagina: ${userInfo.pageContext} | ${userInfo.isAdmin ? 'Admin' : 'Utente'}]` : '';
      const userContent = contextText
        ? `Contesto partita:\n${contextText}${pageLine}\n\nDomanda utente: ${message}`
        : `${pageLine}\nDomanda utente: ${message}`;
      messages.push({ role: 'user', content: userContent });
      finalReply = await handleToolCalls(reply, messages, req.db);
    } else {
      finalReply = reply.content;
    }

    // Validazione post-partita per i follow-up
    const matchDataMsg = extractMatchDataFromContext(contextText);
    if (matchDataMsg && finalReply) {
      const MAX_RETRIES = 2;
      for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
        const validation = validateChatResponse(finalReply, matchDataMsg);
        if (validation.valid) break;
        console.log(`[CHAT/MESSAGE] Validazione fallita (tentativo ${attempt + 1}): ${validation.violations.join(', ')}`);
        // Richiama con feedback
        const correctionMsg = `${validation.feedback}\n\nRispondi alla domanda dell'utente: ${message}`;
        const retryReply = await chatWithContext(contextText, correctionMsg, history || [], [], userInfo);
        finalReply = retryReply.content || finalReply;
      }
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

// ── POST /chat/match-analysis-premium ──
// Analisi Premium AI via Mistral (solo admin per ora)
router.post('/match-analysis-premium', async (req, res) => {
  try {
    const { home, away, date, isAdmin, section } = req.body;

    if (!home || !away || !date) {
      return res.status(400).json({ success: false, error: 'Missing home, away or date' });
    }

    if (isAdmin !== true && isAdmin !== 'true') {
      return res.status(403).json({ success: false, error: 'Premium analysis is admin-only' });
    }

    // Check se analisi già salvata su MongoDB (one-shot: non richiamare Mistral)
    const existing = await req.db.collection('daily_predictions_unified')
      .findOne({ home, away, date }, { projection: { analysis_premium: 1 } });

    if (existing && existing.analysis_premium) {
      return res.json({ success: true, analysis: existing.analysis_premium, cached: true });
    }

    const result = await buildUnifiedContext(req.db, home, away, date, section);
    if (!result) {
      return res.json({ success: false, error: 'Match not found in unified predictions' });
    }

    const analysis = await generateMatchAnalysisPremium(result.context);

    // Salva su MongoDB per non richiamare Mistral al prossimo reload
    await req.db.collection('daily_predictions_unified')
      .updateOne({ home, away, date }, { $set: { analysis_premium: analysis } });

    res.json({ success: true, analysis, cached: false });
  } catch (error) {
    console.error('[CHAT/MATCH-ANALYSIS-PREMIUM]', error.message);
    res.status(500).json({ success: false, error: error.message });
  }
});

// ── POST /chat/match-deepdive ──
// Analisi "Scout" con ricerca web (admin + premium)
router.post('/match-deepdive', async (req, res) => {
  // Timeout più lungo per ricerche web (65s)
  if (req.setTimeout) req.setTimeout(65000);

  try {
    const { home, away, date, league, isAdmin, forceRefresh } = req.body;

    if (!home || !away || !date) {
      return res.status(400).json({ success: false, error: 'Missing home, away or date' });
    }

    // Accesso: admin o premium
    if (isAdmin !== true && isAdmin !== 'true') {
      return res.status(403).json({ success: false, error: 'Scout analysis is premium-only' });
    }

    // Check cache su MongoDB
    const existing = await req.db.collection('daily_predictions_unified')
      .findOne({ home, away, date }, { projection: { analysis_deepdive: 1, analysis_deepdive_ts: 1, time: 1 } });

    if (existing && existing.analysis_deepdive && !forceRefresh) {
      const cacheTs = existing.analysis_deepdive_ts ? new Date(existing.analysis_deepdive_ts).getTime() : 0;
      const sixHoursAgo = Date.now() - (6 * 60 * 60 * 1000);

      // Cache auto-refresh se < 3 ore al fischio d'inizio
      let cacheValid = cacheTs > sixHoursAgo;
      if (cacheValid && existing.time) {
        try {
          const matchDateTime = new Date(`${date}T${existing.time}:00`);
          const hoursToKickoff = (matchDateTime.getTime() - Date.now()) / (1000 * 60 * 60);
          if (hoursToKickoff > 0 && hoursToKickoff < 3) {
            cacheValid = false; // Auto-refresh per info più fresche
          }
        } catch (_) { /* ignore parse error */ }
      }

      if (cacheValid) {
        return res.json({ success: true, analysis: existing.analysis_deepdive, cached: true, ts: existing.analysis_deepdive_ts });
      }
    }

    // Genera deepdive con ricerca web
    const analysis = await generateMatchDeepDive(home, away, date, league || '', req.db);

    if (!analysis || analysis === '(risposta vuota)' || analysis === '(limite round tool raggiunto)') {
      return res.json({ success: false, error: 'La ricerca web non ha prodotto risultati. Riprova tra qualche minuto.' });
    }

    // Salva su MongoDB con timestamp
    const now = new Date().toISOString();
    await req.db.collection('daily_predictions_unified')
      .updateOne({ home, away, date }, {
        $set: {
          analysis_deepdive: analysis,
          analysis_deepdive_ts: now
        }
      });

    res.json({ success: true, analysis, cached: false, ts: now });
  } catch (error) {
    console.error('[CHAT/MATCH-DEEPDIVE]', error.message);

    if (error.message?.includes('aborted') || error.name === 'AbortError') {
      return res.status(504).json({ success: false, error: 'Timeout — la ricerca ha impiegato troppo tempo. Riprova.' });
    }

    res.status(500).json({ success: false, error: error.message });
  }
});

module.exports = router;
