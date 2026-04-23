"""
Analisi completa update -3h: 3 categorie separate con pattern interni.
1. Aggiunti su vuoto (120 tip) — pattern vincenti
2. Sostituiti (83 partite) — quando il -3h cambia male
3. Scartati senza sost. (29 tip) — quali vincenti butta
"""
import os, sys
from collections import defaultdict

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


def collect_3h(dates):
    """Raccoglie 3 categorie dal confronto mattino → intermedio."""
    aggiunti_vuoto = []
    sostituiti_old = []  # tip vecchi (c'erano mattina, tolti a -3h)
    sostituiti_new = []  # tip nuovi (non c'erano mattina, aggiunti a -3h) sulla stessa partita
    scartati_sost = []   # tip del mattino tolti completamente (partita vuota a intermedio)

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

        all_matches = set(m_by.keys()) | set(i_by.keys())
        for mk in all_matches:
            m_tips = m_by.get(mk, [])
            i_tips = i_by.get(mk, [])
            m_keys = {tip_key(mt, tt) for mt, tt in m_tips}
            i_keys = {tip_key(mt, tt) for mt, tt in i_tips}

            if not m_keys and i_keys:
                # Aggiunti su vuoto
                for match, tip in i_tips:
                    score = score_for_match(results, match['home'], match['away'])
                    pl, hit = compute_pl(match, tip, score)
                    if pl is None: continue
                    aggiunti_vuoto.append(tip_to_row(match, tip, hit, pl))
            elif m_keys and not i_keys:
                # Scartati senza sostituzione
                for match, tip in m_tips:
                    score = score_for_match(results, match['home'], match['away'])
                    pl, hit = compute_pl(match, tip, score)
                    if pl is None: continue
                    scartati_sost.append(tip_to_row(match, tip, hit, pl))
            elif m_keys and i_keys and m_keys != i_keys:
                # Sostituiti: vecchi tolti + nuovi aggiunti
                for match, tip in m_tips:
                    if tip_key(match, tip) in i_keys:
                        continue
                    score = score_for_match(results, match['home'], match['away'])
                    pl, hit = compute_pl(match, tip, score)
                    if pl is None: continue
                    sostituiti_old.append(tip_to_row(match, tip, hit, pl))
                for match, tip in i_tips:
                    if tip_key(match, tip) in m_keys:
                        continue
                    score = score_for_match(results, match['home'], match['away'])
                    pl, hit = compute_pl(match, tip, score)
                    if pl is None: continue
                    sostituiti_new.append(tip_to_row(match, tip, hit, pl))

    return aggiunti_vuoto, sostituiti_old, sostituiti_new, scartati_sost


def tip_to_row(match, tip, hit, pl):
    return {
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
    }


def stats(rows):
    n = len(rows)
    h = sum(1 for r in rows if r['hit'])
    pl = sum(r['pl'] for r in rows)
    hr = (h / n * 100) if n > 0 else 0
    roi = (pl / n * 100) if n > 0 else 0
    return n, h, hr, pl, roi


def print_tabella(title, rows, keyfn, min_n=5, solo_pos=False):
    groups = defaultdict(list)
    for r in rows:
        groups[keyfn(r)].append(r)
    items = []
    for seg, rs in groups.items():
        if len(rs) < min_n: continue
        n, h, hr, pl, roi = stats(rs)
        if solo_pos and pl <= 0: continue
        items.append((seg, n, h, hr, pl, roi))
    items.sort(key=lambda x: -x[4])
    print(f"\n  {title} (min {min_n} tip{', solo positivi' if solo_pos else ''})")
    if not items:
        print("    (nessuno)")
        return
    print(f"    {'Segmento':<30} {'N':>4} {'HR':>6} {'PL':>8} {'ROI':>7}")
    for seg, n, h, hr, pl, roi in items:
        icon = '✅' if pl > 0 else '❌'
        print(f"    {str(seg):<30} {n:>4} {hr:>5.1f}% {pl:>+6.2f}u {roi:>+5.1f}% {icon}")


def analisi_categoria(nome, rows):
    print("\n" + "=" * 74)
    print(f"  {nome}")
    print("=" * 74)
    n, h, hr, pl, roi = stats(rows)
    print(f"  TOTALE: N={n}  HR={hr:.1f}%  PL={pl:+.2f}u  ROI={roi:+.1f}%")
    print_tabella("PATTERN VINCENTI — mercato", rows, lambda r: r['tipo'], min_n=5, solo_pos=True)
    print_tabella("PATTERN VINCENTI — mercato + pronostico", rows,
                  lambda r: f"{r['tipo']} {r['pronostico']}", min_n=5, solo_pos=True)
    print_tabella("PATTERN VINCENTI — quota", rows, lambda r: quota_bucket(r.get('quota')),
                  min_n=5, solo_pos=True)
    print_tabella("PATTERN VINCENTI — source", rows, lambda r: r['source'], min_n=5, solo_pos=True)
    print_tabella("PATTERN VINCENTI — flag", rows,
                  lambda r: (('E' if r['elite'] else '') + ('M' if r['mixer'] else '') + ('L' if r['low_value'] else '')) or 'nessuno',
                  min_n=5, solo_pos=True)
    print_tabella("PATTERN VINCENTI — mercato + quota", rows,
                  lambda r: f"{r['tipo']} q{quota_bucket(r.get('quota'))}", min_n=5, solo_pos=True)


