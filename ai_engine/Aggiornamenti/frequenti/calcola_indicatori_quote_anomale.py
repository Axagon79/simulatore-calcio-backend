"""
MOTORE DI CALCOLO — Indicatori Quote Anomale
Legge i dati grezzi da `quote_anomale`, calcola i 6 indicatori, li riscrive nel documento.

Indicatori (tutti per singola quota 1/X/2 dove applicabile):
1. Semaforo scostamento (delta pp tra prob implicite)
2. Alert Break-even (delta_pp > aggio specifico)
3. Direzione movimento (conferma/dubbio/stabile)
4. V-Index Relativo (potenziale perso vs apertura)
5. V-Index Assoluto (quota vs media fair book + qt modello, con aggio live ridistribuito)
6. Rendimento + HWR/DR/AWR + aggio per quota
"""
import os
import sys
from datetime import datetime, timezone

# --- Fix percorsi ---
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_dir = os.path.dirname(os.path.dirname(current_dir))
project_root = os.path.dirname(ai_engine_dir)
if ai_engine_dir not in sys.path: sys.path.insert(0, ai_engine_dir)
if project_root not in sys.path: sys.path.insert(0, project_root)

try:
    from config import db
    print(f"✅ DB Connesso: {db.name}")
except ImportError:
    sys.path.append(r"C:\Progetti\simulatore-calcio-backend")
    try:
        from config import db
    except:
        print("❌ Impossibile connettersi al DB.")
        sys.exit(1)

COLLECTION = "quote_anomale"

# --- SOGLIE (da calibrare insieme) ---
# Per ora placeholder — verranno decise dopo analisi dati reali
SOGLIE_SEMAFORO = {
    "giallo": 2.0,     # pp
    "arancione": 5.0,   # pp
    "rosso": 10.0,      # pp
}

# =============================================================================
# FUNZIONI DI CALCOLO
# =============================================================================

def prob_implicita(quota):
    """Probabilità implicita: P = 1/quota. Ritorna 0 se quota non valida."""
    if quota and quota > 0:
        return 1.0 / quota
    return 0.0


def calcola_semaforo(q_apertura, q_chiusura):
    """
    Indicatore 1: Semaforo scostamento.
    Delta in punti percentuali tra prob implicite apertura e chiusura.
    Ritorna: {"delta_pp": float, "livello": str}
    """
    p_ap = prob_implicita(q_apertura)
    p_ch = prob_implicita(q_chiusura)
    delta_pp = abs(p_ch - p_ap) * 100

    if delta_pp >= SOGLIE_SEMAFORO["rosso"]:
        livello = "rosso"
    elif delta_pp >= SOGLIE_SEMAFORO["arancione"]:
        livello = "arancione"
    elif delta_pp >= SOGLIE_SEMAFORO["giallo"]:
        livello = "giallo"
    else:
        livello = "verde"

    return {"delta_pp": round(delta_pp, 2), "livello": livello}


def calcola_breakeven(q1_ap, qx_ap, q2_ap, q_apertura, q_chiusura):
    """
    Indicatore 2: Alert Break-even per singola quota.
    Aggio_Tot = (Somma_P - 1) × 100
    Aggio_S = (1/Q_Apertura / Somma_P) × Aggio_Tot
    Alert se delta_pp > aggio_specifico.
    Ritorna: {"aggio_specifico": float, "alert": bool}
    """
    somma_p = prob_implicita(q1_ap) + prob_implicita(qx_ap) + prob_implicita(q2_ap)
    if somma_p <= 0:
        return {"aggio_specifico": 0.0, "alert": False}

    aggio_tot = (somma_p - 1) * 100
    p_quota = prob_implicita(q_apertura)
    aggio_specifico = (p_quota / somma_p) * aggio_tot if aggio_tot > 0 else 0.0

    # Delta pp per questa quota
    p_ch = prob_implicita(q_chiusura)
    delta_pp = abs(p_ch - p_quota) * 100

    alert = delta_pp > aggio_specifico if aggio_specifico > 0 else False

    return {
        "aggio_specifico": round(aggio_specifico, 2),
        "alert": alert,
    }


def calcola_direzione(q_apertura, q_chiusura):
    """
    Indicatore 3: Direzione del movimento per singola quota.
    Quota scende → prob sale → "conferma" (mercato rafforza)
    Quota sale → prob scende → "dubbio" (mercato dubita)
    Ritorna: "conferma" | "dubbio" | "stabile"
    """
    if not q_apertura or not q_chiusura:
        return "stabile"

    diff = q_chiusura - q_apertura
    # Tolleranza minima per evitare "stabile" su micro-variazioni
    if abs(diff) < 0.02:
        return "stabile"
    elif diff < 0:
        return "conferma"  # quota scende → più probabile
    else:
        return "dubbio"     # quota sale → meno probabile


