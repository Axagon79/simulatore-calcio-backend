"""
AGGREGAZIONE PREDICTION ERRORS
===============================
Legge i documenti da prediction_errors e produce un JSON aggregato
con le statistiche utili per decidere come modificare i pesi.

Output: log/prediction_errors_aggregated.json
"""
import os, sys, json, re
from collections import Counter, defaultdict
from datetime import datetime

current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db

coll = db['prediction_errors']
docs = list(coll.find({}))
total = len(docs)

print(f"\n{'='*60}")
print(f"AGGREGAZIONE PREDICTION ERRORS — {total} documenti")
print(f"{'='*60}\n")

if total == 0:
    print("Nessun documento!")
    sys.exit(0)

# ─────────────────────────────────────────────
# 1. VARIABLES IMPACT — per sistema e per mercato
# ─────────────────────────────────────────────

def get_sistema(source):
    """Raggruppa le source in sistema principale."""
    if not source:
        return "unknown"
    s = source.upper()
    if s.startswith("C"):
        return "C"
    elif s.startswith("A+S") or s.startswith("AS"):
        return "A+S"
    elif s.startswith("A"):
        return "A"
    elif s.startswith("S"):
        return "S"
    elif s.startswith("MC"):
        return "C"
    return "other"

def aggregate_vi(docs_list):
    """Media variables_impact su una lista di documenti."""
    sums = defaultdict(float)
    count = 0
    for d in docs_list:
        vi = d.get("variables_impact", {})
        if vi:
            count += 1
            for k, v in vi.items():
                try:
                    sums[k] += float(v)
                except (ValueError, TypeError):
                    pass
    if count == 0:
        return {}, 0
    return {k: round(v / count, 4) for k, v in sorted(sums.items(), key=lambda x: -x[1])}, count

# Per sistema
sistemi = defaultdict(list)
for d in docs:
    sistemi[get_sistema(d.get("source", ""))].append(d)

vi_per_sistema = {}
for sistema, docs_s in sistemi.items():
    avg, cnt = aggregate_vi(docs_s)
    vi_per_sistema[sistema] = {"count": cnt, "variables_impact_avg": avg}

# Per mercato (prediction_type)
mercati = defaultdict(list)
for d in docs:
    mercati[d.get("prediction_type", "unknown")].append(d)

vi_per_mercato = {}
for mercato, docs_m in mercati.items():
    avg, cnt = aggregate_vi(docs_m)
    vi_per_mercato[mercato] = {"count": cnt, "variables_impact_avg": avg}

# Totale
vi_totale_avg, vi_totale_cnt = aggregate_vi(docs)

print(f"  Variables Impact aggregati per {len(sistemi)} sistemi, {len(mercati)} mercati")

# ─────────────────────────────────────────────
# 2. SUGGESTED ADJUSTMENT — raggruppati per tema
# ─────────────────────────────────────────────

# Estrai parole chiave dai suggested_adjustment
peso_mentions = Counter()  # quante volte viene menzionato ogni peso
direzione_mentions = Counter()  # "ridurre X" vs "aumentare X"

PESI_KEYWORDS = [
    'strisce', 'streak', 'bvs', 'quote', 'lucifero', 'forma',
    'affidabilita', 'affidabilità', 'dna', 'motivazioni', 'motivazione',
    'h2h', 'campo', 'media_gol', 'att_vs_def', 'xg', 'rating',
    'valore_rosa', 'rosa', 'difesa', 'attacco'
]

for d in docs:
    sa = (d.get("suggested_adjustment") or "").lower()
    if not sa:
        continue

    for keyword in PESI_KEYWORDS:
        if keyword in sa:
            peso_mentions[keyword] += 1
            # Cerca direzione
            if re.search(r'ridur|abbass|diminui|meno peso', sa):
                direzione_mentions[f"RIDURRE_{keyword}"] += 1
            if re.search(r'aumenta|alza|maggior|più peso|aggiung', sa):
                direzione_mentions[f"AUMENTARE_{keyword}"] += 1

# Testi unici raggruppati (campione per ogni "tema")
adjustment_testi = []
for d in docs:
    sa = d.get("suggested_adjustment", "")
    if sa:
        adjustment_testi.append({
            "text": sa,
            "source": d.get("source", ""),
            "severity": d.get("severity", ""),
            "prediction_type": d.get("prediction_type", "")
        })

