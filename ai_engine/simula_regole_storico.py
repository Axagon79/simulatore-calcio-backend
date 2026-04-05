"""
SIMULAZIONE REGOLE ORCHESTRATORE SU STORICO
=============================================
Ri-processa tutti i pronostici nel range con le regole ATTUALI
dell'orchestratore (dry-run, ZERO scritture su DB), confronta
con i risultati reali e produce un report .txt dettagliato.

Uso:
  python ai_engine/simula_regole_storico.py --from 2026-02-05 --to 2026-04-05
  python ai_engine/simula_regole_storico.py --date 2026-04-04
"""
import sys, os, argparse, io, time
from datetime import datetime, timedelta

# Path setup
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.join(SCRIPT_DIR, '..')
ORCH_DIR = os.path.join(ROOT_DIR, 'functions_python', 'ai_engine', 'calculators')

sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, 'functions_python', 'ai_engine'))
sys.path.insert(0, ORCH_DIR)

from config import db
from orchestrate_experts import orchestrate_date


# =====================================================
# UTILITA
# =====================================================
def get_market_type(p):
    p = p.strip()
    if p in ('1', 'X', '2'): return 'SEGNO'
    if p in ('1X', 'X2', '12'): return 'DC'
    if p.startswith('Over') or p.startswith('Under') or p in ('Goal', 'GG', 'NoGoal', 'NG'): return 'GOL'
    if p.startswith('MG'): return 'MG'
    if p == 'NO BET': return 'NOBET'
    return 'ALTRO'


def get_section(e):
    if e.get('elite'): return 'Elite'
    if (e.get('curr_q') or 0) >= 2.51: return 'Alto Rend.'
    return 'Pronostici'


def is_pronostici(e):
    """Filtro sezione Pronostici: quota < 2.50, DC < 2.00."""
    q = e.get('curr_q') or 0
    pr = e.get('curr_pr', '')
    if pr in ('1X', 'X2', '12'):
        return q < 2.00
    return q < 2.50


def check_hit(p, h, a):
    p = p.strip()
    t = h + a
    return {
        '1': h > a, 'X': h == a, '2': h < a,
        '1X': h >= a, 'X2': h <= a, '12': h != a,
        'Over 0.5': t > 0, 'Over 1.5': t > 1, 'Over 2.5': t > 2, 'Over 3.5': t > 3,
        'Under 0.5': t < 1, 'Under 1.5': t < 2, 'Under 2.5': t < 3, 'Under 3.5': t < 4,
        'Goal': h > 0 and a > 0, 'GG': h > 0 and a > 0,
        'NoGoal': h == 0 or a == 0, 'NG': h == 0 or a == 0,
        'MG 2-3': 2 <= t <= 3, 'MG 2-4': 2 <= t <= 4, 'MG 3-5': 3 <= t <= 5,
    }.get(p)


def calc_pl(hit, q, s):
    return round(s * (q - 1), 2) if hit else round(-s, 2)


def classify(orig, curr, om, cm):
    if curr == 'NO BET': return 'NOBET'
    if not orig or orig == curr: return 'INVARIATO'
    if om != cm: return 'CAMBIO_MERCATO'
    return 'STESSO_MERCATO'


SC_LABELS = {
    'INVARIATO': 'INVARIATO',
    'CAMBIO_MERCATO': 'CAMBIO MERCATO',
    'STESSO_MERCATO': 'STESSO MERCATO',
    'NOBET': 'NO BET',
}

