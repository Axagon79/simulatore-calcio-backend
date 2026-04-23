"""
WHITELIST FILTER per tip nuovi puri del -1h
=============================================
Calcola il PL cumulativo applicando una WHITELIST:
tip accettati SOLO se rispettano almeno uno dei pattern vincenti.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analizza_aggiunti_1h import collect_aggiunti_1h

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report")


# ========== DEFINIZIONE PATTERN WHITELIST ==========
def is_DC_1X(t):
    return t['tipo'] == 'DOPPIA_CHANCE' and t['pronostico'] == '1X'

def is_SEGNO_q150_169(t):
    q = t.get('quota')
    return t['tipo'] == 'SEGNO' and q is not None and 1.50 <= q < 1.70

def is_DC_q130_149(t):
    q = t.get('quota')
    return t['tipo'] == 'DOPPIA_CHANCE' and q is not None and 1.30 <= q < 1.50

def is_MIXER(t):
    return t.get('mixer') is True

def is_ELITE(t):
    return t.get('elite') is True

def is_source_AS(t):
    return t.get('source') == 'A+S'

def is_DC_AS(t):
    return t['tipo'] == 'DOPPIA_CHANCE' and t.get('source') == 'A+S'


PATTERN_WHITELIST = [
    ('DC 1X',                is_DC_1X),
    ('SEGNO q 1.50-1.69',    is_SEGNO_q150_169),
    ('DC q 1.30-1.49',       is_DC_q130_149),
    ('flag MIXER',           is_MIXER),
    ('flag ELITE',           is_ELITE),
    ('source A+S',           is_source_AS),
    ('DC + A+S',             is_DC_AS),
]


def passa_whitelist(t):
    """Ritorna (True, [pattern matches]) se almeno un pattern accetta il tip."""
    matches = [name for name, fn in PATTERN_WHITELIST if fn(t)]
    return len(matches) > 0, matches


def main():
    from datetime import datetime
    today = datetime.now().strftime('%Y-%m-%d')
    dates = sorted(d for d in os.listdir(REPORT_DIR)
                   if len(d) == 10 and d[4] == '-' and d < today)

    print("=" * 72)
    print("  WHITELIST FILTER sui tip nuovi puri aggiunti dal -1h")
    print("=" * 72)
    print("\n  Pattern accettati (ALMENO UNO deve essere vero):")
    for name, _ in PATTERN_WHITELIST:
        print(f"    - {name}")
    print()

    all_tips = collect_aggiunti_1h(dates)
    total_n = len(all_tips)
    total_pl = sum(t['pl'] for t in all_tips)
    total_hit = sum(1 for t in all_tips if t['hit'])

    passati = []
    bocciati = []
    for t in all_tips:
        ok, matches = passa_whitelist(t)
        t['_matches'] = matches
        (passati if ok else bocciati).append(t)

    def stats(rows):
        n = len(rows)
        h = sum(1 for r in rows if r['hit'])
        pl = sum(r['pl'] for r in rows)
        hr = (h / n * 100) if n > 0 else 0
        roi = (pl / n * 100) if n > 0 else 0
        return n, h, hr, pl, roi

    n_all, h_all, hr_all, pl_all, roi_all = stats(all_tips)
    n_ok, h_ok, hr_ok, pl_ok, roi_ok = stats(passati)
    n_ko, h_ko, hr_ko, pl_ko, roi_ko = stats(bocciati)

    print("━" * 72)
    print("  CONFRONTO — TUTTI vs SOLO WHITELIST vs SCARTATI")
    print("━" * 72)
    print(f"\n  {'Categoria':<22}  {'N':>4}  {'Hit':>4}  {'HR':>6}  {'PL':>9}  {'ROI':>7}")
    print(f"  {'-'*22}  {'-'*4}  {'-'*4}  {'-'*6}  {'-'*9}  {'-'*7}")
    print(f"  {'Tutti (senza filtro)':<22}  {n_all:>4}  {h_all:>4}  {hr_all:>5.1f}%  {pl_all:>+7.2f}u  {roi_all:>+5.1f}%")
    print(f"  {'PASSATI whitelist':<22}  {n_ok:>4}  {h_ok:>4}  {hr_ok:>5.1f}%  {pl_ok:>+7.2f}u  {roi_ok:>+5.1f}%  ✅")
    print(f"  {'BOCCIATI (scartati)':<22}  {n_ko:>4}  {h_ko:>4}  {hr_ko:>5.1f}%  {pl_ko:>+7.2f}u  {roi_ko:>+5.1f}%  ❌")

    print(f"\n  Risparmio applicando la whitelist: {pl_all:+.2f}u (ora) → {pl_ok:+.2f}u (con filtro)")
    print(f"  Delta: {(pl_ok - pl_all):+.2f}u")
    if pl_ok > pl_all:
        print(f"  ✅ La whitelist MIGLIORA il risultato dei tip nuovi del -1h")

    # ========== DETTAGLIO PATTERN PASSATI ==========
    print("\n" + "━" * 72)
    print("  DETTAGLIO: quanti tip ogni pattern accetta (possono sovrapporsi)")
    print("━" * 72)
    for name, fn in PATTERN_WHITELIST:
        matched = [t for t in all_tips if fn(t)]
        n, h, hr, pl, roi = stats(matched)
        print(f"  {name:<22}  N={n:>3}  HR={hr:>5.1f}%  PL={pl:>+6.2f}u  ROI={roi:>+6.1f}%")

    # ========== CATEGORIE ESCLUSE DALLA WHITELIST ==========
    print("\n" + "━" * 72)
    print("  BOCCIATI — breakdown per mercato + pronostico")
    print("━" * 72)
    from collections import defaultdict
    by_cat = defaultdict(list)
    for t in bocciati:
        by_cat[f"{t['tipo']} {t['pronostico']}"].append(t)
    items = []
    for cat, rows in by_cat.items():
        n, h, hr, pl, roi = stats(rows)
        items.append((cat, n, h, hr, pl, roi))
    items.sort(key=lambda x: x[4])  # per PL crescente
    for cat, n, h, hr, pl, roi in items:
        icon = '❌' if pl < 0 else ('✅' if pl > 0 else '⚖️')
        print(f"  {cat:<25}  N={n:>3}  HR={hr:>5.1f}%  PL={pl:>+6.2f}u  ROI={roi:>+6.1f}%  {icon}")


if __name__ == '__main__':
    main()
