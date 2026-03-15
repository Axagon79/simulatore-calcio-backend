const express = require('express');
const router = express.Router();
const { ObjectId } = require('mongodb');
const authenticate = require('../middleware/auth');

// ============================================
// GET /bollette?date=YYYY-MM-DD
// Lista bollette per data (default: oggi). Pubblico.
// ============================================
router.get('/', async (req, res) => {
  try {
    const date = req.query.date || new Date().toISOString().split('T')[0];
    const bollette = await req.db.collection('bollette')
      .find({ date })
      .sort({ tipo: 1, quota_totale: 1 })
      .project({ reasoning: 0 }) // reasoning solo per debug
      .toArray();

    res.json({ success: true, date, bollette });
  } catch (err) {
    console.error('Errore GET /bollette:', err);
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

    if (isSaved) {
      await req.db.collection('bollette').updateOne(
        { _id: bolId },
        { $pull: { saved_by: uid } }
      );
    } else {
      await req.db.collection('bollette').updateOne(
        { _id: bolId },
        { $addToSet: { saved_by: uid } }
      );
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
    const now = new Date();
    const dates = [];
    for (let i = 0; i < 3; i++) {
      const d = new Date(now);
      d.setDate(d.getDate() + i);
      dates.push(d.toISOString().split('T')[0]);
    }

    const docs = await req.db.collection('daily_predictions_unified')
      .find({ date: { $in: dates } })
      .project({ home: 1, away: 1, date: 1, league: 1, match_time: 1, pronostici: 1 })
      .toArray();

    // Costruisci pool (escludi partite iniziate e RE)
    const pool = [];
    for (const doc of docs) {
      const matchDate = doc.date;
      const matchTime = doc.match_time || '00:00';
      try {
        const kickOff = new Date(`${matchDate}T${matchTime}:00`);
        if (kickOff <= now) continue;
      } catch (_) {}

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
      poolText += `\n=== ${date} ===\n`;
      for (const s of poolByDate[date]) {
        poolText += `  ${s.match_key} | ${s.mercato}: ${s.pronostico} @ ${s.quota} | conf=${s.confidence} ★${s.stars}\n`;
      }
    }

    // 3. Chiama Mistral
    const systemPrompt = `Sei un tipster professionista con 20 anni di esperienza. L'utente ti chiede di comporre una bolletta scommesse personalizzata.

Hai a disposizione questo pool di pronostici generati da un sistema AI:
${poolText}

REGOLE:
- Ogni partita può apparire UNA SOLA VOLTA nella bolletta, con UN SOLO mercato
- La quota totale si calcola MOLTIPLICANDO le quote delle selezioni tra loro
- Rispetta le indicazioni dell'utente (quota target, numero selezioni, tipo, ecc.)
- Se l'utente non specifica, usa il tuo giudizio da professionista
- NON inventare partite o pronostici che non sono nel pool

FORMATO RISPOSTA — Restituisci SEMPRE un JSON valido. Nessun testo prima o dopo. Nessun markdown.

Se generi o aggiorni una bolletta:
{"type": "bolletta", "selezioni": [{"match_key": "Home vs Away|YYYY-MM-DD", "mercato": "TIPO", "pronostico": "valore"}], "reasoning": "Motivazione"}

Se rispondi a una domanda, spieghi una scelta, o dai info sulle partite:
{"type": "messaggio", "text": "La tua risposta qui..."}

Se la richiesta non riguarda calcio/scommesse:
{"type": "messaggio", "text": "Posso aiutarti a comporre bollette o darti info sulle partite disponibili!"}

match_key, mercato e pronostico devono corrispondere ESATTAMENTE al pool.`;

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
        max_tokens: 2000,
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
      return res.json({ success: false, error: 'Non ho capito la richiesta. Prova a chiedermi una bolletta, ad esempio: "Fammi una bolletta con quota 5"' });
    }

    // Gestisci risposte non-bolletta
    if (generated.type === 'messaggio') {
      return res.json({ success: true, type: 'messaggio', text: generated.text || '' });
    }
    if (generated.error) {
      return res.json({ success: false, error: generated.error });
    }

    // 4. Valida selezioni contro il pool (type === 'bolletta' o legacy)
    const poolIndex = {};
    for (const s of pool) {
      poolIndex[`${s.match_key}|${s.mercato}|${s.pronostico}`] = s;
    }

    const selezioni = [];
    let quotaTotale = 1.0;
    for (const sel of (generated.selezioni || [])) {
      const key = `${sel.match_key}|${sel.mercato}|${sel.pronostico}`;
      const entry = poolIndex[key];
      if (!entry) continue;

      quotaTotale *= entry.quota;
      selezioni.push({
        home: entry.home,
        away: entry.away,
        league: entry.league,
        match_time: entry.match_time,
        match_date: entry.match_date,
        mercato: entry.mercato,
        pronostico: entry.pronostico,
        quota: entry.quota,
        confidence: entry.confidence,
        stars: entry.stars,
        esito: null,
      });
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

    res.json({ success: true, type: 'bolletta', bolletta });
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

module.exports = router;
