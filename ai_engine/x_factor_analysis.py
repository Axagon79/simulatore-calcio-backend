"""
X FACTOR - Analisi esplorativa v2
Trova pattern ricorrenti nelle partite finite in pareggio (X)
Path h2h_data corretti + nuovi segnali (DNA, Lucifero, BVS, Affidabilita, FC)
"""
import sys, os
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, current_dir)
sys.path.insert(0, project_root)
from config import db
from collections import defaultdict, Counter

print("=== ANALISI X FACTOR v2 ===")
print("Caricamento partite finite...")

all_matches = []
rounds = list(db.h2h_by_round.find({}, {"matches": 1, "league": 1}))
print(f"Round trovati: {len(rounds)}")

for r in rounds:
    league = r.get("league", "Unknown")
    for m in r.get("matches", []):
        if m.get("status") == "Finished" and m.get("real_score"):
            score = m["real_score"]
            parts = score.split(":")
            if len(parts) == 2:
                try:
                    h_goals = int(parts[0])
                    a_goals = int(parts[1])
                    m["_h_goals"] = h_goals
                    m["_a_goals"] = a_goals
                    m["_total_goals"] = h_goals + a_goals
                    m["_is_draw"] = h_goals == a_goals
                    m["_league"] = league
                    all_matches.append(m)
                except:
                    pass

total = len(all_matches)
draws = [m for m in all_matches if m["_is_draw"]]
non_draws = [m for m in all_matches if not m["_is_draw"]]
print(f"Partite totali: {total}")
print(f"Pareggi (X): {len(draws)} ({100*len(draws)/total:.1f}%)")
print(f"Non pareggi: {len(non_draws)} ({100*len(non_draws)/total:.1f}%)")
print()

# === HELPER FUNCTIONS ===

def get_odds(m, key):
    odds = m.get("odds", {})
    if isinstance(odds, dict):
        val = odds.get(key)
        if val and val != "-":
            try: return float(val)
            except: pass
    return None

def get_h2h(m, key):
    """Accede a h2h_data[key] — path corretto"""
    h2h = m.get("h2h_data")
    if not h2h or not isinstance(h2h, dict):
        return None
    val = h2h.get(key)
    if val is not None:
        try: return float(val)
        except: return val
    return None

def get_dna(m, team_key, stat):
    """Accede a h2h_data['h2h_dna']['home_dna'/'away_dna']['att'/'def'/'tec'/'val'] — PATH CORRETTO"""
    h2h = m.get("h2h_data")
    if not h2h or not isinstance(h2h, dict):
        return None
    h2h_dna = h2h.get("h2h_dna")  # LIVELLO EXTRA: h2h_dna contiene home_dna e away_dna
    if not h2h_dna or not isinstance(h2h_dna, dict):
        return None
    dna_key = f"{team_key}_dna"  # 'home_dna' o 'away_dna'
    dna = h2h_dna.get(dna_key)
    if not dna or not isinstance(dna, dict):
        return None
    val = dna.get(stat.lower())  # chiavi lowercase: att, def, tec, val
    if val is not None:
        try: return float(val)
        except: pass
    return None

def get_fc(m, key):
    """Accede a h2h_data['fattore_campo']['field_home'/'field_away'] — PATH CORRETTO"""
    h2h = m.get("h2h_data")
    if not h2h or not isinstance(h2h, dict):
        return None
    fc = h2h.get("fattore_campo")
    if fc and isinstance(fc, dict):
        val = fc.get(key)
        if val is not None:
            try: return float(val)
            except: pass
    # Fallback: path diretto h2h_data['field_home']
    val = h2h.get(key)
    if val is not None:
        try: return float(val)
        except: pass
    return None

def avg(lst):
    return sum(lst) / len(lst) if lst else 0

def compare(label, draw_vals, nondraw_vals):
    """Stampa confronto X vs non-X per un segnale"""
    if draw_vals and nondraw_vals:
        d_avg = avg(draw_vals)
        nd_avg = avg(nondraw_vals)
        delta = d_avg - nd_avg
        print(f"  {label:40s} X: {d_avg:6.2f} (n={len(draw_vals):4d})  |  non-X: {nd_avg:6.2f} (n={len(nondraw_vals):4d})  |  delta: {delta:+.2f}")

