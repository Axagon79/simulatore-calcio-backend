/**
 * postMatchAnalysis.js — Analisi post-partita (pattern Ticket AI)
 *
 * 1. Backend prepara dati STRUTTURATI compatti
 * 2. Mistral LIBERO di analizzare e scrivere come vuole
 * 3. Backend valida: controlla coerenza con i DATI (non con regole di stile)
 * 4. Se incongruenza → DOMANDA a Mistral ("hai detto X ma i dati dicono Y, come mai?")
 * 5. Backend assembla il testo finale
 */

const { callMistral } = require('./llmService');

// ═══════════════════════════════════════════════════════════
// PROMPT — Corto. Mistral e' l'esperto, noi diamo i dati.
// ═══════════════════════════════════════════════════════════

const SYSTEM_PROMPT = `Sei un match analyst per un sito di pronostici sportivi. Scrivi commenti post-partita chiari e professionali, ma con un tono accessibile a tutti. Non essere ne' troppo tecnico ne' troppo colloquiale.

Ricevi i dati di una partita in formato strutturato. Scrivi la tua analisi in JSON con 2 campi:

{
  "partita": "Racconta cosa e' successo in campo basandoti sulle statistiche reali. Chi ha dominato, chi ha creato, chi ha sofferto. Fallo in 4-5 frasi.",
  "verdetto": "Una frase secca: il pronostico ha funzionato o no, e perche' in base a quello che hai raccontato sopra."
}

Restituisci SOLO il JSON. Nessun testo prima o dopo. Nessun markdown.
Scrivi in italiano, come parleresti a un amico che ti chiede com'e' andata la partita.
IMPORTANTE: non ripetere lo stesso concetto. Il verdetto deve aggiungere qualcosa di nuovo rispetto alla partita, non riformulare le stesse cose.
Usa il passato prossimo ("ha confermato", "ha dominato", "ha segnato"), NON l'imperfetto ("confermava", "dominava"). La partita e' finita, parla di fatti accaduti.
Resta FOCALIZZATO sul pronostico in questione. Se il pronostico e' GG, parla di GG. Non divagare su Over, Under, risultati esatti o altri mercati che non c'entrano.
Non dire cose OVVIE dal risultato. Se e' finita 5-0, non dire "il Pisa non ha segnato" — si vede gia dal risultato. Spiega il PERCHE: non ha mai tirato in porta, non ha creato occasioni. Il perche e interessante, il cosa no.
Non parlare troppo di quote. Le quote sono un dato di contesto, non il centro dell'analisi. Concentrati su cosa e' successo in campo.
Parla SEMPLICE. Frasi corte e dirette. Non fare frasi lunghe e complesse per dire cose semplici. Se una squadra ha dominato e l'altra non ha mai tirato in porta, dillo cosi. Non scrivere "la partita e' stata coerente con la superiorita'" — scrivi "il Como ha dominato e il Pisa non ha mai tirato in porta".
Non usare termini tecnici come xG, expected goals, Monte Carlo, confidence, score di coerenza, algoritmo, SofaScore.`;


// ═══════════════════════════════════════════════════════════
// DATI STRUTTURATI
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

