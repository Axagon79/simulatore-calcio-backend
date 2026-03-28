/**
 * postMatchAnalysis.js — Analisi post-partita strutturata (pattern Ticket AI)
 *
 * Stesso flusso dei ticket:
 * 1. Backend prepara i FATTI (stats reali, esiti, verdetti)
 * 2. Mistral genera JSON strutturato (non testo libero)
 * 3. Backend valida il JSON
 * 4. Se errore → feedback specifico + retry
 * 5. Backend assembla il testo finale dal JSON validato
 */

const { callMistral } = require('./llmService');

// ═══════════════════════════════════════════════════════════
// PROMPT — Mistral genera JSON, non testo libero
// ═══════════════════════════════════════════════════════════

const POST_MATCH_PROMPT = `Sei un commentatore sportivo italiano. Ricevi i fatti di una partita gia terminata e devi riscriverli in modo naturale e discorsivo.

REGOLE ASSOLUTE:
- Restituisci SOLO un oggetto JSON valido. Nessun testo prima o dopo. Nessun markdown.
- NON inventare nulla. Usa SOLO i fatti che ti vengono forniti.
- NON usare MAI: xG, Monte Carlo, cicli, Tier, modificatori, indicatori, score, SofaScore, coerenza, confidence
- NON mostrare MAI numeri tipo X/100 o percentuali interne
- Puoi citare SOLO: risultato (2-1), tiri in porta, grandi occasioni, possesso %, pali, quote (@1.73)
- Parla come un amico esperto al bar, non come un data analyst
- Ogni campo deve essere 15-40 parole. Non troppo corto, non troppo lungo.

FORMATO OUTPUT — JSON con 4 campi:
{
  "esito": "una frase che dice subito se il pronostico ha funzionato o no",
  "campo": "2 frasi su cosa e successo in campo basandoti sulle statistiche fornite",
  "giudizio": "1-2 frasi che dicono se il pronostico AVEVA SENSO oppure no, indipendentemente dal risultato. Usa il VERDETTO fornito nei fatti come guida",
  "chiusura": "1 frase di chiusura che lega tutto insieme"
}

IL CAMPO "giudizio" E' FONDAMENTALE — spiega se la scelta era logica o meno:
- Se il VERDETTO dice "confermava il pronostico" e il pronostico era CENTRATO → "Scelta azzeccata e confermata dal campo"
- Se il VERDETTO dice "confermava il pronostico" ma era SBAGLIATO → "La scelta era giusta, il campo ci dava ragione, ma il calcio ha deciso diversamente"
- Se il VERDETTO dice "pura fortuna" → "Onestamente ci e andata bene, il campo diceva altro"
- Se il VERDETTO dice "pronostico sbagliato" → "La scelta non era supportata da quello che si vedeva in campo"

ESEMPI DI TONO GIUSTO:

Esempio 1 (SEGNO 1 centrato, dominio netto):
{
  "esito": "Pronostico centrato, vittoria netta e meritata dei padroni di casa.",
  "campo": "Hanno dominato dall'inizio alla fine con 8 tiri in porta contro 1 solo dell'avversario. Due grandi occasioni create e zero rischi dietro.",
  "giudizio": "Scelta perfetta: quando una squadra domina cosi tanto, il segno 1 e quasi obbligato. I numeri confermano tutto.",
  "chiusura": "Pronostico giusto per i motivi giusti — non c'e soddisfazione migliore."
}

Esempio 2 (Under 2.5 centrato, partita morta):
{
  "esito": "Under azzeccato, partita davvero povera di emozioni.",
  "campo": "Pochissime occasioni da entrambe le parti. Nessuna delle due squadre ha mai tirato con convinzione in porta, il gioco si e fermato a centrocampo.",
  "giudizio": "La scelta dell'Under era praticamente obbligata guardando come si e sviluppata la partita. Zero pericoli veri.",
  "chiusura": "Una di quelle gare dove il pallone non voleva proprio entrare — pronostico coerente al 100%."
}

Esempio 3 (SEGNO 2 sbagliato, ma il campo diceva 2):
{
  "esito": "Pronostico sbagliato, ma c'e stata tanta sfortuna.",
  "campo": "La squadra ospite ha creato molto di piu: piu tiri in porta, piu occasioni nitide, e ha colpito anche un palo. Il portiere avversario ha fatto due miracoli.",
  "giudizio": "La scelta era giustissima: il campo diceva chiaramente che gli ospiti meritavano di vincere. A volte il calcio non premia chi gioca meglio.",
  "chiusura": "Sconfitta che brucia perche la logica era dalla nostra parte — pura sfortuna."
}

Esempio 4 (GG centrato, ma fortunato):
{
  "esito": "Pronostico centrato, anche se con un pizzico di fortuna.",
  "campo": "Una delle due squadre ha segnato con l'unico tiro in porta di tutta la partita, senza creare praticamente nulla di pericoloso.",
  "giudizio": "Diciamolo onestamente: il GG e uscito piu per un episodio che per una partita aperta. La scelta non era sbagliata, ma i numeri non la supportavano fino in fondo.",
  "chiusura": "Risultato positivo, ma la prossima volta con questi numeri l'NG sarebbe stato piu logico."
}`;


