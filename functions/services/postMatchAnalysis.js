/**
 * postMatchAnalysis.js — Analisi post-partita (pattern IDENTICO ai Ticket AI)
 *
 * Flusso:
 * 1. Backend prepara dati STRUTTURATI compatti (come il pool dei ticket)
 * 2. Mistral genera JSON STRUTTURATO (come le bollette)
 * 3. Backend VALIDA il JSON (come validate_with_errors dei ticket)
 * 4. Se errore → feedback SPECIFICO + retry (come i ticket)
 * 5. Backend ASSEMBLA il testo finale dal JSON validato
 */

const { callMistral } = require('./llmService');

// ═══════════════════════════════════════════════════════════
// PROMPT — Identico alla logica ticket: regole + formato JSON + esempi
// ═══════════════════════════════════════════════════════════

const SYSTEM_PROMPT = `Sei un commentatore sportivo italiano. Ricevi dati strutturati di una partita terminata e generi un commento strutturato in JSON.

═══════════════════════════════════════
REGOLE COMPOSIZIONE
═══════════════════════════════════════

1. Restituisci SOLO un oggetto JSON valido. Nessun testo prima o dopo. Nessun markdown.
2. Usa SOLO i dati forniti. NON inventare nulla.
3. TERMINI VIETATI (se li usi, il JSON viene scartato): xG, Monte Carlo, cicli, Tier, modificatori, indicatori, score, SofaScore, coerenza, confidence, algoritmo, modello, sistema, simulazione
4. NUMERI VIETATI: niente X/100, niente percentuali interne. Puoi usare SOLO: risultato (5-0), tiri in porta (7), occasioni (2), possesso (73%), pali (1), quote (@2.30)
5. TONO: commentatore sportivo al bar, NON data analyst. Frasi brevi e dirette.
6. L'ESITO e' gia deciso nei dati (CENTRATO o SBAGLIATO). NON contraddirlo MAI.
7. Il SIGNIFICATO del pronostico e' spiegato nei dati. NON confonderlo (GG = entrambe segnano, NG = almeno una non segna).

═══════════════════════════════════════
FORMATO OUTPUT — JSON (4 campi obbligatori)
═══════════════════════════════════════

{
  "esito": "max 20 parole — dice subito CENTRATO o SBAGLIATO e il tono generale",
  "campo": "max 35 parole — racconta cosa e' successo usando 2-3 stats dai dati",
  "giudizio": "max 30 parole — NON giudicare la scelta pre-partita. Descrivi solo cosa ha detto il CAMPO durante i 90 minuti. Il verdetto nei dati (meritata/sfortuna/fortunato/sbagliato) ti dice il tono da usare.",
  "chiusura": "max 20 parole — frase finale che lega tutto"
}

IMPORTANTE SUL CAMPO "giudizio":
- NON dire MAI "la scelta era un azzardo" o "il pronostico non aveva senso" — i dati pre-partita potevano essere diversi
- Devi solo dire COSA HA MOSTRATO IL CAMPO nei 90 minuti
- Se verdetto=sfortuna: "Il campo confermava la nostra lettura, ma il risultato ha detto altro"
- Se verdetto=meritata: "I numeri della partita confermano tutto"
- Se verdetto=fortunato: "Sul campo la storia era diversa, ma ci e' andata bene"
- Se verdetto=sbagliato: "Il campo ha raccontato una partita diversa da quella che ci aspettavamo"

═══════════════════════════════════════
ESEMPI (input → output)
═══════════════════════════════════════

INPUT:
partita=Roma vs Empoli|ris=3-0|pron=Vittoria Roma (casa)|esito=CENTRATO|verdetto=meritata|tiri_in_porta=8-1|grandi_occasioni=4-0|poss=65%-35%

OUTPUT:
{"esito":"Pronostico centrato, la Roma ha vinto meritatamente.","campo":"Dominio totale dei giallorossi: 8 tiri in porta contro 1, 4 occasioni nitide e il 65% di possesso. L'Empoli non ha mai impensierito.","giudizio":"I numeri della partita confermano tutto: la Roma ha controllato dal primo all'ultimo minuto.","chiusura":"Vittoria scritta nel destino della partita."}

INPUT:
partita=Inter vs Napoli|ris=0-1|pron=Entrambe segnano (GG)|esito=SBAGLIATO|verdetto=sbagliato|tiri_in_porta=2-3|grandi_occasioni=0-1|poss=48%-52%

OUTPUT:
{"esito":"Pronostico sbagliato, solo il Napoli e' riuscito a segnare.","campo":"L'Inter ha tirato solo 2 volte in porta senza creare nessuna grande occasione. Il Napoli ha gestito con il 52% di possesso.","giudizio":"Il campo ha mostrato un'Inter che non ha mai creato abbastanza per andare in gol. Partita a senso unico nella creazione.","chiusura":"Senza occasioni vere, il gol non puo' arrivare."}

INPUT:
partita=Milan vs Juve|ris=1-2|pron=Vittoria Milan (casa)|esito=SBAGLIATO|verdetto=sfortuna|tiri_in_porta=7-3|grandi_occasioni=3-1|poss=58%-42%|pali=2-0

OUTPUT:
{"esito":"Pronostico sbagliato, ma il Milan meritava molto di piu'.","campo":"Il Milan ha dominato con 7 tiri in porta contro 3, 3 grandi occasioni e 2 pali colpiti. La Juve ha fatto il minimo indispensabile.","giudizio":"Il campo confermava la nostra lettura: il Milan ha fatto tutto tranne segnare abbastanza. Pura sfortuna.","chiusura":"Una di quelle serate dove il calcio ti punisce senza motivo."}

INPUT:
partita=Lazio vs Genoa|ris=2-1|pron=Entrambe segnano (GG)|esito=CENTRATO|verdetto=fortunato|tiri_in_porta=5-1|grandi_occasioni=3-0|poss=62%-38%

OUTPUT:
{"esito":"Pronostico centrato, ma con un bel po' di fortuna.","campo":"La Lazio ha dominato con 5 tiri in porta e 3 grandi occasioni. Il Genoa ha segnato con l'unico tiro in porta della partita.","giudizio":"Sul campo la partita era tutta della Lazio. Il gol del Genoa e' arrivato dal nulla, un episodio piu' che una creazione.","chiusura":"Ci e' andata bene, il campo raccontava un'altra storia."}`;