function buildStructuredInput(params) {
  const { home, away, realScore, tipo, pronostico, esito, postMatchAnalysis,
          homeStats, awayStats, quota, confidence, stars, odds, matchDoc } = params;

  const lines = [];

  lines.push(`partita=${home} vs ${away}|ris=${realScore}|pron=${_spiegaPronostico(tipo, pronostico, home, away)}|esito=${esito ? 'CENTRATO' : 'SBAGLIATO'}`);

  // --- STATISTICHE REALI (tabella per squadra) ---
  if (homeStats && awayStats) {
    const buildRow = (label, stats) => {
      const row = [];
      if (stats.shots_on_target != null) row.push(`tiri_in_porta=${stats.shots_on_target}`);
      const off = (stats.total_shots != null && stats.shots_on_target != null) ? stats.total_shots - stats.shots_on_target : stats.shots_off_target;
      if (off != null && off > 0) row.push(`tiri_fuori=${off}`);
      if (stats.big_chances != null && stats.big_chances > 0) row.push(`grandi_occasioni=${stats.big_chances}`);
      if (stats.possession != null) row.push(`possesso=${stats.possession}%`);
      if (stats.hit_woodwork != null && stats.hit_woodwork > 0) row.push(`pali=${stats.hit_woodwork}`);
      if (stats.big_saves != null && stats.big_saves > 0) row.push(`grandi_parate=${stats.big_saves}`);
      if (stats.red_cards != null && stats.red_cards > 0) row.push(`espulsioni=${stats.red_cards}`);
      return `${label}: ${row.join(', ')}`;
    };

    lines.push(`\nDOPO LA PARTITA (statistiche reali del campo):`);
    lines.push(buildRow(home, homeStats));
    lines.push(buildRow(away, awayStats));
  }

  // --- BLOCCO 3: FATTI GIA' INTERPRETATI (aiuto per Mistral) ---
  const risMatch = realScore.match(/(\d+)-(\d+)/);
  if (risMatch) {
    const hGoals = parseInt(risMatch[1]);
    const aGoals = parseInt(risMatch[2]);
    const totalGoals = hGoals + aGoals;
    const fatti = [];

    // Chi ha segnato
    fatti.push(`${home} ha segnato ${hGoals} gol, ${away} ha segnato ${aGoals} gol, totale ${totalGoals} gol`);

    // Chi ha vinto
    if (hGoals > aGoals) fatti.push(`${home} ha vinto`);
    else if (aGoals > hGoals) fatti.push(`${away} ha vinto`);
    else fatti.push(`Pareggio`);

    // Perche' il pronostico e' centrato/sbagliato
    const pron = _spiegaPronostico(tipo, pronostico, home, away);
    if (esito) {
      // Spiega PERCHE' e' centrato
      if (/GG|Entrambe segnano/i.test(pron)) {
        fatti.push(`Il GG e' CENTRATO perche' entrambe le squadre hanno segnato (${hGoals}-${aGoals})`);
      } else if (/NG|Almeno una non segna/i.test(pron)) {
        const chi0 = hGoals === 0 ? home : (aGoals === 0 ? away : null);
        if (chi0) fatti.push(`Il NG e' CENTRATO perche' ${chi0} non ha segnato (0 gol)`);
        else fatti.push(`Il NG e' CENTRATO`);
      } else if (/Over\s*(\d+\.?\d*)/.test(pron)) {
        const thr = pron.match(/Over\s*(\d+\.?\d*)/)[1];
        fatti.push(`L'Over ${thr} e' CENTRATO perche' ci sono stati ${totalGoals} gol`);
      } else if (/Under\s*(\d+\.?\d*)/.test(pron)) {
        const thr = pron.match(/Under\s*(\d+\.?\d*)/)[1];
        fatti.push(`L'Under ${thr} e' CENTRATO perche' ci sono stati solo ${totalGoals} gol`);
      } else if (/Vittoria\s+(.+?)\s*\(casa\)/i.test(pron)) {
        fatti.push(`Il SEGNO 1 e' CENTRATO perche' ${home} ha vinto ${hGoals}-${aGoals}`);
      } else if (/Vittoria\s+(.+?)\s*\(ospite\)/i.test(pron)) {
        fatti.push(`Il SEGNO 2 e' CENTRATO perche' ${away} ha vinto ${hGoals}-${aGoals}`);
      } else if (/Pareggio/i.test(pron)) {
        fatti.push(`Il PAREGGIO e' CENTRATO (${hGoals}-${aGoals})`);
      } else if (/DC 1X/i.test(pron)) {
        fatti.push(`Il DC 1X e' CENTRATO perche' ${home} ${hGoals > aGoals ? 'ha vinto' : 'ha pareggiato'} (${hGoals}-${aGoals})`);
      } else if (/DC X2/i.test(pron)) {
        fatti.push(`Il DC X2 e' CENTRATO perche' ${away} ${aGoals > hGoals ? 'ha vinto' : 'ha pareggiato'} (${hGoals}-${aGoals})`);
      } else if (/DC 12/i.test(pron)) {
        fatti.push(`Il DC 12 e' CENTRATO perche' non e' finita in pareggio (${hGoals}-${aGoals})`);
      } else if (/Multigol\s*(\d+)-(\d+)/i.test(pron)) {
        const mgm = pron.match(/Multigol\s*(\d+)-(\d+)/i);
        fatti.push(`Il Multigol ${mgm[1]}-${mgm[2]} e' CENTRATO perche' ci sono stati ${totalGoals} gol (dentro il range ${mgm[1]}-${mgm[2]})`);
      } else {
        fatti.push(`Il pronostico "${pron}" e' CENTRATO`);
      }
    } else {
      // Spiega PERCHE' e' sbagliato
      if (/GG|Entrambe segnano/i.test(pron)) {
        const chi0 = hGoals === 0 ? home : (aGoals === 0 ? away : null);
        if (chi0) fatti.push(`Il GG e' SBAGLIATO perche' ${chi0} non ha segnato (0 gol)`);
        else fatti.push(`Il GG e' SBAGLIATO`);
      } else if (/NG|Almeno una non segna/i.test(pron)) {
        fatti.push(`Il NG e' SBAGLIATO perche' entrambe le squadre hanno segnato (${hGoals}-${aGoals})`);
      } else if (/Over\s*(\d+\.?\d*)/.test(pron)) {
        const thr = pron.match(/Over\s*(\d+\.?\d*)/)[1];
        fatti.push(`L'Over ${thr} e' SBAGLIATO perche' ci sono stati solo ${totalGoals} gol (servivano almeno ${Math.ceil(parseFloat(thr))})`);
      } else if (/Under\s*(\d+\.?\d*)/.test(pron)) {
        const thr = pron.match(/Under\s*(\d+\.?\d*)/)[1];
        fatti.push(`L'Under ${thr} e' SBAGLIATO perche' ci sono stati ${totalGoals} gol (servivano massimo ${Math.floor(parseFloat(thr))})`);
      } else if (/Vittoria\s+(.+?)\s*\(casa\)/i.test(pron)) {
        if (hGoals <= aGoals) fatti.push(`Il SEGNO 1 e' SBAGLIATO perche' ${home} non ha vinto (${hGoals}-${aGoals})`);
      } else if (/Vittoria\s+(.+?)\s*\(ospite\)/i.test(pron)) {
        if (aGoals <= hGoals) fatti.push(`Il SEGNO 2 e' SBAGLIATO perche' ${away} non ha vinto (${hGoals}-${aGoals})`);
      } else if (/Pareggio/i.test(pron)) {
        fatti.push(`Il PAREGGIO e' SBAGLIATO perche' la partita e' finita ${hGoals}-${aGoals}`);
      } else if (/DC 1X/i.test(pron)) {
        fatti.push(`Il DC 1X e' SBAGLIATO perche' ${away} ha vinto (${hGoals}-${aGoals}), ${home} non ha ne' vinto ne' pareggiato`);
      } else if (/DC X2/i.test(pron)) {
        fatti.push(`Il DC X2 e' SBAGLIATO perche' ${home} ha vinto (${hGoals}-${aGoals}), ${away} non ha ne' vinto ne' pareggiato`);
      } else if (/DC 12/i.test(pron)) {
        fatti.push(`Il DC 12 e' SBAGLIATO perche' la partita e' finita in pareggio (${hGoals}-${aGoals})`);
      } else if (/Multigol\s*(\d+)-(\d+)/i.test(pron)) {
        const mgm = pron.match(/Multigol\s*(\d+)-(\d+)/i);
        fatti.push(`Il Multigol ${mgm[1]}-${mgm[2]} e' SBAGLIATO perche' ci sono stati ${totalGoals} gol (servivano tra ${mgm[1]} e ${mgm[2]})`);
      } else {
        fatti.push(`Il pronostico "${pron}" e' SBAGLIATO`);
      }
    }

    // Chi ha dominato in campo
    if (homeStats && awayStats) {
      const hSot = homeStats.shots_on_target ?? 0;
      const aSot = awayStats.shots_on_target ?? 0;
      if (hSot > aSot * 2 && hSot >= 5) {
        fatti.push(`${home} ha dominato il campo (${hSot} tiri in porta contro ${aSot})`);
      } else if (aSot > hSot * 2 && aSot >= 5) {
        fatti.push(`${away} ha dominato il campo (${aSot} tiri in porta contro ${hSot})`);
      }
      if (hSot === 0) fatti.push(`${home} non ha MAI tirato in porta`);
      if (aSot === 0) fatti.push(`${away} non ha MAI tirato in porta`);
    }

    lines.push(`\nFATTI CHIAVE (gia' interpretati, NON contraddirli):\n- ${fatti.join('\n- ')}`);
  }

  return lines.join('\n');
}


