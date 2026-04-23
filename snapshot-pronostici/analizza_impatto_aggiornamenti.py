"""
ANALIZZA IMPATTO AGGIORNAMENTI
================================
Risponde a: "Gli aggiornamenti pre-match migliorano o peggiorano i pronostici?"

Confronta snapshot MATTINO (pre-aggiornamenti) vs SERALE (post-aggiornamenti)
e calcola il P/L dei pronostici SCARTATI vs AGGIUNTI dagli update.

Regola:
- PL scartati NEGATIVO  → gli update hanno tolto perdenti → MIGLIORANO
- PL scartati POSITIVO  → gli update hanno tolto vincenti → PEGGIORANO
- PL aggiunti POSITIVO  → gli update aggiungono valore
- PL aggiunti NEGATIVO  → gli update aggiungono spazzatura

Verdetto finale: (PL aggiunti) - (PL scartati) > 0 → update migliorano.
"""

import json
import os
import sys
from datetime import datetime

# Riutilizzo funzioni esistenti da snapshot_pronostici.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from snapshot_pronostici import fetch_results, calculate_hit, calc_pl

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report")


def tip_key(match, tip):
    """Chiave univoca: home|away|tipo|pronostico."""
    return (match['home'], match['away'], tip['tipo'], tip['pronostico'])


def match_key(match):
    return (match['home'], match['away'])


def load_snap(date, label):
    label_dir = os.path.join(REPORT_DIR, date, label)
    if not os.path.isdir(label_dir):
        return None
    files = sorted(f for f in os.listdir(label_dir) if f.endswith('.json'))
    if not files:
        return None
    path = os.path.join(label_dir, files[-1])
    if os.path.getsize(path) == 0:
        return None
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def index_tips(snap):
    """Ritorna dict: tip_key -> (match, tip). Salta NO BET e stake=0."""
    out = {}
    for m in snap['pronostici']:
        for t in m.get('tips', []):
            if t.get('pronostico') == 'NO BET':
                continue
            if (t.get('stake') or 0) <= 0:
                continue
            out[tip_key(m, t)] = (m, t)
    return out


def index_tips_by_match(snap):
    """Ritorna dict: (home,away) -> list of (match, tip). Salta NO BET e stake=0."""
    out = {}
    for m in snap['pronostici']:
        mk = match_key(m)
        for t in m.get('tips', []):
            if t.get('pronostico') == 'NO BET':
                continue
            if (t.get('stake') or 0) <= 0:
                continue
            out.setdefault(mk, []).append((m, t))
    return out


def score_for_match(results, home, away):
    """results = dict da fetch_results. Key 'home_away' → score 'H:A'."""
    return results.get(f"{home}_{away}")


def compute_pl(match, tip, score):
    """Ritorna (pl, hit) oppure (None, None) se non calcolabile."""
    if not score:
        return None, None
    hit = calculate_hit(tip.get('pronostico'), tip.get('tipo'), score)
    if hit is None:
        return None, None
    quota = tip.get('quota') or 0
    if quota <= 1:
        return None, None
    pl = calc_pl(hit, quota)  # usa stake=1 per confronto unitario
    return pl, hit