// ═══════════════════════════════════════════════════════════
// STEP 1 — DATI STRUTTURATI (come il pool dei ticket)
// ═══════════════════════════════════════════════════════════

function _spiegaPronostico(tipo, pronostico, home, away) {
  const p = pronostico.toLowerCase().trim();
  if (p === 'goal' || p === 'gol' || p === 'gg') return `Entrambe segnano (GG)`;
  if (p === 'no goal' || p === 'no gol' || p === 'nogoal' || p === 'ng') return `Almeno una non segna (NG)`;
  const ouMatch = pronostico.match(/^(Over|Under|O|U|OV|UN|OVE|UND)\s*(\d+\.?\d*)/i);
  if (ouMatch) {
    const dir = ouMatch[1].toLowerCase().startsWith('o') ? 'Over' : 'Under';
    return `${dir} ${ouMatch[2]}`;
  }
  if (tipo === 'SEGNO') {
    if (p === '1') return `Vittoria ${home} (casa)`;
    if (p === '2') return `Vittoria ${away} (ospite)`;
    if (p === 'x') return `Pareggio`;
  }
  if (tipo === 'DOPPIA_CHANCE' || tipo === 'DC') {
    if (p.includes('1x')) return `DC 1X — ${home} vince o pareggia`;
    if (p.includes('x2')) return `DC X2 — ${away} vince o pareggia`;
    if (p.includes('12')) return `DC 12 — niente pareggio`;
  }
  const mgMatch = pronostico.match(/MG\s*(\d+)\s*-\s*(\d+)/i);
  if (mgMatch) return `Multigol ${mgMatch[1]}-${mgMatch[2]}`;
  return `${tipo} ${pronostico}`;
}

function _verdettoBrief(esito, verdict) {
  if (!verdict) return '';
  if (esito) {
    if (verdict === 'COERENTE' || verdict === 'RAGIONEVOLE') return 'meritata';
    if (verdict === 'INCERTO') return 'equilibrata';
    if (verdict === 'FORZATO') return 'fortunato';
    return 'pura fortuna';
  } else {
    if (verdict === 'COERENTE' || verdict === 'RAGIONEVOLE') return 'sfortuna';
    if (verdict === 'INCERTO') return 'equilibrata';
    if (verdict === 'FORZATO') return 'forzato';
    return 'sbagliato';
  }
}

/**
 * Costruisce la riga dati strutturata (come match_key dei ticket).
 * Formato compatto: partita=X|ris=X|pron=X|esito=X|verdetto=X|tiri_in_porta=X|grandi_occasioni=X|poss=X|pali=X
 */