// ═══════════════════════════════════════════════════════════
// PREPARA I FATTI — Il backend fa il lavoro pesante
// ═══════════════════════════════════════════════════════════

/**
 * Prepara il contesto dei fatti per Mistral da un pronostico concluso.
 * @param {object} params
 * @param {string} params.home
 * @param {string} params.away
 * @param {string} params.realScore - es. "5-0"
 * @param {string} params.tipo - es. "SEGNO", "GOL"
 * @param {string} params.pronostico - es. "1", "Over 2.5", "GG"
 * @param {boolean} params.esito - true = centrato, false = sbagliato
 * @param {object} params.postMatchAnalysis - { coherence_score, verdict, modifiers_applied }
 * @param {object} params.homeStats - stats SofaScore
 * @param {object} params.awayStats - stats SofaScore
 * @returns {string} Testo fatti per Mistral
 */
function buildFactsForMistral(params) {
  const { home, away, realScore, tipo, pronostico, esito, postMatchAnalysis, homeStats, awayStats } = params;

  const lines = [];
  lines.push(`PARTITA: ${home} vs ${away}`);
  lines.push(`RISULTATO: ${realScore}`);
  lines.push(`PRONOSTICO: ${tipo} ${pronostico} → ${esito ? 'CENTRATO' : 'SBAGLIATO'}`);

  // Verdetto coerenza tradotto in linguaggio semplice
  if (postMatchAnalysis) {
    const v = postMatchAnalysis.verdict;
    const s = postMatchAnalysis.coherence_score;
    let verdetto;
    if (esito) {
      // HIT
      if (v === 'COERENTE' || v === 'RAGIONEVOLE') verdetto = 'Il campo confermava il pronostico — vittoria meritata';
      else if (v === 'INCERTO') verdetto = 'Partita equilibrata, poteva andare in entrambi i modi';
      else if (v === 'FORZATO') verdetto = 'Il campo non lo confermava del tutto — un po\' di fortuna';
      else verdetto = 'Il campo diceva il contrario — pura fortuna';
    } else {
      // MISS
      if (v === 'COERENTE' || v === 'RAGIONEVOLE') verdetto = 'Il campo confermava il pronostico — pura sfortuna';
      else if (v === 'INCERTO') verdetto = 'Partita equilibrata, poteva andare in entrambi i modi';
      else if (v === 'FORZATO') verdetto = 'Il pronostico non era supportato dal campo';
      else verdetto = 'Il campo diceva chiaramente il contrario — pronostico sbagliato';
    }
    lines.push(`VERDETTO: ${verdetto}`);
  }

  // Stats chiave tradotte in fatti leggibili
  if (homeStats && awayStats) {
    const facts = [];

    const hSot = homeStats.shots_on_target ?? '?';
    const aSot = awayStats.shots_on_target ?? '?';
    facts.push(`Tiri in porta: ${home} ${hSot}, ${away} ${aSot}`);

    const hBc = homeStats.big_chances;
    const aBc = awayStats.big_chances;
    if (hBc != null || aBc != null) {
      facts.push(`Grandi occasioni: ${home} ${hBc ?? 0}, ${away} ${aBc ?? 0}`);
    }

    const hBcm = homeStats.big_chances_missed;
    const aBcm = awayStats.big_chances_missed;
    if ((hBcm != null && hBcm > 0) || (aBcm != null && aBcm > 0)) {
      facts.push(`Occasioni sprecate: ${home} ${hBcm ?? 0}, ${away} ${aBcm ?? 0}`);
    }

    const hPoss = homeStats.possession;
    const aPoss = awayStats.possession;
    if (hPoss != null) {
      facts.push(`Possesso: ${home} ${hPoss}%, ${away} ${aPoss ?? '?'}%`);
    }

    const hWood = homeStats.hit_woodwork;
    const aWood = awayStats.hit_woodwork;
    if ((hWood != null && hWood > 0) || (aWood != null && aWood > 0)) {
      facts.push(`Pali/traverse: ${home} ${hWood ?? 0}, ${away} ${aWood ?? 0}`);
    }

    const hSaves = homeStats.big_saves;
    const aSaves = awayStats.big_saves;
    if ((hSaves != null && hSaves > 0) || (aSaves != null && aSaves > 0)) {
      facts.push(`Grandi parate: ${home} ${hSaves ?? 0}, ${away} ${aSaves ?? 0}`);
    }

    const hRed = homeStats.red_cards;
    const aRed = awayStats.red_cards;
    if ((hRed != null && hRed > 0) || (aRed != null && aRed > 0)) {
      facts.push(`Espulsioni: ${home} ${hRed ?? 0}, ${away} ${aRed ?? 0}`);
    }

    const hShots = homeStats.total_shots;
    const aShots = awayStats.total_shots;
    if (hShots != null) {
      facts.push(`Tiri totali: ${home} ${hShots}, ${away} ${aShots ?? '?'}`);
    }

    lines.push(`\nSTATISTICHE CAMPO:`);
    for (const f of facts) {
      lines.push(`- ${f}`);
    }
  }

  return lines.join('\n');
}


