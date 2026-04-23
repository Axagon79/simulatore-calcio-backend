"""
Analisi tip NUOVI PURI aggiunti dal -3h.
Partite vuote al mattino, con tip all'intermedio.
"""
import os, sys
from collections import defaultdict, Counter

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


def collect_aggiunti_3h(dates):
    """Tip aggiunti dal -3h: partita vuota al mattino, con tip all'intermedio."""
    collected = []
    for date in dates:
        m = load_snap(date, 'mattino')
        i = load_snap(date, 'intermedio')
        if not m or not i:
            continue
        results = fetch_results(date)
        if not results:
            continue

        m_by = index_tips_by_match(m)
        i_by = index_tips_by_match(i)

        for mk, i_tips in i_by.items():
            m_tips = m_by.get(mk, [])
            if m_tips:  # partita NON era vuota → non "nuovo puro"
                continue
            for match, tip in i_tips:
                score = score_for_match(results, match['home'], match['away'])
                pl, hit = compute_pl(match, tip, score)
                if pl is None:
                    continue
                collected.append({
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
    return collected


def stats(rows):
    n = len(rows)
    h = sum(1 for r in rows if r['hit'])
    pl = sum(r['pl'] for r in rows)
    hr = (h / n * 100) if n > 0 else 0
    roi = (pl / n * 100) if n > 0 else 0
    return n, h, hr, pl, roi


def print_seg(title, rows, key_fn, min_n=5):
    groups = defaultdict(list)
    for r in rows:
        groups[key_fn(r)].append(r)
    items = []
    for seg, rs in groups.items():
        if len(rs) < min_n:
            continue
        items.append((seg, *stats(rs)))
    items.sort(key=lambda x: -x[4])  # per PL
    print(f"\n  {title} (min {min_n} tip)")
    if not items:
        print("    (nessun segmento)")
        return
    print(f"    {'Segmento':<28} {'N':>4} {'HR':>6} {'PL':>8} {'ROI':>7}")
    for seg, n, h, hr, pl, roi in items:
        icon = '✅' if pl > 0 else '❌'
        print(f"    {str(seg):<28} {n:>4} {hr:>5.1f}% {pl:>+6.2f}u {roi:>+5.1f}% {icon}")


def main():
    from datetime import datetime
    today = datetime.now().strftime('%Y-%m-%d')
    dates = sorted(d for d in os.listdir(REPORT_DIR)
                   if len(d) == 10 and d[4] == '-' and d < today)

    rows = collect_aggiunti_3h(dates)
    n, h, hr, pl, roi = stats(rows)

    print("=" * 74)
    print("  TIP NUOVI PURI AGGIUNTI DAL UPDATE -3h")
    print("  (partite vuote al mattino, con tip all'intermedio)")
    print("=" * 74)
    print(f"\n  Totale: N={n}  HR={hr:.1f}%  PL={pl:+.2f}u  ROI={roi:+.1f}%")

    print_seg("PER MERCATO", rows, lambda r: r['tipo'], min_n=5)
    print_seg("PER MERCATO + PRONOSTICO", rows, lambda r: f"{r['tipo']} {r['pronostico']}", min_n=5)
    print_seg("PER QUOTA", rows, lambda r: quota_bucket(r.get('quota')), min_n=5)
    print_seg("PER SOURCE", rows, lambda r: r['source'], min_n=8)
    print_seg("PER FLAG (no LowValue)", rows,
              lambda r: f"{'Elite' if r['elite'] else ''}{'Mixer' if r['mixer'] else ''}" or 'nessuno',
              min_n=5)
    print_seg("MERCATO + QUOTA", rows,
              lambda r: f"{r['tipo']:>13} q{quota_bucket(r.get('quota'))}", min_n=5)


if __name__ == '__main__':
    main()