def calcola_v_index_relativo(q_apertura, q_chiusura):
    """
    Indicatore 4: V-Index Relativo.
    V_Rel = ((Q_Chiusura - 1) / (Q_Apertura - 1)) × 100
    Misura quanto guadagno potenziale si è perso rispetto all'apertura.
    Ritorna: {"valore": float}
    """
    if not q_apertura or not q_chiusura or q_apertura <= 1:
        return {"valore": 0.0}

    v_rel = ((q_chiusura - 1) / (q_apertura - 1)) * 100
    return {"valore": round(v_rel, 2)}


def calcola_v_index_assoluto_tutti(q1_ap, qx_ap, q2_ap, q1_ch, qx_ch, q2_ch,
                                   qt_1=None, qt_x=None, qt_2=None):
    """
    Indicatore 5: V-Index Assoluto (tutti e 3 i segni).

    Formula:
    1. Probabilità fair apertura book (senza aggio)
    2. Media con probabilità nostro modello (qt) se disponibili
    3. Estrai distribuzione aggio dalle quote live
    4. Applica aggio alle probabilità di riferimento
    5. Confronta quota live vs quota riferimento con aggio

    V_Abs > 100 → quota di valore (book paga più del riferimento)
    V_Abs < 100 → quota compressa (nessun valore)

    Ritorna: {"1": {"valore": float}, "X": {"valore": float}, "2": {"valore": float}}
    """
    if not all([q1_ap, qx_ap, q2_ap, q1_ch, qx_ch, q2_ch]):
        return {"1": {"valore": 0.0}, "X": {"valore": 0.0}, "2": {"valore": 0.0}}

    segni = ['1', 'X', '2']
    q_ap = {'1': q1_ap, 'X': qx_ap, '2': q2_ap}
    q_ch = {'1': q1_ch, 'X': qx_ch, '2': q2_ch}

    # Passo 1: probabilità fair apertura book (senza aggio)
    somma_p_ap = sum(1.0 / q_ap[s] for s in segni)
    p_fair_ap = {s: (1.0 / q_ap[s]) / somma_p_ap for s in segni}

    # Passo 1b: media con nostro modello (se disponibile)
    if qt_1 and qt_x and qt_2 and all(q > 0 for q in [qt_1, qt_x, qt_2]):
        qt = {'1': qt_1, 'X': qt_x, '2': qt_2}
        p_stat = {s: 1.0 / qt[s] for s in segni}
        p_ref = {s: (p_fair_ap[s] + p_stat[s]) / 2.0 for s in segni}
    else:
        # Fallback: solo fair odds apertura
        p_ref = p_fair_ap

    # Passo 2: distribuzione aggio delle quote live
    p_live = {s: 1.0 / q_ch[s] for s in segni}
    overround_live = sum(p_live[s] for s in segni)
    aggio_segno = {s: p_live[s] - (p_live[s] / overround_live) for s in segni}

    # Passo 3: applica aggio al riferimento → quota riferimento finale
    result = {}
    for s in segni:
        p_ref_adj = p_ref[s] + aggio_segno[s]
        if p_ref_adj <= 0:
            result[s] = {"valore": 0.0}
            continue
        q_ref = 1.0 / p_ref_adj
        v_abs = (q_ch[s] / q_ref) * 100.0
        result[s] = {"valore": round(v_abs, 2)}

    return result


def calcola_rendimento(q1, qx, q2):
    """
    Indicatore 6: Rendimento + HWR/DR/AWR + aggio per quota.
    Ritorno% = 1 / (1/H + 1/D + 1/A) × 100
    HWR% = Ritorno% / H
    DR% = Ritorno% / D
    AWR% = Ritorno% / A
    Ritorna: dict con tutti i valori
    """
    if not all([q1, qx, q2]) or any(q <= 0 for q in [q1, qx, q2]):
        return {
            "ritorno_pct": 0.0, "hwr": 0.0, "dr": 0.0, "awr": 0.0,
            "aggio_1": 0.0, "aggio_x": 0.0, "aggio_2": 0.0,
        }

    somma_p = 1/q1 + 1/qx + 1/q2
    ritorno_pct = (1 / somma_p) * 100
    hwr = ritorno_pct / q1
    dr = ritorno_pct / qx
    awr = ritorno_pct / q2

    # Aggio specifico per quota
    aggio_tot = (somma_p - 1) * 100
    aggio_1 = ((1/q1) / somma_p) * aggio_tot if aggio_tot > 0 else 0.0
    aggio_x = ((1/qx) / somma_p) * aggio_tot if aggio_tot > 0 else 0.0
    aggio_2 = ((1/q2) / somma_p) * aggio_tot if aggio_tot > 0 else 0.0

    return {
        "ritorno_pct": round(ritorno_pct, 2),
        "hwr": round(hwr, 2),
        "dr": round(dr, 2),
        "awr": round(awr, 2),
        "aggio_1": round(aggio_1, 2),
        "aggio_x": round(aggio_x, 2),
        "aggio_2": round(aggio_2, 2),
    }