// ═══════════════════════════════════════════════════════════
// VALIDAZIONE — Controlla coerenza con i DATI, non lo stile.
// Se trova problemi, fa DOMANDE a Mistral.
// ═══════════════════════════════════════════════════════════

const REQUIRED_FIELDS = ['partita', 'verdetto'];

// Termini tecnici interni che l'utente non deve vedere
const FORBIDDEN = [/\bxG\b/i, /\bexpected goals?\b/i, /\bMonte Carlo\b/i, /\bcicli\b/i,
  /\bSofaScore\b/i, /\bcoerenza\b/i, /\bconfidence\b/i, /\balgoritmo\b/i,
  /\bsimulazione\b/i, /\/100\b/];

// Helpers per estrarre dati dall'input
function _extractFromInput(inputData) {
  const home = (inputData.match(/partita=(.+?) vs/) || [])[1] || '';
  const away = (inputData.match(/vs (.+?)\|/) || [])[1] || '';
  const tiripMatch = inputData.match(/tiri_in_porta=(\d+)-(\d+)/);
  const tiriTotMatch = inputData.match(/tiri_totali=(\d+)-(\d+)/);
  const possMatch = inputData.match(/possesso=(\d+)-(\d+)/);
  const occasioniMatch = inputData.match(/grandi_occasioni=(\d+)-(\d+)/);
  return { home, away, tiripMatch, tiriTotMatch, possMatch, occasioniMatch };
}

