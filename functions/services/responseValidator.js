/**
 * responseValidator.js — Validatore risposte Mistral (chatbot + Fase 2)
 *
 * Controlla le risposte generate da Mistral contro regole rigide.
 * Se una regola viene violata, genera un feedback specifico per il retry.
 * Max 2 tentativi di correzione.
 *
 * Due modalità:
 *   validateChatResponse(text, matchData) — per il chatbot post-partita
 *   validateAnalysis(text, numericalScore) — per la Fase 2 (futuro)
 */

// ═══════════════════════════════════════════════════════════
// REGOLE CHATBOT POST-PARTITA
// ═══════════════════════════════════════════════════════════

// Termini tecnici interni MAI visibili all'utente
const FORBIDDEN_TERMS = [
  /\bxG\b/i,
  /\bexpected goals?\b/i,
  /\bMonte Carlo\b/i,
  /\bcicli\b/i,
  /\bTier [A-D]\b/i,
  /\bmodificator[ei]\b/i,
  /\bindicator[ei]\b/i,
  /\bcoerenza col campo\b/i,
  /\bscore di coerenza\b/i,
  /\bcoherence.score\b/i,
  /\befficien(za|cy).anomal[ae]\b/i,
  /\bpossesso sterile\b/i,        // termine tecnico interno, descrivilo invece
  /\bself.check\b/i,
  /\bFase [123]\b/i,
  /\bSofaScore\b/i,               // non rivelare la fonte
  /\bpost_match/i,
  /\bthread.score\b/i,
  /\bvolume.score\b/i,
  /\braw.score\b/i,
];

// Pattern numeri interni (tipo 69/100, 50.3/100)
const INTERNAL_NUMBERS = /\b\d{1,3}(?:\.\d+)?\/100\b/;

// Pattern "con solo X cicli" — critica al sistema
const SYSTEM_CRITICISM = [
  /con solo \d+ cicli/i,
  /il (sistema|modello|algoritmo) (ha |non ha |non )(sbagliato|sottovalutato|sovrastimato|previsto male)/i,
  /simulazione.{0,20}non.{0,15}(attendibil|affidabil|sufficient)/i,
  /la simulazione.{0,10}(solo|appena|soltanto)/i,
];

// Lunghezza massima (in parole)
const MAX_WORDS_POST_MATCH = 150;

// Massimo numeri ammessi nella risposta (esclusi risultato e quote)
const MAX_NUMBERS = 5;


/**
 * Valida una risposta del chatbot per partite già concluse.
 * @param {string} text — Risposta di Mistral
 * @param {object} matchData — { home, away, realScore, pronostici: [{tipo, pronostico, esito}] }
 * @returns {{ valid: boolean, violations: string[], feedback: string }}
 */