# --- DRAW RATE PER LEGA ---
print("=== DRAW RATE PER LEGA ===")
league_stats = defaultdict(lambda: {"total": 0, "draws": 0})
for m in all_matches:
    league_stats[m["_league"]]["total"] += 1
    if m["_is_draw"]:
        league_stats[m["_league"]]["draws"] += 1

sorted_leagues = sorted(league_stats.items(), key=lambda x: x[1]["draws"]/max(x[1]["total"],1), reverse=True)
for league, s in sorted_leagues:
    if s["total"] >= 10:
        pct = 100 * s["draws"] / s["total"]
        print(f'  {league:40s} {s["draws"]:3d}/{s["total"]:3d} = {pct:5.1f}%')
print()

# --- ANALISI QUOTE ---
print("=== ANALISI QUOTE ===")
x_odds_draws = [get_odds(m, "X") for m in draws if get_odds(m, "X")]
x_odds_nondraw = [get_odds(m, "X") for m in non_draws if get_odds(m, "X")]
if x_odds_draws:
    print(f"  Quota X media nelle partite finite X:     {avg(x_odds_draws):.2f} (n={len(x_odds_draws)})")
if x_odds_nondraw:
    print(f"  Quota X media nelle partite NON X:        {avg(x_odds_nondraw):.2f} (n={len(x_odds_nondraw)})")

for label, matches in [("PAREGGI", draws), ("NON PAREGGI", non_draws)]:
    diffs = []
    for m in matches:
        q1 = get_odds(m, "1")
        q2 = get_odds(m, "2")
        if q1 and q2:
            diffs.append(abs(q1 - q2))
    if diffs:
        print(f"  Diff media |Q1-Q2| in {label:12s}: {avg(diffs):.2f} (n={len(diffs)})")

print()
print("=== HIT RATE X PER FASCIA QUOTA X ===")
fascia_bins = [(0, 2.80), (2.80, 3.00), (3.00, 3.20), (3.20, 3.40), (3.40, 3.60), (3.60, 4.00), (4.00, 5.00), (5.00, 99)]
for lo, hi in fascia_bins:
    in_range = [m for m in all_matches if get_odds(m, "X") and lo <= get_odds(m, "X") < hi]
    if in_range:
        x_count = sum(1 for m in in_range if m["_is_draw"])
        pct = 100 * x_count / len(in_range)
        print(f"  Quota X {lo:.2f}-{hi:.2f}: {x_count:3d}/{len(in_range):3d} = {pct:5.1f}%")

# --- GOL MEDI ---
print()
print("=== GOL MEDI ===")
draw_goals = [m["_total_goals"] for m in draws]
nondraw_goals = [m["_total_goals"] for m in non_draws]
print(f"  Gol medi nelle X:     {avg(draw_goals):.2f}")
print(f"  Gol medi nelle non-X: {avg(nondraw_goals):.2f}")

print()
print("=== RISULTATI X PIU FREQUENTI ===")
draw_scores = Counter(m["real_score"] for m in draws)
for score, count in draw_scores.most_common(10):
    print(f"  {score}: {count} ({100*count/len(draws):.1f}%)")

# --- X vs UNDER/OVER ---
print()
print("=== X vs UNDER/OVER ===")
under25_draws = sum(1 for m in draws if m["_total_goals"] < 2.5)
under25_nondraws = sum(1 for m in non_draws if m["_total_goals"] < 2.5)
print(f"  X con Under 2.5: {under25_draws}/{len(draws)} = {100*under25_draws/len(draws):.1f}%")
print(f"  Non-X con Under 2.5: {under25_nondraws}/{len(non_draws)} = {100*under25_nondraws/len(non_draws):.1f}%")

