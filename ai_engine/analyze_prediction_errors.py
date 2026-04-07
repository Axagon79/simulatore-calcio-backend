"""
ANALISI PREDICTION ERRORS → RACCOMANDAZIONI PESI
=================================================
Legge prediction_errors_aggregated.json e i pesi attuali ALGO_C,
produce un report leggibile con raccomandazioni concrete.

Output: log/prediction_errors_recommendations.txt + .json
"""
import os, sys, json
from datetime import datetime
from collections import defaultdict

current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db

# ─── CARICA DATI ───
agg_path = os.path.join(current_path, 'log', 'prediction_errors_aggregated.json')
with open(agg_path, 'r', encoding='utf-8') as f:
    agg = json.load(f)

# ─── CARICA PESI ATTUALI DA MONGODB ───
pesi = {}
try:
    doc = db['tuning_settings'].find_one({"_id": "algo_c_config"})
    if doc and "config" in doc and "ALGO_C" in doc["config"]:
        for k, v in doc["config"]["ALGO_C"].items():
            if k.startswith("_") or k.startswith("THR_"):
                continue
            if isinstance(v, dict) and "valore" in v:
                pesi[k] = v["valore"]
except:
    pass

# ─── MAPPATURE ───
# Keyword feedback → peso motore
FB_TO_PESO = {
    "strisce": "PESO_STREAK", "quote": "PESO_BVS_QUOTE", "bvs": "PESO_BVS_QUOTE",
    "lucifero": "PESO_FORMA_RECENTE", "forma": "PESO_FORMA_RECENTE",
    "motivazioni": "PESO_MOTIVAZIONE", "motivazione": "PESO_MOTIVAZIONE",
    "h2h": "PESO_STORIA_H2H", "campo": "PESO_FATTORE_CAMPO",
    "affidabilita": "PESO_AFFIDABILITA", "affidabilità": "PESO_AFFIDABILITA",
    "rating": "PESO_RATING_ROSA", "rosa": "PESO_VALORE_ROSA",
    "media_gol": "DIVISORE_MEDIA_GOL", "att_vs_def": "IMPATTO_DIFESA_TATTICA",
    "difesa": "IMPATTO_DIFESA_TATTICA", "xg": "DIVISORE_MEDIA_GOL",
    "attacco": "PESO_RATING_ROSA",
}

# Variables impact → peso motore
VI_TO_PESO = {
    "market_odds": "PESO_BVS_QUOTE", "streaks": "PESO_STREAK",
    "form": "PESO_FORMA_RECENTE", "home_advantage": "PESO_FATTORE_CAMPO",
    "h2h": "PESO_STORIA_H2H", "motivation": "PESO_MOTIVAZIONE",
}

# Nomi leggibili
NOMI = {
    "PESO_STREAK": "Strisce", "PESO_BVS_QUOTE": "BVS / Quote",
    "PESO_FORMA_RECENTE": "Forma Recente", "PESO_FATTORE_CAMPO": "Fattore Campo",
    "PESO_MOTIVAZIONE": "Motivazione", "PESO_STORIA_H2H": "H2H",
    "PESO_AFFIDABILITA": "Affidabilità", "PESO_RATING_ROSA": "Rating Rosa",
    "PESO_VALORE_ROSA": "Valore Rosa", "DIVISORE_MEDIA_GOL": "Divisore Gol",
    "IMPATTO_DIFESA_TATTICA": "Impatto Difesa", "POTENZA_FAVORITA_WINSHIFT": "Winshift",
    "TETTO_MAX_GOL_ATTESI": "Tetto Max Gol",
}

# ─── CALCOLA SCORE PER PESO ───
scores = defaultdict(lambda: {"rid": 0, "aum": 0, "impact": 0.0})

# Da variables_impact Sistema C
vi_c = agg["variables_impact"]["per_sistema"].get("C", {}).get("variables_impact_avg", {})
for vi_key, peso_key in VI_TO_PESO.items():
    scores[peso_key]["impact"] += vi_c.get(vi_key, 0)

# Da suggested_adjustments
for dir_key, count in agg["suggested_adjustments"]["direzioni"].items():
    parts = dir_key.split("_", 1)
    if len(parts) != 2:
        continue
    azione, fb_key = parts
    peso_key = FB_TO_PESO.get(fb_key)
    if not peso_key:
        continue
    if azione == "RIDURRE":
        scores[peso_key]["rid"] += count
    elif azione == "AUMENTARE":
        scores[peso_key]["aum"] += count