// ═══════════════════════════════════════════════════════════
// CHIAMA MISTRAL + VALIDA JSON + RETRY
// ═══════════════════════════════════════════════════════════

const REQUIRED_FIELDS = ['esito', 'campo', 'giudizio', 'chiusura'];
const MAX_WORDS_PER_FIELD = 50;

/**
 * Valida il JSON generato da Mistral.
 * @returns {{ valid: boolean, errors: string[] }}
 */
function validatePostMatchJSON(parsed) {
  const errors = [];

  // Campi obbligatori
  for (const field of REQUIRED_FIELDS) {
    if (!parsed[field] || typeof parsed[field] !== 'string' || parsed[field].trim().length === 0) {
      errors.push(`Campo "${field}" mancante o vuoto`);
    }
  }

  // Termini vietati
  const forbidden = [/\bxG\b/i, /\bMonte Carlo\b/i, /\bcicli\b/i, /\bTier [A-D]\b/i,
    /\bmodificator[ei]\b/i, /\bSofaScore\b/i, /\bcoerenza\b/i, /\bconfidence\b/i,
    /\bscore\b/i, /\bindicator[ei]\b/i, /\/100\b/];

  const fullText = `${parsed.esito || ''} ${parsed.campo || ''} ${parsed.chiusura || ''}`;
  for (const regex of forbidden) {
    if (regex.test(fullText)) {
      const match = fullText.match(regex);
      errors.push(`Termine vietato: "${match[0]}". Usa linguaggio naturale.`);
    }
  }

  // Lunghezza campi
  for (const field of REQUIRED_FIELDS) {
    const text = parsed[field] || '';
    const words = text.split(/\s+/).length;
    if (words > MAX_WORDS_PER_FIELD) {
      errors.push(`Campo "${field}" troppo lungo: ${words} parole (max ${MAX_WORDS_PER_FIELD})`);
    }
  }

  return { valid: errors.length === 0, errors };
}


/**
 * Genera analisi post-partita strutturata per un singolo pronostico.
 * Pattern identico ai ticket: JSON obbligatorio → validazione → retry con feedback.
 * @returns {string} Testo finale assemblato, pronto per l'utente
 */