print(f"  Suggested adjustments: {len(adjustment_testi)} totali, {len(peso_mentions)} pesi menzionati")

# ─────────────────────────────────────────────
# 3. HR e P/L per source
# ─────────────────────────────────────────────

# Nota: prediction_errors contiene SOLO gli errori.
# Per avere HR servono anche i corretti → li prendiamo da daily_predictions_*
# Qui calcoliamo solo il P/L degli errori e il conteggio

pl_per_source = defaultdict(lambda: {"count": 0, "total_pl": 0.0, "high": 0, "medium": 0, "low": 0})
pl_per_mercato = defaultdict(lambda: {"count": 0, "total_pl": 0.0, "high": 0, "medium": 0, "low": 0})
pl_per_sistema = defaultdict(lambda: {"count": 0, "total_pl": 0.0, "high": 0, "medium": 0, "low": 0})

for d in docs:
    source = d.get("source", "unknown")
    sistema = get_sistema(source)
    mercato = d.get("prediction_type", "unknown")
    pl = d.get("profit_loss", 0)
    sev = d.get("severity", "unknown")

    for bucket, key in [(pl_per_source, source), (pl_per_mercato, mercato), (pl_per_sistema, sistema)]:
        bucket[key]["count"] += 1
        bucket[key]["total_pl"] += pl
        if sev in ("high", "medium", "low"):
            bucket[key][sev] += 1

# Ordina per P/L
pl_per_source = dict(sorted(pl_per_source.items(), key=lambda x: x[1]["total_pl"]))
pl_per_mercato = dict(sorted(pl_per_mercato.items(), key=lambda x: x[1]["total_pl"]))
pl_per_sistema = dict(sorted(pl_per_sistema.items(), key=lambda x: x[1]["total_pl"]))

print(f"  P/L aggregato per {len(pl_per_source)} source, {len(pl_per_sistema)} sistemi")

# ─────────────────────────────────────────────
# 4. SEVERITY per sistema
# ─────────────────────────────────────────────

severity_per_sistema = {}
for sistema, docs_s in sistemi.items():
    sev_count = Counter(d.get("severity", "unknown") for d in docs_s)
    severity_per_sistema[sistema] = dict(sev_count.most_common())

# ─────────────────────────────────────────────
# 5. ERRORI per fascia confidence
# ─────────────────────────────────────────────

fasce_confidence = defaultdict(lambda: {"count": 0, "total_pl": 0.0, "high_severity": 0})
for d in docs:
    conf = d.get("confidence", 0)
    if conf < 40:
        fascia = "0-40"
    elif conf < 50:
        fascia = "40-50"
    elif conf < 60:
        fascia = "50-60"
    elif conf < 70:
        fascia = "60-70"
    elif conf < 80:
        fascia = "70-80"
    else:
        fascia = "80+"

    fasce_confidence[fascia]["count"] += 1
    fasce_confidence[fascia]["total_pl"] += d.get("profit_loss", 0)
    if d.get("severity") == "high":
        fasce_confidence[fascia]["high_severity"] += 1

# Ordina per fascia
fasce_confidence = dict(sorted(fasce_confidence.items()))

print(f"  Fasce confidence: {len(fasce_confidence)}")

# ─────────────────────────────────────────────
# 6. ERRORI per fascia quota
# ─────────────────────────────────────────────

fasce_quota = defaultdict(lambda: {"count": 0, "total_pl": 0.0})
for d in docs:
    q = d.get("quota") or 0
    try:
        q = float(q)
    except (ValueError, TypeError):
        q = 0
    if q < 1.35:
        fascia = "<1.35"
    elif q < 1.55:
        fascia = "1.35-1.55"
    elif q < 1.75:
        fascia = "1.55-1.75"
    elif q < 1.95:
        fascia = "1.75-1.95"
    elif q < 2.15:
        fascia = "1.95-2.15"
    elif q < 2.50:
        fascia = "2.15-2.50"
    else:
        fascia = ">2.50"

    fasce_quota[fascia]["count"] += 1
    fasce_quota[fascia]["total_pl"] += d.get("profit_loss", 0)

fasce_quota = dict(sorted(fasce_quota.items()))

# ─────────────────────────────────────────────
# 7. VARIABLES IMPACT per sistema C + mercato
# ─────────────────────────────────────────────