function _checkNumbers(text, pattern, validNums, label) {
  const questions = [];
  const matches = [...text.matchAll(pattern)];
  for (const m of matches) {
    const nums = [...m[0].matchAll(/\d+/g)].map(x => x[0]);
    for (const n of nums) {
      if (!validNums.includes(n)) {
        questions.push(`Hai scritto ${n} per ${label} ma i dati dicono ${validNums.join('-')}. Usa i numeri corretti: ${validNums.join('-')}.`);
        return questions; // una domanda per tipo basta
      }
    }
  }
  return questions;
}

// ── CHECK 1: pre_match — confronta con dati PRE-MATCH ──
function _checkPreMatch(text, inputData) {
  const questions = [];
  if (!text || text.trim().length < 10) {
    questions.push(`La sezione "pre_match" e' troppo corta. Analizza i dati pre-partita (quote, probabilita').`);
    return questions;
  }

  // Termini vietati
  for (const regex of FORBIDDEN) {
    if (regex.test(text)) {
      const match = text.match(regex);
      questions.push(`In "pre_match" hai usato "${match[0]}". Come lo diresti a un amico al bar senza termini tecnici?`);
    }
  }

  // Controlla che le quote citate corrispondano
  const quotaMatch = inputData.match(/quota=(\d+\.?\d*)/);
  if (quotaMatch) {
    const quota = quotaMatch[1];
    const quoteInText = [...text.matchAll(/(?:quota|@)\s*(\d+\.?\d*)/gi)];
    for (const m of quoteInText) {
      // Tolleranza: la quota puo' essere arrotondata
      const diff = Math.abs(parseFloat(m[1]) - parseFloat(quota));
      if (diff > 0.5 && !inputData.includes(m[1])) {
        questions.push(`In "pre_match" hai citato la quota ${m[1]} ma i dati dicono ${quota}. E' corretto?`);
      }
    }
  }

  return questions;
}