# X + GG/NG
print()
print("=== X vs GG/NG ===")
gg_draws = sum(1 for m in draws if m["_h_goals"] > 0 and m["_a_goals"] > 0)
gg_nondraws = sum(1 for m in non_draws if m["_h_goals"] > 0 and m["_a_goals"] > 0)
print(f"  X con GG (entrambe segnano): {gg_draws}/{len(draws)} = {100*gg_draws/len(draws):.1f}%")
print(f"  Non-X con GG: {gg_nondraws}/{len(non_draws)} = {100*gg_nondraws/len(non_draws):.1f}%")

# ==============================
# NUOVI SEGNALI — PATH CORRETTI
# ==============================

# --- DNA (home_dna / away_dna) ---
print()
print("=" * 60)
print("=== DNA SQUADRE (path: h2h_data.home_dna/away_dna) ===")
print("=" * 60)

for stat in ["def", "att", "tec", "val"]:
    draw_vals = []
    nondraw_vals = []
    for m in draws:
        h = get_dna(m, "home", stat)
        a = get_dna(m, "away", stat)
        if h is not None and a is not None:
            draw_vals.append((h + a) / 2)
    for m in non_draws:
        h = get_dna(m, "home", stat)
        a = get_dna(m, "away", stat)
        if h is not None and a is not None:
            nondraw_vals.append((h + a) / 2)
    compare(f"DNA {stat.upper()} medio combinato", draw_vals, nondraw_vals)

# Differenza DNA (squadre simili = piu X?)
print()
print("=== SIMILARITA DNA (|diff home-away|) ===")
for stat in ["def", "att", "tec", "val"]:
    draw_diffs = []
    nondraw_diffs = []
    for m in draws:
        h = get_dna(m, "home", stat)
        a = get_dna(m, "away", stat)
        if h is not None and a is not None:
            draw_diffs.append(abs(h - a))
    for m in non_draws:
        h = get_dna(m, "home", stat)
        a = get_dna(m, "away", stat)
        if h is not None and a is not None:
            nondraw_diffs.append(abs(h - a))
    compare(f"|Diff DNA {stat.upper()}|", draw_diffs, nondraw_diffs)

# DNA DEF alto combinato (difese forti = meno gol = piu X?)
print()
print("=== DNA DEF ALTO (>60) — hit rate X ===")
for soglia in [50, 55, 60, 65, 70]:
    subset = [m for m in all_matches
              if get_dna(m, "home", "def") is not None and get_dna(m, "away", "def") is not None
              and (get_dna(m, "home", "def") + get_dna(m, "away", "def")) / 2 >= soglia]
    if subset:
        x_count = sum(1 for m in subset if m["_is_draw"])
        print(f"  DNA DEF medio >= {soglia}: {x_count}/{len(subset)} = {100*x_count/len(subset):.1f}% X")

# --- FATTORE CAMPO ---
print()
print("=" * 60)
print("=== FATTORE CAMPO (path: h2h_data.fattore_campo.field_home/away) ===")
print("=" * 60)

draw_fc_h = [get_fc(m, "field_home") for m in draws if get_fc(m, "field_home") is not None]
nondraw_fc_h = [get_fc(m, "field_home") for m in non_draws if get_fc(m, "field_home") is not None]
compare("Fattore campo HOME", draw_fc_h, nondraw_fc_h)

draw_fc_a = [get_fc(m, "field_away") for m in draws if get_fc(m, "field_away") is not None]
nondraw_fc_a = [get_fc(m, "field_away") for m in non_draws if get_fc(m, "field_away") is not None]
compare("Fattore campo AWAY", draw_fc_a, nondraw_fc_a)

# FC basso = meno vantaggio casa = piu X?
print()
print("=== FATTORE CAMPO BASSO — hit rate X ===")
for soglia in [2, 3, 4, 5]:
    subset = [m for m in all_matches if get_fc(m, "field_home") is not None and get_fc(m, "field_home") <= soglia]
    if subset:
        x_count = sum(1 for m in subset if m["_is_draw"])
        print(f"  FC home <= {soglia}: {x_count}/{len(subset)} = {100*x_count/len(subset):.1f}% X")