function buildStructuredInput(params) {
  const { home, away, realScore, tipo, pronostico, esito, postMatchAnalysis, homeStats, awayStats, quota } = params;

  const parts = [];
  parts.push(`partita=${home} vs ${away}`);
  parts.push(`ris=${realScore}`);
  parts.push(`pron=${_spiegaPronostico(tipo, pronostico, home, away)}`);
  parts.push(`esito=${esito ? 'CENTRATO' : 'SBAGLIATO'}`);

  if (postMatchAnalysis) {
    parts.push(`verdetto=${_verdettoBrief(esito, postMatchAnalysis.verdict)}`);
  }

  if (homeStats && awayStats) {
    const hSot = homeStats.shots_on_target ?? '?';
    const aSot = awayStats.shots_on_target ?? '?';
    parts.push(`tiri_in_porta=${hSot}-${aSot}`);

    const hBc = homeStats.big_chances;
    const aBc = awayStats.big_chances;
    if (hBc != null || aBc != null) {
      parts.push(`grandi_occasioni=${hBc ?? 0}-${aBc ?? 0}`);
    }

    const hPoss = homeStats.possession;
    const aPoss = awayStats.possession;
    if (hPoss != null) {
      parts.push(`poss=${hPoss}%-${aPoss ?? '?'}%`);
    }

    const hWood = homeStats.hit_woodwork;
    const aWood = awayStats.hit_woodwork;
    if ((hWood && hWood > 0) || (aWood && aWood > 0)) {
      parts.push(`pali=${hWood ?? 0}-${aWood ?? 0}`);
    }

    const hBsaves = homeStats.big_saves;
    const aBsaves = awayStats.big_saves;
    if ((hBsaves && hBsaves > 0) || (aBsaves && aBsaves > 0)) {
      parts.push(`grandi_parate=${hBsaves ?? 0}-${aBsaves ?? 0}`);
    }

    const hRed = homeStats.red_cards;
    const aRed = awayStats.red_cards;
    if ((hRed && hRed > 0) || (aRed && aRed > 0)) {
      parts.push(`espulsioni=${hRed ?? 0}-${aRed ?? 0}`);
    }

    const hShots = homeStats.total_shots;
    const aShots = awayStats.total_shots;
    if (hShots != null) {
      parts.push(`tiri_totali=${hShots}-${aShots ?? '?'}`);
    }
  }

  if (quota) parts.push(`quota=${quota}`);

  return parts.join('|');
}


// ═══════════════════════════════════════════════════════════
// STEP 3 — VALIDAZIONE JSON (come validate_with_errors dei ticket)
// ═══════════════════════════════════════════════════════════

const REQUIRED_FIELDS = ['esito', 'campo', 'giudizio', 'chiusura'];
const MAX_WORDS = { esito: 25, campo: 40, giudizio: 35, chiusura: 25 };
const FORBIDDEN = [/\bxG\b/i, /\bMonte Carlo\b/i, /\bcicli\b/i, /\bTier [A-D]\b/i,
  /\bmodificator/i, /\bSofaScore\b/i, /\bcoerenza\b/i, /\bconfidence\b/i,
  /\bindicator/i, /\balgoritmo\b/i, /\bmodello\b/i, /\bsistema\b/i, /\bsimulazione\b/i,
  /\/100\b/];

function validateJSON(parsed, inputData) {
  const errors = [];

  // Campi obbligatori
  for (const f of REQUIRED_FIELDS) {
    if (!parsed[f] || typeof parsed[f] !== 'string' || parsed[f].trim().length < 5) {
      errors.push({ code: 'CAMPO_MANCANTE', feedback: `Campo "${f}" mancante o troppo corto (min 5 caratteri)` });
    }
  }

  // Termini vietati
  const fullText = REQUIRED_FIELDS.map(f => parsed[f] || '').join(' ');
  for (const regex of FORBIDDEN) {
    if (regex.test(fullText)) {
      const match = fullText.match(regex);
      errors.push({ code: 'TERMINE_VIETATO', feedback: `Termine vietato: "${match[0]}". Riscrivilo in linguaggio naturale.` });
    }
  }

  // Lunghezza
  for (const f of REQUIRED_FIELDS) {
    const words = (parsed[f] || '').split(/\s+/).length;
    if (words > MAX_WORDS[f]) {
      errors.push({ code: 'TROPPO_LUNGO', feedback: `"${f}" ha ${words} parole (max ${MAX_WORDS[f]}). Accorcia.` });
    }
  }

  // Coerenza esito: se input dice CENTRATO, il testo non deve dire "sbagliato" e viceversa
  if (inputData.includes('esito=CENTRATO')) {
    if (/\b(sbagliato|errato|sbagliamo|non ha funzionato|fallito)\b/i.test(parsed.esito || '')) {
      errors.push({ code: 'ESITO_CONTRADDETTO', feedback: 'L\'esito e\' CENTRATO ma il campo "esito" dice sbagliato. Correggi.' });
    }
  }
  if (inputData.includes('esito=SBAGLIATO')) {
    if (/\b(centrato|azzeccato|perfetto|indovinato)\b/i.test(parsed.esito || '')) {
      errors.push({ code: 'ESITO_CONTRADDETTO', feedback: 'L\'esito e\' SBAGLIATO ma il campo "esito" dice centrato. Correggi.' });
    }
  }

  return { valid: errors.length === 0, errors };
}


