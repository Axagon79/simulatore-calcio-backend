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

const SYSTEM_PROMPT = `Sei un esperto analista di calcio italiano con 25 anni di esperienza. Analizzi partite gia' giocate commentando cosa e' successo sul campo.

Ricevi i dati di una partita in formato strutturato, divisi in PRE-MATCH e POST-MATCH. Scrivi la tua analisi in JSON con 3 fasi, sempre in questo ordine:

{
  "pre_match": "Analisi dei dati PRIMA della partita: cosa dicevano le quote, le probabilita', le nostre previsioni. Il pronostico aveva senso? Era rischioso? Le quote lo supportavano?",
  "partita": "Analisi di cosa e' successo IN CAMPO: racconta la partita basandoti sulle statistiche reali. Chi ha dominato, chi ha creato, chi ha sofferto.",
  "resoconto": "Tira le somme: il pronostico e' stato centrato o sbagliato? Il campo confermava le previsioni o le contraddiceva? Verdetto finale."
}

Restituisci SOLO il JSON. Nessun testo prima o dopo. Nessun markdown.
Scrivi in italiano, come parleresti a un amico che ti chiede com'e' andata la partita.
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

  // --- BLOCCO 1: PRIMA DELLA PARTITA ---
  const pre = [];
  if (quota) pre.push(`quota=${quota}`);
  if (confidence) pre.push(`confidence=${confidence}%`);
  if (stars) pre.push(`stelle=${stars}`);
  if (odds) {
    if (odds['1']) pre.push(`quote_1x2=${odds['1']}/${odds['X'] || '?'}/${odds['2'] || '?'}`);
    if (odds.over_25) pre.push(`quota_over25=${odds.over_25}`);
    if (odds.under_25) pre.push(`quota_under25=${odds.under_25}`);
    if (odds.gg) pre.push(`quota_gg=${odds.gg}`);
    if (odds.ng) pre.push(`quota_ng=${odds.ng}`);
  }
  if (matchDoc) {
    if (matchDoc.expected_total_goals) pre.push(`gol_attesi=${matchDoc.expected_total_goals}`);
    const sim = matchDoc.simulation_data || {};
    if (sim.home_win_pct !== undefined) {
      pre.push(`prob_casa=${sim.home_win_pct}%`);
      pre.push(`prob_pari=${sim.draw_pct}%`);
      pre.push(`prob_ospite=${sim.away_win_pct}%`);
    }
    if (sim.over_25_pct !== undefined) pre.push(`prob_over25=${sim.over_25_pct}%`);
    if (sim.gg_pct !== undefined) pre.push(`prob_gg=${sim.gg_pct}%`);
  }
  if (pre.length > 0) {
    lines.push(`\nPRIMA DELLA PARTITA (dati pre-match):\n${pre.join('|')}`);
  }

  // --- BLOCCO 2: DOPO LA PARTITA ---
  if (homeStats && awayStats) {
    const post = [];
    const add = (label, hKey) => {
      const h = homeStats[hKey]; const a = awayStats[hKey];
      if (h != null) post.push(`${label}=${h}-${a ?? '?'}`);
    };
    const addIfPositive = (label, hKey) => {
      const h = homeStats[hKey]; const a = awayStats[hKey];
      if ((h && h > 0) || (a && a > 0)) post.push(`${label}=${h ?? 0}-${a ?? 0}`);
    };

    add('tiri_in_porta', 'shots_on_target');
    addIfPositive('grandi_occasioni', 'big_chances');
    add('possesso', 'possession');
    add('tiri_totali', 'total_shots');
    addIfPositive('pali', 'hit_woodwork');
    addIfPositive('grandi_parate', 'big_saves');
    addIfPositive('espulsioni', 'red_cards');

    if (post.length > 0) {
      lines.push(`\nDOPO LA PARTITA (statistiche reali del campo):\n${post.join('|')}`);
    }
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

const REQUIRED_FIELDS = ['pre_match', 'partita', 'resoconto'];

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

    // 0 tiri: se una squadra ha 0 non puo' aver tirato
    if (parseInt(aSot) === 0 && new RegExp(away + '.{0,50}\\d+\\s*tir[oi]\\s*in\\s*porta', 'i').test(text)) {
      const m = text.match(new RegExp(away + '.{0,50}(\\d+)\\s*tir[oi]\\s*in\\s*porta', 'i'));
      if (m && parseInt(m[1]) > 0) {
        questions.push(`Hai detto che ${away} ha fatto ${m[1]} tiro in porta ma i dati dicono 0. ${away} non ha MAI tirato in porta.`);
      }
    }
    if (parseInt(hSot) === 0 && new RegExp(home + '.{0,50}\\d+\\s*tir[oi]\\s*in\\s*porta', 'i').test(text)) {
      const m = text.match(new RegExp(home + '.{0,50}(\\d+)\\s*tir[oi]\\s*in\\s*porta', 'i'));
      if (m && parseInt(m[1]) > 0) {
        questions.push(`Hai detto che ${home} ha fatto ${m[1]} tiro in porta ma i dati dicono 0. ${home} non ha MAI tirato in porta.`);
      }
    }

    // Dominio con 0 tiri
    if (parseInt(hSot) === 0 && new RegExp(home + '.{0,30}(dominat|dominio|superior)', 'i').test(text)) {
      questions.push(`Hai detto che ${home} ha dominato ma ha 0 tiri in porta. Come e' possibile?`);
    }
    if (parseInt(aSot) === 0 && new RegExp(away + '.{0,30}(dominat|dominio|superior)', 'i').test(text)) {
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

  // Se ci sono stati gol, non puoi dire "non c'è stato nessun gol" o "senza gol"
  if (totalGoals > 0) {
    if (/\b(nessun gol|zero gol|senza gol|non .{0,15}segnat[oi]|non .{0,15}gol)\b/i.test(text)) {
      // Controlla che non stia parlando di una squadra specifica
      const noGoalGeneric = /\b(nessun gol|zero gol|senza gol)\b/i.test(text);
      if (noGoalGeneric) {
        questions.push(`Hai scritto "nessun gol" o "senza gol" ma la partita e' finita ${hGoals}-${aGoals} (${totalGoals} gol totali). Come mai?`);
      }
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
      if (/\bnon .{0,10}stat[oi] .{0,10}gol\b/i.test(text) || /\bnessun gol\b/i.test(text)) {
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
      questions.push(`Il campo "${f}" manca. Il JSON deve avere 3 campi: pre_match, partita, resoconto.`);
    }
  }
  if (questions.length > 0) return { valid: false, questions };

  // 3 check separati + check logica
  questions.push(..._checkPreMatch(parsed.pre_match, inputData));
  questions.push(..._checkPartita(parsed.partita, inputData));
  questions.push(..._checkPartitaLogica(parsed.partita, inputData));
  questions.push(..._checkPartitaLogica(parsed.resoconto, inputData)); // anche nel resoconto
  questions.push(..._checkResoconto(parsed.resoconto, inputData, parsed.pre_match, parsed.partita));

  // Check semantico su TUTTE le sezioni
  const allText = `${parsed.pre_match || ''} ${parsed.partita || ''} ${parsed.resoconto || ''}`;
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

    // "Pareggio" quando non lo e'
    if (hG !== aG && /\b(pareggio|parità|pari|finita pari)\b/i.test(allText) && !/\b(non .{0,10}pareggio|evitare il pareggio|senza pareggio)\b/i.test(allText)) {
      questions.push(`Hai parlato di "pareggio" ma la partita e' finita ${hG}-${aG}. Non e' un pareggio.`);
    }

    // "Senza gol" / "zero gol" quando ce ne sono
    if (totG > 0 && /\b(senza gol|zero gol|nessun gol|0 gol)\b/i.test(allText)) {
      questions.push(`Hai scritto "senza gol" o "zero gol" ma la partita e' finita ${hG}-${aG} con ${totG} gol. Correggi.`);
    }
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

  const MAX_RETRIES = 2;
  let lastQuestions = [];

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    let userMessage = inputData;

    // Retry: poni le domande
    if (attempt > 0 && lastQuestions.length > 0) {
      const domande = lastQuestions.map((q, i) => `${i + 1}. ${q}`).join('\n');
      userMessage = `${inputData}\n\nHo letto la tua analisi e ho alcune domande:\n${domande}\n\nRiscrivi il JSON tenendo conto di queste domande.`;
    }

    try {
      const response = await callMistral([
        { role: 'system', content: SYSTEM_PROMPT },
        { role: 'user', content: userMessage },
      ], { temperature: 0.5, max_tokens: 500 });

      let content = (response.content || response).toString().trim();
      if (content.startsWith('```')) {
        content = content.replace(/^```(?:json)?\s*/, '').replace(/\s*```$/, '');
      }

      const parsed = JSON.parse(content);
      const validation = validateJSON(parsed, inputData, params);

      if (validation.valid) {
        return `${parsed.pre_match}\n\n${parsed.partita}\n\n${parsed.resoconto}`;
      }

      lastQuestions = validation.questions;
      console.log(`[POST-MATCH] Tentativo ${attempt + 1}: ${validation.questions.length} domande`);

    } catch (err) {
      lastQuestions = [`Il JSON non era valido (${err.message}). Restituisci SOLO un oggetto JSON valido.`];
      console.log(`[POST-MATCH] Tentativo ${attempt + 1}: parse error`);
    }
  }

  return _fallback(params);
}

function _fallback(params) {
  const { home, away, realScore, pronostico, esito } = params;
  return `${esito ? 'Pronostico centrato' : 'Pronostico sbagliato'} per ${home} vs ${away} (${realScore}).`;
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
