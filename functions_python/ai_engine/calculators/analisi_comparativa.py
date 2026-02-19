"""
ANALISI COMPARATIVA — Sistema A vs Sistema C vs Sandbox (Report HTML)

Confronta i pronostici testa a testa: stessa partita, stesso mercato.
Genera un report HTML professionale apribile nel browser.

Uso:
  python analisi_comparativa.py                          # ieri
  python analisi_comparativa.py --date 2026-02-15        # un giorno
  python analisi_comparativa.py --from 2026-02-14 --to 2026-02-15   # range
"""

import sys
import os
import argparse
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import db

LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'log')


# =====================================================================
#  UTILITY
# =====================================================================

def parse_score(sc):
    if not sc or ':' not in str(sc):
        return None, None
    try:
        return int(sc.split(':')[0]), int(sc.split(':')[1])
    except Exception:
        return None, None


def check_pronostico(pred, score_str):
    gh, ga = parse_score(score_str)
    if gh is None:
        return None
    tipo = pred.get('tipo', '')
    pron = pred.get('pronostico', '')
    tot = gh + ga

    if tipo == 'SEGNO':
        return {'1': gh > ga, 'X': gh == ga, '2': gh < ga}.get(pron)

    if tipo == 'DOPPIA_CHANCE':
        if pron == '1X': return gh >= ga
        if pron == 'X2': return gh <= ga
        if pron == '12': return gh != ga
        return None

    if tipo == 'GOL':
        if 'Over' in pron:
            try: return tot > float(pron.split()[-1])
            except: return None
        if 'Under' in pron:
            try: return tot < float(pron.split()[-1])
            except: return None
        if pron == 'Goal':   return gh > 0 and ga > 0
        if pron == 'NoGoal': return gh == 0 or ga == 0

    if tipo == 'X_FACTOR':
        return gh == ga if pron == 'X' else None

    if tipo == 'RISULTATO_ESATTO':
        return f'{gh}:{ga}' == pron

    return None


def market_label(pred):
    tipo = pred.get('tipo', '')
    pron = pred.get('pronostico', '')
    if tipo == 'SEGNO':           return '1X2'
    if tipo == 'DOPPIA_CHANCE':   return 'DOPPIA CHANCE'
    if tipo == 'GOL':
        if 'Over' in pron:
            try:    return f'OVER {pron.split()[-1]}'
            except: return 'OVER'
        if 'Under' in pron:
            try:    return f'UNDER {pron.split()[-1]}'
            except: return 'UNDER'
        if pron == 'Goal':        return 'GOAL (GG)'
        if pron == 'NoGoal':      return 'NOGOAL (NG)'
    if tipo == 'X_FACTOR':        return 'X FACTOR'
    if tipo == 'RISULTATO_ESATTO':return 'RISULTATO ESATTO'
    return tipo


def market_group(pred):
    tipo = pred.get('tipo', '')
    pron = pred.get('pronostico', '')
    if tipo == 'SEGNO':           return '1X2'
    if tipo == 'DOPPIA_CHANCE':   return 'DC'
    if tipo == 'GOL':
        if 'Over' in pron or 'Under' in pron:
            try:
                line = pron.split()[-1]
                return f'O/U {line}'
            except:
                return 'O/U'
        if pron in ('Goal', 'NoGoal'): return 'GG/NG'
    if tipo == 'X_FACTOR':        return 'XF'
    if tipo == 'RISULTATO_ESATTO':return 'RE'
    return tipo


MARKET_LABEL_ORDER = [
    '1X2', 'DOPPIA CHANCE',
    'OVER 1.5', 'OVER 2.5', 'OVER 3.5',
    'UNDER 1.5', 'UNDER 2.5', 'UNDER 3.5',
    'GOAL (GG)', 'NOGOAL (NG)',
    'X FACTOR', 'RISULTATO ESATTO',
]