async function generatePostMatchComment(params) {
  const facts = buildFactsForMistral(params);

  const MAX_RETRIES = 2;
  let lastErrors = [];

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    let userMessage = `Ecco i fatti della partita:\n\n${facts}\n\nGenera il JSON.`;

    // Se retry, aggiungi feedback errori
    if (attempt > 0 && lastErrors.length > 0) {
      userMessage += `\n\nCORREZIONE RICHIESTA — Il tuo JSON precedente aveva questi errori:\n`;
      for (const err of lastErrors) {
        userMessage += `- ${err}\n`;
      }
      userMessage += `\nCorreggi e restituisci SOLO il JSON valido.`;
    }

    try {
      const response = await callMistral([
        { role: 'system', content: POST_MATCH_PROMPT },
        { role: 'user', content: userMessage },
      ], { temperature: 0.3, max_tokens: 500 });

      let content = (response.content || response).toString().trim();

      // Rimuovi markdown wrapping
      if (content.startsWith('```')) {
        content = content.replace(/^```(?:json)?\s*/, '').replace(/\s*```$/, '');
      }

      const parsed = JSON.parse(content);
      const validation = validatePostMatchJSON(parsed);

      if (validation.valid) {
        // Assembla testo finale
        return assembleText(parsed);
      }

      lastErrors = validation.errors;
      console.log(`[POST-MATCH] Tentativo ${attempt + 1}/${MAX_RETRIES + 1} fallito: ${validation.errors.join(', ')}`);

    } catch (err) {
      lastErrors = [`Errore parsing JSON: ${err.message}`];
      console.log(`[POST-MATCH] Tentativo ${attempt + 1}/${MAX_RETRIES + 1} errore: ${err.message}`);
    }
  }

  // Fallback: risposta generica basata sui fatti
  return assembleFallback(params);
}


// ═══════════════════════════════════════════════════════════
// ASSEMBLA TESTO FINALE
// ═══════════════════════════════════════════════════════════

/**
 * Assembla il testo finale dal JSON validato di Mistral.
 */
function assembleText(parsed) {
  return `${parsed.esito} ${parsed.campo} ${parsed.giudizio} ${parsed.chiusura}`;
}

/**
 * Fallback se Mistral fallisce dopo tutti i retry.
 * Genera un testo generico ma corretto dai fatti.
 */
function assembleFallback(params) {
  const { home, away, realScore, pronostico, esito, postMatchAnalysis } = params;
  const esitoStr = esito ? 'Pronostico centrato' : 'Pronostico sbagliato';

  let verdetto = '';
  if (postMatchAnalysis) {
    const v = postMatchAnalysis.verdict;
    if (esito && (v === 'FORZATO' || v === 'ERRATO')) verdetto = ', con un po\' di fortuna';
    else if (!esito && (v === 'COERENTE' || v === 'RAGIONEVOLE')) verdetto = ', nonostante il campo fosse dalla nostra parte';
    else if (!esito && (v === 'FORZATO' || v === 'ERRATO')) verdetto = ', il campo confermava che era la scelta sbagliata';
  }

  return `${esitoStr} per ${home} vs ${away} (${realScore}), avevamo giocato ${pronostico}${verdetto}.`;
}


// ═══════════════════════════════════════════════════════════
// GENERA COMMENTI PER TUTTI I PRONOSTICI DI UNA PARTITA
// ═══════════════════════════════════════════════════════════

/**
 * Genera commenti post-partita per tutti i pronostici conclusi di una partita.
 * Usata dal chatbot quando l'utente chiede di una partita finita.
 * @param {object} db - MongoDB connection
 * @param {string} home
 * @param {string} away
 * @param {string} date
 * @returns {string|null} Testo completo con tutti i commenti, o null se non disponibile
 */
async function generateMatchPostMatchAnalysis(db, home, away, date) {
  // Carica pronostici
  const pred = await db.collection('daily_predictions_unified').findOne(
    { home, away, date },
    { projection: { pronostici: 1, real_score: 1, live_score: 1 } }
  );
  if (!pred) return null;

  const realScore = pred.real_score || (pred.live_score ? pred.live_score.replace(':', '-') : null);
  if (!realScore) return null;

  // Carica stats SofaScore
  const pms = await db.collection('post_match_stats').findOne(
    { home, away, date },
    { projection: { home_stats: 1, away_stats: 1 } }
  );

  const comments = [];

  for (const p of (pred.pronostici || [])) {
    if (p.esito === undefined || p.esito === null) continue;
    if (p.tipo === 'RISULTATO_ESATTO') continue;
    if (p.pronostico === 'NO BET') continue;

    const comment = await generatePostMatchComment({
      home, away, realScore,
      tipo: p.tipo,
      pronostico: p.pronostico,
      esito: p.esito === true,
      postMatchAnalysis: p.post_match_analysis || null,
      homeStats: pms ? pms.home_stats : null,
      awayStats: pms ? pms.away_stats : null,
    });

    comments.push(`**${p.tipo} ${p.pronostico}** @${p.quota || '?'}: ${comment}`);
  }

  if (comments.length === 0) return null;

  return `${home} ${realScore} ${away}\n\n${comments.join('\n\n')}`;
}


module.exports = { generatePostMatchComment, generateMatchPostMatchAnalysis, buildFactsForMistral, validatePostMatchJSON };