def calcola_tutti_indicatori(doc, qt_1=None, qt_x=None, qt_2=None):
    """
    Funzione master: prende un documento quote_anomale, calcola tutti i 6 indicatori.
    qt_1/qt_x/qt_2: quote teoriche dal nostro modello (da h2h_by_round).
    Ritorna un dict con tutti gli indicatori da salvare nel documento.
    """
    qa = doc.get("quote_apertura", {})
    qc = doc.get("quote_chiusura", {})

    q1_ap = qa.get("1")
    qx_ap = qa.get("X")
    q2_ap = qa.get("2")

    q1_ch = qc.get("1")
    qx_ch = qc.get("X")
    q2_ch = qc.get("2")

    # Se non ci sono quote chiusura, non calcolare scostamenti
    if not all([q1_ch, qx_ch, q2_ch]):
        return None

    if not all([q1_ap, qx_ap, q2_ap]):
        return None

    # Somma P apertura (serve per break-even e V-Index assoluto)
    somma_p_ap = prob_implicita(q1_ap) + prob_implicita(qx_ap) + prob_implicita(q2_ap)

    # 1. Semaforo scostamento (per quota)
    semaforo = {
        "1": calcola_semaforo(q1_ap, q1_ch),
        "X": calcola_semaforo(qx_ap, qx_ch),
        "2": calcola_semaforo(q2_ap, q2_ch),
    }

    # 2. Alert Break-even (per quota)
    aggio_tot = (somma_p_ap - 1) * 100 if somma_p_ap > 1 else 0.0
    be_1 = calcola_breakeven(q1_ap, qx_ap, q2_ap, q1_ap, q1_ch)
    be_x = calcola_breakeven(q1_ap, qx_ap, q2_ap, qx_ap, qx_ch)
    be_2 = calcola_breakeven(q1_ap, qx_ap, q2_ap, q2_ap, q2_ch)

    alert_breakeven = {
        "aggio_tot": round(aggio_tot, 2),
        "1": be_1,
        "X": be_x,
        "2": be_2,
    }

    # 3. Direzione (per quota)
    direzione = {
        "1": calcola_direzione(q1_ap, q1_ch),
        "X": calcola_direzione(qx_ap, qx_ch),
        "2": calcola_direzione(q2_ap, q2_ch),
    }

    # 4. V-Index Relativo (per quota)
    v_index_rel = {
        "1": calcola_v_index_relativo(q1_ap, q1_ch),
        "X": calcola_v_index_relativo(qx_ap, qx_ch),
        "2": calcola_v_index_relativo(q2_ap, q2_ch),
    }

    # 5. V-Index Assoluto (per quota) — confronto con media fair book + qt modello
    v_index_abs = calcola_v_index_assoluto_tutti(
        q1_ap, qx_ap, q2_ap,
        q1_ch, qx_ch, q2_ch,
        qt_1=qt_1, qt_x=qt_x, qt_2=qt_2,
    )

    # 6. Rendimento (per match — apertura e chiusura)
    rendimento_apertura = calcola_rendimento(q1_ap, qx_ap, q2_ap)
    rendimento_chiusura = calcola_rendimento(q1_ch, qx_ch, q2_ch)

    return {
        "semaforo": semaforo,
        "alert_breakeven": alert_breakeven,
        "direzione": direzione,
        "v_index_rel": v_index_rel,
        "v_index_abs": v_index_abs,
        "rendimento_apertura": rendimento_apertura,
        "rendimento_chiusura": rendimento_chiusura,
        "ts_indicatori": datetime.now(timezone.utc),
    }


# =============================================================================
# ESECUZIONE: leggi da MongoDB, calcola, riscrivi
# =============================================================================

