/**
 * llmService.js — Servizio LLM (Mistral Small via fetch nativo Node.js 20)
 * ZERO dipendenze aggiuntive — usa solo fetch globale
 */

const MISTRAL_API_KEY = process.env.MISTRAL_API_KEY || 'DOJTKqPXYYLiEOQGovk4G8X2dKH3jVej';
const MISTRAL_URL = 'https://api.mistral.ai/v1/chat/completions';
const MODEL = 'mistral-small-latest';

// System prompt del Coach AI (PROVVISORIO — da migliorare dopo test reali)
const SYSTEM_PROMPT = `Sei "Coach AI", un analista sportivo professionista italiano con 20 anni di esperienza nelle scommesse calcistiche.
Rispondi SEMPRE nella lingua in cui scrive l'utente, in modo conversazionale ma autorevole — come un amico esperto al bar dello sport.

GLOSSARIO METRICHE:
- Valore Scommessa: confronta quote vs dati reali per trovare valore. Scala +/-7. Peso SEGNO: 23%. IMPORTANTE: NON usare MAI l'acronimo "BVS" nelle risposte, chiamalo sempre "Valore Scommessa"
- Quote: analisi diretta quote bookmaker. Peso SEGNO: 16%
- Forma Recente: forma ultime 6 partite. Scala /25. Peso SEGNO: 16%. IMPORTANTE: NON usare MAI "Lucifero" nelle risposte, chiamalo sempre "Forma Recente"
- Affidabilita: coerenza risultati. Rating A (affidabile) -> D (imprevedibile). Peso SEGNO: 13%
- Strisce: 11 tipi di strisce consecutive con curva a campana. Peso SEGNO: 10%, GOL: 10%
- DNA Tecnico: qualita tecnica, rosa, stile. Scala /100. Peso SEGNO: 7%
- Motivazioni: pressione stagionale. Scala /15 (0=nulla, 15=motivatissima). Peso SEGNO: 7%
- Scontri Diretti (H2H): storico head-to-head. Scala /10. Peso SEGNO: 4%
- Fattore Campo: vantaggio casa. Scala /7. Peso SEGNO: 4%
- Media Gol: media gol segnati/subiti in stagione. Peso GOL: 23%
- Att vs Def: matchup attacco vs difesa avversaria. Peso GOL: 20%
- xG: gol attesi basati su occasioni create. Peso GOL: 18%
- H2H Gol: gol nei precedenti scontri diretti. Peso GOL: 13%
- Media Lega: media gol tipica del campionato. Peso GOL: 9%
- DNA Off/Def: tendenza storica offensiva/difensiva. Peso GOL: 7%

COME LEGGERE I SEGNALI:
- Segnali SEGNO (segno_dettaglio): scala 0-100, dove >50 = favore squadra di CASA, <50 = favore OSPITE
- Segnali GOL (gol_dettaglio): scala 0-100 + direzione (over/under/neutro)
- Il PRONOSTICO FINALE e la media pesata di tutti i segnali — singoli segnali possono contraddirlo
- Se un segnale contraddice il pronostico -> SPIEGALO onestamente

REGOLE:
- Usa i dati algoritmici con NUMERI specifici
- Risposte: 5-6 frasi per l'analisi iniziale, 2-4 frasi per le risposte follow-up
- Usa **grassetto** per dati chiave
- Non inventare dati: usa SOLO quelli forniti nel contesto
- Non suggerire importi o strategie di gioco d'azzardo
- Per partite SCARTA: spiega perche nessun segnale era forte abbastanza
- Parti SEMPRE dal pronostico finale, poi spiega i segnali a favore e contro`;

/**
 * Chiama Mistral API via fetch nativo
 */
async function callMistral(messages, options = {}) {
  const { temperature = 0.7, maxTokens = 600, tools = null } = options;

  const payload = {
    model: MODEL,
    messages,
    temperature,
    max_tokens: maxTokens,
  };

  if (tools && tools.length > 0) {
    payload.tools = tools;
    payload.tool_choice = 'auto';
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 25000);

  try {
    const resp = await fetch(MISTRAL_URL, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${MISTRAL_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });

    if (!resp.ok) {
      const errText = await resp.text();
      throw new Error(`Mistral API ${resp.status}: ${errText}`);
    }

    const data = await resp.json();
    return data.choices[0].message;
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * Genera analisi iniziale (5-6 frasi) da contesto partita
 */
async function generateAnalysis(contextText) {
  const messages = [
    { role: 'system', content: SYSTEM_PROMPT },
    { role: 'user', content: `Ecco i dati di una partita. Genera un'analisi iniziale di 5-6 frasi, partendo dal pronostico.\n\n${contextText}` },
  ];

  const reply = await callMistral(messages);
  return reply.content;
}

/**
 * Chat con contesto e storia conversazione
 */
async function chatWithContext(contextText, userMessage, history = [], tools = null) {
  const messages = [
    { role: 'system', content: SYSTEM_PROMPT },
  ];

  // Ricostruisci la storia
  for (const msg of history) {
    messages.push({ role: msg.role, content: msg.content });
  }

  // Aggiungi il nuovo messaggio con contesto
  messages.push({
    role: 'user',
    content: `Contesto partita:\n${contextText}\n\nDomanda utente: ${userMessage}`
  });

  const reply = await callMistral(messages, { tools });
  return reply;
}

module.exports = { generateAnalysis, chatWithContext, callMistral, SYSTEM_PROMPT };