def classify_day(from_idx_by_match, to_idx_by_match, results):
    """
    Classifica le differenze tra due snapshot in 4 categorie:
      - sostituiti: partita in entrambi, set di tip cambiato → delta PL (nuovo - vecchio)
      - aggiunti_su_vuoto: partita solo nel 'to' (o senza tip nel 'from') → solo PL nuovo
      - scartati_senza_sost: partita solo nel 'from' → solo PL vecchio (perso)
      - invariati: partita con stesso set di tip → baseline
    Ritorna stats aggregate per ciascuna categoria.
    """
    # Stat: N_tip, N_hit_equiv, PL
    # Per 'sostituiti' contiamo come delta: PL_nuovo - PL_vecchio
    # e teniamo anche le sottocomponenti per diagnostica.

    stats = {
        'sostituiti_delta': [0, 0.0],                # (num_partite, delta_pl_totale)
        'sostituiti_old': [0, 0, 0.0],               # (n_tip_vecchi, hit, pl)
        'sostituiti_new': [0, 0, 0.0],               # (n_tip_nuovi, hit, pl)
        'aggiunti_su_vuoto': [0, 0, 0.0],            # (n, hit, pl)
        'scartati_senza_sost': [0, 0, 0.0],          # (n, hit, pl)  -- pl del vecchio
        'invariati': [0, 0, 0.0],                    # (n, hit, pl)  -- baseline
    }

    def pl_list(tip_list, results):
        """Ritorna (n, hit, pl_sum) per una lista di (match, tip)."""
        n_ok = 0
        n_hit = 0
        pl_sum = 0.0
        for match, tip in tip_list:
            score = score_for_match(results, match['home'], match['away'])
            pl, hit = compute_pl(match, tip, score)
            if pl is None:
                continue
            n_ok += 1
            pl_sum += pl
            if hit:
                n_hit += 1
        return n_ok, n_hit, pl_sum

    all_matches = set(from_idx_by_match.keys()) | set(to_idx_by_match.keys())
    for mk in all_matches:
        f_tips = from_idx_by_match.get(mk, [])
        t_tips = to_idx_by_match.get(mk, [])
        f_keys = {tip_key(m, t) for m, t in f_tips}
        t_keys = {tip_key(m, t) for m, t in t_tips}

        if f_keys == t_keys and f_keys:
            # Invariato: stesso set di tip
            n, h, pl = pl_list(t_tips, results)
            stats['invariati'][0] += n
            stats['invariati'][1] += h
            stats['invariati'][2] += pl
        elif f_keys and t_keys and f_keys != t_keys:
            # Sostituito: cambio di tip sulla stessa partita
            n_old, h_old, pl_old = pl_list(f_tips, results)
            n_new, h_new, pl_new = pl_list(t_tips, results)
            if n_old > 0 or n_new > 0:  # almeno uno valutabile
                stats['sostituiti_delta'][0] += 1
                stats['sostituiti_delta'][1] += (pl_new - pl_old)
                stats['sostituiti_old'][0] += n_old
                stats['sostituiti_old'][1] += h_old
                stats['sostituiti_old'][2] += pl_old
                stats['sostituiti_new'][0] += n_new
                stats['sostituiti_new'][1] += h_new
                stats['sostituiti_new'][2] += pl_new
        elif not f_keys and t_keys:
            # Aggiunto su vuoto
            n, h, pl = pl_list(t_tips, results)
            stats['aggiunti_su_vuoto'][0] += n
            stats['aggiunti_su_vuoto'][1] += h
            stats['aggiunti_su_vuoto'][2] += pl
        elif f_keys and not t_keys:
            # Scartato senza sostituzione
            n, h, pl = pl_list(f_tips, results)
            stats['scartati_senza_sost'][0] += n
            stats['scartati_senza_sost'][1] += h
            stats['scartati_senza_sost'][2] += pl

    return stats


def empty_1h_analysis():
    """Categorie di azioni del -1h, classificate in base a cosa aveva fatto il -3h.
       Ogni categoria ha [n_tip, hit, pl]."""
    return {
        # Sostituzioni del -1h: il tip cambia tra intermedio e serale
        'sost_ripristina_mattino':   [0, 0, 0.0],  # -1h rimette un tip che c'era al mattino e il -3h aveva tolto
        'sost_cambia_dopo_3h':       [0, 0, 0.0],  # il -3h aveva già cambiato, il -1h cambia ancora (doppio cambio)
        'sost_su_intatto_da_3h':     [0, 0, 0.0],  # il -3h non aveva toccato, il -1h decide di cambiare

        # Aggiunti su vuoto del -1h: compaiono tra intermedio e serale
        'add_nuovi_veri':            [0, 0, 0.0],  # partita era vuota al mattino e all'intermedio, -1h aggiunge
        'add_dopo_3h_aveva_tolto':   [0, 0, 0.0],  # al mattino c'era un altro tip, il -3h aveva svuotato, -1h riempie

        # Scartati senza sost. del -1h: spariscono tra intermedio e serale
        'scart_fix_aggiunta_3h':     [0, 0, 0.0],  # il tip era stato AGGIUNTO dal -3h (non c'era al mattino), -1h lo toglie
        'scart_svuota_originale':    [0, 0, 0.0],  # il tip c'era già al mattino, -3h l'aveva lasciato, -1h lo toglie
    }


