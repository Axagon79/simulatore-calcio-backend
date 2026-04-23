"""
Snapshot Pronostici — Cattura lo stato dei pronostici come li vede l'utente.

Uso:
  python snapshot_pronostici.py mattino
  python snapshot_pronostici.py intermedio
  python snapshot_pronostici.py serale
  python snapshot_pronostici.py confronto
"""

import sys
import json
import os
import re
import urllib.request
from datetime import datetime, timedelta
from collections import defaultdict

API_BASE = "https://api-6b34yfzjia-uc.a.run.app"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(SCRIPT_DIR, "report")


def fetch_predictions(date_str):
    """Chiama l'API produzione e ritorna le predictions."""
    url = f"{API_BASE}/simulation/daily-predictions-unified?date={date_str}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    return data.get("predictions", [])


def split_pronostici_alto_rendimento(preds):
    """Divide i tip con la stessa logica del frontend UnifiedPredictions.tsx."""
    pronostici = []
    alto_rendimento = []

    for p in preds:
        if p.get("is_exact_score"):
            continue

        tips = p.get("pronostici", [])
        tips_normali = []
        tips_ar = []

        for t in tips:
            tipo = t.get("tipo", "")
            quota = t.get("quota") or 0

            if tipo == "RISULTATO_ESATTO":
                tips_ar.append(t)
                continue

            soglia = 2.00 if tipo == "DOPPIA_CHANCE" else 2.51
            if quota >= soglia:
                tips_ar.append(t)
            else:
                tips_normali.append(t)

        base = {
            "home": p.get("home"),
            "away": p.get("away"),
            "match_time": p.get("match_time", "-"),
            "league": p.get("league", "?"),
            "decision": p.get("decision", ""),
        }

        if tips_normali:
            pronostici.append({**base, "tips": tips_normali})
        if tips_ar:
            alto_rendimento.append({**base, "tips": tips_ar})

    return pronostici, alto_rendimento


def count_tips(matches):
    return sum(len(m["tips"]) for m in matches)


def build_json(label, date_str, pronostici, alto_rendimento):
    """Costruisce il dizionario JSON dello snapshot."""
    now = datetime.now()
    return {
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "label": label,
        "date": date_str,
        "riepilogo": {
            "pronostici": {"partite": len(pronostici), "tip": count_tips(pronostici)},
            "alto_rendimento": {"partite": len(alto_rendimento), "tip": count_tips(alto_rendimento)},
        },
        "pronostici": pronostici,
        "alto_rendimento": alto_rendimento,
    }


def format_tip_line(t, is_last=True):
    """Formatta una riga di tip."""
    connector = "└─" if is_last else "├─"
    tipo = t.get("tipo", "")
    pronostico = t.get("pronostico", "")
    quota = t.get("quota") or "-"
    conf = t.get("confidence") or 0
    stake = t.get("stake") or "-"
    source = t.get("source", "")

    # Allineamento colonne
    tipo_str = f"{tipo:<16}"
    prono_str = f"{pronostico:<9}"
    quota_str = f"@{quota:<5}"
    conf_str = f"conf: {conf:>5.1f}%"
    stake_str = f"stake: {stake}"
    src_str = f"src: {source}"

    return f"│         {connector} {tipo_str} {prono_str} {quota_str}  {conf_str}   {stake_str}   {src_str}"


def build_txt(snapshot):
    """Genera il file TXT formattato."""
    lines = []
    ts = snapshot["timestamp"]
    label = snapshot["label"].upper()
    date_str = snapshot["date"]
    riepilogo = snapshot["riepilogo"]

    # Header
    lines.append("╔══════════════════════════════════════════════════════════════════════════════════╗")
    lines.append(f"║{'SNAPSHOT PRONOSTICI — ' + date_str:^82}║")
    lines.append(f"║{'Ore ' + ts[11:16] + ' (' + snapshot['label'].capitalize() + ')':^82}║")
    lines.append("╚══════════════════════════════════════════════════════════════════════════════════╝")
    lines.append("")

    # Riepilogo
    p_info = riepilogo["pronostici"]
    ar_info = riepilogo["alto_rendimento"]
    tot_p = p_info["partite"] + ar_info["partite"]
    tot_t = p_info["tip"] + ar_info["tip"]

    lines.append("┌──────────────────────────────────────────────────────────────────────────────────┐")
    lines.append(f"│  RIEPILOGO{' ' * 71}│")
    lines.append(f"│  Pronostici:      {p_info['partite']:>2} partite  —  {p_info['tip']:>2} tip{' ' * 39}│")
    lines.append(f"│  Alto Rendimento:  {ar_info['partite']:>2} partite  —   {ar_info['tip']:>1} tip{' ' * 39}│")
    lines.append(f"│  Totale:          {tot_p:>2} partite  —  {tot_t:>2} tip{' ' * 39}│")
    lines.append("└──────────────────────────────────────────────────────────────────────────────────┘")
    lines.append("")
    lines.append("")

    # Sezione Pronostici
    lines.append("══════════════════════════════════════════════════════════════════════════════════")
    lines.append(f"  PRONOSTICI  ({p_info['partite']} partite — {p_info['tip']} tip)")
    lines.append("══════════════════════════════════════════════════════════════════════════════════")
    lines.append("")

    _render_section(lines, snapshot["pronostici"])

    lines.append("")

    # Sezione Alto Rendimento
    lines.append("══════════════════════════════════════════════════════════════════════════════════")
    lines.append(f"  ALTO RENDIMENTO  ({ar_info['partite']} partite — {ar_info['tip']} tip)")
    lines.append("══════════════════════════════════════════════════════════════════════════════════")
    lines.append("")

    _render_section(lines, snapshot["alto_rendimento"])

    # Footer obiettivo
    lines.append("")
    lines.append("══════════════════════════════════════════════════════════════════════════════════")
    lines.append("  OBIETTIVO MONITORAGGIO")
    lines.append("══════════════════════════════════════════════════════════════════════════════════")
    lines.append("  Verificare se i pre-match update (-3h e -1h) migliorano, peggiorano o")
    lines.append("  lasciano invariato il rendimento rispetto ai pronostici notturni.")
    lines.append("══════════════════════════════════════════════════════════════════════════════════")

    return "\n".join(lines)


