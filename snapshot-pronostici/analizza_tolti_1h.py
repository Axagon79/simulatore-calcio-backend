"""
ANALIZZA TIP TOLTI DAL -1h
============================
Per i tip che il -1h ha RIMOSSO (scartati senza sostituzione),
calcola quanti avrebbero vinto e quanti persi.
Separa le due sottocategorie:
  A) "svuota originale": c'era al mattino, -3h non l'aveva toccato
  B) "fix aggiunta 3h": non c'era al mattino, l'aveva aggiunto il -3h
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


def collect_tolti_1h(dates):
    """Trova tip rimossi dal -1h, classificati per origine."""
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

        # Per ogni tip presente all'intermedio, guarda se il -1h l'ha tolto.
        # "Tolto" = tip presente all'intermedio ma assente al serale.
        # Include sia svuotamenti totali che rimozioni durante una sostituzione.
        for mk, i_tips in i_by.items():
            s_tips = s_by.get(mk, [])
            m_tips = m_by.get(mk, [])
            s_keys = {tip_key(mt, tt) for mt, tt in s_tips}
            m_keys = {tip_key(mt, tt) for mt, tt in m_tips}

            for match, tip in i_tips:
                k = tip_key(match, tip)
                if k in s_keys:
                    continue  # il tip è ancora presente al serale → non tolto

                score = score_for_match(results, match['home'], match['away'])
                pl, hit = compute_pl(match, tip, score)
                if pl is None:
                    continue

                origine = 'svuota_originale' if k in m_keys else 'fix_aggiunta_3h'

                collected.append({
                    'date': date,
                    'home': match['home'],
                    'away': match['away'],
                    'tipo': tip.get('tipo'),
                    'pronostico': tip.get('pronostico'),
                    'quota': tip.get('quota'),
                    'source': tip.get('source') or '?',
                    'origine': origine,
                    'hit': hit,
                    'pl': pl,
                })

    return collected


def stats(rows):
    n = len(rows)
    hit = sum(1 for r in rows if r['hit'])
    pl = sum(r['pl'] for r in rows)
    hr = (hit / n * 100) if n > 0 else 0
    roi = (pl / n * 100) if n > 0 else 0
    return n, hit, hr, pl, roi


def main():
    from datetime import datetime
    today = datetime.now().strftime('%Y-%m-%d')
    dates = sorted(d for d in os.listdir(REPORT_DIR)
                   if len(d) == 10 and d[4] == '-' and d < today)

    rows = collect_tolti_1h(dates)

    print("=" * 72)
    print("  TIP TOLTI DAL -1h (scartati senza sostituzione)")
    print("=" * 72)
    print(f"  Periodo: {dates[0]} → {dates[-1]}")
    print(f"  Totale tip tolti: {len(rows)}\n")

    # Globale
    n, hit, hr, pl, roi = stats(rows)
    print(f"  TOTALE: N={n}  Vincenti={hit}  Perdenti={n-hit}")
    print(f"          PL 'perso' non togliendoli = {pl:+.2f}u")
    print(f"          Quindi togliendoli si 'risparmia' {-pl:+.2f}u\n")

    # Per origine
    sva = [r for r in rows if r['origine'] == 'svuota_originale']
    fix = [r for r in rows if r['origine'] == 'fix_aggiunta_3h']

    def report(name, rows):
        n, hit, hr, pl, roi = stats(rows)
        persi = n - hit
        pct_corretti = (persi / n * 100) if n > 0 else 0
        print(f"  {name}")
        print(f"    N={n}  Vincenti={hit} ({hr:.1f}%)  Perdenti={persi} ({pct_corretti:.1f}%)")
        print(f"    PL complessivo dei tip tolti: {pl:+.2f}u")
        print(f"    → Togliendoli il -1h 'risparmia' {-pl:+.2f}u")
        print(f"    → DECISIONI CORRETTE: {persi}/{n} ({pct_corretti:.1f}%)")
        print(f"    → DECISIONI SBAGLIATE (avrebbero vinto): {hit}/{n} ({hr:.1f}%)")
        print()

    print("━" * 72)
    print("  BREAKDOWN PER ORIGINE")
    print("━" * 72)
    print()
    report("A) SVUOTA TIP ORIGINALE (c'era al mattino, -3h non aveva toccato)", sva)
    report("B) FIX AGGIUNTA -3h (non c'era al mattino, -3h aveva aggiunto)", fix)

    # Dettaglio tip VINCENTI tolti (errore del -1h)
    print("━" * 72)
    print("  TIP VINCENTI TOLTI DAL -1h (sbagliato toglierli)")
    print("━" * 72)
    win_tolti = [r for r in rows if r['hit']]
    n_win = len(win_tolti)
    pl_win = sum(r['pl'] for r in win_tolti)
    print(f"  {n_win} tip che avrebbero vinto, guadagno perso: {pl_win:+.2f}u\n")

    # Breakdown per tipo
    by_tipo = defaultdict(list)
    for r in win_tolti:
        by_tipo[r['tipo']].append(r)
    print("  Per mercato:")
    for tipo, rs in sorted(by_tipo.items(), key=lambda x: -len(x[1])):
        n, hit, hr, pl, roi = stats(rs)
        print(f"    {tipo:<18}  N={n:>3}  PL={pl:>+6.2f}u")

    # Per pronostico specifico
    by_pron = defaultdict(list)
    for r in win_tolti:
        by_pron[f"{r['tipo']} {r['pronostico']}"].append(r)
    print("\n  Per mercato + pronostico:")
    items = sorted(by_pron.items(), key=lambda x: -len(x[1]))
    for pron, rs in items[:15]:
        n, hit, hr, pl, roi = stats(rs)
        print(f"    {pron:<25}  N={n:>3}  PL={pl:>+6.2f}u")


if __name__ == '__main__':
    main()