BADGE = {
    'single': 'SNG', 'consensus_both': 'A+S', 'priority_chain': 'PRI', 'union': 'UNI',
    'scrematura_segno': 'SCR', 'scrematura_segno_x': 'SCR-X',
    'screm_dc_to_over15': 'SCR-O1.5', 'screm_dc_to_under25': 'SCR-U25', 'screm_o15_to_dc': 'SCR-DC',
    'mc_filter_convert': 'MCF',
    'as_o25_to_dc': 'REC-DC', 'as_o25_to_segno1': 'REC-1', 'as_o25_to_under25': 'REC-U25',
    'goal_to_u25': 'G-U25', 'goal_to_o15': 'G-O15',
    'o25_s6_to_goal': 'O25-G', 'dc_s6_to_goal': 'DC-G',
    'dc_s1_to_u25': 'DC-U25', 'mg23_s4_to_u25': 'MG-U25', 'o15_s5_low_to_u25': 'O15-U25',
    'gol_s1_to_ng': 'G1-NG', 'gol_s2_to_ng': 'G2-NG', 'gol_s5_q160_to_ng': 'G5-NG',
    'dc_s4_to_ng': 'DC-NG', 'dcx2_s9_f180_to_ng': 'X2-NG',
    'segno_s6_to_o25': 'SE-O25', 'segno_s9_f150_to_goal': 'SE9-G',
    'gg_conf_dc_downgrade': 'GG-DC', 'u25_high_segno_add': '+SE',
    'gol_s3_filter': 'G3x', 'gol_s4_filter': 'G4x', 'gol_s4_q180_filter': 'G4qx',
    'gol_s7_filter': 'G7x', 'u25_s7_nobet': 'U25x', 'mg23_s7_nobet': 'MGx',
    'gol_s7_q190_nobet': 'G7qx', 'segno_s1_low_q_filter': 'SE1x',
    'x2_s2_filter': 'X2x', 'segno_s2_toxic_q_filter': 'SE2x',
    'se2_s8_q190_filter': 'SE8x',
    'se2_s9_f180_cap6': 'CAP6', 'gol_s8_q150_cap6': 'CAP6', 'segno_s7_weak_q_cap5': 'CAP5',
    'combo_96_dc_flip': 'FLIP', 'multigol_v6': 'MG',
    'goal_q190_to_u25': 'G19-U', 'goal_q170_to_o15': 'G17-O',
}

def badge(rule):
    if rule in BADGE: return BADGE[rule]
    if rule.startswith('home_win_combo_'): return f'HW{rule.split("_")[-1]}'
    if rule.startswith('x_draw_combo_'): return f'XD{rule.split("_")[-1]}'
    if rule.startswith('diamond_pattern_'): return f'DIA{rule.split("_")[-1]}'
    return rule[:7]