// ═══════════════════════════════════════════════════════════
// STEP 2+4 — CHIAMA MISTRAL + RETRY (come call_mistral dei ticket)
// ═══════════════════════════════════════════════════════════

async function generateComment(params) {
  const inputData = buildStructuredInput(params);

  const MAX_RETRIES = 2;
  let lastErrors = [];

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    let userMessage = inputData;

    // Retry: aggiungi feedback errori (identico ai ticket)
    if (attempt > 0 && lastErrors.length > 0) {
      const feedback = lastErrors.map(e => `- ${e.code}: ${e.feedback}`).join('\n');
      userMessage = `${inputData}\n\nCORREZIONE — Il JSON precedente aveva errori:\n${feedback}\nCorreggi e restituisci SOLO il JSON.`;
    }

    try {
      const response = await callMistral([
        { role: 'system', content: SYSTEM_PROMPT },
        { role: 'user', content: userMessage },
      ], { temperature: 0.3, max_tokens: 400 });

      let content = (response.content || response).toString().trim();
      if (content.startsWith('```')) {
        content = content.replace(/^```(?:json)?\s*/, '').replace(/\s*```$/, '');
      }

      const parsed = JSON.parse(content);
      const validation = validateJSON(parsed, inputData);

      if (validation.valid) {
        return `${parsed.esito} ${parsed.campo} ${parsed.giudizio} ${parsed.chiusura}`;
      }

      lastErrors = validation.errors;
      console.log(`[POST-MATCH] Tentativo ${attempt + 1}: ${validation.errors.map(e => e.code).join(', ')}`);

    } catch (err) {
      lastErrors = [{ code: 'JSON_INVALIDO', feedback: `Errore parsing: ${err.message}. Restituisci SOLO JSON valido.` }];
      console.log(`[POST-MATCH] Tentativo ${attempt + 1}: parse error`);
    }
  }

  // Fallback (come i ticket che scartano la bolletta invalida)
  return _fallback(params);
}

function _fallback(params) {
  const { home, away, realScore, pronostico, esito, postMatchAnalysis } = params;
  const esitoStr = esito ? 'Pronostico centrato' : 'Pronostico sbagliato';
  let extra = '';
  if (postMatchAnalysis) {
    const v = postMatchAnalysis.verdict;
    if (esito && (v === 'FORZATO' || v === 'ERRATO')) extra = ', con un po\' di fortuna';
    else if (!esito && (v === 'COERENTE' || v === 'RAGIONEVOLE')) extra = ', nonostante il campo fosse dalla nostra parte';
    else if (!esito && (v === 'FORZATO' || v === 'ERRATO')) extra = ', la scelta non era supportata dal campo';
  }
  return `${esitoStr} per ${home} vs ${away} (${realScore})${extra}.`;
}


// ═══════════════════════════════════════════════════════════
// STEP 5 — GENERA PER TUTTI I PRONOSTICI (come generate_bollette)
// ═══════════════════════════════════════════════════════════

async function generateMatchPostMatchAnalysis(db, home, away, date) {
  const pred = await db.collection('daily_predictions_unified').findOne(
    { home, away, date },
    { projection: { pronostici: 1, real_score: 1, live_score: 1 } }
  );
  if (!pred) return null;

  const realScore = pred.real_score || (pred.live_score ? pred.live_score.replace(':', '-') : null);
  if (!realScore) return null;

  const pms = await db.collection('post_match_stats').findOne(
    { home, away, date },
    { projection: { home_stats: 1, away_stats: 1 } }
  );

  const comments = [];

  for (const p of (pred.pronostici || [])) {
    if (p.esito === undefined || p.esito === null) continue;
    if (p.tipo === 'RISULTATO_ESATTO') continue;
    if (p.pronostico === 'NO BET') continue;

    const comment = await generateComment({
      home, away, realScore,
      tipo: p.tipo,
      pronostico: p.pronostico,
      esito: p.esito === true,
      quota: p.quota,
      postMatchAnalysis: p.post_match_analysis || null,
      homeStats: pms ? pms.home_stats : null,
      awayStats: pms ? pms.away_stats : null,
    });

    comments.push(`**${p.tipo} ${p.pronostico}** @${p.quota || '?'}: ${comment}`);
  }

  if (comments.length === 0) return null;
  return `${home} ${realScore} ${away}\n\n${comments.join('\n\n')}`;
}


module.exports = { generateComment, generateMatchPostMatchAnalysis, buildStructuredInput, validateJSON };
