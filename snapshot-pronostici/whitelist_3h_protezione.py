"""Whitelist protezione per i tip eliminati dal -3h — pattern UNICI (alto %Win + bassa sovrapposizione con perdenti)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trova_pattern_3h_eliminati import collect

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report")


def protect(t):
    q = t.get('quota') or 0
    s = t.get('stars') or 0
    src = t.get('source') or ''
    tipo = t['tipo']
    pron = t['pronostico']
    elite = t['elite']
    mixer = t['mixer']
    low = t['low_value']

    # 1. DC X2 + quota 1.50-1.69 (6/6 = 100%)
    if tipo == 'DOPPIA_CHANCE' and pron == 'X2' and 1.50 <= q < 1.70:
        return True
    # 2. Quota 1.30-1.49 + Elite (13/14 = 92.9%)
    if 1.30 <= q < 1.50 and elite:
        return True
    # 3. Quota 1.50-1.69 + stelle 2.5-2.9 (8/9 = 88.9%)
    if 1.50 <= q < 1.70 and 2.5 <= s < 3.0:
        return True
    # 4. Quota 1.50-1.69 + source C (9/11 = 81.8%)
    if 1.50 <= q < 1.70 and src == 'C':
        return True
    # 5. Quota 1.90-2.19 + non Elite + non Mixer + non Low (12/16 = 75%)
    if 1.90 <= q < 2.20 and not elite and not mixer and not low:
        return True
    # 6. GOL Over 2.5 (6/7 = 85.7%)
    if tipo == 'GOL' and pron == 'Over 2.5':
        return True
    # 7. SEGNO 1 + quota 1.90-2.19 (7/10 = 70%)
    if tipo == 'SEGNO' and pron == '1' and 1.90 <= q < 2.20:
        return True
    # 8. Elite (16/19 = 84.2%)
    if elite:
        return True
    return False


def main():
    from datetime import datetime
    today = datetime.now().strftime('%Y-%m-%d')
    dates = sorted(d for d in os.listdir(REPORT_DIR) if len(d) == 10 and d[4] == '-' and d < today)
    rows = collect(dates)

    salvati = [r for r in rows if protect(r)]
    non_salvati = [r for r in rows if not protect(r)]

    def stats(rs):
        n = len(rs)
        w = sum(1 for r in rs if r['hit'])
        pl = sum(r['pl'] for r in rs)
        return n, w, n - w, pl

    ntot, wtot, ltot, pltot = stats(rows)
    nsa, wsa, lsa, plsa = stats(salvati)
    nns, wns, lns, plns = stats(non_salvati)

    print("=" * 70)
    print("  WHITELIST PROTEZIONE sui tip eliminati dal -3h")
    print("=" * 70)
    print(f"\n  Totale tip eliminati dal -3h: {ntot}")
    print(f"  Vincenti totali: {wtot}   Perdenti totali: {ltot}   PL: {pltot:+.2f}u\n")
    print(f"  🛡️  PROTETTI (non possono essere eliminati): {nsa}")
    print(f"      Vincenti: {wsa} ({wsa/nsa*100 if nsa else 0:.1f}%)   Perdenti: {lsa}   PL: {plsa:+.2f}u")
    print(f"\n  🗑️  LASCIATI ELIMINARE: {nns}")
    print(f"      Vincenti: {wns} ({wns/nns*100 if nns else 0:.1f}%)   Perdenti: {lns}   PL: {plns:+.2f}u")


if __name__ == '__main__':
    main()