# Dettaglio più fine: Sistema C spezzato per mercato
vi_c_per_mercato = {}
docs_c = sistemi.get("C", [])
mercati_c = defaultdict(list)
for d in docs_c:
    mercati_c[d.get("prediction_type", "unknown")].append(d)

for mercato, docs_cm in mercati_c.items():
    avg, cnt = aggregate_vi(docs_cm)
    vi_c_per_mercato[mercato] = {"count": cnt, "variables_impact_avg": avg}

# ─────────────────────────────────────────────
# BUILD OUTPUT
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# 8. HR E P/L REALI DAI PRONOSTICI (non solo errori)
# ─────────────────────────────────────────────

print("  Calcolo HR e P/L reali dai pronostici...")

hr_reali = {}
for coll_name, sistema_label in [
    ('daily_predictions_engine_c', 'C'),
    ('daily_predictions', 'A'),
    ('daily_predictions_sandbox', 'S'),
]:
    coll_pred = db[coll_name]
    stats_hr = defaultdict(lambda: {'emessi': 0, 'con_risultato': 0, 'corretti': 0, 'errati': 0, 'pl': 0.0})

    for doc in coll_pred.find({'pronostici': {'$exists': True}}, {'pronostici': 1}):
        for p in doc.get('pronostici', []):
            tipo = p.get('tipo', 'unknown')
            stats_hr[tipo]['emessi'] += 1
            esito = p.get('esito')
            if esito is True or esito is False:
                stats_hr[tipo]['con_risultato'] += 1
                if esito is True:
                    stats_hr[tipo]['corretti'] += 1
                else:
                    stats_hr[tipo]['errati'] += 1
                pl_val = p.get('profit_loss', 0) or 0
                try:
                    stats_hr[tipo]['pl'] += float(pl_val)
                except (ValueError, TypeError):
                    pass

    # Calcola HR per mercato
    sistema_stats = {}
    for tipo, d in stats_hr.items():
        hr_val = round(d['corretti'] / d['con_risultato'] * 100, 1) if d['con_risultato'] > 0 else 0
        sistema_stats[tipo] = {
            'emessi': d['emessi'],
            'con_risultato': d['con_risultato'],
            'corretti': d['corretti'],
            'errati': d['errati'],
            'hr': hr_val,
            'pl': round(d['pl'], 1)
        }

    # Totale (esclusi RE)
    tot_r = sum(d['con_risultato'] for t, d in stats_hr.items() if t != 'RISULTATO_ESATTO')
    tot_c = sum(d['corretti'] for t, d in stats_hr.items() if t != 'RISULTATO_ESATTO')
    tot_pl = sum(d['pl'] for t, d in stats_hr.items() if t != 'RISULTATO_ESATTO')
    sistema_stats['_TOTALE_NO_RE'] = {
        'con_risultato': tot_r,
        'corretti': tot_c,
        'hr': round(tot_c / tot_r * 100, 1) if tot_r > 0 else 0,
        'pl': round(tot_pl, 1)
    }

    hr_reali[sistema_label] = sistema_stats

print(f"  HR reali calcolati per {len(hr_reali)} sistemi")

output = {
    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "total_errors": total,

    "hr_e_pl_reali": hr_reali,

    "variables_impact": {
        "totale": {"count": vi_totale_cnt, "avg": vi_totale_avg},
        "per_sistema": vi_per_sistema,
        "per_mercato": vi_per_mercato,
        "sistema_c_per_mercato": vi_c_per_mercato
    },

    "suggested_adjustments": {
        "pesi_menzionati": dict(peso_mentions.most_common()),
        "direzioni": dict(direzione_mentions.most_common()),
        "totale_con_testo": len(adjustment_testi)
    },

    "pl_e_severity": {
        "per_sistema": pl_per_sistema,
        "per_mercato": pl_per_mercato,
        "per_source": pl_per_source,
        "severity_per_sistema": severity_per_sistema
    },

    "fasce_confidence": fasce_confidence,
    "fasce_quota": fasce_quota
}

# Salva
log_dir = os.path.join(current_path, 'log')
os.makedirs(log_dir, exist_ok=True)
out_path = os.path.join(log_dir, 'prediction_errors_aggregated.json')

with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"\n✅ Salvato in: {out_path}")
print(f"   Dimensione: {os.path.getsize(out_path) / 1024:.1f} KB")
