"""Whitelist protezione v2 con pattern trovati (puri >75%)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analizza_protezione_tolti import collect_tolti, quota_bucket

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report")


def protected(t):
    tipo = t['tipo']
    q = t.get('quota') or 0
    src = t.get('source') or ''
    elite = t['elite']
    mixer = t['mixer']
    low = t['low_value']
    pron = t['pronostico']
    # 1. Elite + Mixer + noLow
    if elite and mixer and not low:
        return True
    # 2. Quota 1.50-1.69 + Mixer + noLow
    if 1.50 <= q < 1.70 and mixer and not low:
        return True
    # 3. Mixer + noLow + origine_mattino
    if mixer and not low and t['origine_svuota']:
        return True
    # 4. GOL + quota 1.50-1.69 + source C_screm
    if tipo == 'GOL' and 1.50 <= q < 1.70 and src == 'C_screm':
        return True
    # 5. SEGNO + Mixer + origine_mattino
    if tipo == 'SEGNO' and mixer and t['origine_svuota']:
        return True
    # 6. source C_goal_conv
    if src == 'C_goal_conv':
        return True
    return False


def main():
    from datetime import datetime
    today = datetime.now().strftime('%Y-%m-%d')
    dates = sorted(d for d in os.listdir(REPORT_DIR)
                   if len(d) == 10 and d[4] == '-' and d < today)

    rows = collect_tolti(dates)
    salvati = [r for r in rows if protected(r)]
    buttati = [r for r in rows if not protected(r)]

    def stats(rs):
        n = len(rs)
        w = sum(1 for r in rs if r['hit'])
        l = n - w
        pl_win = sum(r['pl'] for r in rs if r['hit'])
        pl_loss = sum(r['pl'] for r in rs if not r['hit'])
        pl = pl_win + pl_loss
        return n, w, l, pl, pl_win, pl_loss

    ntot, wtot, ltot, pltot, plw_tot, pll_tot = stats(rows)
    nsav, wsav, lsav, plsav, plwsav, pllsav = stats(salvati)
    nbut, wbut, lbut, plbut, plwbut, pllbut = stats(buttati)

    print("=" * 74)
    print("  WHITELIST PROTEZIONE v2")
    print("=" * 74)
    print(f"\n  Totale tolti: {ntot}  Vincenti: {wtot}  Perdenti: {ltot}")
    print(f"\n  SALVATI: {nsav}  → win {wsav} ({wsav/nsav*100 if nsav else 0:.1f}%)  perd {lsav}")
    print(f"    PL vincenti recuperati: {plwsav:+.2f}u")
    print(f"    PL perdenti subiti:     {pllsav:+.2f}u")
    print(f"    Saldo salvataggi:       {plsav:+.2f}u")
    print(f"\n  BUTTATI: {nbut}  → win {wbut}  perd {lbut}")
    print(f"    PL vincenti ancora persi: {plwbut:+.2f}u")
    print(f"    Risparmio sui perdenti:   {-pllbut:+.2f}u")

    # Confronto scenari
    # A: attuale, tutti buttati → il sistema risparmia -pltot
    risparmio_attuale = -pltot
    # B: con protezione → risparmia -plbut (solo i buttati), subisce plsav (gioca i salvati)
    saldo_v2 = -plbut + plsav
    delta = saldo_v2 - risparmio_attuale

    print(f"\n  ═════════════════════════════════════")
    print(f"  Scenario attuale (butta tutti):   {risparmio_attuale:+.2f}u")
    print(f"  Scenario con whitelist v2:        {saldo_v2:+.2f}u")
    print(f"  DELTA:                            {delta:+.2f}u")
    if delta > 0:
        print(f"  ✅ La whitelist v2 migliora di {delta:.2f}u")
    else:
        print(f"  ❌ Non conviene")


if __name__ == '__main__':
    main()