# --- LUCIFERO (FORMA RECENTE) ---
print()
print("=" * 60)
print("=== LUCIFERO / FORMA RECENTE (path: h2h_data.lucifero_home/away, scala 0-25) ===")
print("=" * 60)

draw_luc_h = [get_h2h(m, "lucifero_home") for m in draws if get_h2h(m, "lucifero_home") is not None]
nondraw_luc_h = [get_h2h(m, "lucifero_home") for m in non_draws if get_h2h(m, "lucifero_home") is not None]
compare("Lucifero HOME", draw_luc_h, nondraw_luc_h)

draw_luc_a = [get_h2h(m, "lucifero_away") for m in draws if get_h2h(m, "lucifero_away") is not None]
nondraw_luc_a = [get_h2h(m, "lucifero_away") for m in non_draws if get_h2h(m, "lucifero_away") is not None]
compare("Lucifero AWAY", draw_luc_a, nondraw_luc_a)

# Similarita forma (entrambe in forma simile = piu X?)
print()
print("=== SIMILARITA FORMA (|Lucifero home - away|) ===")
draw_luc_diff = []
nondraw_luc_diff = []
for m in draws:
    h = get_h2h(m, "lucifero_home")
    a = get_h2h(m, "lucifero_away")
    if h is not None and a is not None:
        draw_luc_diff.append(abs(h - a))
for m in non_draws:
    h = get_h2h(m, "lucifero_home")
    a = get_h2h(m, "lucifero_away")
    if h is not None and a is not None:
        nondraw_luc_diff.append(abs(h - a))
compare("|Diff Lucifero|", draw_luc_diff, nondraw_luc_diff)

# Fascia forma simile — hit rate X
print()
print("=== FORMA SIMILE — hit rate X ===")
for soglia in [2, 3, 4, 5, 7, 10]:
    subset = [m for m in all_matches
              if get_h2h(m, "lucifero_home") is not None and get_h2h(m, "lucifero_away") is not None
              and abs(get_h2h(m, "lucifero_home") - get_h2h(m, "lucifero_away")) <= soglia]
    if subset:
        x_count = sum(1 for m in subset if m["_is_draw"])
        print(f"  |Diff Lucifero| <= {soglia}: {x_count}/{len(subset)} = {100*x_count/len(subset):.1f}% X")

# --- BVS (BET VALUE SCORE) ---
print()
print("=" * 60)
print("=== BVS — BET VALUE SCORE (path: h2h_data.bvs_match_index, scala -6 a +7) ===")
print("=" * 60)

draw_bvs = [get_h2h(m, "bvs_match_index") for m in draws if get_h2h(m, "bvs_match_index") is not None]
nondraw_bvs = [get_h2h(m, "bvs_match_index") for m in non_draws if get_h2h(m, "bvs_match_index") is not None]
compare("BVS match index", draw_bvs, nondraw_bvs)

# BVS per fascia — hit rate X
print()
print("=== BVS PER FASCIA — hit rate X ===")
bvs_bins = [(-7, -3), (-3, -1), (-1, 1), (1, 3), (3, 8)]
for lo, hi in bvs_bins:
    subset = [m for m in all_matches if get_h2h(m, "bvs_match_index") is not None
              and lo <= get_h2h(m, "bvs_match_index") < hi]
    if subset:
        x_count = sum(1 for m in subset if m["_is_draw"])
        print(f"  BVS [{lo:+d}, {hi:+d}): {x_count}/{len(subset)} = {100*x_count/len(subset):.1f}% X")

# Classification
print()
print("=== CLASSIFICATION — hit rate X ===")
for cls in ["PURO", "SEMI", "NON_BVS"]:
    h2h_cls = [m for m in all_matches
               if m.get("h2h_data", {}).get("classification") == cls]
    if h2h_cls:
        x_count = sum(1 for m in h2h_cls if m["_is_draw"])
        print(f"  {cls:10s}: {x_count}/{len(h2h_cls)} = {100*x_count/len(h2h_cls):.1f}% X")