def classify_1h_actions(m_by_match, i_by_match, s_by_match, results):
    """
    Per ogni azione del -1h (differenza intermedio→serale), guarda cosa
    aveva fatto il -3h (mattino→intermedio) sulla stessa partita/tip.
    """
    out = empty_1h_analysis()

    def pl_for(tip_list, results):
        n_ok, n_hit, pl_sum = 0, 0, 0.0
        for match, tip in tip_list:
            score = score_for_match(results, match['home'], match['away'])
            pl, hit = compute_pl(match, tip, score)
            if pl is None:
                continue
            n_ok += 1
            pl_sum += pl
            if hit:
                n_hit += 1
        return n_ok, n_hit, pl_sum

    def add_to(key, tip_list):
        n, h, pl = pl_for(tip_list, results)
        out[key][0] += n
        out[key][1] += h
        out[key][2] += pl

    all_matches = set(m_by_match.keys()) | set(i_by_match.keys()) | set(s_by_match.keys())
    for mk in all_matches:
        m_tips = m_by_match.get(mk, [])
        i_tips = i_by_match.get(mk, [])
        s_tips = s_by_match.get(mk, [])
        m_keys = {tip_key(mt, tt) for mt, tt in m_tips}
        i_keys = {tip_key(mt, tt) for mt, tt in i_tips}
        s_keys = {tip_key(mt, tt) for mt, tt in s_tips}

        # Azioni del -1h = differenza i -> s. Se uguali, nulla da classificare.
        if i_keys == s_keys:
            continue

        # --- CASO 1: SOSTITUZIONE ---
        # La partita aveva tip all'intermedio, ne ha al serale, ma set diversi
        if i_keys and s_keys:
            # Tip aggiunti dal -1h (erano assenti all'intermedio, presenti al serale)
            added_by_1h = [(mt, tt) for mt, tt in s_tips if tip_key(mt, tt) not in i_keys]
            # Tip rimossi dal -1h (presenti all'intermedio, assenti al serale)
            removed_by_1h = [(mt, tt) for mt, tt in i_tips if tip_key(mt, tt) not in s_keys]

            # Sottocasi per i TIP AGGIUNTI dal -1h durante sostituzione:
            for mt, tt in added_by_1h:
                k = tip_key(mt, tt)
                if k in m_keys:
                    # questo tip c'era al mattino, il -3h l'aveva rimosso, il -1h lo rimette
                    add_to('sost_ripristina_mattino', [(mt, tt)])
                elif m_keys != i_keys:
                    # il -3h aveva già cambiato il set di tip → -1h cambia ancora
                    add_to('sost_cambia_dopo_3h', [(mt, tt)])
                else:
                    # il -3h non aveva toccato questa partita → iniziativa del -1h
                    add_to('sost_su_intatto_da_3h', [(mt, tt)])

            # I tip rimossi dal -1h durante sostituzione: guardali come SCARTATI
            # (per capire se stavano fixing un'aggiunta del -3h o svuotando originali)
            for mt, tt in removed_by_1h:
                k = tip_key(mt, tt)
                if k not in m_keys and k in i_keys:
                    # il tip era stato aggiunto dal -3h (non al mattino, sì all'intermedio)
                    add_to('scart_fix_aggiunta_3h', [(mt, tt)])
                elif k in m_keys and k in i_keys:
                    # era presente già al mattino
                    add_to('scart_svuota_originale', [(mt, tt)])

            continue  # Già classificato come sostituzione

        # --- CASO 2: AGGIUNTA SU VUOTO ---
        # La partita era VUOTA all'intermedio, piena al serale
        if not i_keys and s_keys:
            for mt, tt in s_tips:
                if not m_keys:
                    # vuota sia al mattino che all'intermedio → aggiunta "vera"
                    add_to('add_nuovi_veri', [(mt, tt)])
                else:
                    # c'era roba al mattino, il -3h aveva svuotato, il -1h riempie
                    add_to('add_dopo_3h_aveva_tolto', [(mt, tt)])
            continue

        # --- CASO 3: SCARTATO SENZA SOSTITUZIONE ---
        # Piena all'intermedio, vuota al serale
        if i_keys and not s_keys:
            for mt, tt in i_tips:
                k = tip_key(mt, tt)
                if k not in m_keys:
                    # tip aggiunto dal -3h, ora -1h lo toglie → correzione
                    add_to('scart_fix_aggiunta_3h', [(mt, tt)])
                else:
                    # tip presente anche al mattino → -1h lo svuota
                    add_to('scart_svuota_originale', [(mt, tt)])
            continue

    return out