def load_real_results(date_str):
    parts = date_str.split('-')
    start = datetime(int(parts[0]), int(parts[1]), int(parts[2]))
    end = start + timedelta(days=1)
    results = {}
    for r in db['h2h_by_round'].aggregate([
        {'$unwind': '$matches'},
        {'$match': {
            'matches.date_obj': {'$gte': start, '$lt': end},
            'matches.status': 'Finished'
        }},
        {'$project': {
            'matches.home': 1, 'matches.away': 1, 'matches.real_score': 1
        }}
    ]):
        m = r['matches']
        results[m['home'] + '__' + m['away']] = m['real_score']
    return results


def date_range(start_str, end_str):
    s = datetime.strptime(start_str, '%Y-%m-%d')
    e = datetime.strptime(end_str, '%Y-%m-%d')
    out = []
    while s <= e:
        out.append(s.strftime('%Y-%m-%d'))
        s += timedelta(days=1)
    return out


def build_index(preds_list):
    """Costruisce indice (match_key, market_group) -> pronostico."""
    idx = {}
    for doc in preds_list:
        key = doc.get('home', '') + '__' + doc.get('away', '')
        for p in doc.get('pronostici', []):
            mg = market_group(p)
            idx[(key, mg)] = p
    return idx


# =====================================================================
#  RACCOLTA DATI
# =====================================================================

SYSTEMS = ['A', 'C', 'S']
COLLECTIONS = {
    'A': 'daily_predictions',
    'C': 'daily_predictions_engine_c',
    'S': 'daily_predictions_sandbox',
}
COLORS = {
    'A': '#42a5f5',
    'C': '#ff9800',
    'S': '#ab47bc',
}
LABELS = {
    'A': 'Sistema A',
    'C': 'Sistema C',
    'S': 'Sandbox',
}


def collect_data(dates):
    details = []
    stats = {s: defaultdict(lambda: [0, 0]) for s in SYSTEMS}  # market_label -> [ok, tot]
    h2h = defaultdict(lambda: {s: [0, 0] for s in SYSTEMS})    # market_group -> {sys: [ok, tot]}
    total_matches_real = 0
    solo_counts = {s: [0, 0] for s in SYSTEMS}  # [count, ok]

    for dt in dates:
        real = load_real_results(dt)
        total_matches_real += len(real)

        # Carica tutti e 3 i sistemi
        preds_all = {}
        indexes = {}
        for sys_id in SYSTEMS:
            coll_name = COLLECTIONS[sys_id]
            preds_all[sys_id] = list(db[coll_name].find({'date': dt}))
            indexes[sys_id] = build_index(preds_all[sys_id])

        # Raccogli tutti i match_key + market_group unici da tutti i sistemi
        all_combos = set()
        all_match_info = {}  # match_key -> (home, away)
        for sys_id in SYSTEMS:
            for doc in preds_all[sys_id]:
                key = doc.get('home', '') + '__' + doc.get('away', '')
                all_match_info[key] = (doc.get('home', ''), doc.get('away', ''))
                for p in doc.get('pronostici', []):
                    mg = market_group(p)
                    all_combos.add((key, mg))

        # Itera su tutte le combinazioni
        for (match_key, mg) in all_combos:
            score = real.get(match_key)
            if not score:
                continue

            home, away = all_match_info.get(match_key, ('?', '?'))

            # Verifica hit per ogni sistema
            hits = {}
            preds_for_detail = {}
            mls = {}
            active_systems = []
            for sys_id in SYSTEMS:
                p = indexes[sys_id].get((match_key, mg))
                if p is None:
                    hits[sys_id] = None
                    preds_for_detail[sys_id] = None
                    mls[sys_id] = '-'
                    continue
                ok = check_pronostico(p, score)
                if ok is None:
                    hits[sys_id] = None
                    preds_for_detail[sys_id] = None
                    mls[sys_id] = '-'
                    continue
                hits[sys_id] = ok
                preds_for_detail[sys_id] = p
                mls[sys_id] = market_label(p)
                active_systems.append(sys_id)

                # Stats individuali
                stats[sys_id][mls[sys_id]][1] += 1
                if ok:
                    stats[sys_id][mls[sys_id]][0] += 1

            # H2H: solo se almeno 2 sistemi hanno un pronostico
            if len(active_systems) >= 2:
                for sys_id in active_systems:
                    h2h[mg][sys_id][1] += 1
                    if hits[sys_id]:
                        h2h[mg][sys_id][0] += 1

            # Se solo 1 sistema ha un pronostico
            if len(active_systems) == 1:
                s = active_systems[0]
                solo_counts[s][0] += 1
                if hits[s]:
                    solo_counts[s][1] += 1

            # Dettaglio (solo se almeno 1 sistema ha dato pronostico)
            if active_systems:
                # Determina vincitore
                if len(active_systems) >= 2:
                    winners = [s for s in active_systems if hits[s]]
                    if len(winners) == len(active_systems):
                        winner = 'TUTTI OK'
                    elif len(winners) == 0:
                        winner = 'TUTTI KO'
                    elif len(winners) == 1:
                        winner = winners[0]
                    else:
                        winner = '+'.join(winners)
                else:
                    winner = f'solo_{active_systems[0]}'

                details.append({
                    'date': dt, 'home': home, 'away': away, 'score': score,
                    'mg': mg,
                    'ml': {s: mls[s] for s in SYSTEMS},
                    'pred': {s: (preds_for_detail[s].get('pronostico', '?') if preds_for_detail[s] else '-') for s in SYSTEMS},
                    'hit': hits,
                    'winner': winner,
                })

    return {
        'details': details,
        'stats': {s: dict(stats[s]) for s in SYSTEMS},
        'h2h': dict(h2h),
        'solo_counts': solo_counts,
        'total_matches_real': total_matches_real,
    }