// ── CHECK 2: partita — confronta con dati POST-MATCH ──
function _checkPartita(text, inputData) {
  const questions = [];
  if (!text || text.trim().length < 10) {
    questions.push(`La sezione "partita" e' troppo corta. Racconta cosa e' successo in campo.`);
    return questions;
  }

  const { home, away, tiripMatch, tiriTotMatch, possMatch } = _extractFromInput(inputData);

  // Termini vietati
  for (const regex of FORBIDDEN) {
    if (regex.test(text)) {
      const match = text.match(regex);
      questions.push(`In "partita" hai usato "${match[0]}". Come lo diresti senza termini tecnici?`);
    }
  }

  // Tiri in porta
  if (tiripMatch) {
    const hSot = tiripMatch[1];
    const aSot = tiripMatch[2];
    const sumSot = String(parseInt(hSot) + parseInt(aSot));
    questions.push(..._checkNumbers(text, /(\d+)\s*tir[oi]\s*in\s*porta/gi, [hSot, aSot, sumSot], 'tiri in porta'));
    questions.push(..._checkNumbers(text, /tir[oi]\s*in\s*porta\s*[:(]?\s*(\d+)\s*(?:a|contro|-|–)\s*(\d+)/gi, [hSot, aSot, sumSot], 'tiri in porta'));

    // 0 tiri: se una squadra ha 0, non puo' aver tirato
    // Pattern stretto: "Pisa con 7 tiri in porta" o "Pisa ha fatto 7 tiri in porta"
    // NON becca: "Pisa ha subito 7 tiri in porta" (quelli sono del Como)
    if (parseInt(aSot) === 0) {
      const m = text.match(new RegExp(away + '.{0,10}(?:con|ha fatto|ha avuto|ha tirato)\\s*(\\d+)\\s*tir[oi]\\s*in\\s*porta', 'i'));
      if (m && parseInt(m[1]) > 0) {
        questions.push(`Hai detto che ${away} ha fatto ${m[1]} tiro in porta ma i dati dicono 0. ${away} non ha MAI tirato in porta.`);
      }
    }
    if (parseInt(hSot) === 0) {
      const m = text.match(new RegExp(home + '.{0,10}(?:con|ha fatto|ha avuto|ha tirato)\\s*(\\d+)\\s*tir[oi]\\s*in\\s*porta', 'i'));
      if (m && parseInt(m[1]) > 0) {
        questions.push(`Hai detto che ${home} ha fatto ${m[1]} tiro in porta ma i dati dicono 0. ${home} non ha MAI tirato in porta.`);
      }
    }

    // Dominio con 0 tiri — solo se dice "X ha dominato", non "X è stato dominato"
    if (parseInt(hSot) === 0 && new RegExp(home + '.{0,15}ha (dominat|avuto il dominio|mostrato superiorit)', 'i').test(text)) {
      questions.push(`Hai detto che ${home} ha dominato ma ha 0 tiri in porta. Come e' possibile?`);
    }
    if (parseInt(aSot) === 0 && new RegExp(away + '.{0,15}ha (dominat|avuto il dominio|mostrato superiorit)', 'i').test(text)) {
      questions.push(`Hai detto che ${away} ha dominato ma ha 0 tiri in porta. Come e' possibile?`);
    }
  }

  // Tiri totali
  if (tiriTotMatch) {
    const hTot = tiriTotMatch[1];
    const aTot = tiriTotMatch[2];
    const sumTot = String(parseInt(hTot) + parseInt(aTot));
    questions.push(..._checkNumbers(text, /(\d+)\s*tiri\s*totali/gi, [hTot, aTot, sumTot], 'tiri totali'));
    questions.push(..._checkNumbers(text, /tiri\s*totali\s*[:(]?\s*(\d+)/gi, [hTot, aTot, sumTot], 'tiri totali'));
    questions.push(..._checkNumbers(text, /tiri\s*totali\s*(\d+)\s*(?:a|contro|-|–)\s*(\d+)/gi, [hTot, aTot, sumTot], 'tiri totali'));
  }

  // Possesso
  if (possMatch) {
    const hPoss = possMatch[1];
    const aPoss = possMatch[2];
    const possInText = [...text.matchAll(/(\d+)\s*%?\s*(?:di\s*)?possesso/gi), ...text.matchAll(/possesso\s*[:(]?\s*(\d+)/gi)];
    for (const pm of possInText) {
      const n = pm[1];
      if (n !== hPoss && n !== aPoss) {
        questions.push(`Hai scritto possesso ${n}% ma i dati dicono ${hPoss}%-${aPoss}%. Quale e' corretto?`);
        break;
      }
    }
  }

  return questions;
}

// ── CHECK 2b: partita — coerenza logica col risultato ──
function _checkPartitaLogica(text, inputData) {
  const questions = [];
  const { home, away } = _extractFromInput(inputData);
  const risMatch = inputData.match(/ris=(\d+)-(\d+)/);
  if (!risMatch) return questions;

  const hGoals = parseInt(risMatch[1]);
  const aGoals = parseInt(risMatch[2]);
  const totalGoals = hGoals + aGoals;

  // "Senza gol" generico quando ci sono gol — solo frasi che parlano della partita intera
  if (totalGoals > 0) {
    if (/\b(partita senza gol|nessun gol nella partita|zero gol totali)\b/i.test(text)) {
      questions.push(`Hai scritto "senza gol" riferito alla partita ma sono stati segnati ${totalGoals} gol (${hGoals}-${aGoals}).`);
    }
  }

  // Se una squadra ha segnato X gol, non puoi dire che "non ha segnato"
  if (hGoals > 0) {
    const homeNotScored = new RegExp(home + '.{0,30}(non ha segnat|non .{0,10}gol|senza segna|non .{0,10}rete)', 'i');
    if (homeNotScored.test(text)) {
      questions.push(`Hai detto che ${home} non ha segnato ma il risultato e' ${hGoals}-${aGoals}. ${home} ha fatto ${hGoals} gol.`);
    }
    const homeNoGoalWay = new RegExp(home + '.{0,30}(non ha trovato la via del gol|non .{0,15}riuscit.{0,5}segna)', 'i');
    if (homeNoGoalWay.test(text)) {
      questions.push(`Hai detto che ${home} non ha trovato la via del gol ma ha fatto ${hGoals} gol. Come e' possibile?`);
    }
  }
  if (aGoals > 0) {
    const awayNotScored = new RegExp(away + '.{0,30}(non ha segnat|non .{0,10}gol|senza segna|non .{0,10}rete)', 'i');
    if (awayNotScored.test(text)) {
      questions.push(`Hai detto che ${away} non ha segnato ma il risultato e' ${hGoals}-${aGoals}. ${away} ha fatto ${aGoals} gol.`);
    }
  }

  // Se il pronostico era GG ed e' SBAGLIATO, il motivo e' che UNA squadra non ha segnato, non che "non ci sono gol"
  const pronMatch = inputData.match(/pron=(.+?)\|/);
  if (pronMatch && /GG|Entrambe segnano/i.test(pronMatch[1]) && inputData.includes('esito=SBAGLIATO')) {
    // Chi non ha segnato?
    const whoDidntScore = hGoals === 0 ? home : (aGoals === 0 ? away : null);
    if (whoDidntScore && totalGoals > 0) {
      // Se dice "non ci sono stati gol" quando ce ne sono stati, e' sbagliato
      if (/\b(partita senza gol|nessun gol nella partita|non ci sono stati gol)\b/i.test(text)) {
        questions.push(`Il GG e' sbagliato perche' ${whoDidntScore} non ha segnato (0 gol), non perche' non ci sono stati gol. La partita e' finita ${hGoals}-${aGoals} con ${totalGoals} gol totali.`);
      }
    }
  }

  return questions;
}

// ── CHECK 3: resoconto — confronta con esito e coerenza tra sezioni ──
function _checkResoconto(text, inputData, parsedPreMatch, parsedPartita) {
  const questions = [];
  if (!text || text.trim().length < 10) {
    questions.push(`La sezione "resoconto" e' troppo corta. Tira le somme: il pronostico ha funzionato? Il campo confermava?`);
    return questions;
  }

  // Termini vietati
  for (const regex of FORBIDDEN) {
    if (regex.test(text)) {
      const match = text.match(regex);
      questions.push(`In "resoconto" hai usato "${match[0]}". Come lo diresti senza termini tecnici?`);
    }
  }

  // Coerenza esito
  if (inputData.includes('esito=CENTRATO')) {
    if (/\b(sbagliato|errato|flop|fallito|non ha funzionato)\b/i.test(text)) {
      questions.push(`Nel resoconto dici che il pronostico e' sbagliato, ma l'esito nei dati e' CENTRATO. Il pronostico ha funzionato, non e' sbagliato.`);
    }
  }
  if (inputData.includes('esito=SBAGLIATO')) {
    if (/\b(centrato|azzeccato|perfetto|indovinato|ha funzionato)\b/i.test(text)) {
      questions.push(`Nel resoconto dici che il pronostico e' centrato, ma l'esito nei dati e' SBAGLIATO. Il pronostico NON ha funzionato.`);
    }
  }

  // Coerenza logica: se in "partita" dice che una squadra ha dominato, il resoconto non puo' dire il contrario
  const { home, away, tiripMatch } = _extractFromInput(inputData);
  if (tiripMatch) {
    const hSot = parseInt(tiripMatch[1]);
    const aSot = parseInt(tiripMatch[2]);
    // Se la differenza tiri in porta e' schiacciante (>= 5) e il resoconto dice "partita equilibrata"
    if (Math.abs(hSot - aSot) >= 5 && /\b(equilibrat|pari|bilanciata|incerta)\b/i.test(text)) {
      const dominante = hSot > aSot ? home : away;
      questions.push(`Nel resoconto dici "equilibrata" ma i tiri in porta erano ${hSot}-${aSot}. ${dominante} ha chiaramente dominato, non era equilibrata.`);
    }
  }

  return questions;
}

// ── VALIDATOR PRINCIPALE: 3 check separati ──
function validateJSON(parsed, inputData) {
  const questions = [];

  // Struttura base
  for (const f of REQUIRED_FIELDS) {
    if (!parsed[f] || typeof parsed[f] !== 'string') {
      questions.push(`Il campo "${f}" manca. Il JSON deve avere 2 campi: partita, verdetto.`);
    }
  }
  if (questions.length > 0) return { valid: false, questions };

  // Check partita + logica + verdetto
  questions.push(..._checkPartita(parsed.partita, inputData));
  questions.push(..._checkPartitaLogica(parsed.partita, inputData));
  questions.push(..._checkPartitaLogica(parsed.verdetto, inputData));

  // Coerenza esito nel verdetto
  if (inputData.includes('esito=CENTRATO')) {
    if (/\b(sbagliato|errato|flop|fallito|non ha funzionato)\b/i.test(parsed.verdetto || '')) {
      questions.push(`Nel verdetto dici sbagliato ma l'esito e' CENTRATO. Correggi.`);
    }
  }
  if (inputData.includes('esito=SBAGLIATO')) {
    if (/\b(centrato|azzeccato|perfetto|indovinato|ha funzionato)\b/i.test(parsed.verdetto || '')) {
      questions.push(`Nel verdetto dici centrato ma l'esito e' SBAGLIATO. Correggi.`);
    }
  }

  // Check semantico su tutto
  const allText = `${parsed.partita || ''} ${parsed.verdetto || ''}`;
  const { home, away, tiripMatch: tp } = _extractFromInput(inputData);
  const risM = inputData.match(/ris=(\d+)-(\d+)/);

  if (risM) {
    const hG = parseInt(risM[1]);
    const aG = parseInt(risM[2]);
    const totG = hG + aG;

    // "Partita noiosa/morta/senza emozioni" quando ci sono 4+ gol
    if (totG >= 4 && /\b(noios[ae]|mort[ae]|senza emozion|piatt[ae]|soporífera|soporifera)\b/i.test(allText)) {
      questions.push(`Hai descritto la partita come "noiosa" o "senza emozioni" ma sono stati segnati ${totG} gol. Una partita con ${totG} gol non e' noiosa.`);
    }

    // "Goleada/valanga/massacro" quando ci sono 1-2 gol
    if (totG <= 2 && /\b(goleada|valanga|massacro|distruzion|annientat|demolit)\b/i.test(allText)) {
      questions.push(`Hai usato termini come "goleada" o "massacro" ma ci sono stati solo ${totG} gol. Non e' una goleada.`);
    }

    // "Ha vinto X" quando ha vinto Y
    if (hG > aG) {
      // Casa ha vinto
      if (new RegExp(away + '.{0,20}(ha vinto|vittoria|trionfato|si .{0,5}impost)', 'i').test(allText)) {
        questions.push(`Hai detto che ${away} ha vinto ma il risultato e' ${hG}-${aG}: ha vinto ${home}. Correggi.`);
      }
    } else if (aG > hG) {
      if (new RegExp(home + '.{0,20}(ha vinto|vittoria|trionfato|si .{0,5}impost)', 'i').test(allText)) {
        questions.push(`Hai detto che ${home} ha vinto ma il risultato e' ${hG}-${aG}: ha vinto ${away}. Correggi.`);
      }
    }

    // "Pareggio" quando non lo e' — solo se dice esplicitamente "e' finita in pareggio" o "pareggio finale"
    if (hG !== aG && /\b(finit[ao] in pareggio|pareggio finale|risultato.*pareggio|e' .*pareggio)\b/i.test(allText)) {
      questions.push(`Hai parlato di "pareggio" ma la partita e' finita ${hG}-${aG}. Non e' un pareggio.`);
    }

    // "Senza gol" / "zero gol" — solo se si riferisce alla partita intera, non a una squadra
    // "senza gol per il Pisa" e' corretto, "partita senza gol" no
    if (totG > 0 && /\b(partita senza gol|zero gol totali|nessun gol in partita|nessun gol nella partita)\b/i.test(allText)) {
      questions.push(`Hai scritto "senza gol" riferito alla partita ma sono stati segnati ${totG} gol (${hG}-${aG}). Correggi.`);
    }
  }

  // Tono autodistruttivo — non demolire il pronostico
  if (/\b(clamorosamente sbagliato|flop totale|disastro|disastroso|imbarazzante|figuraccia|ridicolo|assurdo|folle|pazzesco errore|errore madornale)\b/i.test(allText)) {
    const match = allText.match(/\b(clamorosamente sbagliato|flop totale|disastro|disastroso|imbarazzante|figuraccia|ridicolo|assurdo|folle|pazzesco errore|errore madornale)\b/i);
    questions.push(`Hai usato "${match[0]}" che e' un tono troppo negativo. Il pronostico puo' essere sbagliato ma non serve demolirlo. Riformula in modo piu' equilibrato — tipo "il campo ha detto altro" o "non e' andata come previsto".`);
  }

  // "Possesso equilibrato" quando e' 70-30
  if (tp) {
    const possM = inputData.match(/possesso=(\d+)-(\d+)/);
    if (possM) {
      const diff = Math.abs(parseInt(possM[1]) - parseInt(possM[2]));
      if (diff >= 25 && /\b(possesso equilibrat|possesso simil|possesso pari|alla pari nel possesso)\b/i.test(allText)) {
        questions.push(`Hai detto "possesso equilibrato" ma i dati dicono ${possM[1]}%-${possM[2]}%. Una differenza di ${diff}% non e' equilibrata.`);
      }
    }
  }

  return { valid: questions.length === 0, questions };
}


// ═══════════════════════════════════════════════════════════
// CHIAMA MISTRAL + RETRY CON DOMANDE
// ═══════════════════════════════════════════════════════════

async function generateComment(params) {
  const inputData = buildStructuredInput(params);

  const MAX_RETRIES = 3;
  let lastQuestions = [];

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    let userMessage = inputData;

    // Retry: far capire al modello che ha sbagliato, senza confonderlo
    if (attempt > 0 && lastQuestions.length > 0) {
      const domande = lastQuestions.map((q, i) => `${i + 1}. ${q}`).join('\n');
      userMessage = `${inputData}\n\nATTENZIONE: Nel tentativo precedente hai commesso questi errori o incongruenze rispetto ai dati forniti:\n${domande}\n\nAnalizza di nuovo i dati e genera un nuovo JSON corretto, correggendo gli errori indicati e rispettando i dati.`;
    }

    try {
      const response = await callMistral([
        { role: 'system', content: SYSTEM_PROMPT },
        { role: 'user', content: userMessage },
      ], { temperature: 0.5, maxTokens: 500 });

      let content = (response.content || response || '').toString().trim();
      console.log(`[POST-MATCH] Tentativo ${attempt + 1} raw (${content.length} chars): ${content.substring(0, 200)}`);

      if (!content) {
        lastQuestions = ['Risposta vuota. Genera il JSON richiesto.'];
        continue;
      }

      // Estrai JSON in modo sicuro — ignora testo prima/dopo le parentesi graffe
      const jsonMatch = content.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        content = jsonMatch[0];
      }

      const parsed = JSON.parse(content);

      // Se il JSON ha i 3 campi, accettalo al primo tentativo
      // Il validator fa domande solo dal secondo tentativo in poi
      if (parsed.partita && parsed.verdetto) {
        if (attempt === 0) {
          // Primo tentativo: accetta se ha i 3 campi (validazione soft)
          const validation = validateJSON(parsed, inputData);
          if (validation.valid) {
            return `${parsed.partita}\n\n${parsed.verdetto}`;
          }
          // Se ha errori critici (esito contraddetto), riprova
          const critici = validation.questions.filter(q =>
            q.includes('CENTRATO') || q.includes('SBAGLIATO') || q.includes('non ha segnato') ||
            q.includes('ha vinto') || q.includes('ha dominato ma ha 0'));
          if (critici.length === 0) {
            // Solo errori minori — accetta comunque
            console.log(`[POST-MATCH] Tentativo 1: errori minori ignorati (${validation.questions.length})`);
            return `${parsed.partita}\n\n${parsed.verdetto}`;
          }
          lastQuestions = critici;
          console.log(`[POST-MATCH] Tentativo 1: ${critici.length} errori critici → ${critici.join(' | ')}`);
        } else {
          // Retry: validazione completa
          const validation = validateJSON(parsed, inputData);
          if (validation.valid) {
            return `${parsed.partita}\n\n${parsed.verdetto}`;
          }
          lastQuestions = validation.questions;
          console.log(`[POST-MATCH] Tentativo ${attempt + 1}: ${validation.questions.length} domande → ${validation.questions.join(' | ')}`);
        }
      } else {
        lastQuestions = ['Il JSON deve avere 2 campi: partita, verdetto.'];
        console.log(`[POST-MATCH] Tentativo ${attempt + 1}: campi mancanti`);
      }

    } catch (err) {
      lastQuestions = [`Il formato che hai restituito non era un JSON valido. Ricorda di restituire SOLO la struttura JSON richiesta, senza aggiungere alcun testo o commento fuori dalle parentesi graffe.`];
      console.log(`[POST-MATCH] Tentativo ${attempt + 1}: parse error`);
    }
  }

  // Log dettagliato per debug
  console.log(`[POST-MATCH] FALLBACK per ${params.home} vs ${params.away}. Ultime domande: ${JSON.stringify(lastQuestions)}`);
  return _fallback(params, lastQuestions);
}

function _fallback(params, lastQuestions) {
  const { home, away, realScore, tipo, pronostico, esito } = params;
  // In produzione: risposta generica ma corretta basata sui fatti pre-digeriti
  const pron = _spiegaPronostico(tipo, pronostico, home, away);
  const esitoStr = esito ? 'Pronostico centrato' : 'Pronostico sbagliato';

  // Costruisci un fallback un po' piu' informativo
  const risM = realScore.match(/(\d+)-(\d+)/);
  if (risM) {
    const hG = parseInt(risM[1]);
    const aG = parseInt(risM[2]);
    let motivo = '';
    if (!esito) {
      if (/GG|Entrambe/i.test(pron)) {
        const chi0 = hG === 0 ? home : (aG === 0 ? away : null);
        if (chi0) motivo = ` — ${chi0} non ha segnato`;
      } else if (/NG/i.test(pron)) {
        motivo = ` — entrambe hanno segnato`;
      } else if (/Over/i.test(pron)) {
        motivo = ` — solo ${hG + aG} gol totali`;
      } else if (/Under/i.test(pron)) {
        motivo = ` — ${hG + aG} gol totali, troppi`;
      }
    }
    return `${esitoStr}: ${pron} per ${home} vs ${away} (${realScore})${motivo}.`;
  }

  return `${esitoStr} per ${home} vs ${away} (${realScore}).`;
}


// ═══════════════════════════════════════════════════════════
// GENERA PER TUTTI I PRONOSTICI DI UNA PARTITA
// ═══════════════════════════════════════════════════════════

async function generateMatchPostMatchAnalysis(db, home, away, date) {
  const pred = await db.collection('daily_predictions_unified').findOne(
    { home, away, date },
    { projection: { pronostici: 1, real_score: 1, live_score: 1, odds: 1,
                     expected_total_goals: 1, simulation_data: 1, confidence_segno: 1, confidence_gol: 1 } }
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
      confidence: p.confidence,
      stars: p.stars,
      odds: pred.odds,
      matchDoc: pred,
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