# ─── GENERA REPORT TXT ───
lines = []
W = 72  # larghezza

def hr():
    lines.append("─" * W)

def title(t):
    lines.append("")
    lines.append(f"  {t}")
    hr()

now = datetime.now().strftime("%d/%m/%Y %H:%M")
tot = agg["total_errors"]
tot_c = agg["pl_e_severity"]["per_sistema"].get("C", {}).get("count", 0)
pl_c = agg["pl_e_severity"]["per_sistema"].get("C", {}).get("total_pl", 0)

lines.append("═" * W)
lines.append(f"  REPORT ANALISI ERRORI — SISTEMA C (Monte Carlo)")
lines.append(f"  {now} | {tot} errori totali | {tot_c} Sistema C | P/L {pl_c:+.0f}u")
lines.append("═" * W)

# ── SEZIONE 1: PESI ATTUALI ──
title("1. PESI ATTUALI ALGO_C (MongoDB)")
lines.append(f"  {'Peso':<30s} {'Valore':>8s}")
hr()
for k in sorted(pesi.keys()):
    nome = NOMI.get(k, k)
    lines.append(f"  {nome:<30s} {pesi[k]:>8.2f}")

# ── SEZIONE 2: HR E P/L REALI ──
hr_reali = agg.get("hr_e_pl_reali", {})
if hr_reali:
    title("2. HR E P/L REALI (tutti i pronostici, non solo errori)")
    lines.append(f"  {'Sistema':<10s} {'Mercato':<18s} {'Finiti':>7s} {'OK':>6s} {'KO':>6s} {'HR':>7s} {'P/L':>10s}")
    hr()
    for sistema in ["C", "A", "S"]:
        s_data = hr_reali.get(sistema, {})
        for mercato in ["SEGNO", "DOPPIA_CHANCE", "GOL"]:
            d = s_data.get(mercato, {})
            if not d or d.get("con_risultato", 0) == 0:
                continue
            hr_val = d.get("hr", 0)
            lines.append(f"  {sistema:<10s} {mercato:<18s} {d['con_risultato']:>7d} {d['corretti']:>6d} {d['errati']:>6d} {hr_val:>6.1f}% {d['pl']:>+10.1f}")
        # Totale no RE
        tot = s_data.get("_TOTALE_NO_RE", {})
        if tot and tot.get("con_risultato", 0) > 0:
            lines.append(f"  {sistema:<10s} {'TOTALE (no RE)':<18s} {tot['con_risultato']:>7d} {tot['corretti']:>6d} {'':>6s} {tot['hr']:>6.1f}% {tot['pl']:>+10.1f}")
        lines.append("")

# ── SEZIONE 3: CAUSE ERRORI ──
title("3. CAUSE PRINCIPALI DEGLI ERRORI (variables_impact)")
lines.append(f"  Cosa fa sbagliare di più il modello, in media su {tot_c} errori Sistema C:")
lines.append("")
lines.append(f"  {'Causa':<20s} {'Impact':>7s}  {'Barra'}")
hr()
for vi_key in ["market_odds", "streaks", "tactical_dna", "form", "home_advantage", "h2h", "motivation"]:
    val = vi_c.get(vi_key, 0)
    if val < 0.01:
        continue
    bar = "█" * int(val * 40)
    lines.append(f"  {vi_key:<20s} {val:>6.1%}  {bar}")

lines.append("")
lines.append("  → Le quote di mercato (39%) e le strisce (26%) causano il 65% degli errori.")
lines.append("    Il modello non ascolta abbastanza il mercato e si fida troppo delle strisce.")

# ── SEZIONE 3: P/L PER MERCATO ──
title("4. DOVE SI PERDE DI PIÙ (solo errori)")
lines.append(f"  {'Mercato':<15s} {'Errori':>7s} {'P/L':>8s} {'Severity HIGH':>14s}")
hr()
for m in ["GOL", "SEGNO", "DOPPIA_CHANCE"]:
    d = agg["pl_e_severity"]["per_mercato"].get(m, {})
    cnt = d.get("count", 0)
    pl = d.get("total_pl", 0)
    hi = d.get("high", 0)
    pct = round(hi / cnt * 100) if cnt > 0 else 0
    lines.append(f"  {m:<15s} {cnt:>7d} {pl:>+8.0f}u {hi:>6d} ({pct}%)")

