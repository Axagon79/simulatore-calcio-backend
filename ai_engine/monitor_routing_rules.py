"""
MONITOR REGOLE ORCHESTRATORE
=============================
Analisi completa dell'impatto di ogni regola di routing su tutto lo storico.
Per ogni regola confronta: P/L attuale vs P/L che si sarebbe ottenuto
senza la trasformazione (controfattuale).

Uso: python ai_engine/monitor_routing_rules.py [--date 2026-04-04] [--from 2026-03-01] [--to 2026-04-04]
"""
import sys, os, argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from config import db


# =====================================================
# CHECK HIT
# =====================================================
def check_hit(pronostico, h, a):
    p = pronostico.strip()
    total = h + a
    MAP = {
        '1': h > a, 'X': h == a, '2': h < a,
        '1X': h >= a, 'X2': h <= a, '12': h != a,
        'Over 0.5': total > 0, 'Over 1.5': total > 1,
        'Over 2.5': total > 2, 'Over 3.5': total > 3,
        'Under 0.5': total < 1, 'Under 1.5': total < 2,
        'Under 2.5': total < 3, 'Under 3.5': total < 4,
        'Goal': h > 0 and a > 0, 'GG': h > 0 and a > 0,
        'NoGoal': h == 0 or a == 0, 'NG': h == 0 or a == 0,
        'MG 2-3': 2 <= total <= 3, 'MG 2-4': 2 <= total <= 4,
        'MG 3-5': 3 <= total <= 5,
    }
    return MAP.get(p)


def calc_pl(hit, quota, stake):
    if hit:
        return round(stake * (quota - 1), 2)
    return round(-stake, 2)


# =====================================================
# CARICA RISULTATI
# =====================================================
def load_results(date_from, date_to):
    """Carica tutti i risultati da h2h_by_round nel range."""
    results = {}
    for h2h_doc in db.h2h_by_round.find({}, {'matches': 1}):
        for m in h2h_doc.get('matches', []):
            date_val = str(m.get('date_obj', ''))[:10]
            if date_val < date_from or date_val > date_to:
                continue
            score = m.get('real_score', '')
            if score and ':' in score:
                try:
                    hg, ag = int(score.split(':')[0]), int(score.split(':')[1])
                    key = f"{date_val}_{m['home']}_vs_{m['away']}"
                    results[key] = (hg, ag)
                except (ValueError, KeyError):
                    pass
    return results


# =====================================================
# REGOLE BASE (nessuna trasformazione effettiva)
# =====================================================
BASE_RULES = {'single', 'consensus_both', 'priority_chain', 'union', 'multigol_v6'}
BASE_PREFIXES = ('home_win_combo_', 'x_draw_combo_', 'diamond_pattern_')
CAP_RULES = {'se2_s9_f180_cap6', 'segno_s7_weak_q_cap5', 'gol_s8_q150_cap6'}


def is_base_rule(rule):
    if rule in BASE_RULES or rule in CAP_RULES or rule == 'none' or rule == '':
        return True
    return any(rule.startswith(px) for px in BASE_PREFIXES)


