/**
 * MongoDB Atlas Trigger — Aggiorna collection `pl_storico`
 *
 * COME CONFIGURARE IN ATLAS:
 * 1. Atlas Console → App Services → Triggers → Add Trigger
 * 2. Tipo: Database Trigger
 * 3. Cluster: pup-pals-cluster
 * 4. Database: (il tuo DB)
 * 5. Collection: daily_predictions_unified
 * 6. Operation Type: Insert, Update, Replace
 * 7. Full Document: ON
 * 8. Incollare il codice della funzione qui sotto
 *
 * Il trigger ricalcola il P/L del giorno ogni volta che un documento
 * in daily_predictions_unified viene modificato (es. daemon aggiorna
 * live_score, step 29 scrive esito).
 */

exports = async function(changeEvent) {
  const doc = changeEvent.fullDocument;
  if (!doc || !doc.date) return;

  const targetDate = doc.date;
  const db = context.services.get("mongodb-atlas").db(changeEvent.ns.db);

  // Recupera tutti i pronostici del giorno
  const dayDocs = await db.collection("daily_predictions_unified")
    .find({ date: targetDate })
    .toArray();

  // --- Helper: parse score "H:A" ---
  function parseScore(s) {
    if (!s || typeof s !== "string") return null;
    const parts = s.split(":");
    if (parts.length !== 2) return null;
    const home = parseInt(parts[0]), away = parseInt(parts[1]);
    if (isNaN(home) || isNaN(away)) return null;
    let sign;
    if (home > away) sign = "1";
    else if (home < away) sign = "2";
    else sign = "X";
    return { home, away, total: home + away, sign, btts: home > 0 && away > 0 };
  }

  // --- Helper: verifica pronostico ---
  function checkPronostico(pronostico, tipo, parsed) {
    if (!parsed || !pronostico) return null;
    const p = pronostico.trim();

    if (tipo === "SEGNO") return p === parsed.sign;

    if (tipo === "DOPPIA_CHANCE") {
      if (p === "1X") return parsed.sign === "1" || parsed.sign === "X";
      if (p === "X2") return parsed.sign === "X" || parsed.sign === "2";
      if (p === "12") return parsed.sign === "1" || parsed.sign === "2";
      return null;
    }

    if (tipo === "GOL") {
      const overMatch = p.match(/^Over\s+(\d+\.?\d*)$/i);
      if (overMatch) return parsed.total > parseFloat(overMatch[1]);
      const underMatch = p.match(/^Under\s+(\d+\.?\d*)$/i);
      if (underMatch) return parsed.total < parseFloat(underMatch[1]);
      if (p.toLowerCase() === "goal") return parsed.btts;
      if (p.toLowerCase() === "nogoal") return !parsed.btts;
      const mgMatch = p.match(/^MG\s+(\d+)-(\d+)$/i);
      if (mgMatch) return parsed.total >= parseInt(mgMatch[1]) && parsed.total <= parseInt(mgMatch[2]);
      return null;
    }

    if (tipo === "X_FACTOR") return p === parsed.sign;

    if (tipo === "RISULTATO_ESATTO") {
      return p.replace("-", ":") === `${parsed.home}:${parsed.away}`;
    }

    return null;
  }

  // --- Calcolo P/L per sezioni ---
  const sez = {
    tutti: { pl: 0, bets: 0, wins: 0, staked: 0 },
    pronostici: { pl: 0, bets: 0, wins: 0, staked: 0 },
    elite: { pl: 0, bets: 0, wins: 0, staked: 0 },
    alto_rendimento: { pl: 0, bets: 0, wins: 0, staked: 0 },
  };

  for (const doc of dayDocs) {
    const score = doc.live_score || null;
    const matchOver = (() => {
      if (doc.live_status === "Finished") return true;
      if (doc.date && doc.match_time) {
        const kickoff = new Date(`${doc.date}T${doc.match_time}:00`);
        const elapsed = (Date.now() - kickoff.getTime()) / (1000 * 60);
        if (elapsed > 130) return true;
      }
      return false;
    })();

    for (const p of (doc.pronostici || [])) {
      // Priorità: esito dallo step 29, poi calcolo da score
      let esito = p.esito;
      if ((esito === undefined || esito === null) && score && matchOver) {
        const parsed = parseScore(score);
        if (parsed) esito = checkPronostico(p.pronostico, p.tipo, parsed);
      }

      if (esito === undefined || esito === null || esito === "void") continue;
      const quota = p.quota || 0;
      const stake = p.stake || 1;
      if (quota <= 1) continue;
      if (p.pronostico === "NO BET") continue;

      const profit = esito === true ? (quota - 1) * stake : -stake;
      const isHit = esito === true;

      const soglia = p.tipo === "DOPPIA_CHANCE" ? 2.00 : 2.51;
      const isAltoRendimento = p.tipo === "RISULTATO_ESATTO" || quota >= soglia;
      const isPronostici = !isAltoRendimento && p.tipo !== "RISULTATO_ESATTO";

      sez.tutti.bets++; sez.tutti.staked += stake; sez.tutti.pl += profit;
      if (isHit) sez.tutti.wins++;

      if (isPronostici) {
        sez.pronostici.bets++; sez.pronostici.staked += stake; sez.pronostici.pl += profit;
        if (isHit) sez.pronostici.wins++;
      }

      if (p.elite) {
        sez.elite.bets++; sez.elite.staked += stake; sez.elite.pl += profit;
        if (isHit) sez.elite.wins++;
      }

      if (isAltoRendimento) {
        sez.alto_rendimento.bets++; sez.alto_rendimento.staked += stake; sez.alto_rendimento.pl += profit;
        if (isHit) sez.alto_rendimento.wins++;
      }
    }
  }

  // Arrotonda e calcola HR/ROI
  for (const s of Object.values(sez)) {
    s.pl = Math.round(s.pl * 100) / 100;
    s.staked = Math.round(s.staked * 100) / 100;
    s.hr = s.bets > 0 ? Math.round((s.wins / s.bets) * 1000) / 10 : 0;
    s.roi = s.staked > 0 ? Math.round((s.pl / s.staked) * 1000) / 10 : 0;
  }

  // Upsert in pl_storico
  await db.collection("pl_storico").updateOne(
    { date: targetDate },
    {
      $set: {
        ...sez,
        updated_at: new Date(),
      },
      $setOnInsert: {
        date: targetDate,
        created_at: new Date(),
      }
    },
    { upsert: true }
  );

  console.log(`pl_storico aggiornato per ${targetDate}: bets=${sez.tutti.bets}, pl=${sez.tutti.pl}`);
};