# --- AFFIDABILITA ---
print()
print("=" * 60)
print("=== AFFIDABILITA (path: h2h_data.affidabilita_casa/trasferta, scala 0-10) ===")
print("=" * 60)

def get_affidabilita(m, key):
    """Accede a h2h_data['affidabilità']['affidabilità_casa/trasferta'] — PATH CORRETTO"""
    h2h = m.get("h2h_data")
    if not h2h or not isinstance(h2h, dict):
        return None
    aff = h2h.get("affidabilità")
    if not aff or not isinstance(aff, dict):
        return None
    val = aff.get(key)
    if val is not None:
        try: return float(val)
        except: pass
    return None

for field_name, label in [("affidabilità_casa", "Affidabilita CASA"), ("affidabilità_trasferta", "Affidabilita TRASFERTA")]:
    draw_aff = [get_affidabilita(m, field_name) for m in draws if get_affidabilita(m, field_name) is not None]
    nondraw_aff = [get_affidabilita(m, field_name) for m in non_draws if get_affidabilita(m, field_name) is not None]
    compare(label, draw_aff, nondraw_aff)

# Trust letter
print()
print("=== TRUST LETTER — hit rate X ===")
for letter in ["A", "B", "C", "D"]:
    for side in ["home", "away"]:
        key = f"trust_{side}_letter"
        subset = [m for m in all_matches if m.get("h2h_data", {}).get(key) == letter]
        if subset:
            x_count = sum(1 for m in subset if m["_is_draw"])
            print(f"  Trust {side:5s} = {letter}: {x_count}/{len(subset)} = {100*x_count/len(subset):.1f}% X")

# --- H2H STORICO ---
print()
print("=" * 60)
print("=== H2H STORICO (path: h2h_data.home_score/away_score/total_matches/avg_total_goals) ===")
print("=" * 60)

# H2H score medio
draw_h2h_home = [get_h2h(m, "home_score") for m in draws if get_h2h(m, "home_score") is not None]
nondraw_h2h_home = [get_h2h(m, "home_score") for m in non_draws if get_h2h(m, "home_score") is not None]
compare("H2H home_score", draw_h2h_home, nondraw_h2h_home)

draw_h2h_away = [get_h2h(m, "away_score") for m in draws if get_h2h(m, "away_score") is not None]
nondraw_h2h_away = [get_h2h(m, "away_score") for m in non_draws if get_h2h(m, "away_score") is not None]
compare("H2H away_score", draw_h2h_away, nondraw_h2h_away)

# Differenza H2H score (simili = piu X?)
print()
print("=== DIFFERENZA H2H SCORE ===")
draw_h2h_diff = []
nondraw_h2h_diff = []
for m in draws:
    hs = get_h2h(m, "home_score")
    aws = get_h2h(m, "away_score")
    if hs is not None and aws is not None:
        draw_h2h_diff.append(abs(hs - aws))
for m in non_draws:
    hs = get_h2h(m, "home_score")
    aws = get_h2h(m, "away_score")
    if hs is not None and aws is not None:
        nondraw_h2h_diff.append(abs(hs - aws))
compare("|H2H home_score - away_score|", draw_h2h_diff, nondraw_h2h_diff)

# H2H gol medi storici
draw_h2h_goals = [get_h2h(m, "avg_total_goals") for m in draws if get_h2h(m, "avg_total_goals") is not None]
nondraw_h2h_goals = [get_h2h(m, "avg_total_goals") for m in non_draws if get_h2h(m, "avg_total_goals") is not None]
compare("H2H avg_total_goals storico", draw_h2h_goals, nondraw_h2h_goals)

# Total matches (piu partite = H2H piu affidabile)
draw_total = [get_h2h(m, "total_matches") for m in draws if get_h2h(m, "total_matches") is not None]
nondraw_total = [get_h2h(m, "total_matches") for m in non_draws if get_h2h(m, "total_matches") is not None]
compare("H2H total_matches", draw_total, nondraw_total)