# =====================================================
# CARICA RISULTATI
# =====================================================
def load_results(d1, d2):
    from datetime import datetime as dt
    r = {}
    date_start = dt.strptime(d1, '%Y-%m-%d')
    date_end = dt.strptime(d2, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    for doc in db.h2h_by_round.find(
        {'matches.date_obj': {'$gte': date_start, '$lte': date_end}},
        {'matches': 1}
    ):
        for m in doc.get('matches', []):
            do = m.get('date_obj')
            if not do: continue
            dv = str(do)[:10]
            if dv < d1 or dv > d2: continue
            sc = m.get('real_score', '')
            if sc and ':' in sc:
                try:
                    hg, ag = int(sc.split(':')[0]), int(sc.split(':')[1])
                    r[f"{dv}_{m['home']}_vs_{m['away']}"] = (hg, ag)
                except: pass
    return r


# =====================================================
# SIMULAZIONE + ANALISI
# =====================================================
def simulate_and_analyze(date_from, date_to):
    out_name = f"sim_regole_{date_from}_{date_to}.txt" if date_from != date_to else f"sim_regole_{date_from}.txt"
    out_dir = os.path.join(ROOT_DIR, 'log')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, out_name)
    L = []
    W = 120

    def w(s=''):
        L.append(s)

    def sep(char='='):
        w(char * W)

    def header(title):
        w()
        sep()
        w(f'  {title}')
        sep()
        w()

    # 1. Carica risultati reali
    print("Caricamento risultati reali...")
    results_map = load_results(date_from, date_to)
    print(f"Risultati trovati: {len(results_map)}")

    # 2. Simula orchestratore per ogni data (dry-run)
    print("\nSimulazione orchestratore (dry-run)...")
    start = datetime.strptime(date_from, '%Y-%m-%d')
    end = datetime.strptime(date_to, '%Y-%m-%d')
    dates = []
    d = start
    while d <= end:
        dates.append(d.strftime('%Y-%m-%d'))
        d += timedelta(days=1)

    all_unified_docs = []
    total_days = len(dates)
    t_start = time.time()

    for i, dt_str in enumerate(dates):
        # Silenzia output orchestratore
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            result = orchestrate_date(dt_str, dry_run=True)
            if isinstance(result, list):
                all_unified_docs.extend(result)
                n = len(result)
            else:
                n = result
        except Exception as e:
            sys.stdout = old_stdout
            print(f"  ERRORE {dt_str}: {e}")
            continue
        finally:
            sys.stdout = old_stdout

        # Barra di avanzamento
        done = i + 1
        pct = done / total_days * 100
        elapsed = time.time() - t_start
        avg = elapsed / done
        eta = avg * (total_days - done)
        eta_m, eta_s = int(eta // 60), int(eta % 60)
        bar_len = 40
        filled = int(bar_len * done / total_days)
        bar = '#' * filled + '-' * (bar_len - filled)
        print(f"\r  [{bar}] {pct:5.1f}%  {done}/{total_days}  ETA {eta_m}m{eta_s:02d}s  ({dt_str} — {n} partite)", end='', flush=True)

    elapsed_total = time.time() - t_start
    print(f"\n\nTotale documenti simulati: {len(all_unified_docs)}  (tempo: {int(elapsed_total//60)}m{int(elapsed_total%60):02d}s)")

    # 3. Confronta con risultati reali
    all_entries = []
    for doc in all_unified_docs:
        date = doc.get('date', '')
        home = doc.get('home', '')
        away = doc.get('away', '')
        key = f"{date}_{home}_vs_{away}"

        if key not in results_map:
            continue
        hg, ag = results_map[key]

        for p in doc.get('pronostici', []):
            if p.get('tipo') == 'RISULTATO_ESATTO': continue
            curr_pr = p.get('pronostico', '')
            curr_q = p.get('quota', 0) or 0
            stake = p.get('stake', 0) or 0
            orig_pr = p.get('original_pronostico', '') or curr_pr
            orig_q = p.get('original_quota', 0) or 0
            om = get_market_type(orig_pr)
            cm = get_market_type(curr_pr)
            sc = classify(orig_pr, curr_pr, om, cm)
            ch = check_hit(curr_pr, hg, ag)
            oh = check_hit(orig_pr, hg, ag) if orig_pr and orig_pr != 'NO BET' else None
            all_entries.append({
                'match': f"{home} vs {away}", 'date': date,
                'score': f"{hg}:{ag}", 'scenario': sc, 'rule': p.get('routing_rule', 'none') or 'none',
                'orig_pr': orig_pr, 'orig_q': orig_q,
                'curr_pr': curr_pr, 'curr_q': curr_q,
                'orig_hit': oh, 'curr_hit': ch, 'stake': stake,
                'elite': p.get('elite', False),
                'pl_actual': calc_pl(ch, curr_q, stake) if ch is not None else 0,
                'pl_original': calc_pl(oh, orig_q if orig_q > 0 else curr_q, stake) if oh is not None else 0,
            })

    print(f"Pronostici con risultato: {len(all_entries)}")

    # 4. Raggruppa per regola
    rules = {}
    for e in all_entries:
        rules.setdefault(e['rule'], []).append(e)

    sorted_rules = sorted(rules.keys(), key=lambda r: sum(
        e['pl_actual'] - e['pl_original'] for e in rules[r]
        if e['scenario'] != 'INVARIATO' and e['orig_hit'] is not None
    ))

    # =====================================================
    # REPORT
    # =====================================================

    # INTESTAZIONE
    sep()
    w(f'  SIMULAZIONE REGOLE ORCHESTRATORE (REGOLE ATTUALI SU STORICO)')
    w(f'  Periodo: {date_from}  ->  {date_to}')
    w(f'  Generato: {datetime.now().strftime("%d/%m/%Y %H:%M")}')
    w(f'  Partite con risultato: {len(results_map)}   Documenti simulati: {len(all_unified_docs)}')
    w(f'  Pronostici analizzati: {len(all_entries)} (esclusi RE)')
    sep()

    # RIEPILOGO GLOBALE
    header('RIEPILOGO GLOBALE')
    tot_wr = [e for e in all_entries if e['curr_hit'] is not None and e['scenario'] != 'NOBET']
    tot_h = sum(1 for e in tot_wr if e['curr_hit'])
    tot_m = sum(1 for e in tot_wr if not e['curr_hit'])
    tot_pl = sum(e['pl_actual'] for e in tot_wr)
    if tot_h + tot_m > 0:
        w(f'  Totale:  {tot_h}/{tot_h+tot_m} ({tot_h/(tot_h+tot_m)*100:.1f}%)  P/L: {tot_pl:+.1f}u')

    # Per scenario
    for sc_code in ['INVARIATO', 'CAMBIO_MERCATO', 'STESSO_MERCATO']:
        sc_wr = [e for e in tot_wr if e['scenario'] == sc_code]
        if not sc_wr: continue
        sh = sum(1 for e in sc_wr if e['curr_hit'])
        sm = sum(1 for e in sc_wr if not e['curr_hit'])
        sp = sum(e['pl_actual'] for e in sc_wr)
        w(f'  {SC_LABELS[sc_code]:<20s}  {sh}/{sh+sm} ({sh/(sh+sm)*100:.1f}%)  P/L: {sp:+.1f}u')

    # NO BET
    nb_entries = [e for e in all_entries if e['scenario'] == 'NOBET']
    if nb_entries:
        nb_h = sum(1 for e in nb_entries if e['orig_hit'] is True)
        nb_m = sum(1 for e in nb_entries if e['orig_hit'] is False)
        nb_pl = sum(e['pl_original'] for e in nb_entries if e['orig_hit'] is not None)
        w(f'  NO BET filtrati: {len(nb_entries)}  (avrebbero centrato: {nb_h}, mancato: {nb_m}, P/L perso: {nb_pl:+.1f}u)')

    # Delta controfattuale globale
    tf = [e for e in tot_wr if e['scenario'] != 'INVARIATO' and e['orig_hit'] is not None]
    delta_gl = sum(e['pl_actual'] - e['pl_original'] for e in tf)
    sv_gl = sum(1 for e in tf if e['curr_hit'] and e['orig_hit'] is False)
    dm_gl = sum(1 for e in tf if not e['curr_hit'] and e['orig_hit'] is True)
    w()
    w(f'  Delta controfattuale globale: {delta_gl:+.1f}u  (salvati: {sv_gl}, danneggiati: {dm_gl})')

    # CLASSIFICA
    header('CLASSIFICA REGOLE — SOLO PRONOSTICI (quota < 2.50, DC < 2.00)')
    w(f'  Legenda: HR ATT = dopo trasformazione | HR ORIG = se avessimo tenuto l\'originale | DELTA = P/L ATT - P/L ORIG')
    w()

    w(f'  {"BADGE":<8s} {"REGOLA":<28s} {"N":>4s}  {"HR ATTUALE":>14s} {"P/L ATT":>9s}  {"HR ORIGINALE":>14s} {"P/L ORIG":>9s}  {"DELTA":>9s}  {"SALV":>5s} {"DANN":>5s}  {"VERD":>6s}')
    w(f'  {"-"*8} {"-"*28}  {"----":>4s}  {"-"*14} {"-"*9}  {"-"*14} {"-"*9}  {"-"*9}  {"-----":>5s} {"-----":>5s}  {"-"*6}')

    for rule in sorted_rules:
        ee = [e for e in rules[rule] if is_pronostici(e)]
        wr = [e for e in ee if e['curr_hit'] is not None and e['scenario'] != 'NOBET']
        if not wr: continue
        th = sum(1 for e in wr if e['curr_hit'])
        tm = sum(1 for e in wr if not e['curr_hit'])
        tp = sum(e['pl_actual'] for e in wr)
        tf_r = [e for e in wr if e['scenario'] != 'INVARIATO']
        delta = sum(e['pl_actual'] - e['pl_original'] for e in tf_r if e['orig_hit'] is not None)
        sv = sum(1 for e in tf_r if e['curr_hit'] and e['orig_hit'] is False)
        dm = sum(1 for e in tf_r if not e['curr_hit'] and e['orig_hit'] is True)

        # HR e P/L originale (solo per entries trasformate con orig_hit valido)
        tf_valid = [e for e in tf_r if e['orig_hit'] is not None]
        if tf_valid:
            oh_count = sum(1 for e in tf_valid if e['orig_hit'])
            om_count = sum(1 for e in tf_valid if not e['orig_hit'])
            o_pl = sum(e['pl_original'] for e in tf_valid)
            ah_count = sum(1 for e in tf_valid if e['curr_hit'])
            am_count = sum(1 for e in tf_valid if not e['curr_hit'])
            a_pl = sum(e['pl_actual'] for e in tf_valid)
            hr_att = f"{ah_count}/{ah_count+am_count} ({ah_count/(ah_count+am_count)*100:.0f}%)"
            hr_orig = f"{oh_count}/{oh_count+om_count} ({oh_count/(oh_count+om_count)*100:.0f}%)"
        else:
            hr_att = f"{th}/{th+tm} ({th/(th+tm)*100:.0f}%)"
            hr_orig = '-'
            a_pl = tp
            o_pl = 0

        if not tf_r: v = 'base'
        elif delta > 5: v = 'TOP'
        elif delta > 0: v = 'OK'
        elif delta > -2: v = '~'
        elif delta > -10: v = 'MALE'
        else: v = 'GRAVE'

        w(f'  {badge(rule):<8s} {rule:<28s} {th+tm:>4d}  {hr_att:>14s} {a_pl:>+9.1f}  {hr_orig:>14s} {o_pl:>+9.1f}  {delta:>+9.1f}  {sv:>5d} {dm:>5d}  {v:>6s}')

    # DETTAGLIO PER REGOLA
    for rule in sorted_rules:
        ee = rules[rule]
        wr = [e for e in ee if e['curr_hit'] is not None and e['scenario'] != 'NOBET']
        nb = [e for e in ee if e['scenario'] == 'NOBET']
        if not wr and not nb: continue

        th = sum(1 for e in wr if e['curr_hit'])
        tm = sum(1 for e in wr if not e['curr_hit'])
        tp = sum(e['pl_actual'] for e in wr)
        tf_r = [e for e in wr if e['scenario'] != 'INVARIATO']
        delta = sum(e['pl_actual'] - e['pl_original'] for e in tf_r if e['orig_hit'] is not None)

        header(f'REGOLA: {badge(rule)}  ({rule})')
        if th + tm > 0:
            w(f'  HR: {th}/{th+tm} ({th/(th+tm)*100:.0f}%)    P/L: {tp:+.1f}u    Delta CF: {delta:+.1f}u')
        w()

        # Per sezione
        sections = {'Pronostici': [], 'Elite': [], 'Alto Rend.': []}
        for e in ee:
            sections[get_section(e)].append(e)

        for sec_name in ['Pronostici', 'Elite', 'Alto Rend.']:
            sec = sections[sec_name]
            if not sec: continue

            sec_wr = [e for e in sec if e['curr_hit'] is not None and e['scenario'] != 'NOBET']
            sec_nb = [e for e in sec if e['scenario'] == 'NOBET']
            if not sec_wr and not sec_nb: continue

            sh = sum(1 for e in sec_wr if e['curr_hit'])
            sm_cnt = sum(1 for e in sec_wr if not e['curr_hit'])

            w(f'  --- {sec_name} ---')
            if sh + sm_cnt > 0:
                sp = sum(e['pl_actual'] for e in sec_wr)
                w(f'  HR: {sh}/{sh+sm_cnt} ({sh/(sh+sm_cnt)*100:.0f}%)    P/L: {sp:+.1f}u')
            w()

            for sc_code in ['INVARIATO', 'CAMBIO_MERCATO', 'STESSO_MERCATO', 'NOBET']:
                sc_entries = [e for e in sec if e['scenario'] == sc_code]
                if not sc_entries: continue

                sc_label = SC_LABELS[sc_code]

                if sc_code == 'NOBET':
                    w(f'  [{sc_label}] ({len(sc_entries)} casi)')
                    w()
                    w(f'    {"ESITO":<20s} {"PARTITA":<40s} {"ORIGINALE":<18s} {"RIS":>5s}  {"P/L PERSO":>10s}')
                    w(f'    {"-"*20} {"-"*40} {"-"*18} {"-"*5}  {"-"*10}')
                    for e in sc_entries:
                        if e['orig_hit'] is True:
                            esito = 'AVREBBE CENTRATO'
                        elif e['orig_hit'] is False:
                            esito = 'Avrebbe mancato'
                        else:
                            esito = '?'
                        orig_str = f"{e['orig_pr']} @{e['orig_q']:.2f}" if e['orig_q'] > 0 else e['orig_pr']
                        w(f'    {esito:<20s} {e["match"]:<40s} {orig_str:<18s} {e["score"]:>5s}  {e["pl_original"]:>+10.1f}')
                    w()
                    continue

                sc_wr = [e for e in sc_entries if e['curr_hit'] is not None]
                if not sc_wr: continue

                sc_hit = [e for e in sc_wr if e['curr_hit']]
                sc_miss = [e for e in sc_wr if not e['curr_hit']]

                w(f'  [{sc_label}] ({len(sc_wr)} casi)')
                w()

                if sc_code == 'INVARIATO':
                    w(f'    {"":>3s} {"PARTITA":<40s} {"PRONOSTICO":<12s} {"QUOTA":>6s} {"STK":>4s} {"RIS":>5s}  {"P/L":>8s}')
                    w(f'    {"---":>3s} {"-"*40} {"-"*12} {"-"*6} {"----":>4s} {"-"*5}  {"-"*8}')
                    for e in sorted(sc_wr, key=lambda x: x['pl_actual']):
                        mark = 'OK' if e['curr_hit'] else 'KO'
                        w(f'    {mark:>3s} {e["match"]:<40s} {e["curr_pr"]:<12s} {e["curr_q"]:>6.2f} {e["stake"]:>4d} {e["score"]:>5s}  {e["pl_actual"]:>+8.1f}')
                    w()
                else:
                    if sc_hit:
                        w(f'    CENTRATI ({len(sc_hit)}):')
                        w()
                        w(f'    {"GIUDIZIO":<20s} {"PARTITA":<35s} {"ORIGINALE":<15s} {"TRASFORMATO":<15s} {"RIS":>5s} {"STK":>4s} {"DQ":>6s} {"DPL":>8s}')
                        w(f'    {"-"*20} {"-"*35} {"-"*15} {"-"*15} {"-"*5} {"----":>4s} {"-"*6} {"-"*8}')
                        for e in sorted(sc_hit, key=lambda x: x['pl_actual'] - x['pl_original']):
                            qd = e['curr_q'] - e['orig_q'] if e['orig_q'] > 0 else 0
                            pd = e['pl_actual'] - e['pl_original']
                            if e['orig_hit'] is False:
                                giudizio = 'SALVATO'
                            elif e['orig_hit'] is True and qd < -0.1:
                                giudizio = f'OK ma quota inf.'
                            elif e['orig_hit'] is True:
                                giudizio = 'Entrambi OK'
                            else:
                                giudizio = '-'
                            o = f"{e['orig_pr']} @{e['orig_q']:.2f}" if e['orig_q'] > 0 else e['orig_pr']
                            t = f"{e['curr_pr']} @{e['curr_q']:.2f}"
                            w(f'    {giudizio:<20s} {e["match"]:<35s} {o:<15s} {t:<15s} {e["score"]:>5s} {e["stake"]:>4d} {qd:>+6.2f} {pd:>+8.1f}')
                        w()

                    if sc_miss:
                        w(f'    MANCATI ({len(sc_miss)}):')
                        w()
                        w(f'    {"GIUDIZIO":<20s} {"PARTITA":<35s} {"ORIGINALE":<15s} {"TRASFORMATO":<15s} {"RIS":>5s} {"STK":>4s} {"DPL":>8s}')
                        w(f'    {"-"*20} {"-"*35} {"-"*15} {"-"*15} {"-"*5} {"----":>4s} {"-"*8}')
                        for e in sorted(sc_miss, key=lambda x: x['pl_actual'] - x['pl_original']):
                            pd = e['pl_actual'] - e['pl_original']
                            if e['orig_hit'] is True:
                                giudizio = 'DANNEGGIATO'
                            elif e['orig_hit'] is False:
                                giudizio = 'Entrambi KO'
                            else:
                                giudizio = '-'
                            o = f"{e['orig_pr']} @{e['orig_q']:.2f}" if e['orig_q'] > 0 else e['orig_pr']
                            t = f"{e['curr_pr']} @{e['curr_q']:.2f}"
                            w(f'    {giudizio:<20s} {e["match"]:<35s} {o:<15s} {t:<15s} {e["score"]:>5s} {e["stake"]:>4d} {pd:>+8.1f}')
                        w()

    # Scrivi file
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L))
    print(f"\nReport salvato in: {out_path}")


def main():
    parser = argparse.ArgumentParser(description='Simulazione regole orchestratore su storico')
    parser.add_argument('--date', help='Singola data (YYYY-MM-DD)')
    parser.add_argument('--from', dest='date_from', help='Data inizio (YYYY-MM-DD)')
    parser.add_argument('--to', dest='date_to', help='Data fine (YYYY-MM-DD)')
    args = parser.parse_args()

    if args.date:
        d1 = d2 = args.date
    elif args.date_from and args.date_to:
        d1, d2 = args.date_from, args.date_to
    else:
        d2 = datetime.now().strftime('%Y-%m-%d')
        d1 = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')

    simulate_and_analyze(d1, d2)


if __name__ == '__main__':
    main()
