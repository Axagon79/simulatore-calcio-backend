const express = require('express');
const router = express.Router();
const { ObjectId } = require('mongodb');
const authenticate = require('../middleware/auth');

// ============================================
// Helper: arricchisce bollette con real_score da daily_predictions_unified
// ============================================
async function enrichBollette(db, bollette) {
  if (!bollette.length) return bollette;

  // Raccogli tutte le date delle bollette + giorno dopo (partite notturne es. 00:30)
  const dateSet = new Set();
  for (const b of bollette) {
    if (!b.date) continue;
    dateSet.add(b.date);
    const next = new Date(b.date);
    next.setDate(next.getDate() + 1);
    dateSet.add(next.toISOString().split('T')[0]);
  }
  const dates = [...dateSet];
  if (!dates.length) return bollette;

  // Stessa fonte della pagina pronostici: h2h_by_round (come endpoint /live-scores)
  const dateRanges = dates.map(d => ({
    start: new Date(d + 'T00:00:00.000Z'),
    end: new Date(d + 'T23:59:59.999Z'),
  }));
  const dateConditions = dateRanges.map(r => ({
    'matches.date_obj': { $gte: r.start, $lte: r.end }
  }));

  const pipeline = [
    { $unwind: '$matches' },
    { $match: { $or: dateConditions } },
    { $project: {
      _id: 0,
      home: '$matches.home',
      away: '$matches.away',
      real_score: '$matches.real_score',
      live_score: '$matches.live_score',
      live_status: '$matches.live_status',
      live_minute: '$matches.live_minute',
    }}
  ];
  const scores = await db.collection('h2h_by_round').aggregate(pipeline).toArray();

  // Anche coppe europee (come fa /live-scores)
  for (const d of dates) {
    const [y, m, dd] = d.split('-');
    const cupDatePrefix = `${dd}-${m}-${y}`;
    for (const cupColl of ['matches_champions_league', 'matches_europa_league']) {
      const cupMatches = await db.collection(cupColl).find({
        match_date: { $regex: `^${cupDatePrefix}` }
      }).toArray();
      for (const cm of cupMatches) {
        scores.push({
          home: cm.home_team,
          away: cm.away_team,
          real_score: cm.real_score || null,
          live_score: cm.live_score || null,
          live_status: cm.live_status || null,
          live_minute: cm.live_minute || null,
        });
      }
    }
  }

  // Indice per home+away
  const scoreIndex = {};
  for (const s of scores) {
    const key = `${s.home}|${s.away}`;
    if (!scoreIndex[key] || s.real_score) {
      scoreIndex[key] = s;
    }
  }

  // Arricchisci selezioni
  for (const b of bollette) {
    for (const s of (b.selezioni || [])) {
      const key = `${s.home}|${s.away}`;
      const info = scoreIndex[key];
      if (info) {
        if (info.real_score) s.real_score = info.real_score;
        if (info.live_score) s.live_score = info.live_score;
        if (info.live_status) s.live_status = info.live_status;
        if (info.live_minute != null) s.live_minute = info.live_minute;
        if (info.live_status === 'Finished' || info.real_score) s.match_finished = true;
      }
    }
  }
  return bollette;
}

// ============================================
// GET /bollette?date=YYYY-MM-DD
// Lista bollette per data (default: oggi). Pubblico.
// ============================================
router.get('/', async (req, res) => {
  try {
    const date = req.query.date || new Date().toISOString().split('T')[0];
    let bollette = await req.db.collection('bollette')
      .find({ date })
      .sort({ tipo: 1, quota_totale: 1 })
      .project({ reasoning: 0 }) // reasoning solo per debug
      .toArray();

    bollette = await enrichBollette(req.db, bollette);
    res.json({ success: true, date, bollette });
  } catch (err) {
    console.error('Errore GET /bollette:', err);
    res.status(500).json({ success: false, error: 'Errore server' });
  }
});

