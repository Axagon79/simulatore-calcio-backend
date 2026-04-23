"""
ANALIZZA AGGIUNTI DAL -1h
==========================
Estrae tutti i tip AGGIUNTI dal update -1h (presenti a serale ma non a intermedio).
Li incrocia con risultati reali e cerca pattern per identificare i più performanti.

Segmenta per: mercato, fascia di quota, source, stelle.
"""

import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from snapshot_pronostici import fetch_results, calculate_hit, calc_pl
from analizza_impatto_aggiornamenti import (
    load_snap, index_tips_by_match, tip_key, score_for_match, compute_pl
)

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report")


def quota_bucket(q):
    """Fascia quota."""
    if q is None or q <= 1:
        return 'N/A'
    if q < 1.30:
        return '1.00-1.29'
    if q < 1.50:
        return '1.30-1.49'
    if q < 1.70:
        return '1.50-1.69'
    if q < 1.90:
        return '1.70-1.89'
    if q < 2.20:
        return '1.90-2.19'
    if q < 2.50:
        return '2.20-2.49'
    if q < 3.00:
        return '2.50-2.99'
    return '3.00+'


def stars_bucket(s):
    if s is None:
        return 'N/A'
    if s < 2.5:
        return '<2.5'
    if s < 3.0:
        return '2.5-2.9'
    if s < 3.5:
        return '3.0-3.4'
    if s < 4.0:
        return '3.5-3.9'
    return '≥4.0'


def collect_aggiunti_1h(dates):
    """Per ogni giorno, trova i tip aggiunti dal -1h e li ritorna con esito e P/L.
    Filtra SOLO i 'nuovi puri': partita vuota sia al mattino che all'intermedio."""
    collected = []  # lista di dict con info tip + hit + pl

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

        # Per ogni partita presente a serale
        for mk, s_tips in s_by.items():
            i_tips = i_by.get(mk, [])
            m_tips = m_by.get(mk, [])

            # FILTRO "NUOVI PURI": la partita deve essere VUOTA sia al mattino che all'intermedio
            if m_tips or i_tips:
                continue

            for match, tip in s_tips:
                score = score_for_match(results, match['home'], match['away'])
                pl, hit = compute_pl(match, tip, score)
                if pl is None:
                    continue

                collected.append({
                    'date': date,
                    'home': match['home'],
                    'away': match['away'],
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
                })

    return collected


def agg_stats(rows):
    n = len(rows)
    hit = sum(1 for r in rows if r['hit'])
    pl = sum(r['pl'] for r in rows)
    stake = n  # stake=1 per ogni tip
    hr = (hit / n * 100) if n > 0 else 0
    roi = (pl / stake * 100) if stake > 0 else 0
    return n, hit, hr, round(pl, 2), roi


def print_segment(title, rows, sort_by=None):
    print(f"\n  {title}")
    print(f"  {'-' * (len(title) + 2)}")
    if not rows:
        print("  (nessun dato)")
        return
    # Aggrega per segmento
    segs = defaultdict(list)
    for r in rows:
        segs[r['segment']].append(r)
    items = []
    for seg, srows in segs.items():
        n, hit, hr, pl, roi = agg_stats(srows)
        items.append((seg, n, hit, hr, pl, roi))
    # Ordina
    if sort_by == 'pl':
        items.sort(key=lambda x: -x[4])
    elif sort_by == 'roi':
        items.sort(key=lambda x: -x[5])
    else:
        items.sort(key=lambda x: -x[1])  # per N decrescente

    print(f"  {'Segmento':<25} {'N':>4} {'Hit':>4} {'HR':>6} {'PL':>9} {'ROI':>7}")
    for seg, n, hit, hr, pl, roi in items:
        icon = '✅' if pl > 0 else ('❌' if pl < 0 else '⚖️')
        print(f"  {str(seg):<25} {n:>4} {hit:>4} {hr:>5.1f}% {pl:>+7.2f}u {roi:>+5.1f}% {icon}")