# --- H2H RANK ---
print()
print("=== RANK IN CLASSIFICA ===")
draw_rank_diff = []
nondraw_rank_diff = []
for m in draws:
    hr = get_h2h(m, "home_rank")
    ar = get_h2h(m, "away_rank")
    if hr is not None and ar is not None:
        draw_rank_diff.append(abs(hr - ar))
for m in non_draws:
    hr = get_h2h(m, "home_rank")
    ar = get_h2h(m, "away_rank")
    if hr is not None and ar is not None:
        nondraw_rank_diff.append(abs(hr - ar))
compare("|Diff classifica home-away|", draw_rank_diff, nondraw_rank_diff)

# Fascia diff classifica — hit rate X
print()
print("=== DIFF CLASSIFICA — hit rate X ===")
for soglia in [2, 3, 5, 8, 10]:
    subset = [m for m in all_matches
              if get_h2h(m, "home_rank") is not None and get_h2h(m, "away_rank") is not None
              and abs(get_h2h(m, "home_rank") - get_h2h(m, "away_rank")) <= soglia]
    if subset:
        x_count = sum(1 for m in subset if m["_is_draw"])
        print(f"  |Diff rank| <= {soglia}: {x_count}/{len(subset)} = {100*x_count/len(subset):.1f}% X")

# ==============================
# COMBINAZIONI SEGNALI AGGIORNATE
# ==============================
print()
print("=" * 60)
print("=== COMBINAZIONI SEGNALI (hit rate X) — AGGIORNATO ===")
print("=" * 60)

def check_signals_v2(m):
    signals = {}
    # 1. Quota X bassa
    qx = get_odds(m, "X")
    signals["quota_x_bassa"] = qx is not None and qx < 3.30
    # 2. Quote equilibrate
    q1 = get_odds(m, "1")
    q2 = get_odds(m, "2")
    signals["quote_equilibrate"] = q1 is not None and q2 is not None and abs(q1 - q2) < 0.50
    # 3. Under favorito (quota over alta)
    qu = get_odds(m, "over_25")
    signals["under_favorito"] = qu is not None and qu > 2.00
    # 4. DNA difensivo simile
    h_def = get_dna(m, "home", "def")
    a_def = get_dna(m, "away", "def")
    signals["dna_def_simile"] = h_def is not None and a_def is not None and abs(h_def - a_def) < 15
    # 5. DNA DEF alto (difese forti)
    signals["dna_def_alto"] = h_def is not None and a_def is not None and (h_def + a_def) / 2 >= 60
    # 6. Fattore campo basso
    fc_h = get_fc(m, "field_home")
    signals["fc_basso"] = fc_h is not None and fc_h <= 3
    # 7. Forma simile (Lucifero)
    luc_h = get_h2h(m, "lucifero_home")
    luc_a = get_h2h(m, "lucifero_away")
    signals["forma_simile"] = luc_h is not None and luc_a is not None and abs(luc_h - luc_a) <= 4
    # 8. Classifica vicina
    hr = get_h2h(m, "home_rank")
    ar = get_h2h(m, "away_rank")
    signals["rank_vicini"] = hr is not None and ar is not None and abs(hr - ar) <= 5
    # 9. Draw league alta (>30%)
    league = m.get("_league", "")
    l_stats = league_stats.get(league, {"total": 0, "draws": 0})
    dr = l_stats["draws"] / max(l_stats["total"], 1)
    signals["lega_alta_x"] = dr >= 0.30
    return signals

combos = defaultdict(lambda: {"total": 0, "draws": 0})
for m in all_matches:
    sigs = check_signals_v2(m)
    n_active = sum(1 for v in sigs.values() if v)

    # Singoli segnali
    for k, v in sigs.items():
        if v:
            combos[k]["total"] += 1
            if m["_is_draw"]:
                combos[k]["draws"] += 1

    # Numero segnali attivi
    key = f"{n_active}_segnali"
    combos[key]["total"] += 1
    if m["_is_draw"]:
        combos[key]["draws"] += 1

print("  Singoli segnali:")
signal_names = ["quota_x_bassa", "quote_equilibrate", "under_favorito", "dna_def_simile",
                "dna_def_alto", "fc_basso", "forma_simile", "rank_vicini", "lega_alta_x"]