def analyze_day(date, results):
    m = load_snap(date, 'mattino')
    i = load_snap(date, 'intermedio')
    s = load_snap(date, 'serale')
    if not m or not s:
        return None

    m_by_match = index_tips_by_match(m)
    s_by_match = index_tips_by_match(s)
    i_by_match = index_tips_by_match(i) if i else None

    out = {
        'date': date,
        'intermedio_presente': i_by_match is not None,
        'global': classify_day(m_by_match, s_by_match, results),
    }
    if i_by_match is not None:
        out['mi'] = classify_day(m_by_match, i_by_match, results)  # -3h
        out['is'] = classify_day(i_by_match, s_by_match, results)  # -1h
        out['1h_detail'] = classify_1h_actions(m_by_match, i_by_match, s_by_match, results)
    return out


def accumulate(cum, stats):
    """Somma stats di un giorno in cum (entrambi dict con stesse chiavi)."""
    for k, v in stats.items():
        for j in range(len(v)):
            cum[k][j] += v[j]


def empty_cum():
    return {
        'sostituiti_delta': [0, 0.0],
        'sostituiti_old': [0, 0, 0.0],
        'sostituiti_new': [0, 0, 0.0],
        'aggiunti_su_vuoto': [0, 0, 0.0],
        'scartati_senza_sost': [0, 0, 0.0],
        'invariati': [0, 0, 0.0],
    }


def hr(n, h):
    return (h / n * 100) if n > 0 else 0


def roi_of(n, pl):
    return (pl / n * 100) if n > 0 else 0


def total_impact(cum):
    return cum['sostituiti_delta'][1] + cum['aggiunti_su_vuoto'][2] - cum['scartati_senza_sost'][2]


def print_summary_line(label, cum, width=30):
    d_sost = cum['sostituiti_delta'][1]
    pl_avv = cum['aggiunti_su_vuoto'][2]
    pl_sns = cum['scartati_senza_sost'][2]
    tot = d_sost + pl_avv - pl_sns
    icon = '✅' if tot > 0 else ('❌' if tot < 0 else '⚖️')
    print(f"  {label:<{width}} {tot:>+8.2f}u  {icon}")