def segment_by(rows, key_fn):
    out = []
    for r in rows:
        rc = dict(r)
        rc['segment'] = key_fn(r)
        out.append(rc)
    return out


def main():
    from datetime import datetime
    today = datetime.now().strftime('%Y-%m-%d')
    dates = sorted(d for d in os.listdir(REPORT_DIR)
                   if len(d) == 10 and d[4] == '-' and d < today)

    print("=" * 72)
    print("  ANALISI TIP NUOVI PURI AGGIUNTI DAL UPDATE -1h")
    print("  (partite VUOTE sia al mattino che all'intermedio)")
    print("=" * 72)
    print(f"  Periodo: {dates[0]} → {dates[-1]}\n")

    rows = collect_aggiunti_1h(dates)
    print(f"  Tip nuovi puri aggiunti dal -1h: {len(rows)}\n")

    # --- TOTALE ---
    n, hit, hr, pl, roi = agg_stats(rows)
    print(f"  TOTALE: N={n}  Hit={hit}  HR={hr:.1f}%  PL={pl:+.2f}u  ROI={roi:+.1f}%\n")

    # --- PER MERCATO ---
    print("\n" + "━" * 72)
    print("  PER MERCATO (SEGNO / DOPPIA_CHANCE / GOL)")
    print("━" * 72)
    print_segment("", segment_by(rows, lambda r: r['tipo']), sort_by='pl')

    # --- PER MERCATO + PRONOSTICO ---
    print("\n" + "━" * 72)
    print("  PER MERCATO + PRONOSTICO")
    print("━" * 72)
    print_segment("", segment_by(rows, lambda r: f"{r['tipo']} {r['pronostico']}"), sort_by='pl')

    # --- PER QUOTA ---
    print("\n" + "━" * 72)
    print("  PER FASCIA QUOTA")
    print("━" * 72)
    print_segment("", segment_by(rows, lambda r: quota_bucket(r.get('quota'))), sort_by='pl')

    # --- PER SOURCE ---
    print("\n" + "━" * 72)
    print("  PER SOURCE")
    print("━" * 72)
    print_segment("", segment_by(rows, lambda r: r['source']), sort_by='pl')

    # --- PER STELLE ---
    print("\n" + "━" * 72)
    print("  PER STELLE")
    print("━" * 72)
    print_segment("", segment_by(rows, lambda r: stars_bucket(r.get('stars'))), sort_by='pl')

    # --- COMBINATO: MERCATO + FASCIA QUOTA ---
    print("\n" + "━" * 72)
    print("  COMBINATO: MERCATO + FASCIA QUOTA (min 5 tip)")
    print("━" * 72)
    combined = segment_by(rows, lambda r: f"{r['tipo']:>13} | q {quota_bucket(r.get('quota'))}")
    # Filtra a min 5
    from collections import Counter
    counts = Counter(r['segment'] for r in combined)
    filtered = [r for r in combined if counts[r['segment']] >= 5]
    print_segment("", filtered, sort_by='roi')

    # --- COMBINATO: MERCATO + SOURCE ---
    print("\n" + "━" * 72)
    print("  COMBINATO: MERCATO + SOURCE (min 5 tip)")
    print("━" * 72)
    combined2 = segment_by(rows, lambda r: f"{r['tipo']:>13} | {r['source']}")
    counts = Counter(r['segment'] for r in combined2)
    filtered = [r for r in combined2 if counts[r['segment']] >= 5]
    print_segment("", filtered, sort_by='roi')

    # --- FLAG: elite / mixer / low_value ---
    print("\n" + "━" * 72)
    print("  PER FLAG (elite / mixer / low_value)")
    print("━" * 72)
    def flag_key(r):
        parts = []
        if r['elite']:
            parts.append('ELITE')
        if r['mixer']:
            parts.append('MIXER')
        if r['low_value']:
            parts.append('LOW')
        return '+'.join(parts) if parts else 'nessuno'
    print_segment("", segment_by(rows, flag_key), sort_by='pl')


if __name__ == '__main__':
    main()