for k in signal_names:
    s = combos[k]
    if s["total"] > 0:
        pct = 100 * s["draws"] / s["total"]
        base_delta = pct - (100 * len(draws) / total)
        print(f"    {k:25s}: {s['draws']:4d}/{s['total']:4d} = {pct:5.1f}%  (delta: {base_delta:+.1f}%)")

print()
print("  Per numero segnali attivi:")
for i in range(10):
    key = f"{i}_segnali"
    s = combos[key]
    if s["total"] > 0:
        pct = 100 * s["draws"] / s["total"]
        print(f"    {i} segnali: {s['draws']:4d}/{s['total']:4d} = {pct:5.1f}%")

# --- TOP COMBINAZIONI DI 2 SEGNALI ---
print()
print("=== TOP COMBINAZIONI DI 2 SEGNALI ===")
from itertools import combinations
combo2_stats = {}
for m in all_matches:
    sigs = check_signals_v2(m)
    active = [k for k, v in sigs.items() if v]
    for c in combinations(sorted(active), 2):
        if c not in combo2_stats:
            combo2_stats[c] = {"total": 0, "draws": 0}
        combo2_stats[c]["total"] += 1
        if m["_is_draw"]:
            combo2_stats[c]["draws"] += 1

sorted_combos = sorted(combo2_stats.items(), key=lambda x: x[1]["draws"]/max(x[1]["total"],1), reverse=True)
print("  Top 15 coppie per hit rate X (min 30 partite):")
shown = 0
for combo, s in sorted_combos:
    if s["total"] >= 30:
        pct = 100 * s["draws"] / s["total"]
        print(f"    {combo[0]:25s} + {combo[1]:25s}: {s['draws']:3d}/{s['total']:3d} = {pct:5.1f}%")
        shown += 1
        if shown >= 15:
            break

# --- CONTEGGIO DISPONIBILITA DATI ---
print()
print("=" * 60)
print("=== DISPONIBILITA DATI ===")
print("=" * 60)
fields = [
    ("odds.X (NowGoal)", lambda m: get_odds(m, "X") is not None),
    ("odds.1 + odds.2", lambda m: get_odds(m, "1") is not None and get_odds(m, "2") is not None),
    ("odds.over_25 (SNAI)", lambda m: get_odds(m, "over_25") is not None),
    ("odds.gg (SNAI)", lambda m: get_odds(m, "gg") is not None),
    ("h2h_dna.home_dna.def", lambda m: get_dna(m, "home", "def") is not None),
    ("h2h_dna.away_dna.def", lambda m: get_dna(m, "away", "def") is not None),
    ("fattore_campo.field_home", lambda m: get_fc(m, "field_home") is not None),
    ("lucifero_home", lambda m: get_h2h(m, "lucifero_home") is not None),
    ("lucifero_away", lambda m: get_h2h(m, "lucifero_away") is not None),
    ("bvs_match_index", lambda m: get_h2h(m, "bvs_match_index") is not None),
    ("classification", lambda m: m.get("h2h_data", {}).get("classification") is not None),
    ("affidabilità.casa (nested)", lambda m: get_affidabilita(m, "affidabilità_casa") is not None),
    ("affidabilità.trasferta", lambda m: get_affidabilita(m, "affidabilità_trasferta") is not None),
    ("home_score (H2H)", lambda m: get_h2h(m, "home_score") is not None),
    ("avg_total_goals (H2H)", lambda m: get_h2h(m, "avg_total_goals") is not None),
    ("home_rank", lambda m: get_h2h(m, "home_rank") is not None),
    ("total_matches (H2H)", lambda m: get_h2h(m, "total_matches") is not None),
]
for name, check in fields:
    count = sum(1 for m in all_matches if check(m))
    pct = 100 * count / total
    print(f"  {name:30s}: {count:4d}/{total} = {pct:5.1f}%")

print()
print("=== ANALISI X FACTOR v2 COMPLETATA ===")
