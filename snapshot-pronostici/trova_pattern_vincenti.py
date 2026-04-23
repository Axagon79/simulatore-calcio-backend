"""
Cerca pattern PURI tra i 250 tip tolti: segmenti con ALTA % di vincenti.
Prova combinazioni a 2 e 3 dimensioni per trovare pattern forti.
"""
import os, sys
from collections import defaultdict
from itertools import combinations

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analizza_protezione_tolti import collect_tolti, quota_bucket, stars_bucket

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report")


def features(t):
    """Ritorna un dict di feature categoriche per il tip."""
    return {
        'tipo': t['tipo'],
        'pron': f"{t['tipo']}_{t['pronostico']}",
        'quota': quota_bucket(t.get('quota')),
        'stars': stars_bucket(t.get('stars')),
        'source': t['source'],
        'elite': 'Elite' if t['elite'] else 'noElite',
        'mixer': 'Mixer' if t['mixer'] else 'noMixer',
        'lowv': 'Low' if t['low_value'] else 'noLow',
        'origine': 'matt' if t['origine_svuota'] else 'fix3h',
    }


def main():
    from datetime import datetime
    today = datetime.now().strftime('%Y-%m-%d')
    dates = sorted(d for d in os.listdir(REPORT_DIR)
                   if len(d) == 10 and d[4] == '-' and d < today)

    rows = collect_tolti(dates)
    n_tot = len(rows)
    n_win = sum(1 for r in rows if r['hit'])
    print(f"Totale tolti: {n_tot} | Vincenti: {n_win} ({n_win/n_tot*100:.1f}%)\n")

    # Arricchisci ogni row con le feature
    for r in rows:
        r['feat'] = features(r)

    feat_keys = list(features(rows[0]).keys())

    # Analisi combinazioni 1, 2, 3 feature
    for ncomb in (1, 2, 3):
        print(f"\n{'='*78}")
        print(f"  COMBINAZIONI DI {ncomb} FEATURE")
        print(f"{'='*78}")
        all_segments = defaultdict(list)
        for r in rows:
            for combo in combinations(feat_keys, ncomb):
                key = tuple((k, r['feat'][k]) for k in combo)
                all_segments[key].append(r)

        # Filtra: min 8 tip, purezza ≥ 65%
        rows_out = []
        for key, rs in all_segments.items():
            n = len(rs)
            if n < 8:
                continue
            w = sum(1 for r in rs if r['hit'])
            pct = w / n * 100
            if pct < 65:
                continue
            pl_win = sum(r['pl'] for r in rs if r['hit'])
            pl_loss = sum(r['pl'] for r in rs if not r['hit'])
            pl_net = pl_win + pl_loss  # se salvati, guadagno pl_win + perdita pl_loss
            rows_out.append((key, n, w, pct, pl_win, pl_loss, pl_net))

        # Ordina per PL netto
        rows_out.sort(key=lambda x: -x[6])

        if not rows_out:
            print("  (nessun pattern puro con N≥8 e %Win≥65%)")
            continue

        print(f"\n  {'Pattern':<52} {'N':>3} {'Win':>3} {'%W':>5} {'WinPL':>7} {'LossPL':>7} {'Net':>7}")
        for key, n, w, pct, plw, pll, pln in rows_out[:25]:
            label = " & ".join(f"{k}={v}" for k, v in key)
            print(f"  {label[:52]:<52} {n:>3} {w:>3} {pct:>4.1f}% {plw:>+6.2f}u {pll:>+6.2f}u {pln:>+6.2f}u")


if __name__ == '__main__':
    main()
