"""
WHITELIST di PROTEZIONE per tip tolti dal -1h.
Se un tip matcha la whitelist, il -1h NON può toglierlo.
Calcolo: quanti dei 250 tolti salveremmo, quanti vincenti, quanti perdenti.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analizza_protezione_tolti import collect_tolti

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report")


# WHITELIST di PROTEZIONE
def protected(t):
    tipo = t['tipo']
    pron = t['pronostico']
    q = t.get('quota') or 0
    src = t.get('source') or ''
    # 1. GOL + quota 1.50-1.69
    if tipo == 'GOL' and 1.50 <= q < 1.70:
        return True
    # 2. DC + quota 1.30-1.49
    if tipo == 'DOPPIA_CHANCE' and 1.30 <= q < 1.50:
        return True
    # 3. GOL + Mixer
    if tipo == 'GOL' and t['mixer']:
        return True
    # 4. DC + Elite
    if tipo == 'DOPPIA_CHANCE' and t['elite']:
        return True
    # 5. Source C_goal_conv
    if src == 'C_goal_conv':
        return True
    # 6. Elite + Mixer insieme
    if t['elite'] and t['mixer']:
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
        pl = sum(r['pl'] for r in rs)
        pl_win = sum(r['pl'] for r in rs if r['hit'])
        pl_loss = sum(r['pl'] for r in rs if not r['hit'])
        return n, w, l, pl, pl_win, pl_loss

    ntot, wtot, ltot, pltot, plw, pll = stats(rows)
    nsav, wsav, lsav, plsav, plwsav, pllsav = stats(salvati)
    nbut, wbut, lbut, plbut, plwbut, pllbut = stats(buttati)

    print("=" * 74)
    print("  RISULTATO WHITELIST PROTEZIONE")
    print("=" * 74)
    print(f"\n  TOTALE TIP TOLTI dal -1h: {ntot}  (vincenti {wtot}, perdenti {ltot})")
    print(f"  PL complessivo tolti: {pltot:+.2f}u\n")

    print(f"  🛡️  SALVATI dalla protezione: {nsav}/{ntot} ({nsav/ntot*100:.1f}%)")
    print(f"       - Vincenti salvati (giusto!):   {wsav}  → guadagno recuperato: {plwsav:+.2f}u")
    print(f"       - Perdenti salvati (errore):    {lsav}  → costo aggiuntivo: {pllsav:+.2f}u")
    print(f"       - Saldo netto salvataggio: {plsav:+.2f}u")
    print()
    print(f"  🗑️  ANCORA BUTTATI: {nbut}/{ntot} ({nbut/ntot*100:.1f}%)")
    print(f"       - Vincenti buttati (errore):   {wbut}  → guadagno ancora perso: {plwbut:+.2f}u")
    print(f"       - Perdenti buttati (giusto):   {lbut}  → risparmio: {pllbut:+.2f}u")
    print(f"       - Saldo netto buttati: {plbut:+.2f}u")

    print()
    print("━" * 74)
    print("  CONFRONTO SCENARI")
    print("━" * 74)
    # Scenario A: situazione attuale (tutti buttati)
    # Saldo attuale = - pl_tot (perché togliere risparmia -pltot)
    risparmio_attuale = -pltot
    # Scenario B: con whitelist protezione (butta solo i non protetti, salva gli altri)
    # Saldo = -pl(buttati) - 0 (salvati restano come sono, si gioca il loro pl)
    # L'utente guadagna: dagli effetti del buttati c'è risparmio (-plbut), dai salvati gioca (+plsav)
    saldo_whitelist = -plbut + plsav
    delta = saldo_whitelist - risparmio_attuale

    print(f"\n  Scenario A (ATTUALE, butta tutti i 250): il sistema 'guadagna' {risparmio_attuale:+.2f}u")
    print(f"                                            (= risparmio netto togliendo tip)")
    print(f"\n  Scenario B (CON WHITELIST di protezione):")
    print(f"      - Butta i {nbut} non protetti → risparmio {-plbut:+.2f}u")
    print(f"      - Salva i {nsav} protetti → PL giocato {plsav:+.2f}u")
    print(f"      - SALDO totale: {saldo_whitelist:+.2f}u")
    print(f"\n  Δ vs scenario attuale: {delta:+.2f}u  ", end='')
    if delta > 0:
        print("✅ LA WHITELIST MIGLIORA")
    elif delta < 0:
        print("❌ la whitelist peggiora")
    else:
        print("⚖️  neutro")


if __name__ == '__main__':
    main()