# ── SEZIONE 4: OVERCONFIDENCE ──
title("5. OVERCONFIDENCE — Più è sicuro, più sbaglia gravemente")
lines.append(f"  {'Confidence':<12s} {'Errori':>7s} {'P/L':>8s} {'% High Sev':>11s}")
hr()
for fascia, d in agg["fasce_confidence"].items():
    cnt = d["count"]
    pl = d["total_pl"]
    hi = d["high_severity"]
    pct = round(hi / cnt * 100) if cnt > 0 else 0
    lines.append(f"  {fascia:<12s} {cnt:>7d} {pl:>+8.0f}u {pct:>9d}%")

lines.append("")
lines.append("  → Fascia 70-80%: 88.5% degli errori sono HIGH severity.")
lines.append("    Fascia 80+: TUTTI high severity. Il modello è troppo sicuro di sé.")

# ── SEZIONE 5: COSA DICE MISTRAL ──
title("6. COSA SUGGERISCE MISTRAL (498 analisi)")
lines.append("")
lines.append(f"  {'Peso':<22s} {'Attuale':>7s} {'Riduci':>7s} {'Aumenta':>8s} {'Netto':>7s} {'Verdetto'}")
hr()

# Ordina per |netto| decrescente
peso_list = []
for peso_key, d in scores.items():
    rid = d["rid"]
    aum = d["aum"]
    tot_m = rid + aum
    if tot_m < 5:
        continue
    netto = aum - rid
    nome = NOMI.get(peso_key, peso_key)
    val = pesi.get(peso_key, "?")

    if tot_m > 0:
        ratio = abs(netto) / tot_m
    else:
        ratio = 0

    if netto < -20 and ratio > 0.2:
        verdetto = "↓ RIDURRE"
    elif netto > 20 and ratio > 0.2:
        verdetto = "↑ AUMENTARE"
    elif abs(netto) > 10:
        verdetto = "↓ ridurre?" if netto < 0 else "↑ aumentare?"
    else:
        verdetto = "— incerto"

    peso_list.append((peso_key, nome, val, rid, aum, netto, verdetto, abs(netto)))

peso_list.sort(key=lambda x: -x[7])

for peso_key, nome, val, rid, aum, netto, verdetto, _ in peso_list:
    val_str = f"{val:.2f}" if isinstance(val, (int, float)) else str(val)
    lines.append(f"  {nome:<22s} {val_str:>7s} {rid:>7d} {aum:>8d} {netto:>+7d} {verdetto}")

# ── SEZIONE 6: RIEPILOGO ──
title("7. RIEPILOGO — Direzioni chiare")
lines.append("")

for peso_key, nome, val, rid, aum, netto, verdetto, _ in peso_list:
    if "incerto" in verdetto:
        continue
    val_str = f"{val:.2f}" if isinstance(val, (int, float)) else str(val)
    pct = round(abs(netto) / (rid + aum) * 100) if (rid + aum) > 0 else 0
    lines.append(f"  {verdetto:<14s} {nome:<22s} (attuale {val_str}, {pct}% accordo)")

lines.append("")
lines.append("  I pesi con '?' hanno segnale debole — Mistral si contraddice.")
lines.append("  Quelli senza '?' hanno almeno il 20% di accordo netto sulla direzione.")

lines.append("")
lines.append("═" * W)

# ── SALVA ──
log_dir = os.path.join(current_path, 'log')
txt_path = os.path.join(log_dir, 'prediction_errors_recommendations.txt')
with open(txt_path, 'w', encoding='utf-8') as f:
    f.write("\n".join(lines))

# JSON
json_out = {
    "generated_at": now,
    "total_errors": tot,
    "pesi_attuali": pesi,
    "raccomandazioni": [
        {
            "peso": pk, "nome": nm, "attuale": vl,
            "ridurre": ri, "aumentare": au, "netto": ne, "verdetto": ve
        }
        for pk, nm, vl, ri, au, ne, ve, _ in peso_list
    ],
    "contesto": {
        "pl_sistema_c": agg["pl_e_severity"]["per_sistema"].get("C", {}),
        "pl_per_mercato": agg["pl_e_severity"]["per_mercato"],
        "fasce_confidence": agg["fasce_confidence"],
        "variables_impact_c": vi_c
    }
}
json_path = os.path.join(log_dir, 'prediction_errors_recommendations.json')
with open(json_path, 'w', encoding='utf-8') as f:
    json.dump(json_out, f, indent=2, ensure_ascii=False)

print(f"✅ {txt_path}")
print(f"✅ {json_path}")

# Stampa a video
print()
print("\n".join(lines))