function validateChatResponse(text, matchData) {
  const violations = [];

  if (!text || text.trim().length === 0) {
    return { valid: false, violations: ['empty_response'], feedback: 'La risposta e vuota. Genera una risposta.' };
  }

  // 1. Termini tecnici vietati
  for (const regex of FORBIDDEN_TERMS) {
    if (regex.test(text)) {
      const match = text.match(regex);
      violations.push(`forbidden_term: "${match[0]}"`);
    }
  }

  // 2. Numeri interni (X/100)
  if (INTERNAL_NUMBERS.test(text)) {
    const matches = text.match(new RegExp(INTERNAL_NUMBERS.source, 'g'));
    violations.push(`internal_numbers: ${matches.join(', ')}`);
  }

  // 3. Critica al sistema
  for (const regex of SYSTEM_CRITICISM) {
    if (regex.test(text)) {
      const match = text.match(regex);
      violations.push(`system_criticism: "${match[0]}"`);
    }
  }

  // 4. Esito pronostico chiaro
  // Se abbiamo dati sui pronostici, verifica che la risposta menzioni l'esito
  if (matchData && matchData.pronostici && matchData.pronostici.length > 0) {
    const hasOutcome = /\b(centrat[oa]|sbaglia[ot]|pres[oa]|giusto|sbagliato|azzeccat[oa]|andato bene|andata bene|andato male|andata male|vint[oa]|pers[oa]|indovinat[oa]|funzionato|non ha funzionato)\b/i.test(text);
    if (!hasOutcome) {
      violations.push('missing_outcome');
    }
  }

  // 5. Troppo lungo
  const wordCount = text.split(/\s+/).length;
  if (wordCount > MAX_WORDS_POST_MATCH) {
    violations.push(`too_long: ${wordCount} parole (max ${MAX_WORDS_POST_MATCH})`);
  }

  // 6. Troppi numeri (conta numeri nella risposta, escludi risultato tipo "2-1" e quote tipo "@1.73")
  const textWithoutScores = text.replace(/\d+-\d+/g, '').replace(/@\d+\.\d+/g, '');
  const numberMatches = textWithoutScores.match(/\b\d+(?:\.\d+)?%?\b/g) || [];
  // Filtra via numeri piccoli e comuni (0, 1, 2 isolati che fanno parte del discorso)
  const significantNumbers = numberMatches.filter(n => {
    const val = parseFloat(n);
    return val > 2 || n.includes('%');
  });
  if (significantNumbers.length > MAX_NUMBERS) {
    violations.push(`too_many_numbers: ${significantNumbers.length} (max ${MAX_NUMBERS})`);
  }

  // Genera feedback per il retry
  if (violations.length === 0) {
    return { valid: true, violations: [], feedback: '' };
  }

  const feedbackParts = [];

  if (violations.some(v => v.startsWith('forbidden_term'))) {
    feedbackParts.push('HAI USATO TERMINI TECNICI INTERNI. Riscrivi senza nominare: xG, Monte Carlo, cicli, Tier, modificatori, indicatori, score di coerenza, SofaScore. Usa linguaggio da commentatore sportivo.');
  }

  if (violations.some(v => v.startsWith('internal_numbers'))) {
    feedbackParts.push('HAI MOSTRATO NUMERI INTERNI (tipo X/100). L\'utente non deve vedere scale interne. Traduci in linguaggio naturale.');
  }

  if (violations.some(v => v.startsWith('system_criticism'))) {
    feedbackParts.push('HAI CRITICATO IL SISTEMA. Tu SEI il sistema. Non dire mai "la simulazione non era attendibile" o "il modello ha sbagliato". Se il pronostico era sbagliato, spiega cosa e successo in campo.');
  }

  if (violations.some(v => v === 'missing_outcome')) {
    feedbackParts.push('NON HAI DETTO CHIARAMENTE SE IL PRONOSTICO ERA GIUSTO O SBAGLIATO. La prima cosa che l\'utente vuole sapere e: ha funzionato si o no? Dillo subito nelle prime parole.');
  }

  if (violations.some(v => v.startsWith('too_long'))) {
    feedbackParts.push('RISPOSTA TROPPO LUNGA. Massimo 150 parole. Sii diretto e conciso. L\'utente vuole capire in 10 secondi.');
  }

  if (violations.some(v => v.startsWith('too_many_numbers'))) {
    feedbackParts.push('TROPPI NUMERI. Massimo 2-3 dati numerici (tiri in porta, possesso). Tutto il resto va descritto a parole.');
  }

  const feedback = 'CORREZIONE RICHIESTA — La tua risposta viola queste regole:\n' + feedbackParts.join('\n') + '\n\nRiscrivi la risposta rispettando TUTTE le regole. Stessa analisi, linguaggio diverso.';

  return { valid: false, violations, feedback };
}


/**
 * Valida un'analisi automatica Fase 2 (futuro).
 * Controlla che lo score Mistral sia coerente con il calcolo numerico.
 * @param {string} text — Analisi testuale di Mistral
 * @param {number} numericalScore — Score calcolato dalla Fase 1
 * @param {number} tolerance — Margine accettabile (default ±20)
 * @returns {{ valid: boolean, violations: string[], feedback: string }}
 */
function validateAnalysis(text, numericalScore, tolerance = 20) {
  // Fase 2 — placeholder, da implementare
  // Per ora ritorna sempre valid
  return { valid: true, violations: [], feedback: '' };
}


/**
 * Estrae dati match dal contesto per la validazione.
 * Parsa il testo di contesto per trovare pronostici e esiti.
 * @param {string} contextText — Contesto generato da contextBuilder
 * @returns {object|null} matchData per validateChatResponse
 */
function extractMatchDataFromContext(contextText) {
  if (!contextText) return null;

  // Cerca se la partita e finita (ha "ESITI PRONOSTICI")
  if (!contextText.includes('ESITI PRONOSTICI') && !contextText.includes('RISULTATO FINALE')) {
    return null; // partita non conclusa, nessuna validazione post-partita
  }

  const matchData = { pronostici: [] };

  // Estrai home/away
  const matchLine = contextText.match(/PARTITA:\s*(.+?)\s+vs\s+(.+)/);
  if (matchLine) {
    matchData.home = matchLine[1].trim();
    matchData.away = matchLine[2].trim();
  }

  // Estrai risultato
  const scoreLine = contextText.match(/RISULTATO FINALE:.+?(\d+)\s*[-:]\s*(\d+)/);
  if (scoreLine) {
    matchData.realScore = `${scoreLine[1]}-${scoreLine[2]}`;
  }

  // Estrai esiti pronostici
  const esitoRegex = /(SEGNO|GOL|DOPPIA_CHANCE|MG)\s+(.+?)\s+@[\d.?]+\s+→\s+(CENTRATO|SBAGLIATO)/g;
  let m;
  while ((m = esitoRegex.exec(contextText)) !== null) {
    matchData.pronostici.push({
      tipo: m[1],
      pronostico: m[2].trim(),
      esito: m[3] === 'CENTRATO',
    });
  }

  return matchData.pronostici.length > 0 ? matchData : null;
}


module.exports = { validateChatResponse, validateAnalysis, extractMatchDataFromContext };