# =====================================================
# ANALISI PRINCIPALE
# =====================================================
def analyze(date_from, date_to):
    print("=" * 80)
    print(f"MONITOR REGOLE ORCHESTRATORE — {date_from} → {date_to}")
    print("=" * 80)

    # Carica risultati
    print("\nCaricamento risultati...")
    results_map = load_results(date_from, date_to)
    print(f"Risultati trovati: {len(results_map)}")

    # Carica pronostici unified
    query = {}
    if date_from == date_to:
        query['date'] = date_from
    else:
        query['date'] = {'$gte': date_from, '$lte': date_to}

    docs = list(db.daily_predictions_unified.find(
        query, {'home': 1, 'away': 1, 'date': 1, 'pronostici': 1}
    ))
    print(f"Documenti unified: {len(docs)}")

    # Struttura per raccogliere stats
    rule_stats = {}  # rule -> {hit, miss, pl, orig_hit, orig_miss, orig_pl, nobet_would_hit, nobet_would_miss, examples_bad, examples_good}

    for doc in docs:
        date = doc['date']
        home = doc['home']
        away = doc['away']
        key = f"{date}_{home}_vs_{away}"

        if key not in results_map:
            continue
        hg, ag = results_map[key]

        for p in doc.get('pronostici', []):
            rule = p.get('routing_rule', 'none') or 'none'
            pr = p.get('pronostico', '')
            quota = p.get('quota', 0) or 0
            stake = p.get('stake', 0) or 0
            orig_pr = p.get('original_pronostico', '')
            orig_q = p.get('original_quota', 0) or 0

            if rule not in rule_stats:
                rule_stats[rule] = {
                    'hit': 0, 'miss': 0, 'pl': 0,
                    'orig_hit': 0, 'orig_miss': 0, 'orig_pl': 0,
                    'nobet_would_hit': 0, 'nobet_would_miss': 0, 'nobet_orig_pl': 0,
                    'same_result': 0, 'saved': 0, 'damaged': 0,
                    'quota_diff_sum': 0, 'quota_diff_count': 0,
                    'examples_saved': [], 'examples_damaged': [],
                }

            stats = rule_stats[rule]

            # NO BET
            if pr == 'NO BET':
                if orig_pr:
                    orig_hit = check_hit(orig_pr, hg, ag)
                    if orig_hit is True:
                        stats['nobet_would_hit'] += 1
                        if orig_q > 0:
                            stats['nobet_orig_pl'] += calc_pl(True, orig_q, stake)
                    elif orig_hit is False:
                        stats['nobet_would_miss'] += 1
                        if stake > 0:
                            stats['nobet_orig_pl'] += calc_pl(False, orig_q, stake)
                continue

            hit = check_hit(pr, hg, ag)
            if hit is None:
                continue

            pl = calc_pl(hit, quota, stake)

            if hit:
                stats['hit'] += 1
            else:
                stats['miss'] += 1
            stats['pl'] += pl

            # Controfattuale (solo se c'è un originale diverso)
            if orig_pr and orig_pr != pr and orig_pr != '?':
                orig_hit = check_hit(orig_pr, hg, ag)
                if orig_hit is not None:
                    use_q = orig_q if orig_q > 0 else quota
                    orig_pl = calc_pl(orig_hit, use_q, stake)
                    if orig_hit:
                        stats['orig_hit'] += 1
                    else:
                        stats['orig_miss'] += 1
                    stats['orig_pl'] += orig_pl

                    delta = pl - orig_pl
                    if hit == orig_hit:
                        stats['same_result'] += 1
                        # Entrambi centrati o entrambi mancati: guarda differenza quota
                        if hit and orig_q > 0:
                            stats['quota_diff_sum'] += (quota - orig_q)
                            stats['quota_diff_count'] += 1
                    elif hit and not orig_hit:
                        stats['saved'] += 1
                        if len(stats['examples_saved']) < 3:
                            stats['examples_saved'].append(
                                f"{date} {home} vs {away}: {orig_pr}@{orig_q:.2f}(X) → {pr}@{quota:.2f}(V) Δ={delta:+.2f}u"
                            )
                    elif not hit and orig_hit:
                        stats['damaged'] += 1
                        if len(stats['examples_damaged']) < 3:
                            stats['examples_damaged'].append(
                                f"{date} {home} vs {away}: {orig_pr}@{orig_q:.2f}(V) → {pr}@{quota:.2f}(X) Δ={delta:+.2f}u"
                            )

    # =====================================================
    # STAMPA RISULTATI
    # =====================================================

    # Separa base da ottimizzati
    base_rules = {r: s for r, s in rule_stats.items() if is_base_rule(r)}
    opt_rules = {r: s for r, s in rule_stats.items() if not is_base_rule(r)}

    # Totali
    tot_hit = sum(s['hit'] for s in rule_stats.values())
    tot_miss = sum(s['miss'] for s in rule_stats.values())
    tot_pl = sum(s['pl'] for s in rule_stats.values())
    base_hit = sum(s['hit'] for s in base_rules.values())
    base_miss = sum(s['miss'] for s in base_rules.values())
    base_pl = sum(s['pl'] for s in base_rules.values())
    opt_hit = sum(s['hit'] for s in opt_rules.values())
    opt_miss = sum(s['miss'] for s in opt_rules.values())
    opt_pl = sum(s['pl'] for s in opt_rules.values())

    print(f"\n{'='*80}")
    print("RIEPILOGO GENERALE")
    print(f"{'='*80}")
    if tot_hit + tot_miss > 0:
        print(f"Totale:       {tot_hit}/{tot_hit+tot_miss} ({tot_hit/(tot_hit+tot_miss)*100:.1f}%) P/L: {tot_pl:+.2f}u")
    if base_hit + base_miss > 0:
        print(f"Base:         {base_hit}/{base_hit+base_miss} ({base_hit/(base_hit+base_miss)*100:.1f}%) P/L: {base_pl:+.2f}u")
    if opt_hit + opt_miss > 0:
        print(f"Trasformati:  {opt_hit}/{opt_hit+opt_miss} ({opt_hit/(opt_hit+opt_miss)*100:.1f}%) P/L: {opt_pl:+.2f}u")

    # Delta controfattuale globale
    opt_orig_pl = sum(s['orig_pl'] for s in opt_rules.values())
    opt_saved = sum(s['saved'] for s in opt_rules.values())
    opt_damaged = sum(s['damaged'] for s in opt_rules.values())
    opt_same = sum(s['same_result'] for s in opt_rules.values())

    print(f"\n--- CONTROFATTUALE (solo trasformati con originale diverso) ---")
    print(f"P/L attuale:    {opt_pl:+.2f}u")
    print(f"P/L originale:  {opt_orig_pl:+.2f}u")
    print(f"Delta:          {opt_pl - opt_orig_pl:+.2f}u")
    print(f"Salvati (orig mancava, nuovo centra): {opt_saved}")
    print(f"Danneggiati (orig centrava, nuovo manca): {opt_damaged}")
    print(f"Stesso risultato: {opt_same}")

    # NO BET impact
    tot_nb_hit = sum(s['nobet_would_hit'] for s in rule_stats.values())
    tot_nb_miss = sum(s['nobet_would_miss'] for s in rule_stats.values())
    tot_nb_orig_pl = sum(s['nobet_orig_pl'] for s in rule_stats.values())
    if tot_nb_hit + tot_nb_miss > 0:
        print(f"\n--- NO BET FILTRATI ---")
        print(f"Avrebbero centrato: {tot_nb_hit}")
        print(f"Avrebbero mancato: {tot_nb_miss}")
        print(f"P/L perso dai filtri: {tot_nb_orig_pl:+.2f}u")

    # Dettaglio per regola ottimizzata
    print(f"\n{'='*80}")
    print("DETTAGLIO PER REGOLA OTTIMIZZATA")
    print(f"{'='*80}")
    print(f"{'Regola':35s} {'HR':>10s} {'P/L':>8s} {'Δ CF':>8s} {'Salv':>5s} {'Dann':>5s} {'=':>5s} {'ΔQ med':>8s} {'VERD.':>8s}")
    print("-" * 100)

    for rule, s in sorted(opt_rules.items(), key=lambda x: x[1]['pl'] - x[1]['orig_pl'] if x[1]['orig_pl'] != 0 else x[1]['pl']):
        tot = s['hit'] + s['miss']
        if tot == 0:
            continue
        hr = f"{s['hit']}/{tot} ({s['hit']/tot*100:.0f}%)"
        delta_cf = s['pl'] - s['orig_pl'] if s['orig_pl'] != 0 else 0
        avg_q_diff = s['quota_diff_sum'] / s['quota_diff_count'] if s['quota_diff_count'] > 0 else 0

        # Verdetto
        if delta_cf > 5:
            verdict = '✅ TOP'
        elif delta_cf > 0:
            verdict = '✅ OK'
        elif delta_cf > -2:
            verdict = '⚠️ ~'
        elif delta_cf > -10:
            verdict = '❌ MALE'
        else:
            verdict = '🚨 GRAVE'

        # Se non ci sono dati controfattuali, verdetto neutro
        if s['orig_pl'] == 0 and s['saved'] == 0 and s['damaged'] == 0:
            verdict = '— N/D'

        print(f"{rule:35s} {hr:>10s} {s['pl']:>+8.2f} {delta_cf:>+8.2f} {s['saved']:>5d} {s['damaged']:>5d} {s['same_result']:>5d} {avg_q_diff:>+8.2f} {verdict:>8s}")

    # Dettaglio NO BET per regola
    print(f"\n{'='*80}")
    print("DETTAGLIO FILTRI NO BET")
    print(f"{'='*80}")
    print(f"{'Regola':35s} {'Centr.':>7s} {'Manc.':>7s} {'P/L perso':>10s} {'VERD.':>8s}")
    print("-" * 75)
    for rule, s in sorted(opt_rules.items(), key=lambda x: x[1]['nobet_orig_pl']):
        nb_tot = s['nobet_would_hit'] + s['nobet_would_miss']
        if nb_tot == 0:
            continue
        nb_hr = s['nobet_would_hit'] / nb_tot * 100
        # Verdetto NO BET: se più della metà avrebbe centrato, è un filtro troppo aggressivo
        if nb_hr > 70:
            verdict = '🚨 TROPPO'
        elif nb_hr > 50:
            verdict = '⚠️ AGGR.'
        else:
            verdict = '✅ OK'
        print(f"{rule:35s} {s['nobet_would_hit']:>7d} {s['nobet_would_miss']:>7d} {s['nobet_orig_pl']:>+10.2f} {verdict:>8s}")

    # Esempi peggiori
    all_damaged = []
    all_saved = []
    for rule, s in opt_rules.items():
        all_damaged.extend(s['examples_damaged'])
        all_saved.extend(s['examples_saved'])

    if all_damaged:
        print(f"\n{'='*80}")
        print(f"ESEMPI DANNEGGIATI (max 10)")
        print(f"{'='*80}")
        for ex in all_damaged[:10]:
            print(f"  {ex}")

    if all_saved:
        print(f"\n{'='*80}")
        print(f"ESEMPI SALVATI (max 10)")
        print(f"{'='*80}")
        for ex in all_saved[:10]:
            print(f"  {ex}")


def main():
    parser = argparse.ArgumentParser(description='Monitor regole orchestratore')
    parser.add_argument('--date', help='Analizza singola data (YYYY-MM-DD)')
    parser.add_argument('--from', dest='date_from', help='Data inizio (YYYY-MM-DD)')
    parser.add_argument('--to', dest='date_to', help='Data fine (YYYY-MM-DD)')
    parser.add_argument('--last', type=int, help='Ultimi N giorni')
    args = parser.parse_args()

    if args.date:
        date_from = date_to = args.date
    elif args.date_from and args.date_to:
        date_from = args.date_from
        date_to = args.date_to
    elif args.last:
        date_to = datetime.now().strftime('%Y-%m-%d')
        date_from = (datetime.now() - timedelta(days=args.last)).strftime('%Y-%m-%d')
    else:
        # Default: tutto lo storico
        date_from = '2026-01-01'
        date_to = datetime.now().strftime('%Y-%m-%d')

    analyze(date_from, date_to)


if __name__ == '__main__':
    main()