def main():
    from datetime import datetime
    today = datetime.now().strftime('%Y-%m-%d')
    dates = sorted(d for d in os.listdir(REPORT_DIR)
                   if len(d) == 10 and d[4] == '-' and d < today)

    av, so, sn, ss = collect_3h(dates)

    print("=" * 74)
    print("  ANALISI COMPLETA UPDATE -3h (mattino → intermedio)")
    print("=" * 74)
    print(f"\n  Periodo: {dates[0]} → {dates[-1]}")
    print(f"  Aggiunti su vuoto:          {len(av)} tip")
    print(f"  Sostituiti (vecchi tolti):  {len(so)} tip")
    print(f"  Sostituiti (nuovi messi):   {len(sn)} tip")
    print(f"  Scartati senza sost.:       {len(ss)} tip")

    # Categoria 1: AGGIUNTI SU VUOTO (da filtrare: tenere solo i pattern buoni)
    analisi_categoria("1) AGGIUNTI SU VUOTO dal -3h (quali tenere)", av)

    # Categoria 2a: SOSTITUITI — VECCHI TOLTI (quelli che il -3h ha rimosso vincenti)
    # Per "proteggerli" cerco pattern tra quelli VINCENTI
    vincenti_tolti = [r for r in so if r['hit']]
    print("\n" + "=" * 74)
    print(f"  2) SOSTITUITI: TIP VECCHI TOLTI ERRONEAMENTE ({len(vincenti_tolti)} vincenti su {len(so)} totali)")
    print("=" * 74)
    n, h, hr, pl, roi = stats(so)
    print(f"  TUTTI i tip tolti nella sostituzione:  N={n} HR={hr:.1f}%  PL={pl:+.2f}u")
    # Cerco segmenti dove il -3h sbaglia di più a togliere (%Win alta tra i tolti)
    for keyfn, title in [
        (lambda r: r['tipo'], "mercato"),
        (lambda r: f"{r['tipo']} {r['pronostico']}", "mercato + pronostico"),
        (lambda r: quota_bucket(r.get('quota')), "quota"),
        (lambda r: r['source'], "source"),
        (lambda r: f"{r['tipo']} q{quota_bucket(r.get('quota'))}", "mercato+quota"),
    ]:
        groups = defaultdict(list)
        for r in so:
            groups[keyfn(r)].append(r)
        items = []
        for seg, rs in groups.items():
            if len(rs) < 5: continue
            w = sum(1 for r in rs if r['hit'])
            pct = w / len(rs) * 100
            pl_win = sum(r['pl'] for r in rs if r['hit'])
            if pct < 60: continue
            items.append((seg, len(rs), w, pct, pl_win))
        items.sort(key=lambda x: -x[3])
        print(f"\n  Dove il -3h toglie più vincenti — per {title} (min 5, %Win≥60%)")
        if not items:
            print("    (nessuno)")
            continue
        print(f"    {'Segmento':<30} {'N':>4} {'Win':>4} {'%Win':>6} {'PL persi':>9}")
        for seg, n, w, pct, pl_win in items:
            print(f"    {str(seg):<30} {n:>4} {w:>4} {pct:>5.1f}% {pl_win:>+7.2f}u")

    # Categoria 2b: SOSTITUITI — NUOVI MESSI
    analisi_categoria("2b) SOSTITUITI: TIP NUOVI messi dal -3h (quali tenere)", sn)

    # Categoria 3: SCARTATI SENZA SOSTITUZIONE — quali vincenti butta
    vincenti_scartati = [r for r in ss if r['hit']]
    print("\n" + "=" * 74)
    print(f"  3) SCARTATI SENZA SOSTITUZIONE — vincenti buttati ({len(vincenti_scartati)} su {len(ss)})")
    print("=" * 74)
    n, h, hr, pl, roi = stats(ss)
    print(f"  TUTTI i tip scartati: N={n} HR={hr:.1f}% PL={pl:+.2f}u")
    for keyfn, title in [
        (lambda r: r['tipo'], "mercato"),
        (lambda r: f"{r['tipo']} {r['pronostico']}", "mercato + pronostico"),
        (lambda r: quota_bucket(r.get('quota')), "quota"),
        (lambda r: r['source'], "source"),
    ]:
        groups = defaultdict(list)
        for r in ss:
            groups[keyfn(r)].append(r)
        items = []
        for seg, rs in groups.items():
            if len(rs) < 3: continue
            w = sum(1 for r in rs if r['hit'])
            pct = w / len(rs) * 100
            pl_win = sum(r['pl'] for r in rs if r['hit'])
            if pct < 60: continue
            items.append((seg, len(rs), w, pct, pl_win))
        items.sort(key=lambda x: -x[3])
        print(f"\n  Pattern con più vincenti scartati — per {title} (min 3, %Win≥60%)")
        if not items:
            print("    (nessuno)")
            continue
        print(f"    {'Segmento':<30} {'N':>4} {'Win':>4} {'%Win':>6} {'PL persi':>9}")
        for seg, n, w, pct, pl_win in items:
            print(f"    {str(seg):<30} {n:>4} {w:>4} {pct:>5.1f}% {pl_win:>+7.2f}u")


if __name__ == '__main__':
    main()
