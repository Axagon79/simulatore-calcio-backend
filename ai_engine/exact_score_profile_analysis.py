"""
Analisi Profilo Risultato Esatto — Per ogni score, qual è il profilo tipico dei segnali?
Approccio: stessa logica dell'X Factor — trovare i pattern che distinguono ogni risultato.
"""
import sys, os
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db
from collections import defaultdict
import statistics

h2h_collection = db['h2h_by_round']

# ==================== RACCOLTA DATI ====================

print("Raccogliendo partite finite da h2h_by_round...")

pipeline = [
    {"$unwind": "$matches"},
    {"$match": {
        "matches.real_score": {"$exists": True, "$nin": ["-:-", "", None]},
        "matches.h2h_data": {"$exists": True},
    }},
    {"$project": {
        "league": 1,
        "match": "$matches",
    }}
]

matches = []
for doc in h2h_collection.aggregate(pipeline):
    m = doc['match']
    m['_league'] = doc.get('league', 'Unknown')

    score_str = m.get('real_score', '')
    if ':' not in score_str:
        continue
    parts = score_str.split(':')
    try:
        home_goals = int(parts[0].strip())
        away_goals = int(parts[1].strip())
    except (ValueError, IndexError):
        continue

    m['_home_goals'] = home_goals
    m['_away_goals'] = away_goals
    m['_score_key'] = f"{home_goals}:{away_goals}"
    matches.append(m)

print(f"Partite totali: {len(matches)}")

# ==================== ESTRAZIONE SEGNALI ====================

def extract_signals(m):
    """Estrae tutti i segnali numerici e categorici da una partita."""
    h2h = m.get('h2h_data', {}) or {}
    odds = m.get('odds', {}) or {}
    h2h_dna = h2h.get('h2h_dna', {}) or {}
    home_dna = h2h_dna.get('home_dna', {}) or {}
    away_dna = h2h_dna.get('away_dna', {}) or {}
    fc = h2h.get('fattore_campo', {}) or {}
    affid = h2h.get('affidabilità', {}) or {}

    signals = {}

    # --- NUMERICI ---
    # Fattore Campo
    signals['fc_home'] = _float(fc.get('field_home'))
    signals['fc_away'] = _float(fc.get('field_away'))

    # H2H Score (scala 0-10)
    signals['h2h_home_score'] = _float(h2h.get('home_score'))
    signals['h2h_away_score'] = _float(h2h.get('away_score'))
    signals['h2h_score_diff'] = None
    if signals['h2h_home_score'] is not None and signals['h2h_away_score'] is not None:
        signals['h2h_score_diff'] = signals['h2h_home_score'] - signals['h2h_away_score']

    # BVS
    signals['bvs'] = _float(h2h.get('bvs_match_index'))

    # Lucifero
    signals['lucifero_home'] = _float(h2h.get('lucifero_home'))
    signals['lucifero_away'] = _float(h2h.get('lucifero_away'))

    # DNA
    signals['dna_home_att'] = _float(home_dna.get('att'))
    signals['dna_home_def'] = _float(home_dna.get('def'))
    signals['dna_away_att'] = _float(away_dna.get('att'))
    signals['dna_away_def'] = _float(away_dna.get('def'))
    # Differenze DNA
    if signals['dna_home_att'] is not None and signals['dna_away_att'] is not None:
        signals['dna_att_diff'] = signals['dna_home_att'] - signals['dna_away_att']
    else:
        signals['dna_att_diff'] = None
    if signals['dna_home_def'] is not None and signals['dna_away_def'] is not None:
        signals['dna_def_diff'] = signals['dna_home_def'] - signals['dna_away_def']
    else:
        signals['dna_def_diff'] = None

    # Avg total goals
    signals['avg_total_goals'] = _float(h2h.get('avg_total_goals'))

    # Total matches H2H
    signals['total_matches'] = _float(h2h.get('total_matches'))

    # Rank
    signals['home_rank'] = _float(h2h.get('home_rank'))
    signals['away_rank'] = _float(h2h.get('away_rank'))
    if signals['home_rank'] is not None and signals['away_rank'] is not None:
        signals['rank_diff'] = signals['home_rank'] - signals['away_rank']
    else:
        signals['rank_diff'] = None

    # Affidabilità
    signals['affid_home'] = _float(affid.get('affidabilità_casa'))
    signals['affid_away'] = _float(affid.get('affidabilità_trasferta'))

    # Quote
    signals['quota_1'] = _float(odds.get('1'))
    signals['quota_X'] = _float(odds.get('X'))
    signals['quota_2'] = _float(odds.get('2'))
    if signals['quota_1'] is not None and signals['quota_2'] is not None:
        signals['quota_diff'] = signals['quota_1'] - signals['quota_2']
    else:
        signals['quota_diff'] = None

    # Quote O/U e GG/NG
    signals['quota_over'] = _float(odds.get('over_25'))
    signals['quota_under'] = _float(odds.get('under_25'))
    signals['quota_gg'] = _float(odds.get('gg'))
    signals['quota_ng'] = _float(odds.get('no_gg'))

    # --- CATEGORICI ---
    signals['classification'] = h2h.get('classification')
    signals['trust_home'] = h2h.get('trust_home_letter')
    signals['trust_away'] = h2h.get('trust_away_letter')

    return signals