// ============================================
// GET /bollette/storico?date=YYYY-MM-DD — Bollette + stats per data
// ============================================
router.get('/storico', async (req, res) => {
  try {
    const date = req.query.date;
    if (!date) return res.status(400).json({ success: false, error: 'Parametro date richiesto' });

    let bollette = await req.db.collection('bollette')
      .find({ date, custom: { $ne: true } })
      .sort({ tipo: 1, quota_totale: 1 })
      .toArray();

    bollette = await enrichBollette(req.db, bollette);

    // Stats per fascia
    const stats = { totale: bollette.length, per_tipo: {} };
    for (const b of bollette) {
      const tipo = b.tipo || 'altro';
      if (!stats.per_tipo[tipo]) stats.per_tipo[tipo] = { totale: 0, vinte: 0, perse: 0, pending: 0 };
      stats.per_tipo[tipo].totale++;
      if (b.esito_globale === 'vinta') stats.per_tipo[tipo].vinte++;
      else if (b.esito_globale === 'persa') stats.per_tipo[tipo].perse++;
      else stats.per_tipo[tipo].pending++;
    }

    // Stats globali
    const vinte = bollette.filter(b => b.esito_globale === 'vinta').length;
    const perse = bollette.filter(b => b.esito_globale === 'persa').length;
    const pending = bollette.filter(b => !b.esito_globale).length;

    res.json({
      success: true, date, bollette,
      stats: { totale: bollette.length, vinte, perse, pending, per_tipo: stats.per_tipo },
    });
  } catch (err) {
    console.error('Errore GET /bollette/storico:', err);
    res.status(500).json({ success: false, error: 'Errore server' });
  }
});

// ============================================
// GET /bollette/date-disponibili — Lista date con bollette generate
// ============================================
router.get('/date-disponibili', async (req, res) => {
  try {
    const dates = await req.db.collection('bollette').distinct('date', { custom: { $ne: true } });
    res.json({ success: true, dates: dates.sort().reverse() });
  } catch (err) {
    console.error('Errore GET /bollette/date-disponibili:', err);
    res.status(500).json({ success: false, error: 'Errore server' });
  }
});

// ============================================
// PUT /bollette/:id/save — Toggle saved_by (auth)
// ============================================
router.put('/:id/save', authenticate, async (req, res) => {
  try {
    const bolId = new ObjectId(req.params.id);
    const uid = req.userId;

    const doc = await req.db.collection('bollette').findOne({ _id: bolId });
    if (!doc) return res.status(404).json({ success: false, error: 'Bolletta non trovata' });

    const isSaved = (doc.saved_by || []).includes(uid);
    const stakeAmount = req.body?.stake_amount || 0;

    if (isSaved) {
      await req.db.collection('bollette').updateOne(
        { _id: bolId },
        { $pull: { saved_by: uid }, $unset: { [`user_stakes.${uid}`]: '' } }
      );
    } else {
      const update = { $addToSet: { saved_by: uid } };
      if (stakeAmount > 0) {
        update.$set = { [`user_stakes.${uid}`]: stakeAmount };
      }
      await req.db.collection('bollette').updateOne({ _id: bolId }, update);
    }

    res.json({ success: true, saved: !isSaved });
  } catch (err) {
    console.error('Errore PUT /bollette/:id/save:', err);
    res.status(500).json({ success: false, error: 'Errore server' });
  }
});

// ============================================
// GET /bollette/saved — Bollette salvate dall'utente (auth)
// ============================================
router.get('/saved', authenticate, async (req, res) => {
  try {
    const uid = req.userId;
    const bollette = await req.db.collection('bollette')
      .find({ saved_by: uid })
      .sort({ date: -1 })
      .project({ reasoning: 0 })
      .toArray();

    res.json({ success: true, bollette });
  } catch (err) {
    console.error('Errore GET /bollette/saved:', err);
    res.status(500).json({ success: false, error: 'Errore server' });
  }
});

// ============================================
// POST /bollette/generate — Genera bolletta on-demand con Mistral (auth)
// L'utente descrive cosa vuole, Mistral compone la bolletta dal pool
// ============================================
const MISTRAL_URL = 'https://api.mistral.ai/v1/chat/completions';
const MISTRAL_MODEL = 'mistral-small-latest';