# =====================================================================
#  GENERAZIONE HTML
# =====================================================================

CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: 'Segoe UI', -apple-system, sans-serif;
    background: #0f1118;
    color: #e0e0e0;
    padding: 24px;
    line-height: 1.6;
}
h1 { color: #fff; font-size: 26px; text-align: center; margin-bottom: 6px; }
.subtitle { text-align: center; color: #888; font-size: 14px; margin-bottom: 28px; }
.cards {
    display: flex; gap: 14px; justify-content: center;
    flex-wrap: wrap; margin-bottom: 32px;
}
.card {
    background: #1a1d2e; border-radius: 12px;
    padding: 18px 24px; text-align: center; min-width: 120px;
}
.card .num { font-size: 30px; font-weight: 700; }
.card .lbl { font-size: 12px; color: #888; margin-top: 2px; }
.card.a .num { color: #42a5f5; }
.card.c .num { color: #ff9800; }
.card.s .num { color: #ab47bc; }
.card.ok .num { color: #4caf50; }
.card.ko .num { color: #ef5350; }
h2 {
    color: #fff; font-size: 18px; margin: 36px 0 10px;
    padding-bottom: 8px; border-bottom: 2px solid #252840;
}
.note { color: #666; font-size: 12px; margin-bottom: 10px; font-style: italic; }
table { width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 13px; }
th {
    background: #181b28; color: #777; padding: 8px 10px; text-align: left;
    font-weight: 600; text-transform: uppercase; font-size: 11px;
    letter-spacing: 0.5px; position: sticky; top: 0; z-index: 1;
}
th.center, td.c { text-align: center; }
td { padding: 7px 10px; border-bottom: 1px solid #1c1f30; }
tr:hover td { background: #181b28; }
.num { font-variant-numeric: tabular-nums; }
.w { color: #4caf50; font-weight: 600; }
.l { color: #ef5350; font-weight: 600; }
.d { color: #777; }
.a-col { color: #42a5f5; }
.c-col { color: #ff9800; }
.s-col { color: #ab47bc; }
.badge {
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 11px; font-weight: 700; white-space: nowrap;
}
.b-a { background: rgba(66,165,245,0.15); color: #42a5f5; }
.b-c { background: rgba(255,152,0,0.15); color: #ff9800; }
.b-s { background: rgba(171,71,188,0.15); color: #ab47bc; }
.b-ok { background: rgba(76,175,80,0.15); color: #4caf50; }
.b-ko { background: rgba(239,83,80,0.15); color: #ef5350; }
.b-p { background: rgba(158,158,158,0.12); color: #999; }
.b-solo { background: rgba(100,100,100,0.12); color: #666; }
.row-best-a td { background: rgba(66,165,245,0.04); }
.row-best-c td { background: rgba(255,152,0,0.04); }
.row-best-s td { background: rgba(171,71,188,0.04); }
.tot-row td { border-top: 2px solid #42a5f5; font-weight: 700; background: #131520; }
.score-cell { font-weight: 700; font-size: 14px; color: #fff; }
.footer {
    text-align: center; color: #444; font-size: 11px;
    margin-top: 40px; padding-top: 16px; border-top: 1px solid #1c1f30;
}
"""


def hr_class(pct):
    if pct >= 60: return 'w'
    if pct < 45: return 'l'
    return ''


def fmt_stats_cells(ok, tot):
    if tot == 0:
        return '<td class="c">-</td><td class="c">-</td><td class="c">-</td><td class="c">-</td>'
    persi = tot - ok
    pct = ok / tot * 100
    hc = hr_class(pct)
    return (f'<td class="c num">{tot}</td>'
            f'<td class="c num w">{ok}</td>'
            f'<td class="c num l">{persi}</td>'
            f'<td class="c num {hc}">{pct:.1f}%</td>')


def best_badge_3(hrs, tots):
    """Badge migliore tra 3 sistemi. hrs/tots = dict {A: val, C: val, S: val}."""
    active = {s: hrs[s] for s in SYSTEMS if tots[s] > 0}
    if not active:
        return '-'
    if len(active) == 1:
        s = list(active.keys())[0]
        return f'<span class="badge b-solo">solo {s}</span>'
    best_hr = max(active.values())
    best_sys = [s for s, h in active.items() if h == best_hr]
    if len(best_sys) == len(active):
        return '<span class="badge b-p">PARI</span>'
    if len(best_sys) == 1:
        s = best_sys[0]
        second = max(h for sys, h in active.items() if sys != s)
        css = f'b-{s.lower()}'
        return f'<span class="badge {css}">{s} (+{best_hr - second:.0f}%)</span>'
    return f'<span class="badge b-p">{"+".join(best_sys)}</span>'


def generate_html(dates, data):
    details = data['details']
    stats = data['stats']
    h2h = data['h2h']

    date_label = dates[0] if len(dates) == 1 else f'{dates[0]} &rarr; {dates[-1]}'
    giorni = len(dates)

    # Calcoli globali per le card
    global_ok = {}
    global_tot = {}
    for sys_id in SYSTEMS:
        ok_sum = sum(v[0] for v in stats[sys_id].values())
        tot_sum = sum(v[1] for v in stats[sys_id].values())
        global_ok[sys_id] = ok_sum
        global_tot[sys_id] = tot_sum

    html = f'''<!DOCTYPE html>
<html lang="it"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>A vs C vs S | {date_label}</title>
<style>{CSS}</style>
</head><body>
<h1>Report Comparativo &mdash; A vs C vs Sandbox</h1>
<p class="subtitle">{date_label} &nbsp;|&nbsp; {giorni} giorn{"o" if giorni == 1 else "i"}
&nbsp;|&nbsp; {data["total_matches_real"]} partite con risultato
&nbsp;|&nbsp; Generato {datetime.now().strftime("%d/%m/%Y %H:%M")}</p>

<div class="cards">
'''

    for sys_id in SYSTEMS:
        ok = global_ok[sys_id]
        tot = global_tot[sys_id]
        hr = ok / tot * 100 if tot else 0
        css_class = sys_id.lower()
        html += f'<div class="card {css_class}"><div class="num">{hr:.1f}%</div><div class="lbl">{LABELS[sys_id]} ({ok}/{tot})</div></div>\n'

    # Card confronti H2H
    n_h2h = 0
    for mg_data in h2h.values():
        max_tot = max(mg_data[s][1] for s in SYSTEMS)
        n_h2h += max_tot

    html += f'<div class="card"><div class="num" style="color:#fff">{n_h2h}</div><div class="lbl">CONFRONTI H2H</div></div>\n'
    html += '</div>\n'

    # ===== TABELLA 1: STATISTICHE PER MERCATO =====
    html += '''<h2>1. Statistiche per Mercato</h2>
<p class="note">Per ogni mercato: pronostici emessi, vinti, persi e hit rate per ciascun sistema.</p>
<table>
<tr>
<th rowspan="2">Mercato</th>
'''
    for sys_id in SYSTEMS:
        color = COLORS[sys_id]
        html += f'<th class="center" colspan="4" style="color:{color}">{LABELS[sys_id]}</th>\n'
    html += '<th class="center" rowspan="2">Migliore</th></tr>\n<tr>\n'
    for _ in SYSTEMS:
        html += '<th class="center">Em.</th><th class="center">Vinti</th><th class="center">Persi</th><th class="center">HR%</th>\n'
    html += '</tr>\n'

    all_labels = sorted(
        set(ml for sys_id in SYSTEMS for ml in stats[sys_id].keys()),
        key=lambda x: MARKET_LABEL_ORDER.index(x) if x in MARKET_LABEL_ORDER else 99
    )

    totals = {s: [0, 0] for s in SYSTEMS}

    for ml in all_labels:
        hrs = {}
        tots_ml = {}
        for sys_id in SYSTEMS:
            ok, n = stats[sys_id].get(ml, [0, 0])
            totals[sys_id][0] += ok
            totals[sys_id][1] += n
            hrs[sys_id] = ok / n * 100 if n else 0
            tots_ml[sys_id] = n

        # Riga colorata per il migliore
        active = {s: hrs[s] for s in SYSTEMS if tots_ml[s] > 0}
        best_sys = max(active, key=active.get) if active else None
        row_class = f' class="row-best-{best_sys.lower()}"' if best_sys and len(active) > 1 else ''

        html += f'<tr{row_class}><td><strong>{ml}</strong></td>'
        for sys_id in SYSTEMS:
            ok, n = stats[sys_id].get(ml, [0, 0])
            html += fmt_stats_cells(ok, n)
        html += f'<td class="c">{best_badge_3(hrs, tots_ml)}</td></tr>\n'

    # Riga totale
    hrs_t = {s: totals[s][0] / totals[s][1] * 100 if totals[s][1] else 0 for s in SYSTEMS}
    tots_t = {s: totals[s][1] for s in SYSTEMS}
    html += '<tr class="tot-row"><td><strong>TOTALE</strong></td>'
    for sys_id in SYSTEMS:
        html += fmt_stats_cells(totals[sys_id][0], totals[sys_id][1])
    html += f'<td class="c">{best_badge_3(hrs_t, tots_t)}</td></tr>\n'
    html += '</table>\n'

    # ===== TABELLA 2: TESTA A TESTA =====
    html += '''<h2>2. Testa a Testa per Mercato</h2>
<p class="note">Confronti dove almeno 2 sistemi hanno un pronostico per la stessa partita e la stessa linea.</p>
<table>
<tr>
<th>Mercato</th>
'''
    for sys_id in SYSTEMS:
        color = COLORS[sys_id]
        html += f'<th class="center" style="color:{color}">HR {sys_id}</th>\n'
    html += '<th class="center">Tot</th><th class="center">Migliore</th></tr>\n'

    h2h_sorted = sorted(h2h.keys(), key=lambda x: (
        0 if '1X2' in x else 1 if 'DC' in x else 2 if 'O/U' in x else 3 if 'GG' in x else 4 if 'XF' in x else 5 if 'RE' in x else 6
    ))

    h2h_totals = {s: [0, 0] for s in SYSTEMS}

    for mg in h2h_sorted:
        mg_data = h2h[mg]
        hrs_mg = {}
        tots_mg = {}
        for sys_id in SYSTEMS:
            ok, tot = mg_data[sys_id]
            hrs_mg[sys_id] = ok / tot * 100 if tot else 0
            tots_mg[sys_id] = tot
            h2h_totals[sys_id][0] += ok
            h2h_totals[sys_id][1] += tot

        n = max(tots_mg.values())

        html += f'<tr><td><strong>{mg}</strong></td>'
        for sys_id in SYSTEMS:
            ok, tot = mg_data[sys_id]
            if tot > 0:
                pct = ok / tot * 100
                html += f'<td class="c num {hr_class(pct)}">{ok}/{tot} ({pct:.0f}%)</td>'
            else:
                html += '<td class="c d">-</td>'
        html += f'<td class="c num">{n}</td>'
        html += f'<td class="c">{best_badge_3(hrs_mg, tots_mg)}</td></tr>\n'

    # Riga totale H2H
    hrs_h = {s: h2h_totals[s][0] / h2h_totals[s][1] * 100 if h2h_totals[s][1] else 0 for s in SYSTEMS}
    tots_h = {s: h2h_totals[s][1] for s in SYSTEMS}
    html += '<tr class="tot-row"><td><strong>TOTALE</strong></td>'
    for sys_id in SYSTEMS:
        ok, tot = h2h_totals[sys_id]
        if tot > 0:
            pct = ok / tot * 100
            html += f'<td class="c num {hr_class(pct)}">{ok}/{tot} ({pct:.0f}%)</td>'
        else:
            html += '<td class="c d">-</td>'
    html += f'<td class="c num">{n_h2h}</td>'
    html += f'<td class="c">{best_badge_3(hrs_h, tots_h)}</td></tr>\n'
    html += '</table>\n'

    # ===== TABELLA 3: DETTAGLIO PARTITA PER PARTITA =====
    html += '''<h2>3. Dettaglio Partita per Partita</h2>
<p class="note">Ogni pronostico confrontato tra i 3 sistemi. Il risultato reale è sempre visibile.</p>
<table>
<tr>
<th>Data</th><th>Partita</th><th class="center">Ris.</th>
<th>Mercato</th>
<th class="center" style="color:#42a5f5">Pred A</th><th class="center">Esito</th>
<th class="center" style="color:#ff9800">Pred C</th><th class="center">Esito</th>
<th class="center" style="color:#ab47bc">Pred S</th><th class="center">Esito</th>
<th class="center">Vincitore</th>
</tr>
'''

    details.sort(key=lambda d: (
        d['date'], d['home'],
        MARKET_LABEL_ORDER.index(d['ml']['A']) if d['ml']['A'] in MARKET_LABEL_ORDER else 99
    ))

    prev_match = ''
    for d in details:
        match_key = f"{d['date']}_{d['home']}_{d['away']}"

        if match_key != prev_match:
            if prev_match:
                html += '<tr><td colspan="11" style="padding:0;border-bottom:2px solid #252840"></td></tr>\n'
            prev_match = match_key

        # Pred + esito per ciascun sistema
        cells = ''
        for sys_id in SYSTEMS:
            pred_str = d['pred'][sys_id]
            hit = d['hit'][sys_id]
            if pred_str == '-':
                cells += f'<td class="c d">&mdash;</td><td class="c d">&mdash;</td>'
            elif hit is True:
                cells += f'<td class="c"><strong>{pred_str}</strong></td><td class="c"><span class="w">&#10003;</span></td>'
            elif hit is False:
                cells += f'<td class="c"><strong>{pred_str}</strong></td><td class="c"><span class="l">&#10007;</span></td>'
            else:
                cells += f'<td class="c"><strong>{pred_str}</strong></td><td class="c d">&mdash;</td>'

        # Badge vincitore
        w = d['winner']
        if w == 'TUTTI OK':
            wb = '<span class="badge b-ok">TUTTI OK</span>'
        elif w == 'TUTTI KO':
            wb = '<span class="badge b-ko">TUTTI KO</span>'
        elif w in SYSTEMS:
            wb = f'<span class="badge b-{w.lower()}">{w} VINCE</span>'
        elif w.startswith('solo_'):
            wb = f'<span class="badge b-solo">{w}</span>'
        elif '+' in w:
            wb = f'<span class="badge b-ok">{w} OK</span>'
        else:
            wb = f'<span class="badge b-p">{w}</span>'

        # Mostra market label (prende il primo non-dash)
        ml_display = next((d['ml'][s] for s in SYSTEMS if d['ml'][s] != '-'), d['mg'])

        html += f'''<tr>
<td>{d['date']}</td><td>{d['home']} - {d['away']}</td>
<td class="c score-cell">{d['score']}</td>
<td>{ml_display}</td>
{cells}
<td class="c">{wb}</td></tr>\n'''

    html += '</table>\n'

    # Footer con conteggi solo
    solo_info = []
    for sys_id in SYSTEMS:
        cnt, ok = data['solo_counts'][sys_id]
        if cnt > 0:
            pct = ok / cnt * 100
            solo_info.append(f'Solo {sys_id}: {cnt} ({ok} ok, {pct:.0f}%)')

    solo_str = ' &mdash; '.join(solo_info) if solo_info else 'Nessun pronostico isolato'

    html += f'''<p class="note" style="margin-top:16px">
Pronostici emessi da un solo sistema: {solo_str}</p>

<p class="footer">analisi_comparativa.py &nbsp;|&nbsp; PupPals Football AI
&nbsp;|&nbsp; {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}</p>
</body></html>'''

    return html


# =====================================================================
#  MAIN
# =====================================================================

def run_analysis(dates):
    data = collect_data(dates)

    if not data['details']:
        print('\n  Nessun confronto possibile per le date selezionate.')
        return

    html = generate_html(dates, data)

    os.makedirs(LOG_DIR, exist_ok=True)
    if len(dates) == 1:
        fname = f'report_A_vs_C_vs_S_{dates[0]}.html'
    else:
        fname = f'report_A_vs_C_vs_S_{dates[0]}_{dates[-1]}.html'
    path = os.path.join(LOG_DIR, fname)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)

    # Quick console summary
    stats = data['stats']
    print(f'\n  Report HTML salvato in: {path}')
    print(f'  Partite con risultato: {data["total_matches_real"]}')
    print()
    for sys_id in SYSTEMS:
        ok = sum(v[0] for v in stats[sys_id].values())
        tot = sum(v[1] for v in stats[sys_id].values())
        hr = ok / tot * 100 if tot else 0
        print(f'  {LABELS[sys_id]:12s}: {ok}/{tot} = {hr:.1f}%')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Confronto A vs C vs Sandbox')
    parser.add_argument('--date', '-d', help='Singola data (YYYY-MM-DD)')
    parser.add_argument('--from', '-f', dest='from_date', help='Data inizio range (YYYY-MM-DD)')
    parser.add_argument('--to', '-t', dest='to_date', help='Data fine range (YYYY-MM-DD)')
    args = parser.parse_args()

    if args.date:
        dates = [args.date]
    elif args.from_date and args.to_date:
        dates = date_range(args.from_date, args.to_date)
    elif args.from_date:
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        dates = date_range(args.from_date, yesterday)
    else:
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        dates = [yesterday]

    print(f'\n  Date selezionate: {dates[0]}' + (f' -> {dates[-1]} ({len(dates)} giorni)' if len(dates) > 1 else ''))
    run_analysis(dates)
