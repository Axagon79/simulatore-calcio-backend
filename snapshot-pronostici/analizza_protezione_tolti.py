"""
ANALIZZA TIP VINCENTI TOLTI DAL -1h — cerco pattern di PROTEZIONE.

Dato che il -1h toglie 250 tip di cui 123 sarebbero stati vincenti,
cerchiamo caratteristiche che identifichino i vincenti per evitare di toglierli.

Logica: per ogni segmento (mercato, quota, source, stelle, flag),
confronto i TOLTI-VINCENTI vs TOLTI-PERDENTI e cerco dove la proporzione
di vincenti è particolarmente alta (> 60%).
"""

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from snapshot_pronostici import fetch_results
from analizza_impatto_aggiornamenti import (
    load_snap, index_tips_by_match, tip_key, score_for_match, compute_pl
)

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report")


def quota_bucket(q):
    if q is None or q <= 1:
        return 'N/A'
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


def collect_tolti(dates):
    """Tutti i tip tolti dal -1h (include rimozioni durante sostituzioni)."""
    collected = []
    for date in dates:
        m = load_snap(date, 'mattino')
        i = load_snap(date, 'intermedio')
        s = load_snap(date, 'serale')
        if not m or not i or not s:
            continue
        results = fetch_results(date)
        if not results:
            continue

        m_by = index_tips_by_match(m)
        i_by = index_tips_by_match(i)
        s_by = index_tips_by_match(s)

        for mk, i_tips in i_by.items():
            s_tips = s_by.get(mk, [])
            m_tips = m_by.get(mk, [])
            s_keys = {tip_key(mt, tt) for mt, tt in s_tips}
            m_keys = {tip_key(mt, tt) for mt, tt in m_tips}

            for match, tip in i_tips:
                k = tip_key(match, tip)
                if k in s_keys:
                    continue  # non tolto
                score = score_for_match(results, match['home'], match['away'])
                pl, hit = compute_pl(match, tip, score)
                if pl is None:
                    continue
                collected.append({
                    'tipo': tip.get('tipo'),
                    'pronostico': tip.get('pronostico'),
                    'quota': tip.get('quota'),
                    'stars': tip.get('stars'),
                    'confidence': tip.get('confidence'),
                    'source': tip.get('source') or '?',
                    'elite': bool(tip.get('elite')),
                    'mixer': bool(tip.get('mixer')),
                    'low_value': bool(tip.get('low_value')),
                    'hit': hit,
                    'pl': pl,
                    'origine_svuota': k in m_keys,  # True se era al mattino
                })
    return collected


def segment_stats(rows, key_fn, min_n=5):
    """Raggruppa per segmento e restituisce (seg, n_tot, n_win, n_loss, pct_win, pl, pl_win_lost).
    pl_win_lost = guadagno perso togliendo i vincenti di questo segmento."""
    groups = defaultdict(list)
    for r in rows:
        groups[key_fn(r)].append(r)
    out = []
    for seg, rs in groups.items():
        n = len(rs)
        if n < min_n:
            continue
        win = sum(1 for r in rs if r['hit'])
        loss = n - win
        pl = sum(r['pl'] for r in rs)
        pl_win = sum(r['pl'] for r in rs if r['hit'])
        pct_win = win / n * 100
        out.append((seg, n, win, loss, pct_win, pl, pl_win))
    out.sort(key=lambda x: -x[4])  # ordina per % vincenti decrescente
    return out


def print_segment(title, rows, key_fn, min_n=5):
    segs = segment_stats(rows, key_fn, min_n=min_n)
    print(f"\n{title} (min {min_n} tip)")
    print(f"  {'-' * (len(title) + 18)}")
    if not segs:
        print("  (nessun segmento con N sufficiente)")
        return
    print(f"  {'Segmento':<28} {'N':>4} {'Win':>4} {'Loss':>5} {'%Win':>6} {'PL tolti':>10} {'Win persi':>10}")
    for seg, n, win, loss, pct_win, pl, pl_win in segs:
        icon = '🟢' if pct_win >= 60 else ('🟡' if pct_win >= 50 else '🔴')
        print(f"  {str(seg):<28} {n:>4} {win:>4} {loss:>5} {pct_win:>5.1f}% {pl:>+8.2f}u {pl_win:>+8.2f}u  {icon}")


def main():
    from datetime import datetime
    today = datetime.now().strftime('%Y-%m-%d')
    dates = sorted(d for d in os.listdir(REPORT_DIR)
                   if len(d) == 10 and d[4] == '-' and d < today)

    rows = collect_tolti(dates)
    n_tot = len(rows)
    n_win = sum(1 for r in rows if r['hit'])
    n_loss = n_tot - n_win
    print("=" * 80)
    print("  PATTERN DI PROTEZIONE — tra i tip TOLTI dal -1h, quali sarebbero vincenti?")
    print("=" * 80)
    print(f"  Totale tolti: {n_tot}  |  Vincenti: {n_win} ({n_win/n_tot*100:.1f}%)  |  Perdenti: {n_loss}")
    print(f"  Obiettivo: cercare segmenti con % vincenti ≥ 60% (mele buone nel cesto)\n")
    print(f"  Legenda: 🟢 ≥60% vinc.   🟡 50-59%   🔴 <50%")

    # Segmentazioni
    print_segment("  PER MERCATO", rows, lambda r: r['tipo'])
    print_segment("  PER MERCATO + PRONOSTICO", rows, lambda r: f"{r['tipo']} {r['pronostico']}")
    print_segment("  PER FASCIA QUOTA", rows, lambda r: quota_bucket(r.get('quota')))
    print_segment("  PER STELLE", rows, lambda r: stars_bucket(r.get('stars')))
    print_segment("  PER SOURCE", rows, lambda r: r['source'], min_n=8)

    # Combinati
    print_segment("  MERCATO + FASCIA QUOTA", rows,
                  lambda r: f"{r['tipo']} q {quota_bucket(r.get('quota'))}")
    print_segment("  MERCATO + FLAG", rows,
                  lambda r: f"{r['tipo']} {'Elite' if r['elite'] else ''}{'Mixer' if r['mixer'] else ''}{'Low' if r['low_value'] else ''}" or f"{r['tipo']} nessuno")
    print_segment("  FASCIA QUOTA + FLAG", rows,
                  lambda r: f"q{quota_bucket(r.get('quota'))} {'E' if r['elite'] else ''}{'M' if r['mixer'] else ''}{'L' if r['low_value'] else ''}".strip())

    # Origine svuotamento
    print_segment("  PER ORIGINE (svuota orig. vs fix -3h)", rows,
                  lambda r: 'svuota_originale' if r['origine_svuota'] else 'fix_aggiunta_3h')

    # Focus: tip con stake alto / quota bassa (più "sicuri")
    print_segment("  QUOTA BASSA + ORIGINE MATTINO", rows,
                  lambda r: f"q{quota_bucket(r.get('quota'))} {'matt' if r['origine_svuota'] else '3h'}")


if __name__ == '__main__':
    main()