router.post('/generate', authenticate, async (req, res) => {
  try {
    const { message, history } = req.body;
    if (!message || !message.trim()) {
      return res.status(400).json({ success: false, error: 'Messaggio richiesto' });
    }

    const MISTRAL_API_KEY = process.env.MISTRAL_API_KEY;
    if (!MISTRAL_API_KEY) {
      return res.status(500).json({ success: false, error: 'MISTRAL_API_KEY non configurata' });
    }

    // 1. Leggi pool pronostici (oggi + domani + dopodomani, no partite già iniziate)
    // Usa ora CET (Europe/Rome) perché match_time è in CET
    const nowUtc = new Date();
    const nowCET = new Date(nowUtc.toLocaleString('en-US', { timeZone: 'Europe/Rome' }));
    const dates = [];
    for (let i = 0; i < 3; i++) {
      const d = new Date(nowCET);
      d.setDate(d.getDate() + i);
      dates.push(d.toISOString().split('T')[0]);
    }

    const docs = await req.db.collection('daily_predictions_unified')
      .find({ date: { $in: dates } })
      .project({ home: 1, away: 1, date: 1, league: 1, match_time: 1, pronostici: 1, odds: 1 })
      .toArray();

    // Costruisci pool (escludi partite iniziate e RE)
    const pool = [];
    const allMatches = []; // tutte le partite con odds per selezioni fuori pool
    for (const doc of docs) {
      const matchDate = doc.date;
      const matchTime = doc.match_time || '00:00';
      try {
        const [hh, mm] = matchTime.split(':').map(Number);
        const kickOff = new Date(matchDate);
        kickOff.setHours(hh, mm, 0, 0);
        if (kickOff <= nowCET) continue;
      } catch (_) {}

      // Salva partita con odds per selezioni fuori pool
      allMatches.push({
        match_key: `${doc.home} vs ${doc.away}|${matchDate}`,
        home: doc.home, away: doc.away, league: doc.league || '',
        match_time: matchTime, match_date: matchDate,
        odds: doc.odds || {},
      });

      for (const p of (doc.pronostici || [])) {
        const quota = p.quota;
        if (!quota || quota <= 1.0) continue;
        if (p.tipo === 'RISULTATO_ESATTO') continue;

        pool.push({
          match_key: `${doc.home} vs ${doc.away}|${matchDate}`,
          home: doc.home,
          away: doc.away,
          league: doc.league || '',
          match_time: matchTime,
          match_date: matchDate,
          mercato: p.tipo || '',
          pronostico: p.pronostico || '',
          quota: Math.round(quota * 100) / 100,
          confidence: p.confidence || 0,
          stars: p.stars || 0,
        });
      }
    }

    if (pool.length < 2) {
      return res.json({ success: false, error: 'Pool insufficiente per generare una bolletta' });
    }

    // 2. Serializza pool
    const poolByDate = {};
    for (const s of pool) {
      if (!poolByDate[s.match_date]) poolByDate[s.match_date] = [];
      poolByDate[s.match_date].push(s);
    }
    let poolText = '';
    for (const date of Object.keys(poolByDate).sort()) {
      poolText += `\n=== PRONOSTICI AI — ${date} ===\n`;
      for (const s of poolByDate[date]) {
        poolText += `  ${s.match_key} | ${s.mercato}: ${s.pronostico} @ ${s.quota} | conf=${s.confidence} ★${s.stars}\n`;
      }
    }

    // 3. Costruisci lista partite con odds per selezioni fuori pool
    let matchesText = '\n=== PARTITE DISPONIBILI CON QUOTE ===\n';
    for (const m of allMatches) {
      const o = m.odds;
      const parts = [];
      if (o['1']) parts.push(`1=${o['1']}`);
      if (o['X']) parts.push(`X=${o['X']}`);
      if (o['2']) parts.push(`2=${o['2']}`);
      // Doppie chance calcolate
      if (o['1'] && o['X']) { const dc1x = (1 / (1/o['1'] + 1/o['X'])).toFixed(2); parts.push(`1X=${dc1x}`); }
      if (o['X'] && o['2']) { const dcx2 = (1 / (1/o['X'] + 1/o['2'])).toFixed(2); parts.push(`X2=${dcx2}`); }
      if (o['1'] && o['2']) { const dc12 = (1 / (1/o['1'] + 1/o['2'])).toFixed(2); parts.push(`12=${dc12}`); }
      if (o['over_15']) parts.push(`Over1.5=${o['over_15']}`);
      if (o['under_15']) parts.push(`Under1.5=${o['under_15']}`);
      if (o['over_25']) parts.push(`Over2.5=${o['over_25']}`);
      if (o['under_25']) parts.push(`Under2.5=${o['under_25']}`);
      if (o['over_35']) parts.push(`Over3.5=${o['over_35']}`);
      if (o['under_35']) parts.push(`Under3.5=${o['under_35']}`);
      if (o['gg']) parts.push(`Goal=${o['gg']}`);
      if (o['ng']) parts.push(`NoGoal=${o['ng']}`);
      matchesText += `  ${m.match_key} | ore ${m.match_time} | ${parts.join(', ')}\n`;
    }

    // 4. Chiama Mistral
    const systemPrompt = `Sei un tipster professionista con 20 anni di esperienza nelle scommesse calcistiche. Rispondi in italiano, in modo diretto e professionale.

CONVENZIONE 1-X-2 (NON SBAGLIARE MAI):
- "1" = vittoria squadra di CASA (la PRIMA nel match_key)
- "X" = pareggio
- "2" = vittoria squadra OSPITE (la SECONDA nel match_key)

COME SCEGLIERE LE PARTITE:
- Confidence (0-100) e Stelle (1-5) nei pronostici AI indicano quanto il sistema è sicuro
- Quote basse (1.20-1.50) = favorite ma poco valore, Quote alte (3.0+) = rischiose ma rendono
- Cerca VALORE: partite dove la quota offre più di quello che il rischio suggerisce
- Considera la forma recente, il fattore campo, e la qualità delle squadre
- NON mettere partite a caso — ogni selezione deve avere una motivazione

PRONOSTICI CONSIGLIATI DAL SISTEMA AI:
${poolText}

${matchesText}

La data di oggi è: ${new Date().toISOString().split('T')[0]}
L'ora attuale è: ${new Date().toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Rome' })}.
PARTITE GIÀ INIZIATE: se l'orario della partita è PRIMA dell'ora attuale E la data è oggi, quella partita è GIÀ INIZIATA. NON metterla MAI in bolletta. Esempio: ora sono le 21:00 e una partita è alle 20:45 di oggi → è GIÀ INIZIATA, non usarla.

REGOLE:
- L'utente è LIBERO di scegliere QUALSIASI pronostico su QUALSIASI partita disponibile, anche se NON è tra i pronostici AI consigliati
- Se l'utente sceglie un pronostico fuori dai consigliati AI, metti "from_pool": false nella selezione e aggiungi un flag nel campo "warnings". NON menzionare i warning nel campo "reasoning" — il reasoning deve contenere SOLO la motivazione delle scelte, senza avvisi o disclaimer
- Quando COMPONI TU la bolletta, scegli le partite con COGNIZIONE DI CAUSA: analizza le quote, cerca valore, considera i pronostici AI come guida. Non mettere partite a caso solo per raggiungere la quota target
- Nel campo "reasoning" spiega SEMPRE perché hai scelto quelle partite e quei mercati specifici — l'utente vuole capire la logica. MAI inserire avvisi ⚠️ o warning nel reasoning
- Per le quote, usa quelle dalla sezione PARTITE DISPONIBILI CON QUOTE
- Se non hai la quota per un pronostico, chiedi all'utente di fornirtela. Se te la dà, usala
- Ogni partita può apparire UNA SOLA VOLTA nella bolletta
- La quota totale = prodotto di tutte le quote
- Per selezioni fuori dai pronostici AI, aggiungi "from_pool": false

COMPORTAMENTO FONDAMENTALE:
- Quando l'utente ti chiede di comporre una bolletta (es. "fammi un biglietto con 3 partite e quota 3"), TU DEVI COMPORLA SUBITO. Sei il tipster, decidi tu quali partite mettere. NON elencare le partite chiedendo "quali vuoi?" — SCEGLI TU e restituisci direttamente la bolletta in formato JSON.
- Chiedi chiarimenti SOLO se la richiesta è veramente incomprensibile, MAI se ti ha dato indicazioni su numero partite, quota o tipo di mercato
- Se l'utente NON specifica le date (es. "fammi un biglietto con 5 partite"), chiedigli: "Vuoi partite solo di oggi, solo dei prossimi giorni, o un mix?"
- Se l'utente NON specifica una quota target, chiedigli anche: "Hai in mente una quota totale target o posso sceglierla io?"
- Fai ENTRAMBE le domande in un unico messaggio, non in due messaggi separati. Se l'utente risponde che non gli interessa la quota, scegli tu da professionista
- Se l'utente chiede info sulle partite (non una bolletta), allora puoi elencarle
- Quando l'utente ti corregge (es. "queste sono già iniziate"), NON elencare le partite rimaste chiedendo "scegli tu". COMPONI SUBITO una nuova bolletta corretta in formato JSON e restituiscila. Sei il tipster, DECIDI TU.

QUOTA TARGET — OBBLIGATORIO:
- Quota totale = prodotto delle quote singole. Tolleranza: ±10%.
- PRIMA di rispondere DEVI fare il calcolo. Se sbaglia, CAMBIA selezione.
- Esempi:
  * Quota 3, 3 partite → serve media ~1.45 (1.45 × 1.45 × 1.45 = 3.05 ✅)
  * Quota 3, 4 partite → serve media ~1.32 (1.32 × 1.32 × 1.32 × 1.32 = 3.03 ✅)
  * Quota 5, 3 partite → serve media ~1.71 (1.71 × 1.71 × 1.71 = 5.00 ✅)
  * SBAGLIATO: quota target 3, selezioni 1.67 × 1.65 × 1.37 × 1.35 = 5.10 ❌ (troppo alta!)
- Se metti quote troppo alte o troppo basse, USA MERCATI DIVERSI. Mercati con quote basse: DC, Over 1.5. Mercati con quote medie: Under 2.5, Goal. Mercati con quote alte: 1X2, Under 1.5.

COME RISPONDERE:
- Sii COMPLETO e DETTAGLIATO fin dalla prima risposta
- Quando elenchi partite, ORDINALE per data e poi per orario. Usa il formato: "📅 Oggi (15/03):" poi "📅 Domani (16/03):" ecc.
- Per ogni partita mostra: nome squadre, orario, e i mercati disponibili con quote
- Distingui SEMPRE tra oggi, domani, dopodomani — non mescolare le date
- "Questa sera" significa SOLO partite di OGGI con orario serale, non domani o dopodomani
- Rispondi in italiano, sii diretto e professionale

FORMATO RISPOSTA — SEMPRE JSON valido. Nessun testo fuori dal JSON. Nessun markdown.
ATTENZIONE: anche quando CORREGGI un errore o l'utente ti chiede di rifare, rispondi SEMPRE con il JSON bolletta pulito. MAI mettere JSON dentro un blocco di testo o dentro \`\`\`json\`\`\`. Ogni risposta è O una bolletta O un messaggio, mai un mix.

Bolletta:
{"type": "bolletta", "selezioni": [{"match_key": "Home vs Away|YYYY-MM-DD", "mercato": "SEGNO", "pronostico": "2", "quota": 1.85, "from_pool": false}], "reasoning": "Ho scelto queste partite perché...", "warnings": ["non_pool"]}

Risposta testuale:
{"type": "messaggio", "text": "La tua risposta qui. Usa \\n per andare a capo."}

match_key deve essere nel formato "Home vs Away|YYYY-MM-DD" delle partite disponibili.`;

    const resp = await fetch(MISTRAL_URL, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${MISTRAL_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: MISTRAL_MODEL,
        messages: [
          { role: 'system', content: systemPrompt },
          ...(history || []).map(h => ({ role: h.role, content: h.content })),
          { role: 'user', content: message },
        ],
        temperature: 0.4,
        max_tokens: 4000,
      }),
    });

    if (!resp.ok) {
      const errText = await resp.text();
      console.error('Errore Mistral:', resp.status, errText);
      return res.status(502).json({ success: false, error: 'Errore nella generazione' });
    }

    const data = await resp.json();
    let content = (data.choices?.[0]?.message?.content || '').trim();

    // Rimuovi markdown wrapping
    if (content.startsWith('```')) {
      content = content.replace(/^```(?:json)?\s*/, '').replace(/\s*```$/, '');
    }

    let generated;
    try {
      generated = JSON.parse(content);
    } catch (_) {
      // Se il JSON non è valido, Mistral ha probabilmente risposto in testo libero
      // Restituiscilo come messaggio testuale
      if (content && content.length > 5) {
        return res.json({ success: true, type: 'messaggio', text: content });
      }
      return res.json({ success: false, error: 'Non ho capito la richiesta. Prova a chiedermi una bolletta, ad esempio: "Fammi una bolletta con quota 5"' });
    }

    // Gestisci risposte non-bolletta
    if (generated.type === 'messaggio') {
      return res.json({ success: true, type: 'messaggio', text: generated.text || '' });
    }
    if (generated.error) {
      return res.json({ success: false, error: generated.error });
    }

    // Valida selezioni — dal pool o fuori pool
    const poolIndex = {};
    for (const s of pool) {
      poolIndex[`${s.match_key}|${s.mercato}|${s.pronostico}`] = s;
    }
    const matchIndex = {};
    for (const m of allMatches) {
      matchIndex[m.match_key] = m;
    }

    const selezioni = [];
    let quotaTotale = 1.0;
    const warnings = generated.warnings || [];

    for (const sel of (generated.selezioni || [])) {
      const key = `${sel.match_key}|${sel.mercato}|${sel.pronostico}`;
      const entry = poolIndex[key];

      if (entry) {
        // Selezione dal pool AI
        quotaTotale *= entry.quota;
        selezioni.push({
          home: entry.home, away: entry.away, league: entry.league,
          match_time: entry.match_time, match_date: entry.match_date,
          mercato: entry.mercato, pronostico: entry.pronostico,
          quota: entry.quota, confidence: entry.confidence, stars: entry.stars,
          esito: null, from_pool: true,
        });
      } else {
        // Selezione fuori pool — usa dati dalla partita + quota da Mistral
        const match = matchIndex[sel.match_key];
        if (!match && !sel.quota) continue; // partita non esiste e nessuna quota

        const quota = sel.quota || 0;
        if (quota <= 0) continue;

        quotaTotale *= quota;
        selezioni.push({
          home: match?.home || sel.match_key.split(' vs ')[0]?.split('|')[0] || '',
          away: match?.away || sel.match_key.split(' vs ')[1]?.split('|')[0] || '',
          league: match?.league || '',
          match_time: match?.match_time || '',
          match_date: match?.match_date || sel.match_key.split('|')[1] || '',
          mercato: sel.mercato, pronostico: sel.pronostico,
          quota: quota, confidence: 0, stars: 0,
          esito: null, from_pool: false,
        });
      }
    }

    if (selezioni.length < 1) {
      return res.json({ success: false, error: 'Nessuna selezione valida trovata nel pool' });
    }

    quotaTotale = Math.round(quotaTotale * 100) / 100;

    // Determina tipo
    let tipo = 'ambiziosa';
    if (quotaTotale < 3.0) tipo = 'selettiva';
    else if (quotaTotale < 8.0) tipo = 'bilanciata';

    const bolletta = {
      selezioni,
      quota_totale: quotaTotale,
      tipo,
      reasoning: generated.reasoning || '',
    };

    res.json({ success: true, type: 'bolletta', bolletta, warnings });
  } catch (err) {
    console.error('Errore POST /bollette/generate:', err);
    res.status(500).json({ success: false, error: 'Errore server' });
  }
});