def _build_alias_cache():
    """
    Carica db.teams e costruisce una mappa alias→nome canonico.
    Ogni alias (name, aliases[], aliases_transfermarkt) viene mappato lowercase al name.
    """
    cache = {}  # alias_lower → canonical_name
    all_teams = list(db.teams.find({}, {"name": 1, "aliases": 1, "aliases_transfermarkt": 1}))
    for t in all_teams:
        canonical = t.get("name", "")
        if not canonical:
            continue
        # name stesso
        cache[canonical.lower()] = canonical
        # aliases array
        for a in t.get("aliases", []):
            if a:
                cache[a.lower()] = canonical
        # aliases_transfermarkt (può essere stringa o array)
        atm = t.get("aliases_transfermarkt", [])
        if isinstance(atm, str):
            if atm:
                cache[atm.lower()] = canonical
        elif isinstance(atm, list):
            for a in atm:
                if a:
                    cache[a.lower()] = canonical
    return cache


# Cache alias globale (caricata una volta)
_ALIAS_CACHE = None

def _get_alias_cache():
    global _ALIAS_CACHE
    if _ALIAS_CACHE is None:
        _ALIAS_CACHE = _build_alias_cache()
        print(f"🏷️  Alias cache caricata: {len(_ALIAS_CACHE)} voci")
    return _ALIAS_CACHE


def _resolve_name(raw_name):
    """Risolve un nome raw al nome canonico via alias cache. Ritorna None se non trovato."""
    cache = _get_alias_cache()
    return cache.get(raw_name.lower().strip())


def _preload_qt_cache(target_date, leagues):
    """
    Precarica qt_1/qt_X/qt_2 + real_score da h2h_by_round per tutte le leghe e data.
    Ritorna dict: (league, canonical_home, canonical_away) → {qt_1, qt_X, qt_2, real_score}
    """
    cache = {}
    for league in leagues:
        rounds = list(db.h2h_by_round.find(
            {"league": league},
            {"matches.home": 1, "matches.away": 1, "matches.date": 1,
             "matches.date_obj": 1, "matches.real_score": 1,
             "matches.h2h_data.qt_1": 1,
             "matches.h2h_data.qt_X": 1, "matches.h2h_data.qt_2": 1}
        ))
        for round_doc in rounds:
            for m in round_doc.get('matches', []):
                m_date = m.get('date_obj') or m.get('date', '')
                if hasattr(m_date, 'strftime'):
                    m_date_str = m_date.strftime('%Y-%m-%d')
                else:
                    m_date_str = str(m_date)[:10]

                if m_date_str != target_date:
                    continue

                h2h = m.get('h2h_data', {})
                home = m.get('home', '')
                away = m.get('away', '')
                cache[(league, home, away)] = {
                    "qt_1": h2h.get('qt_1'),
                    "qt_X": h2h.get('qt_X'),
                    "qt_2": h2h.get('qt_2'),
                    "real_score": m.get('real_score'),
                }

    return cache


def _lookup_h2h(cache, league, home_raw, away_raw, alias_mancanti=None):
    """Cerca dati h2h (qt + real_score) nella cache risolvendo i nomi raw tramite alias db.teams.
    Se alias_mancanti è una lista, aggiunge i nomi non risolti per il report finale.
    Ritorna dict con qt_1, qt_X, qt_2, real_score oppure None."""
    home_canonical = _resolve_name(home_raw)
    away_canonical = _resolve_name(away_raw)

    # Log nomi non risolti
    if alias_mancanti is not None:
        if not home_canonical:
            alias_mancanti.append({"nome": home_raw, "league": league, "ruolo": "home"})
        if not away_canonical:
            alias_mancanti.append({"nome": away_raw, "league": league, "ruolo": "away"})

    if home_canonical and away_canonical:
        if (league, home_canonical, away_canonical) in cache:
            return cache[(league, home_canonical, away_canonical)]

    # Fallback: prova match diretto (se h2h_by_round usa lo stesso nome)
    if (league, home_raw, away_raw) in cache:
        return cache[(league, home_raw, away_raw)]

    return None