def print_detail(cum):
    n_part_sost, d_sost = cum['sostituiti_delta']
    n_old, h_old, pl_old = cum['sostituiti_old']
    n_new, h_new, pl_new = cum['sostituiti_new']
    n_avv, h_avv, pl_avv = cum['aggiunti_su_vuoto']
    n_sns, h_sns, pl_sns = cum['scartati_senza_sost']
    n_inv, h_inv, pl_inv = cum['invariati']
    tot = d_sost + pl_avv - pl_sns

    print(f"    Cambio tip su stessa partita ({n_part_sost} partite)")
    print(f"      Vecchi: {n_old:>3} tip  HR {hr(n_old, h_old):>4.1f}%  PL {pl_old:>+7.2f}u")
    print(f"      Nuovi:  {n_new:>3} tip  HR {hr(n_new, h_new):>4.1f}%  PL {pl_new:>+7.2f}u")
    print(f"      → Delta del cambio: {d_sost:>+7.2f}u")
    print(f"    Aggiunti su partita vuota:  {n_avv:>3} tip  PL {pl_avv:>+7.2f}u  (contribuisce {pl_avv:>+7.2f}u)")
    print(f"    Scartati senza sostituire:  {n_sns:>3} tip  PL {pl_sns:>+7.2f}u  (contribuisce {-pl_sns:>+7.2f}u)")
    print(f"    Invariati (baseline):       {n_inv:>3} tip  HR {hr(n_inv, h_inv):>4.1f}%  PL {pl_inv:>+7.2f}u")
    print(f"    ────────────────────────────────────────────────")
    print(f"    TOTALE IMPATTO:             {tot:>+7.2f}u")