// ============================================
// POST /bollette/save-custom — Salva bolletta personalizzata (auth)
// ============================================
router.post('/save-custom', authenticate, async (req, res) => {
  try {
    const { bolletta } = req.body;
    if (!bolletta || !bolletta.selezioni || bolletta.selezioni.length < 1) {
      return res.status(400).json({ success: false, error: 'Bolletta non valida' });
    }

    const today = new Date().toISOString().split('T')[0];
    const doc = {
      date: today,
      tipo: bolletta.tipo || 'bilanciata',
      quota_totale: bolletta.quota_totale,
      label: 'Personalizzata',
      selezioni: bolletta.selezioni,
      esito_globale: null,
      saved_by: [req.userId],
      reasoning: bolletta.reasoning || '',
      generated_at: new Date(),
      custom: true,
      user_id: req.userId,
      pool_size: 0,
      version: 1,
    };

    const result = await req.db.collection('bollette').insertOne(doc);
    doc._id = result.insertedId;

    res.json({ success: true, bolletta: doc });
  } catch (err) {
    console.error('Errore POST /bollette/save-custom:', err);
    res.status(500).json({ success: false, error: 'Errore server' });
  }
});

// ============================================
// GET /bollette/custom — Bollette personalizzate dell'utente (auth)
// ============================================
router.get('/custom', authenticate, async (req, res) => {
  try {
    const bollette = await req.db.collection('bollette')
      .find({ custom: true, user_id: req.userId })
      .sort({ generated_at: -1 })
      .project({ reasoning: 0 })
      .toArray();

    res.json({ success: true, bollette });
  } catch (err) {
    console.error('Errore GET /bollette/custom:', err);
    res.status(500).json({ success: false, error: 'Errore server' });
  }
});