def calcola_e_aggiorna(target_date=None):
    """
    Legge tutti i documenti quote_anomale per una data,
    calcola gli indicatori e li salva nel documento.
    Arricchisce anche l'ultimo snapshot dello storico con gli indicatori.
    """
    collection = db[COLLECTION]

    filtro = {}
    if target_date:
        filtro["date"] = target_date

    # Solo documenti che hanno sia apertura che chiusura
    filtro["quote_apertura"] = {"$exists": True}
    filtro["quote_chiusura"] = {"$exists": True}

    docs = list(collection.find(filtro))
    print(f"📊 Documenti da elaborare: {len(docs)}")

    # Precarica qt da h2h_by_round
    leagues = set(d.get("league", "") for d in docs if d.get("league"))
    qt_cache = _preload_qt_cache(target_date, leagues) if target_date else {}
    print(f"🔑 Qt caricate da h2h_by_round: {len(qt_cache)} partite")

    calcolati = 0
    errori = 0
    qt_trovate = 0
    alias_mancanti = []

    for doc in docs:
        try:
            # Cerca qt + real_score per questa partita
            h2h_data = _lookup_h2h(
                qt_cache, doc.get("league", ""),
                doc.get("home_raw", ""), doc.get("away_raw", ""),
                alias_mancanti=alias_mancanti
            )
            qt_1 = qt_x = qt_2 = None
            real_score = None
            if h2h_data:
                qt_1 = h2h_data.get("qt_1")
                qt_x = h2h_data.get("qt_X")
                qt_2 = h2h_data.get("qt_2")
                real_score = h2h_data.get("real_score")
            if qt_1 and qt_x and qt_2:
                qt_trovate += 1

            indicatori = calcola_tutti_indicatori(doc, qt_1=qt_1, qt_x=qt_x, qt_2=qt_2)
            if indicatori is None:
                continue

            # Salva indicatori + risultato nel documento
            if real_score:
                indicatori["real_score"] = real_score
            update_ops = {"$set": indicatori}

            # Arricchisci l'ultimo snapshot dello storico con gli indicatori
            storico = doc.get("storico", [])
            if storico:
                last_idx = len(storico) - 1
                snapshot_indicatori = {
                    f"storico.{last_idx}.semaforo": indicatori["semaforo"],
                    f"storico.{last_idx}.alert_breakeven": indicatori["alert_breakeven"],
                    f"storico.{last_idx}.direzione": indicatori["direzione"],
                    f"storico.{last_idx}.v_index_rel": indicatori["v_index_rel"],
                    f"storico.{last_idx}.v_index_abs": indicatori["v_index_abs"],
                    f"storico.{last_idx}.rendimento": indicatori["rendimento_chiusura"],
                }
                update_ops["$set"].update(snapshot_indicatori)

            collection.update_one(
                {"_id": doc["_id"]},
                update_ops
            )
            calcolati += 1

        except Exception as e:
            print(f"   ❌ Errore calcolo per {doc.get('home_raw', '?')} vs {doc.get('away_raw', '?')}: {e}")
            errori += 1

    print(f"✅ Indicatori calcolati: {calcolati}")
    print(f"🔑 Qt modello trovate: {qt_trovate}/{calcolati}")
    if errori:
        print(f"❌ Errori: {errori}")

    # Report alias mancanti — squadre non trovate in db.teams
    # Deduplica per nome
    visti = set()
    unici = []
    for am in alias_mancanti:
        if am["nome"] not in visti:
            visti.add(am["nome"])
            unici.append(am)

    if unici:
        print(f"\n⚠️  ALIAS MANCANTI in db.teams ({len(unici)} squadre) — vedi log/alias_mancanti_lucksport.txt")

    # Salva su file (sovrascrive ad ogni run)
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(current_dir))), "log")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "alias_mancanti_lucksport.txt")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"# Alias mancanti LuckSport — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"# Data analizzata: {target_date or 'tutte'}\n")
        f.write(f"# Squadre non trovate in db.teams (aggiungere come alias)\n\n")
        if unici:
            for am in sorted(unici, key=lambda x: (x["league"], x["nome"])):
                f.write(f"{am['nome']}  |  {am['league']}\n")
        else:
            f.write("Nessun alias mancante ✓\n")
    print(f"📄 Log alias salvato in: {log_path}")

    return calcolati, errori


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Calcolo Indicatori Quote Anomale")
    parser.add_argument("--date", type=str, default=None,
                        help="Data target YYYY-MM-DD (default: tutte)")

    args = parser.parse_args()

    target = args.date
    if target is None:
        target = datetime.now().strftime("%Y-%m-%d")
        print(f"📅 Nessuna data specificata, uso oggi: {target}")

    print(f"\n{'='*60}")
    print(f"🔬 CALCOLO INDICATORI QUOTE ANOMALE")
    print(f"   Data: {target}")
    print(f"{'='*60}\n")

    calcola_e_aggiorna(target_date=target)