def main():
    today = datetime.now().strftime('%Y-%m-%d')
    dates = sorted(d for d in os.listdir(REPORT_DIR)
                   if len(d) == 10 and d[4] == '-' and d < today)

    cum_global = empty_cum()
    cum_mi = empty_cum()
    cum_is = empty_cum()
    cum_1h = empty_1h_analysis()
    days_processed = 0
    days_skipped = 0
    days_with_intermedio = 0

    for date in dates:
        results = fetch_results(date)
        if not results:
            days_skipped += 1
            continue
        r = analyze_day(date, results)
        if r is None:
            days_skipped += 1
            continue
        days_processed += 1
        accumulate(cum_global, r['global'])
        if r['intermedio_presente']:
            days_with_intermedio += 1
            accumulate(cum_mi, r['mi'])
            accumulate(cum_is, r['is'])
            # Accumula analisi dettagliata -1h
            for k, v in r['1h_detail'].items():
                for j in range(len(v)):
                    cum_1h[k][j] += v[j]

    # ================== HEADER ==================
    print()
    print("=" * 72)
    print("  IMPATTO AGGIORNAMENTI PRE-MATCH SUI PRONOSTICI")
    print("=" * 72)
    print(f"  Periodo: {dates[0]} → {dates[-1]}  ({days_processed} giorni validi)")
    print()

    # ================== RISPOSTA IN UNA RIGA ==================
    tot_g = total_impact(cum_global)
    print("┌" + "─" * 70 + "┐")
    print("│  RISPOSTA: gli aggiornamenti stanno MIGLIORANDO o PEGGIORANDO?     │")
    print("│" + " " * 70 + "│")
    verdict = "✅ MIGLIORANO" if tot_g > 0 else ("❌ PEGGIORANO" if tot_g < 0 else "⚖️  NEUTRI")
    linea = f"  {verdict}    →    impatto netto: {tot_g:+.2f}u  (su {days_processed} giorni)"
    print(f"│{linea:<70}│")
    print("└" + "─" * 70 + "┘")
    print()

    # ================== CONFRONTO I DUE UPDATE ==================
    if days_with_intermedio > 0:
        print("━" * 72)
        print("  QUALE DEI DUE UPDATE SI COMPORTA MEGLIO? (diagnostica isolata)")
        print("━" * 72)
        print_summary_line("Update -3h (mattino→interm.):", cum_mi)
        print_summary_line("Update -1h (interm.→serale):", cum_is)
        print()
        print("  NOTA: questi due numeri NON si sommano al totale globale.")
        print("  Se il -3h scarta un tip e il -1h lo rimette, nel globale")
        print("  risulta 'invariato'. Il -3h e -1h si compensano a vicenda.")
        print()

    # ================== DETTAGLIO GLOBALE ==================
    print("━" * 72)
    print("  DETTAGLIO GLOBALE (mattino → serale, quello che vede l'utente)")
    print("━" * 72)
    print_detail(cum_global)
    print()

    # ================== DETTAGLIO PER UPDATE ==================
    if days_with_intermedio > 0:
        print("━" * 72)
        print("  DETTAGLIO UPDATE -3h  (mattino → intermedio)")
        print("━" * 72)
        print_detail(cum_mi)
        print()
        print("━" * 72)
        print("  DETTAGLIO UPDATE -1h  (intermedio → serale)")
        print("━" * 72)
        print_detail(cum_is)
        print()

        # ================== COSA FA DAVVERO IL -1h? ==================
        print("━" * 72)
        print("  COSA FA DAVVERO IL -1h? (azioni divise per origine)")
        print("━" * 72)
        c = cum_1h
        print()
        print("  AZIONI SOSTITUZIONE (-1h cambia il tip)")
        n, h, pl = c['sost_ripristina_mattino']
        print(f"    Ripristina tip del mattino (il -3h l'aveva tolto):   N={n:>3}  HR={hr(n,h):>4.1f}%  PL={pl:>+7.2f}u")
        n, h, pl = c['sost_cambia_dopo_3h']
        print(f"    Cambia ancora un tip già cambiato dal -3h:           N={n:>3}  HR={hr(n,h):>4.1f}%  PL={pl:>+7.2f}u")
        n, h, pl = c['sost_su_intatto_da_3h']
        print(f"    Cambia un tip che il -3h aveva lasciato invariato:   N={n:>3}  HR={hr(n,h):>4.1f}%  PL={pl:>+7.2f}u")
        print()
        print("  AZIONI AGGIUNTA (-1h aggiunge su partita vuota)")
        n, h, pl = c['add_nuovi_veri']
        print(f"    Nuovi puri (partita vuota al mattino E intermedio):  N={n:>3}  HR={hr(n,h):>4.1f}%  PL={pl:>+7.2f}u")
        n, h, pl = c['add_dopo_3h_aveva_tolto']
        print(f"    Riempie partita che il -3h aveva svuotato:           N={n:>3}  HR={hr(n,h):>4.1f}%  PL={pl:>+7.2f}u")
        print()
        print("  AZIONI SCARTO (-1h rimuove tip)")
        n, h, pl = c['scart_fix_aggiunta_3h']
        print(f"    Corregge aggiunta del -3h (non c'era al mattino):    N={n:>3}  HR={hr(n,h):>4.1f}%  PL={pl:>+7.2f}u")
        n, h, pl = c['scart_svuota_originale']
        print(f"    Svuota tip originale (c'era già al mattino):         N={n:>3}  HR={hr(n,h):>4.1f}%  PL={pl:>+7.2f}u")

        # Aggregati: quanto del lavoro del -1h è "riparazione" del -3h?
        rip_tips = c['sost_ripristina_mattino'][0] + c['sost_cambia_dopo_3h'][0] + c['add_dopo_3h_aveva_tolto'][0] + c['scart_fix_aggiunta_3h'][0]
        ind_tips = c['sost_su_intatto_da_3h'][0] + c['add_nuovi_veri'][0] + c['scart_svuota_originale'][0]
        rip_pl = c['sost_ripristina_mattino'][2] + c['sost_cambia_dopo_3h'][2] + c['add_dopo_3h_aveva_tolto'][2] - c['scart_fix_aggiunta_3h'][2]
        ind_pl = c['sost_su_intatto_da_3h'][2] + c['add_nuovi_veri'][2] - c['scart_svuota_originale'][2]
        print()
        print(f"  ════════════════════════════════════════════════════")
        print(f"  RIPARAZIONI (-1h reagisce a qualcosa del -3h):  {rip_tips} tip  impact {rip_pl:+.2f}u")
        print(f"  INIZIATIVE (-1h sceglie indipendentemente):     {ind_tips} tip  impact {ind_pl:+.2f}u")
        print()


if __name__ == '__main__':
    main()
