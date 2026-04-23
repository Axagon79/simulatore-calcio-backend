"""Cerca pattern PURI tra i 122 tip aggiunti dal -3h su partite NO BET al mattino."""
import os, sys
from collections import defaultdict
from itertools import combinations

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from snapshot_pronostici import fetch_results
from analizza_impatto_aggiornamenti import (
    load_snap, index_tips_by_match, tip_key, score_for_match, compute_pl
)

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report")


def quota_bucket(q):
    if q is None or q <= 1: return 'N/A'
    if q < 1.30: return '1.00-1.29'
    if q < 1.50: return '1.30-1.49'
    if q < 1.70: return '1.50-1.69'
    if q < 1.90: return '1.70-1.89'
    if q < 2.20: return '1.90-2.19'
    if q < 2.50: return '2.20-2.49'
    if q < 3.00: return '2.50-2.99'
    return '3.00+'


def stars_bucket(s):
    if s is None: return 'N/A'
    if s < 2.5: return '<2.5'
    if s < 3.0: return '2.5-2.9'
    if s < 3.5: return '3.0-3.4'
    if s < 4.0: return '3.5-3.9'
    return '≥4.0'


def collect(dates):
    rows = []
    for date in dates:
        m = load_snap(date, 'mattino')
        i = load_snap(date, 'intermedio')
        if not m or not i: continue
        results = fetch_results(date)
        if not results: continue
        m_by = index_tips_by_match(m)
        i_by = index_tips_by_match(i)
        for mk, i_tips in i_by.items():
            if m_by.get(mk): continue  # partita aveva già tip al mattino
            for match, tip in i_tips:
                score = score_for_match(results, match['home'], match['away'])
                pl, hit = compute_pl(match, tip, score)
                if pl is None: continue
                rows.append({
                    'tipo': tip.get('tipo'),
                    'pronostico': tip.get('pronostico'),
                    'quota': tip.get('quota'),
                    'stars': tip.get('stars'),
                    'source': tip.get('source') or '?',
                    'elite': bool(tip.get('elite')),
                    'mixer': bool(tip.get('mixer')),
                    'low_value': bool(tip.get('low_value')),
                    'hit': hit,
                    'pl': pl,
                })
    return rows


def features(r):
    return {
        'tipo': r['tipo'],
        'pron': f"{r['tipo']}_{r['pronostico']}",
        'quota': quota_bucket(r.get('quota')),
        'stars': stars_bucket(r.get('stars')),
        'source': r['source'],
        'elite': 'Elite' if r['elite'] else 'noElite',
        'mixer': 'Mixer' if r['mixer'] else 'noMixer',
        'lowv': 'Low' if r['low_value'] else 'noLow',
    }


def main():
    from datetime import datetime
    today = datetime.now().strftime('%Y-%m-%d')
    dates = sorted(d for d in os.listdir(REPORT_DIR) if len(d) == 10 and d[4] == '-' and d < today)
    rows = collect(dates)

    for r in rows:
        r['feat'] = features(r)

    n_tot = len(rows)
    n_win = sum(1 for r in rows if r['hit'])
    pl_tot = sum(r['pl'] for r in rows)
    print(f"Totale tip aggiunti dal -3h su partite NO BET: {n_tot}")
    print(f"Vincenti: {n_win} ({n_win/n_tot*100:.1f}%)  PL: {pl_tot:+.2f}u\n")

    fkeys = list(features(rows[0]).keys())

    # Cerco pattern puri: min 6 tip, %Win >= 65%, PL > 0
    for ncomb in (1, 2, 3):
        print(f"\n{'=' * 76}")
        print(f"  COMBINAZIONI DI {ncomb} FEATURE — pattern puri (min 6 tip, %Win ≥65%, PL>0)")
        print(f"{'=' * 76}")
        segments = defaultdict(list)
        for r in rows:
            for combo in combinations(fkeys, ncomb):
                key = tuple((k, r['feat'][k]) for k in combo)
                segments[key].append(r)
        items = []
        for key, rs in segments.items():
            n = len(rs)
            if n < 6: continue
            w = sum(1 for r in rs if r['hit'])
            pct = w / n * 100
            pl = sum(r['pl'] for r in rs)
            if pct < 65 or pl <= 0: continue
            items.append((key, n, w, pct, pl))
        items.sort(key=lambda x: -x[4])
        if not items:
            print("  (nessun pattern)")
            continue
        print(f"\n  {'Pattern':<56} {'N':>3} {'W':>3} {'%W':>5} {'PL':>8}")
        for key, n, w, pct, pl in items[:20]:
            label = " & ".join(f"{k}={v}" for k, v in key)
            print(f"  {label[:56]:<56} {n:>3} {w:>3} {pct:>4.1f}% {pl:>+7.2f}u")


if __name__ == '__main__':
    main()