def _render_section(lines, matches):
    """Renderizza una sezione (pronostici o alto rendimento) raggruppata per lega."""
    by_league = defaultdict(list)
    for m in matches:
        by_league[m["league"]].append(m)

    for league in sorted(by_league.keys()):
        items = sorted(by_league[league], key=lambda x: x["match_time"])
        n_partite = len(items)
        n_tip = sum(len(m["tips"]) for m in items)
        partite_label = "partita" if n_partite == 1 else "partite"
        tip_label = "tip" if n_tip == 1 else "tip"

        lines.append(f"┌─ {league} ({n_partite} {partite_label}, {n_tip} {tip_label}) " + "─" * max(0, 76 - len(league) - len(str(n_partite)) - len(str(n_tip)) - len(partite_label) - len(tip_label) - 8))
        lines.append("│")

        for m in items:
            home = m["home"]
            away = m["away"]
            mt = m["match_time"]
            nb = " [NO BET]" if m.get("decision") == "NO_BET" else ""

            lines.append(f"│  {mt}  {home} vs {away}{nb}")

            tips = m["tips"]
            for i, t in enumerate(tips):
                is_last = i == len(tips) - 1
                lines.append(format_tip_line(t, is_last))

            lines.append("│")

        lines.append("└" + "─" * 82)
        lines.append("")


def get_label_dir(date_str, label):
    """Crea e ritorna il path della cartella report/DATA/LABEL/."""
    label_dir = os.path.join(REPORT_DIR, date_str, label)
    os.makedirs(label_dir, exist_ok=True)
    return label_dir


