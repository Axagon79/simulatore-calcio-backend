/**
 * MongoDB Atlas Trigger — Propaga real_score da h2h_by_round a daily_predictions_unified
 *
 * CONFIGURAZIONE ATLAS:
 * 1. Atlas Console → Triggers → Add Trigger
 * 2. Tipo: Database
 * 3. Cluster: pup-pals-cluster
 * 4. Database: football_simulator_db
 * 5. Collection: h2h_by_round
 * 6. Operation Type: Insert, Update, Replace
 * 7. Full Document: ON
 * 8. Incollare il codice qui sotto
 *
 * Quando un risultato arriva in h2h_by_round, trova le predictions
 * corrispondenti e scrive real_score + hit direttamente nel documento.
 * Così l'endpoint non deve più fare aggregation.
 */

exports = async function(changeEvent) {
  const fullDoc = changeEvent.fullDocument;
  if (!fullDoc || !fullDoc.matches) return;

  const db = context.services.get("pup-pals-cluster").db(changeEvent.ns.db);

  // Trova match con risultato finale
  const finishedMatches = (fullDoc.matches || []).filter(
    m => m.status === "Finished" && m.real_score
  );

  if (finishedMatches.length === 0) return;

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

  // Per ogni partita finita, aggiorna la prediction corrispondente
  for (const match of finishedMatches) {
    const dateStr = match.date_obj
      ? new Date(match.date_obj).toISOString().split("T")[0]
      : null;
    if (!dateStr) continue;

    // Trova la prediction
    const pred = await db.collection("daily_predictions_unified").findOne({
      home: match.home,
      away: match.away,
      date: dateStr
    });

    if (!pred) continue;
    // Se ha già real_score uguale, skip
    if (pred.real_score === match.real_score) continue;

    const parsed = parseScore(match.real_score);
    const realSign = parsed ? parsed.sign : null;

    // Calcola hit per ogni pronostico
    const updatedPronostici = (pred.pronostici || []).map(p => {
      const hit = parsed ? checkPronostico(p.pronostico, p.tipo, parsed) : null;
      return { ...p, hit };
    });

    const matchHit = updatedPronostici.some(p => p.hit === true);

    // Aggiorna il documento
    await db.collection("daily_predictions_unified").updateOne(
      { _id: pred._id },
      {
        $set: {
          real_score: match.real_score,
          real_sign: realSign,
          hit: matchHit,
          pronostici: updatedPronostici,
          real_score_updated_at: new Date()
        }
      }
    );

    console.log(`Propagato ${match.real_score} a ${match.home} vs ${match.away} (${dateStr})`);
  }
};