def _float(val):
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# ==================== RAGGRUPPAMENTO PER RISULTATO ====================

print("Raggruppando per risultato esatto...")

# Raggruppa partite per score
score_groups = defaultdict(list)
for m in matches:
    score_groups[m['_score_key']].append(extract_signals(m))

# Ordina per frequenza
sorted_scores = sorted(score_groups.keys(), key=lambda s: -len(score_groups[s]))

# Media globale per ogni segnale numerico (baseline)
all_signals = [extract_signals(m) for m in matches]
NUMERIC_SIGNALS = [
    'fc_home', 'fc_away', 'h2h_home_score', 'h2h_away_score', 'h2h_score_diff',
    'bvs', 'lucifero_home', 'lucifero_away',
    'dna_home_att', 'dna_home_def', 'dna_away_att', 'dna_away_def',
    'dna_att_diff', 'dna_def_diff',
    'avg_total_goals', 'total_matches',
    'home_rank', 'away_rank', 'rank_diff',
    'affid_home', 'affid_away',
    'quota_1', 'quota_X', 'quota_2', 'quota_diff',
    'quota_over', 'quota_under', 'quota_gg', 'quota_ng',
]

CATEGORIC_SIGNALS = ['classification', 'trust_home', 'trust_away']

baseline = {}
for sig in NUMERIC_SIGNALS:
    vals = [s[sig] for s in all_signals if s[sig] is not None]
    baseline[sig] = statistics.mean(vals) if vals else None


# ==================== OUTPUT: PROFILO PER RISULTATO ====================

print(f"\n{'='*80}")
print("PROFILO MEDIO PER RISULTATO ESATTO")
print(f"{'='*80}")

# Top 15 risultati
TOP_SCORES = sorted_scores[:15]

# Header
print(f"\n{'Segnale':<22}", end="")
print(f"{'GLOBALE':>8}", end="")
for score in TOP_SCORES:
    n = len(score_groups[score])
    print(f" {score}({n})", end="")
    # Padding
    col_width = max(8, len(f"{score}({n})") + 1)
print()
print("-" * 200)

for sig in NUMERIC_SIGNALS:
    base_val = baseline[sig]
    if base_val is None:
        continue

    print(f"  {sig:<20}", end="")
    print(f"{base_val:>8.2f}", end="")

    for score in TOP_SCORES:
        group = score_groups[score]
        vals = [s[sig] for s in group if s[sig] is not None]
        if vals:
            avg = statistics.mean(vals)
            delta = avg - base_val
            # Evidenzia delta significativi
            marker = ""
            if abs(delta) > abs(base_val) * 0.15 and abs(delta) > 1:
                marker = " ***" if delta > 0 else " ---"
            elif abs(delta) > abs(base_val) * 0.08 and abs(delta) > 0.5:
                marker = " **" if delta > 0 else " --"
            elif abs(delta) > abs(base_val) * 0.04:
                marker = " *" if delta > 0 else " -"
            print(f"  {avg:>6.2f}{marker}", end="")
        else:
            print(f"  {'N/A':>6}", end="")

    print()

# ==================== CATEGORICI ====================

print(f"\n{'='*80}")
print("DISTRIBUZIONE CATEGORICI PER RISULTATO")
print(f"{'='*80}")

for cat_sig in CATEGORIC_SIGNALS:
    print(f"\n--- {cat_sig} ---")

    # Distribuzione globale
    global_dist = defaultdict(int)
    for s in all_signals:
        val = s[cat_sig]
        if val is not None:
            global_dist[val] += 1
    global_total = sum(global_dist.values())

    # Per ogni risultato
    for score in TOP_SCORES[:10]:
        group = score_groups[score]
        n = len(group)
        dist = defaultdict(int)
        for s in group:
            val = s[cat_sig]
            if val is not None:
                dist[val] += 1
        local_total = sum(dist.values())

        if local_total == 0:
            continue

        parts = []
        for val in sorted(global_dist.keys()):
            local_pct = 100 * dist.get(val, 0) / local_total if local_total else 0
            global_pct = 100 * global_dist[val] / global_total if global_total else 0
            delta = local_pct - global_pct
            marker = ""
            if abs(delta) > 5:
                marker = "▲" if delta > 0 else "▼"
            elif abs(delta) > 2:
                marker = "↑" if delta > 0 else "↓"
            parts.append(f"{val}={local_pct:.1f}%{marker}")

        print(f"  {score:>5} (n={n:>3}): {', '.join(parts)}")


# ==================== DELTA PIÙ SIGNIFICATIVI ====================

print(f"\n{'='*80}")
print("DELTA PIÙ SIGNIFICATIVI — Quali segnali distinguono di più ogni risultato?")
print(f"{'='*80}")