def do_snapshot(label, date_str):
    """Esegue lo snapshot: fetch API, split, salva JSON + TXT."""
    now = datetime.now()
    time_str = now.strftime("%H%M")
    label_dir = get_label_dir(date_str, label)

    print(f"Fetching pronostici per {date_str}...")
    preds = fetch_predictions(date_str)
    print(f"  Ricevute {len(preds)} partite dall'API")

    pronostici, alto_rendimento = split_pronostici_alto_rendimento(preds)
    print(f"  Pronostici: {len(pronostici)} partite, {count_tips(pronostici)} tip")
    print(f"  Alto Rendimento: {len(alto_rendimento)} partite, {count_tips(alto_rendimento)} tip")

    snapshot = build_json(label, date_str, pronostici, alto_rendimento)

    # Salva JSON
    json_path = os.path.join(label_dir, f"snapshot_{time_str}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    print(f"  JSON salvato: {json_path}")

    # Salva TXT
    txt_content = build_txt(snapshot)
    txt_path = os.path.join(label_dir, f"snapshot_{time_str}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(txt_content)
    print(f"  TXT salvato: {txt_path}")

    return snapshot


def do_confronto_auto():
    """Scansiona tutte le date in report/ e genera confronti mancanti."""
    if not os.path.exists(REPORT_DIR):
        print("Nessuna cartella report/ trovata.")
        return

    date_dirs = sorted([
        d for d in os.listdir(REPORT_DIR)
        if os.path.isdir(os.path.join(REPORT_DIR, d)) and len(d) == 10  # YYYY-MM-DD
    ])

    if not date_dirs:
        print("Nessuna data trovata in report/")
        return

    generati = []
    gia_completi = []
    mancano_snapshot = []

    for date_str in date_dirs:
        date_dir = os.path.join(REPORT_DIR, date_str)
        confronto_dir = os.path.join(date_dir, "confronto")

        # Controlla se il confronto esiste già
        if os.path.exists(confronto_dir) and any(f.endswith(".json") for f in os.listdir(confronto_dir)):
            gia_completi.append(date_str)
            continue

        # Conta snapshot disponibili
        n_snap = sum(
            1 for label in ["mattino", "intermedio", "serale"]
            if os.path.exists(os.path.join(date_dir, label))
            and any(f.endswith(".json") for f in os.listdir(os.path.join(date_dir, label)))
        )

        if n_snap < 2:
            mancano_snapshot.append(f"{date_str} ({n_snap} snapshot)")
            continue

        print(f"\n{'='*60}")
        print(f"Genero confronto per {date_str}...")
        print(f"{'='*60}")
        do_confronto_singolo(date_str)
        generati.append(date_str)

    # Riepilogo
    print(f"\n{'='*60}")
    print("RIEPILOGO CONFRONTI")
    print(f"{'='*60}")
    if generati:
        print(f"  Generati ora:       {', '.join(generati)}")
    if gia_completi:
        print(f"  Gia' completi:      {', '.join(gia_completi)}")
    if mancano_snapshot:
        print(f"  Mancano snapshot:   {', '.join(mancano_snapshot)}")
    if not generati and not mancano_snapshot:
        print("  Tutto aggiornato!")


def fetch_results(date_str):
    """Recupera i risultati reali delle partite dal DB via API live-scores."""
    results = {}

    # Prima controlla se c'è un file risultati locale (utile per test/demo)
    local_path = os.path.join(REPORT_DIR, date_str, "risultati.json")
    if os.path.exists(local_path):
        with open(local_path, "r", encoding="utf-8") as f:
            results = json.load(f)
        print(f"  Risultati caricati da file locale: {len(results)}")
        return results

    try:
        url = f"{API_BASE}/live-scores?date={date_str}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        for m in data.get("scores", data.get("matches", [])):
            home = m.get("home", "")
            away = m.get("away", "")
            score = m.get("score") or m.get("real_score") or m.get("result", "")
            if home and away and score and ":" in str(score):
                key = f"{home}_{away}"
                results[key] = str(score)
    except Exception as e:
        print(f"  Attenzione: impossibile recuperare live-scores ({e})")

    # Fallback: prova anche unified predictions per real_score
    if not results:
        try:
            url = f"{API_BASE}/simulation/daily-predictions-unified?date={date_str}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
            for p in data.get("predictions", []):
                rs = p.get("real_score") or p.get("live_score", "")
                if rs and ":" in str(rs) and str(rs) not in ("-:-", "-"):
                    key = f"{p['home']}_{p['away']}"
                    results[key] = str(rs)
        except Exception as e:
            print(f"  Attenzione: impossibile recuperare predictions ({e})")

    return results


def calculate_hit(pronostico, tipo, score_str):
    """Calcola se un pronostico è vincente dato il risultato reale."""
    if not score_str or ":" not in score_str:
        return None

    parts = score_str.split(":")
    try:
        home_goals = int(parts[0].strip())
        away_goals = int(parts[1].strip())
    except (ValueError, IndexError):
        return None

    total = home_goals + away_goals
    p = pronostico.strip()

    if tipo == "SEGNO":
        if p == "1":
            return home_goals > away_goals
        elif p == "X":
            return home_goals == away_goals
        elif p == "2":
            return home_goals < away_goals
        return None

    elif tipo == "DOPPIA_CHANCE":
        if p in ("1X", "X1"):
            return home_goals >= away_goals
        elif p in ("X2", "2X"):
            return home_goals <= away_goals
        elif p in ("12", "21"):
            return home_goals != away_goals
        return None

    elif tipo == "GOL":
        if p == "Over 0.5":
            return total > 0
        elif p == "Over 1.5":
            return total > 1
        elif p == "Over 2.5":
            return total > 2
        elif p == "Over 3.5":
            return total > 3
        elif p == "Over 4.5":
            return total > 4
        elif p == "Under 0.5":
            return total < 1
        elif p == "Under 1.5":
            return total < 2
        elif p == "Under 2.5":
            return total < 3
        elif p == "Under 3.5":
            return total < 4
        elif p == "Under 4.5":
            return total < 5
        elif p == "Goal":
            return home_goals > 0 and away_goals > 0
        elif p == "NoGoal":
            return home_goals == 0 or away_goals == 0
        elif p.startswith("MG "):
            # Multi-Goal: "MG 2-4" -> totale gol tra 2 e 4
            mg_match = re.match(r"MG\s+(\d+)-(\d+)", p)
            if mg_match:
                mg_min = int(mg_match.group(1))
                mg_max = int(mg_match.group(2))
                return mg_min <= total <= mg_max
        return None

    elif tipo == "RISULTATO_ESATTO":
        # "2:0" o "2-0"
        re_match = re.match(r"(\d+)[:\-](\d+)", p)
        if re_match:
            exp_home = int(re_match.group(1))
            exp_away = int(re_match.group(2))
            return home_goals == exp_home and away_goals == exp_away
        return None

    return None


def calc_pl(hit, quota):
    """Calcola P/L flat stake 1u."""
    if hit is None:
        return 0
    return (quota - 1) if hit else -1


def calc_stats(tips_with_results):
    """Calcola statistiche per un set di tip con risultati."""
    total = len(tips_with_results)
    verified = [t for t in tips_with_results if t["hit"] is not None]
    vinti = [t for t in verified if t["hit"]]
    persi = [t for t in verified if not t["hit"]]
    no_result = total - len(verified)

    hr = round(len(vinti) / len(verified) * 100, 1) if verified else None
    pl = round(sum(t["pl"] for t in verified), 2)
    yield_pct = round(pl / len(verified) * 100, 1) if verified else None

    # Per mercato
    by_market = defaultdict(lambda: {"vinti": 0, "persi": 0, "pl": 0.0})
    for t in verified:
        m = t["tipo"]
        if t["hit"]:
            by_market[m]["vinti"] += 1
        else:
            by_market[m]["persi"] += 1
        by_market[m]["pl"] += t["pl"]

    return {
        "totale_tip": total,
        "verificati": len(verified),
        "vinti": len(vinti),
        "persi": len(persi),
        "no_result": no_result,
        "hr": hr,
        "pl": pl,
        "yield": yield_pct,
        "per_mercato": dict(by_market),
    }


def tip_map_full(snapshot):
    """Mappa tutti i tip di uno snapshot con chiave univoca."""
    result = {}
    for section in ["pronostici", "alto_rendimento"]:
        for m in snapshot.get(section, []):
            for t in m["tips"]:
                key = f"{m['home']}_{m['away']}_{t['tipo']}_{t['pronostico']}"
                result[key] = {
                    "home": m["home"],
                    "away": m["away"],
                    "match_key": f"{m['home']}_{m['away']}",
                    "match_time": m["match_time"],
                    "league": m["league"],
                    "section": section,
                    **t,
                }
    return result


def do_confronto_singolo(date_str):
    """Confronta gli snapshot di una singola giornata con risultati reali."""
    date_dir = os.path.join(REPORT_DIR, date_str)
    if not os.path.exists(date_dir):
        print(f"Nessuna cartella trovata per {date_str}")
        return

    # Cerca i JSON nelle sottocartelle mattino/intermedio/serale
    # Salta file vuoti o JSON corrotti (es. fallimento chiamata API che ha lasciato file a 0 byte)
    snapshots = []
    for label in ["mattino", "intermedio", "serale"]:
        label_dir = os.path.join(date_dir, label)
        if not os.path.exists(label_dir):
            continue
        json_files = sorted([f for f in os.listdir(label_dir) if f.endswith(".json")])
        if not json_files:
            continue
        path = os.path.join(label_dir, json_files[-1])
        try:
            if os.path.getsize(path) == 0:
                print(f"  Skip {label}: file vuoto ({json_files[-1]})")
                continue
            with open(path, "r", encoding="utf-8") as fh:
                snap = json.load(fh)
                snapshots.append(snap)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  Skip {label}: JSON corrotto ({json_files[-1]}) - {e}")
            continue

    if len(snapshots) < 2:
        print(f"Servono almeno 2 snapshot per il confronto. Trovati: {len(snapshots)}")
        return

    print(f"Trovati {len(snapshots)} snapshot:")
    for snap in snapshots:
        print(f"  {snap['label']:>12} ({snap['timestamp'][11:16]}) — {snap['riepilogo']['pronostici']['tip']}+{snap['riepilogo']['alto_rendimento']['tip']} tip")

    # Recupera risultati reali
    print(f"\nRecupero risultati reali per {date_str}...")
    results = fetch_results(date_str)
    print(f"  Risultati trovati: {len(results)} partite")

    primo = snapshots[0]
    ultimo = snapshots[-1]
    map_primo = tip_map_full(primo)
    map_ultimo = tip_map_full(ultimo)

    keys_primo = set(map_primo.keys())
    keys_ultimo = set(map_ultimo.keys())

    nuovi = keys_ultimo - keys_primo
    rimossi = keys_primo - keys_ultimo
    comuni = keys_primo & keys_ultimo

    # Calcola hit/miss per ogni tip
    def enrich_with_results(tip_map):
        enriched = []
        for k, t in tip_map.items():
            score = results.get(t["match_key"], "")
            hit = calculate_hit(t["pronostico"], t["tipo"], score)
            pl = calc_pl(hit, t.get("quota", 0) or 0)
            enriched.append({**t, "score": score, "hit": hit, "pl": round(pl, 2)})
        return enriched

    tips_primo = enrich_with_results(map_primo)
    tips_ultimo = enrich_with_results(map_ultimo)

    stats_primo = calc_stats(tips_primo)
    stats_ultimo = calc_stats(tips_ultimo)

    # Tip cambiati (quota/confidence/stake/source)
    cambiati = []
    for k in comuni:
        t1 = map_primo[k]
        t2 = map_ultimo[k]
        changes = []
        for field in ["quota", "confidence", "stake", "source"]:
            if t1.get(field) != t2.get(field):
                changes.append(f"{field}: {t1.get(field)} -> {t2.get(field)}")
        if t1.get("section") != t2.get("section"):
            changes.append(f"sezione: {t1['section']} -> {t2['section']}")
        if changes:
            score = results.get(t2["match_key"], "")
            hit = calculate_hit(t2["pronostico"], t2["tipo"], score)
            cambiati.append({
                "match": f"{t2['home']} vs {t2['away']}",
                "time": t2["match_time"],
                "tipo": t2["tipo"],
                "pronostico": t2["pronostico"],
                "score": score,
                "hit": hit,
                "changes": changes,
            })

    # Tip nuovi con esito
    nuovi_detail = []
    for k in nuovi:
        t = map_ultimo[k]
        score = results.get(t["match_key"], "")
        hit = calculate_hit(t["pronostico"], t["tipo"], score)
        pl = calc_pl(hit, t.get("quota", 0) or 0)
        nuovi_detail.append({**t, "score": score, "hit": hit, "pl": round(pl, 2)})

    # Tip rimossi con esito (cosa sarebbe successo)
    rimossi_detail = []
    for k in rimossi:
        t = map_primo[k]
        score = results.get(t["match_key"], "")
        hit = calculate_hit(t["pronostico"], t["tipo"], score)
        pl = calc_pl(hit, t.get("quota", 0) or 0)
        rimossi_detail.append({**t, "score": score, "hit": hit, "pl": round(pl, 2)})

    # ═══════════════════════════════════════════════════════════════
    # GENERA REPORT TXT
    # ═══════════════════════════════════════════════════════════════
    labels_usati = [s["label"].capitalize() for s in snapshots]
    orari_usati = [s["timestamp"][11:16] for s in snapshots]
    descrizione = " -> ".join([f"{l} ({o})" for l, o in zip(labels_usati, orari_usati)])

    L = []  # lines
    L.append("╔══════════════════════════════════════════════════════════════════════════════════╗")
    L.append(f"║{'CONFRONTO GIORNALIERO — ' + date_str:^82}║")
    L.append("╚══════════════════════════════════════════════════════════════════════════════════╝")
    L.append("")
    L.append(f"  Questo report confronta i pronostici del {date_str} catturati in {len(snapshots)} momenti:")
    L.append(f"  {descrizione}")
    L.append("")
    L.append(f"  Risultati reali recuperati: {len(results)} partite")
    L.append("")

    # ── TABELLA SNAPSHOT (colonne = snapshot, righe = metriche) ──
    col_w_snap = 20
    header_snaps = "".join(f"{f'{l} ({o})':^{col_w_snap}}" for l, o in zip(labels_usati, orari_usati))
    L.append("┌─" + "─" * (18 + col_w_snap * len(snapshots)) + "─┐")
    L.append(f"│  {'':18}{header_snaps} │")
    L.append("│─" + "─" * (18 + col_w_snap * len(snapshots)) + "─│")
    rows = [
        ("Partite P", [s["riepilogo"]["pronostici"]["partite"] for s in snapshots]),
        ("Tip P", [s["riepilogo"]["pronostici"]["tip"] for s in snapshots]),
        ("Partite AR", [s["riepilogo"]["alto_rendimento"]["partite"] for s in snapshots]),
        ("Tip AR", [s["riepilogo"]["alto_rendimento"]["tip"] for s in snapshots]),
    ]
    for row_label, vals in rows:
        vals_str = "".join(f"{v:^{col_w_snap}}" for v in vals)
        L.append(f"│  {row_label:<18}{vals_str} │")
    L.append("└─" + "─" * (18 + col_w_snap * len(snapshots)) + "─┘")
    L.append("")

    # ── CONFRONTO RENDIMENTO ──
    def format_stats_block(label, stats):
        block = []
        block.append(f"  {label}")
        block.append(f"    Tip totali:    {stats['totale_tip']}")
        block.append(f"    Verificati:    {stats['verificati']}  (senza risultato: {stats['no_result']})")
        block.append(f"    Vinti:         {stats['vinti']}")
        block.append(f"    Persi:         {stats['persi']}")
        hr_str = f"{stats['hr']}%" if stats['hr'] is not None else "N/A"
        yield_str = f"{stats['yield']}%" if stats['yield'] is not None else "N/A"
        pl_str = f"{stats['pl']:+.2f}u" if stats['pl'] else "0.00u"
        block.append(f"    HR:            {hr_str}")
        block.append(f"    P/L:           {pl_str}")
        block.append(f"    Yield:         {yield_str}")
        block.append("")
        # Per mercato
        if stats["per_mercato"]:
            block.append(f"    {'Mercato':<20} {'Vinti':>6} {'Persi':>6} {'P/L':>10}")
            block.append(f"    {'─'*20} {'─'*6} {'─'*6} {'─'*10}")
            for mercato in sorted(stats["per_mercato"].keys()):
                ms = stats["per_mercato"][mercato]
                block.append(f"    {mercato:<20} {ms['vinti']:>6} {ms['persi']:>6} {ms['pl']:>+10.2f}u")
        return block

    L.append("══════════════════════════════════════════════════════════════════════════════════")
    L.append("  SCENARIO A: SENZA AGGIORNAMENTI (solo pronostici notturni)")
    L.append("══════════════════════════════════════════════════════════════════════════════════")
    L.extend(format_stats_block(f"Snapshot {primo['label']} ({primo['timestamp'][11:16]})", stats_primo))
    L.append("")

    L.append("══════════════════════════════════════════════════════════════════════════════════")
    L.append("  SCENARIO B: CON AGGIORNAMENTI (pronostici finali)")
    L.append("══════════════════════════════════════════════════════════════════════════════════")
    L.extend(format_stats_block(f"Snapshot {ultimo['label']} ({ultimo['timestamp'][11:16]})", stats_ultimo))
    L.append("")

    # ── DIFFERENZA ──
    L.append("══════════════════════════════════════════════════════════════════════════════════")
    L.append("  IMPATTO AGGIORNAMENTI: SCENARIO B vs SCENARIO A")
    L.append("══════════════════════════════════════════════════════════════════════════════════")

    diff_vinti = stats_ultimo["vinti"] - stats_primo["vinti"]
    diff_persi = stats_ultimo["persi"] - stats_primo["persi"]
    diff_pl = round(stats_ultimo["pl"] - stats_primo["pl"], 2)
    diff_hr = round(stats_ultimo["hr"] - stats_primo["hr"], 1) if stats_primo["hr"] is not None and stats_ultimo["hr"] is not None else None
    diff_yield = round(stats_ultimo["yield"] - stats_primo["yield"], 1) if stats_primo["yield"] is not None and stats_ultimo["yield"] is not None else None

    L.append(f"  Tip vinti:   {diff_vinti:+d}")
    L.append(f"  Tip persi:   {diff_persi:+d}")
    hr_diff_str = f"{diff_hr:+.1f}%" if diff_hr is not None else "N/A"
    yield_diff_str = f"{diff_yield:+.1f}%" if diff_yield is not None else "N/A"
    L.append(f"  HR:          {hr_diff_str}")
    L.append(f"  P/L:         {diff_pl:+.2f}u")
    L.append(f"  Yield:       {yield_diff_str}")
    L.append("")

    if diff_pl > 0:
        L.append("  ✅ VERDETTO: Gli aggiornamenti hanno MIGLIORATO il rendimento")
    elif diff_pl < 0:
        L.append("  ❌ VERDETTO: Gli aggiornamenti hanno PEGGIORATO il rendimento")
    else:
        L.append("  ➖ VERDETTO: Gli aggiornamenti NON hanno cambiato il rendimento")
    L.append("")

    # ── TABELLA EVOLUZIONE PRONOSTICI ──
    # Raccogli tutti i tip da tutti gli snapshot
    all_tip_keys = set()
    maps_per_snap = []
    for snap in snapshots:
        m = tip_map_full(snap)
        maps_per_snap.append(m)
        all_tip_keys.update(m.keys())

    # Raggruppa per partita (match_key)
    match_tips = defaultdict(list)  # match_key -> list of tip_keys
    match_info = {}  # match_key -> {home, away, match_time, league, score}
    for k in all_tip_keys:
        # Trova info dalla prima mappa che ha questo tip
        for m in maps_per_snap:
            if k in m:
                mk = m[k]["match_key"]
                match_tips[mk].append(k)
                if mk not in match_info:
                    score = results.get(mk, "")
                    match_info[mk] = {
                        "home": m[k]["home"],
                        "away": m[k]["away"],
                        "match_time": m[k]["match_time"],
                        "league": m[k]["league"],
                        "score": score,
                    }
                break

    nuovi_vinti = [t for t in nuovi_detail if t["hit"] is True]
    nuovi_persi = [t for t in nuovi_detail if t["hit"] is False]
    nuovi_nd = [t for t in nuovi_detail if t["hit"] is None]
    nuovi_pl = round(sum(t["pl"] for t in nuovi_detail if t["hit"] is not None), 2)
    rimossi_vinti = [t for t in rimossi_detail if t["hit"] is True]
    rimossi_persi = [t for t in rimossi_detail if t["hit"] is False]
    rimossi_nd = [t for t in rimossi_detail if t["hit"] is None]
    rimossi_pl = round(sum(t["pl"] for t in rimossi_detail if t["hit"] is not None), 2)

    snap_labels = [s["label"].capitalize() for s in snapshots]
    col_w = 14  # larghezza colonna per ogni snapshot

    L.append("══════════════════════════════════════════════════════════════════════════════════")
    L.append("  EVOLUZIONE PRONOSTICI DURANTE LA GIORNATA")
    L.append("══════════════════════════════════════════════════════════════════════════════════")
    L.append("")

    # Header colonne
    header_cols = "".join(f"{lab:^{col_w}}" for lab in snap_labels)
    L.append(f"  {'':40} {header_cols} {'Risultato':^12} {'Esito':^8}")
    L.append(f"  {'─'*40} " + "─" * col_w * len(snap_labels) + " " + "─" * 12 + " " + "─" * 8)

    # Ordina partite per orario
    sorted_matches = sorted(match_info.keys(), key=lambda mk: match_info[mk]["match_time"])

    for mk in sorted_matches:
        mi = match_info[mk]
        match_label = f"{mi['match_time']}  {mi['home']} vs {mi['away']}"
        L.append(f"  {match_label}")

        # Per ogni tip di questa partita
        tip_keys = sorted(match_tips[mk])
        for tk in tip_keys:
            # Trova tipo e pronostico
            tipo = ""
            pronostico = ""
            for m in maps_per_snap:
                if tk in m:
                    tipo = m[tk]["tipo"]
                    pronostico = m[tk]["pronostico"]
                    break

            tip_label = f"  {tipo} {pronostico}"

            # Colonne: quota per ogni snapshot (o — se assente, RIMOSSO se tolto)
            cols = []
            was_present = False
            for i, m in enumerate(maps_per_snap):
                if tk in m:
                    q = m[tk].get("quota", "-")
                    cols.append(f"@{q}")
                    was_present = True
                else:
                    if was_present:
                        cols.append("RIMOSSO")
                    else:
                        cols.append("—")

            cols_str = "".join(f"{c:^{col_w}}" for c in cols)

            # Risultato e esito
            score = mi["score"] or "?"
            hit = None
            for m in reversed(maps_per_snap):
                if tk in m:
                    hit = calculate_hit(m[tk]["pronostico"], m[tk]["tipo"], mi["score"])
                    break
            if hit is None and mi["score"]:
                # Prova col primo snapshot (per tip rimossi)
                for m in maps_per_snap:
                    if tk in m:
                        hit = calculate_hit(m[tk]["pronostico"], m[tk]["tipo"], mi["score"])
                        break

            if hit is True:
                # Check se è nuovo o rimosso
                if tk in nuovi:
                    esito_str = "✅ NUOVO"
                else:
                    esito_str = "✅"
            elif hit is False:
                esito_str = "❌"
            else:
                esito_str = "⏳"

            # Se rimosso e avrebbe vinto
            if tk in rimossi and hit is True:
                esito_str = "✅ PERSA"
            elif tk in rimossi and hit is False:
                esito_str = "❌ evit."

            L.append(f"    {tip_label:<38} {cols_str} {score:^12} {esito_str:^8}")

    L.append("")
    L.append(f"  Legenda: — = non presente | RIMOSSO = tolto dall'aggiornamento")
    L.append(f"           ✅ NUOVO = aggiunto e vinto | ✅ PERSA = rimosso ma avrebbe vinto")
    L.append(f"           ❌ evit. = rimosso e avrebbe perso (sconfitta evitata)")
    L.append("")

    # Riepilogo compatto nuovi/rimossi
    L.append(f"  Tip nuovi:   {len(nuovi_detail)} (vinti: {len(nuovi_vinti)}, persi: {len(nuovi_persi)}, P/L: {nuovi_pl:+.2f}u)")
    L.append(f"  Tip rimossi: {len(rimossi_detail)} (vinti persi: {len(rimossi_vinti)}, sconfitte evitate: {len(rimossi_persi)}, P/L: {rimossi_pl:+.2f}u)")
    L.append(f"  Tip con modifiche (quota/conf/stake): {len(cambiati)}")
    L.append("")

    # ── ANALISI STEP-BY-STEP: impatto di ogni singolo aggiornamento ──
    if len(snapshots) >= 2:
        L.append("══════════════════════════════════════════════════════════════════════════════════")
        L.append("  ANALISI STEP-BY-STEP: IMPATTO DI OGNI AGGIORNAMENTO")
        L.append("══════════════════════════════════════════════════════════════════════════════════")
        L.append("  Quale aggiornamento ha migliorato/peggiorato di piu'?")
        L.append("")

        for i in range(len(snapshots) - 1):
            snap_a = snapshots[i]
            snap_b = snapshots[i + 1]
            map_a = tip_map_full(snap_a)
            map_b = tip_map_full(snap_b)

            tips_a = []
            for k, t in map_a.items():
                score = results.get(t["match_key"], "")
                hit = calculate_hit(t["pronostico"], t["tipo"], score)
                pl = calc_pl(hit, t.get("quota", 0) or 0)
                tips_a.append({**t, "hit": hit, "pl": round(pl, 2)})

            tips_b = []
            for k, t in map_b.items():
                score = results.get(t["match_key"], "")
                hit = calculate_hit(t["pronostico"], t["tipo"], score)
                pl = calc_pl(hit, t.get("quota", 0) or 0)
                tips_b.append({**t, "hit": hit, "pl": round(pl, 2)})

            stats_a = calc_stats(tips_a)
            stats_b = calc_stats(tips_b)

            keys_a = set(map_a.keys())
            keys_b = set(map_b.keys())
            step_nuovi = keys_b - keys_a
            step_rimossi = keys_a - keys_b

            step_nuovi_vinti = sum(1 for k in step_nuovi if calculate_hit(map_b[k]["pronostico"], map_b[k]["tipo"], results.get(map_b[k]["match_key"], "")) is True)
            step_nuovi_persi = sum(1 for k in step_nuovi if calculate_hit(map_b[k]["pronostico"], map_b[k]["tipo"], results.get(map_b[k]["match_key"], "")) is False)
            step_rimossi_vinti = sum(1 for k in step_rimossi if calculate_hit(map_a[k]["pronostico"], map_a[k]["tipo"], results.get(map_a[k]["match_key"], "")) is True)
            step_rimossi_persi = sum(1 for k in step_rimossi if calculate_hit(map_a[k]["pronostico"], map_a[k]["tipo"], results.get(map_a[k]["match_key"], "")) is False)

            step_diff_pl = round(stats_b["pl"] - stats_a["pl"], 2)
            step_diff_hr = round(stats_b["hr"] - stats_a["hr"], 1) if stats_a["hr"] is not None and stats_b["hr"] is not None else None

            label_a = snap_a["label"].capitalize()
            label_b = snap_b["label"].capitalize()
            ora_a = snap_a["timestamp"][11:16]
            ora_b = snap_b["timestamp"][11:16]

            emoji = "📈" if step_diff_pl > 0 else ("📉" if step_diff_pl < 0 else "➖")

            L.append(f"  ┌─ {label_a} ({ora_a}) → {label_b} ({ora_b}) {emoji}")
            L.append(f"  │")
            L.append(f"  │  Tip prima: {stats_a['totale_tip']}  →  Tip dopo: {stats_b['totale_tip']}")

            hr_a_str = f"{stats_a['hr']:.1f}%" if stats_a['hr'] is not None else "N/A"
            hr_b_str = f"{stats_b['hr']:.1f}%" if stats_b['hr'] is not None else "N/A"
            L.append(f"  │  HR:  {hr_a_str} → {hr_b_str}")
            L.append(f"  │  P/L: {stats_a['pl']:+.2f}u → {stats_b['pl']:+.2f}u  (differenza: {step_diff_pl:+.2f}u)")
            L.append(f"  │")
            L.append(f"  │  Tip aggiunti:  {len(step_nuovi):>3}  (vinti: {step_nuovi_vinti}, persi: {step_nuovi_persi})")
            L.append(f"  │  Tip rimossi:   {len(step_rimossi):>3}  (sarebbero stati vinti: {step_rimossi_vinti}, persi: {step_rimossi_persi})")

            if step_rimossi_vinti > 0:
                L.append(f"  │  ⚠️  {step_rimossi_vinti} vincite perse con questo aggiornamento!")
            if step_nuovi_vinti > 0:
                L.append(f"  │  ✅  {step_nuovi_vinti} vincite aggiunte con questo aggiornamento!")

            L.append(f"  └{'─'*78}")
            L.append("")

    # ── RIEPILOGO FINALE ──
    L.append("══════════════════════════════════════════════════════════════════════════════════")
    L.append("  RIEPILOGO FINALE")
    L.append("══════════════════════════════════════════════════════════════════════════════════")
    L.append("")
    L.append(f"  {'':30} {'SENZA update':>16} {'CON update':>16} {'Differenza':>16}")
    L.append(f"  {'':30} {'(mattino)':>16} {'(serale)':>16} {'':>16}")
    L.append(f"  {'─'*30} {'─'*16} {'─'*16} {'─'*16}")

    def fmt_val(v, suffix=""):
        return f"{v}{suffix}" if v is not None else "N/A"

    L.append(f"  {'Tip totali':<30} {stats_primo['totale_tip']:>16} {stats_ultimo['totale_tip']:>16} {stats_ultimo['totale_tip'] - stats_primo['totale_tip']:>+16d}")
    L.append(f"  {'Tip verificati':<30} {stats_primo['verificati']:>16} {stats_ultimo['verificati']:>16} {stats_ultimo['verificati'] - stats_primo['verificati']:>+16d}")
    L.append(f"  {'Vinti':<30} {stats_primo['vinti']:>16} {stats_ultimo['vinti']:>16} {diff_vinti:>+16d}")
    L.append(f"  {'Persi':<30} {stats_primo['persi']:>16} {stats_ultimo['persi']:>16} {diff_persi:>+16d}")

    hr_p = f"{stats_primo['hr']:.1f}%" if stats_primo['hr'] is not None else "N/A"
    hr_u = f"{stats_ultimo['hr']:.1f}%" if stats_ultimo['hr'] is not None else "N/A"
    L.append(f"  {'Hit Rate':<30} {hr_p:>16} {hr_u:>16} {hr_diff_str:>16}")

    pl_p = f"{stats_primo['pl']:+.2f}u"
    pl_u = f"{stats_ultimo['pl']:+.2f}u"
    L.append(f"  {'Profit/Loss':<30} {pl_p:>16} {pl_u:>16} {diff_pl:>+.2f}u{'':>10}")

    y_p = f"{stats_primo['yield']:.1f}%" if stats_primo['yield'] is not None else "N/A"
    y_u = f"{stats_ultimo['yield']:.1f}%" if stats_ultimo['yield'] is not None else "N/A"
    L.append(f"  {'Yield':<30} {y_p:>16} {y_u:>16} {yield_diff_str:>16}")

    L.append("")
    L.append(f"  Tip nuovi aggiunti: {len(nuovi_detail)} (vinti: {len(nuovi_vinti)}, persi: {len(nuovi_persi)}, P/L: {nuovi_pl:+.2f}u)")
    L.append(f"  Tip rimossi:        {len(rimossi_detail)} (sarebbero stati vinti: {len(rimossi_vinti)}, persi: {len(rimossi_persi)}, P/L perso: {rimossi_pl:+.2f}u)")
    L.append(f"  Tip modificati:     {len(cambiati)} (quota/confidence/stake/source)")
    L.append("")

    if diff_pl > 0.5:
        L.append(f"  📈 Gli aggiornamenti pre-match hanno portato un guadagno netto di {diff_pl:+.2f}u")
    elif diff_pl < -0.5:
        L.append(f"  📉 Gli aggiornamenti pre-match hanno causato una perdita netta di {diff_pl:+.2f}u")
    else:
        L.append(f"  📊 Gli aggiornamenti pre-match non hanno avuto un impatto significativo ({diff_pl:+.2f}u)")
    L.append("══════════════════════════════════════════════════════════════════════════════════")

    # ── COMMENTO TESTUALE ──
    L.append("")
    L.append("══════════════════════════════════════════════════════════════════════════════════")
    L.append("  ANALISI DELLA GIORNATA")
    L.append("══════════════════════════════════════════════════════════════════════════════════")
    L.append("")

    # Costruisci il commento in base ai dati
    tot_mattino = stats_primo["totale_tip"]
    tot_serale = stats_ultimo["totale_tip"]
    diff_tip = tot_serale - tot_mattino

    comm = []
    comm.append(f"  La giornata del {date_str} e' partita con {tot_mattino} pronostici al mattino")
    comm.append(f"  e si e' chiusa con {tot_serale} pronostici alla sera ({diff_tip:+d} tip).")
    comm.append("")

    # Aggiornamenti step by step
    if len(snapshots) >= 3:
        # Calcola stats per ogni snapshot
        all_stats = []
        for snap in snapshots:
            m = tip_map_full(snap)
            tips = []
            for k, t in m.items():
                score = results.get(t["match_key"], "")
                hit = calculate_hit(t["pronostico"], t["tipo"], score)
                pl = calc_pl(hit, t.get("quota", 0) or 0)
                tips.append({**t, "hit": hit, "pl": round(pl, 2)})
            all_stats.append(calc_stats(tips))

        comm.append(f"  L'aggiornamento del pomeriggio (Mattino -> Intermedio) ha avuto un impatto")
        step1_pl = round(all_stats[1]["pl"] - all_stats[0]["pl"], 2)
        if step1_pl > 0:
            comm.append(f"  positivo di {step1_pl:+.2f}u sul rendimento.")
        elif step1_pl < 0:
            comm.append(f"  negativo di {step1_pl:+.2f}u sul rendimento.")
        else:
            comm.append(f"  neutro sul rendimento.")

        step2_pl = round(all_stats[2]["pl"] - all_stats[1]["pl"], 2)
        comm.append(f"  L'aggiornamento serale (Intermedio -> Serale) ha avuto un impatto")
        if step2_pl > 0:
            comm.append(f"  positivo di {step2_pl:+.2f}u sul rendimento.")
        elif step2_pl < 0:
            comm.append(f"  negativo di {step2_pl:+.2f}u sul rendimento.")
        else:
            comm.append(f"  neutro sul rendimento.")
        comm.append("")

    # Tip nuovi e rimossi
    if nuovi_detail:
        comm.append(f"  Gli aggiornamenti hanno introdotto {len(nuovi_detail)} pronostici nuovi:")
        if nuovi_vinti:
            comm.append(f"  di questi, {len(nuovi_vinti)} si sono rivelati vincenti ({nuovi_pl:+.2f}u),")
            comm.append(f"  confermando che il sistema ha saputo cogliere opportunita' valide.")
        if nuovi_persi:
            comm.append(f"  tuttavia {len(nuovi_persi)} sono risultati perdenti.")
        comm.append("")

    if rimossi_detail:
        comm.append(f"  Sono stati rimossi {len(rimossi_detail)} pronostici rispetto al mattino:")
        if rimossi_vinti:
            comm.append(f"  attenzione: {len(rimossi_vinti)} di questi sarebbero stati vincenti!")
            comm.append(f"  Questo significa che il sistema ha perso {abs(sum(t['pl'] for t in rimossi_detail if t['hit'] is True)):.2f}u")
            comm.append(f"  di potenziale guadagno eliminando pronostici che avrebbero vinto.")
        if rimossi_persi:
            comm.append(f"  D'altra parte, {len(rimossi_persi)} pronostici rimossi avrebbero perso,")
            comm.append(f"  evitando una perdita di {abs(sum(t['pl'] for t in rimossi_detail if t['hit'] is False)):.2f}u.")
        comm.append("")

    # Bilancio per mercato
    if stats_primo["per_mercato"] and stats_ultimo["per_mercato"]:
        comm.append(f"  Per quanto riguarda i mercati:")
        all_markets = set(list(stats_primo["per_mercato"].keys()) + list(stats_ultimo["per_mercato"].keys()))
        for mkt in sorted(all_markets):
            pl_m = stats_primo["per_mercato"].get(mkt, {"pl": 0})["pl"]
            pl_s = stats_ultimo["per_mercato"].get(mkt, {"pl": 0})["pl"]
            diff_mkt = round(pl_s - pl_m, 2)
            if abs(diff_mkt) > 0.01:
                if diff_mkt > 0:
                    comm.append(f"  - {mkt}: migliorato di {diff_mkt:+.2f}u con gli aggiornamenti")
                else:
                    comm.append(f"  - {mkt}: peggiorato di {diff_mkt:+.2f}u con gli aggiornamenti")
            else:
                comm.append(f"  - {mkt}: invariato")
        comm.append("")

    # Verdetto finale
    if diff_pl > 1:
        comm.append(f"  In conclusione, gli aggiornamenti pre-match hanno portato un beneficio")
        comm.append(f"  significativo di {diff_pl:+.2f}u. Il sistema di update funziona bene")
        comm.append(f"  per questa giornata e ha migliorato la qualita' dei pronostici.")
    elif diff_pl > 0:
        comm.append(f"  In conclusione, gli aggiornamenti hanno portato un leggero miglioramento")
        comm.append(f"  di {diff_pl:+.2f}u. L'impatto e' positivo ma contenuto.")
    elif diff_pl > -0.5:
        comm.append(f"  In conclusione, gli aggiornamenti non hanno avuto un impatto rilevante")
        comm.append(f"  ({diff_pl:+.2f}u). Scommettere con i pronostici del mattino o della sera")
        comm.append(f"  avrebbe portato risultati sostanzialmente equivalenti.")
    else:
        comm.append(f"  In conclusione, gli aggiornamenti pre-match hanno peggiorato il rendimento")
        comm.append(f"  di {diff_pl:+.2f}u. Sarebbe stato meglio scommettere con i pronostici del mattino.")
        comm.append(f"  Valutare se ridurre la frequenza degli aggiornamenti o rivederne la logica.")

    L.extend(comm)
    L.append("")
    L.append("══════════════════════════════════════════════════════════════════════════════════")

    # ── SALVA ──
    confronto_dir = get_label_dir(date_str, "confronto")

    txt_path = os.path.join(confronto_dir, "confronto.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"\nConfronto salvato: {txt_path}")

    json_path = os.path.join(confronto_dir, "confronto.json")
    confronto_data = {
        "date": date_str,
        "risultati_trovati": len(results),
        "snapshots": [{"label": s["label"], "timestamp": s["timestamp"], "riepilogo": s["riepilogo"]} for s in snapshots],
        "scenario_senza_update": stats_primo,
        "scenario_con_update": stats_ultimo,
        "differenza": {
            "vinti": diff_vinti,
            "persi": diff_persi,
            "hr": diff_hr,
            "pl": diff_pl,
            "yield": diff_yield,
        },
        "nuovi": len(nuovi_detail),
        "rimossi": len(rimossi_detail),
        "cambiati": len(cambiati),
        "dettaglio_nuovi": nuovi_detail,
        "dettaglio_rimossi": rimossi_detail,
        "dettaglio_cambiati": cambiati,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(confronto_data, f, ensure_ascii=False, indent=2, default=str)
    print(f"Confronto JSON: {json_path}")


def main():
    if len(sys.argv) < 2:
        print("Uso: python snapshot_pronostici.py <mattino|intermedio|serale|confronto> [data]")
        print("  data: formato YYYY-MM-DD (default: oggi)")
        sys.exit(1)

    label = sys.argv[1].lower()
    date_str = sys.argv[2] if len(sys.argv) > 2 else datetime.now().strftime("%Y-%m-%d")

    valid_labels = ["mattino", "intermedio", "serale", "confronto"]
    if label not in valid_labels:
        print(f"Label non valido: {label}. Usa: {', '.join(valid_labels)}")
        sys.exit(1)

    if label == "confronto":
        if len(sys.argv) > 2:
            do_confronto_singolo(date_str)
        else:
            do_confronto_auto()
    else:
        do_snapshot(label, date_str)

    print("\nDone!")


if __name__ == "__main__":
    main()