// ============================================
// DELETE /bollette/:id/remove — Rimuove bolletta personalizzata (auth)
// ============================================
router.delete('/:id/remove', authenticate, async (req, res) => {
  try {
    const bolId = new ObjectId(req.params.id);
    const uid = req.userId;

    const doc = await req.db.collection('bollette').findOne({ _id: bolId });
    if (!doc) return res.status(404).json({ success: false, error: 'Bolletta non trovata' });

    // Se è una bolletta custom dell'utente, la elimina completamente
    if (doc.custom && doc.user_id === uid) {
      await req.db.collection('bollette').deleteOne({ _id: bolId });
      return res.json({ success: true, deleted: true });
    }

    // Se è una bolletta di sistema, rimuove solo il salvataggio dell'utente
    await req.db.collection('bollette').updateOne(
      { _id: bolId },
      { $pull: { saved_by: uid }, $unset: { [`user_stakes.${uid}`]: '' } }
    );
    res.json({ success: true, deleted: false, unsaved: true });
  } catch (err) {
    console.error('Errore DELETE /bollette/:id/remove:', err);
    res.status(500).json({ success: false, error: 'Errore server' });
  }
});

// ============================================
// GET /bollette/my — Tutte le bollette dell'utente (salvate + custom, tutti i giorni) (auth)
// ============================================
router.get('/my', authenticate, async (req, res) => {
  try {
    const uid = req.userId;
    let bollette = await req.db.collection('bollette')
      .find({ $or: [{ saved_by: uid }, { custom: true, user_id: uid }] })
      .sort({ date: -1, generated_at: -1 })
      .toArray();

    bollette = await enrichBollette(req.db, bollette);

    // Stats
    let vinte = 0, perse = 0, inCorso = 0, totaleStake = 0, totaleProfitto = 0;
    for (const b of bollette) {
      const stake = b.user_stakes?.[uid] || 0;
      totaleStake += stake;

      if (b.esito_globale === 'vinta') {
        vinte++;
        totaleProfitto += stake * (b.quota_totale - 1);
      } else if (b.esito_globale === 'persa') {
        perse++;
        totaleProfitto -= stake;
      } else {
        inCorso++;
      }
    }

    res.json({
      success: true,
      bollette,
      stats: { vinte, perse, in_corso: inCorso, totale: bollette.length, totale_stake: totaleStake, profitto: Math.round(totaleProfitto * 100) / 100 },
    });
  } catch (err) {
    console.error('Errore GET /bollette/my:', err);
    res.status(500).json({ success: false, error: 'Errore server' });
  }
});

module.exports = router;
