"""Whitelist sui 122 aggiunti dal -3h."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trova_pattern_3h_aggiunti import collect

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report")


def wl(t):
    q = t.get('quota') or 0
    s = t.get('stars') or 0
    src = t.get('source') or ''
    tipo = t['tipo']
    pron = t['pronostico']
    # 1. Stelle ≥ 4.0
    if s >= 4.0: return True
    # 2. GOL + quota 1.50-1.69
    if tipo == 'GOL' and 1.50 <= q < 1.70: return True
    # 3. Quota 1.90-2.19 + source C + non Mixer
    if 1.90 <= q < 2.20 and src == 'C' and not t['mixer']: return True
    # 4. SEGNO + quota 1.90-2.19 + source C
    if tipo == 'SEGNO' and 1.90 <= q < 2.20 and src == 'C': return True
    # 5. DC X2 + quota 1.30-1.49
    if tipo == 'DOPPIA_CHANCE' and pron == 'X2' and 1.30 <= q < 1.50: return True
    # 6. GOL NoGoal
    if tipo == 'GOL' and pron and pron.lower() == 'nogoal': return True
    return False


def main():
    from datetime import datetime
    today = datetime.now().strftime('%Y-%m-%d')
    dates = sorted(d for d in os.listdir(REPORT_DIR) if len(d) == 10 and d[4] == '-' and d < today)
    rows = collect(dates)

    salvati = [r for r in rows if wl(r)]
    buttati = [r for r in rows if not wl(r)]

    def stats(rs):
        n = len(rs); w = sum(1 for r in rs if r['hit'])
        pl = sum(r['pl'] for r in rs)
        return n, w, n-w, pl

    n_tot, w_tot, l_tot, pl_tot = stats(rows)
    n_sa, w_sa, l_sa, pl_sa = stats(salvati)
    n_bu, w_bu, l_bu, pl_bu = stats(buttati)

    print("=" * 70)
    print("  WHITELIST 6 pattern sui 122 aggiunti dal -3h")
    print("=" * 70)
    print(f"\n  Totale: {n_tot} tip  ({w_tot} win, {l_tot} loss, PL {pl_tot:+.2f}u)")
    print(f"\n  🛡️  TENUTI: {n_sa}  win {w_sa}  loss {l_sa}  (%Win {w_sa/n_sa*100:.1f}%)  PL {pl_sa:+.2f}u")
    print(f"  🗑️  FILTRATI (NO BET): {n_bu}  win {w_bu}  loss {l_bu}  (%Win {w_bu/n_bu*100:.1f}%)  PL {pl_bu:+.2f}u")
    print()
    delta = pl_sa - pl_tot
    print(f"  Scenario attuale (tutti giocati): {pl_tot:+.2f}u")
    print(f"  Scenario con whitelist:           {pl_sa:+.2f}u")
    print(f"  DELTA: {delta:+.2f}u")


if __name__ == '__main__':
    main()