for score in TOP_SCORES[:12]:
    group = score_groups[score]
    n = len(group)
    print(f"\n  === {score} (n={n}) ===")

    deltas = []
    for sig in NUMERIC_SIGNALS:
        base_val = baseline[sig]
        if base_val is None or base_val == 0:
            continue
        vals = [s[sig] for s in group if s[sig] is not None]
        if len(vals) < 10:
            continue
        avg = statistics.mean(vals)
        delta = avg - base_val
        pct_delta = 100 * delta / abs(base_val) if base_val != 0 else 0
        deltas.append((sig, avg, delta, pct_delta, len(vals)))

    # Ordina per |pct_delta| decrescente
    deltas.sort(key=lambda x: -abs(x[3]))

    for sig, avg, delta, pct_delta, nv in deltas[:8]:
        direction = "▲" if delta > 0 else "▼"
        print(f"    {sig:<22} media={avg:>7.2f} (base {baseline[sig]:>7.2f}) "
              f"delta={delta:>+7.2f} ({pct_delta:>+6.1f}%) {direction}  [n={nv}]")


# ==================== MATRICE SCORE × SEGNALE (compact) ====================

print(f"\n{'='*80}")
print("MATRICE COMPATTA — Risultato × Top segnali discriminanti")
print(f"{'='*80}")

# Trova i segnali più discriminanti in assoluto (massima varianza tra risultati)
sig_variance = {}
for sig in NUMERIC_SIGNALS:
    if baseline[sig] is None or baseline[sig] == 0:
        continue
    avgs = []
    for score in TOP_SCORES[:10]:
        group = score_groups[score]
        vals = [s[sig] for s in group if s[sig] is not None]
        if len(vals) >= 10:
            avgs.append(statistics.mean(vals))
    if len(avgs) >= 5:
        sig_variance[sig] = statistics.variance(avgs)

top_discriminants = sorted(sig_variance.keys(), key=lambda s: -sig_variance[s])[:12]

print(f"\n{'Score':<8}", end="")
for sig in top_discriminants:
    print(f" {sig[:15]:>15}", end="")
print()
print("-" * (8 + 16 * len(top_discriminants)))

for score in TOP_SCORES[:12]:
    group = score_groups[score]
    n = len(group)
    print(f"  {score:<5}({n:>3})", end="")
    for sig in top_discriminants:
        vals = [s[sig] for s in group if s[sig] is not None]
        if vals:
            avg = statistics.mean(vals)
            delta = avg - baseline[sig]
            marker = " " if abs(delta) < abs(baseline[sig]) * 0.05 else ("+" if delta > 0 else "-")
            print(f" {avg:>7.2f}{marker:>1}({delta:>+.1f})", end="")
        else:
            print(f" {'N/A':>15}", end="")
    print()


# ==================== FOCUS: 1-0 vs 0-1 vs 1-1 vs 0-0 ====================

print(f"\n{'='*80}")
print("FOCUS — Confronto diretto: 1:0 vs 0:1 vs 1:1 vs 0:0")
print(f"{'='*80}")

focus_scores = ['1:0', '0:1', '1:1', '0:0']

print(f"\n{'Segnale':<22}", end="")
for score in focus_scores:
    print(f"  {score:>12}", end="")
print(f"  {'GLOBALE':>12}")
print("-" * 80)

for sig in NUMERIC_SIGNALS:
    base_val = baseline[sig]
    if base_val is None:
        continue

    all_available = True
    row_vals = []
    for score in focus_scores:
        group = score_groups[score]
        vals = [s[sig] for s in group if s[sig] is not None]
        if len(vals) < 10:
            all_available = False
            break
        row_vals.append(statistics.mean(vals))

    if not all_available:
        continue

    # Solo se c'è varianza significativa
    if max(row_vals) - min(row_vals) < abs(base_val) * 0.03:
        continue

    print(f"  {sig:<20}", end="")
    for val in row_vals:
        delta = val - base_val
        marker = "▲" if delta > abs(base_val) * 0.05 else ("▼" if delta < -abs(base_val) * 0.05 else " ")
        print(f"  {val:>8.2f} {marker}", end="")
    print(f"  {base_val:>8.2f}")


# ==================== RIEPILOGO ====================

print(f"\n{'='*80}")
print("RIEPILOGO")
print(f"{'='*80}")
print(f"Partite analizzate: {len(matches)}")
print(f"Risultati distinti: {len(score_groups)}")
print(f"Top 5 risultati: {', '.join(f'{s} ({len(score_groups[s])})' for s in TOP_SCORES[:5])}")
print(f"\nSegnali numerici analizzati: {len(NUMERIC_SIGNALS)}")
print(f"Segnali categorici analizzati: {len(CATEGORIC_SIGNALS)}")
print(f"\nTop segnali discriminanti (per varianza tra risultati):")
for i, sig in enumerate(top_discriminants[:8], 1):
    print(f"  {i}. {sig} (varianza: {sig_variance[sig]:.4f})")
