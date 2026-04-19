"""Cerotto 5 preview: verifica backend delle 4 foglie LOSS del Decision Tree.

Metodo allineato a Cerotto 4:
- Finestra 19/02 - 18/04 (date inclusive)
- daily_predictions_unified (NO dedup): 1 riga per pronostico con esito not None
- stake pesato (profit_loss sommato)
- Scatole: MIXER / ELITE / AR / PRONOSTICI (non mutuamente esclusive)

Foglie dal DecisionTreeClassifier (max_depth=4):
  A: quota <= 1.51 AND mc_avg_goals_away > 2.21 AND sig_strisce <= 49.75
  B: 1.51 < quota <= 2.20 AND mc_home_win_pct <= 49.50
  C: quota > 2.20 AND quota_over25 <= 1.81 AND sig_affidabilita > 44.78
  D: quota > 2.20 AND quota_over25 > 1.81

Fonti campi:
  quota            -> pronostico.quota
  mc_*             -> daily_predictions_engine_c.simulation_data.*
  quota_over25     -> daily_predictions_unified.odds.over_25
  sig_strisce      -> daily_predictions.segno_dettaglio.strisce  (Sistema A)
  sig_affidabilita -> daily_predictions.segno_dettaglio.affidabilita

Output: cerotto5_preview/foglie_verificate.md (niente modifiche al codice).
"""
from __future__ import annotations
import os, sys, json
from collections import defaultdict

current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError('config.py non trovato')
    current_path = parent
sys.path.insert(0, current_path)

from config import db

DATE_FROM = '2026-02-19'
DATE_TO = '2026-04-18'

# --- Soglie Cerotto 4 (7 combo in produzione) per verifica sovrapposizione ---
CEROTTO4_COMBOS = [
    # (id, lambda(p, match_ctx) -> bool)
    ('C4_1', lambda p, m: p.get('tipo') == 'SEGNO' and _fascia_quota(p.get('quota')) == '3.00+'),
    ('C4_2', lambda p, m: p.get('tipo') == 'SEGNO' and m['tipo_partita'] == 'aperta'),
    ('C4_3', lambda p, m: p.get('tipo') == 'SEGNO' and _categoria(p) == 'Alto Rendimento'),
    ('C4_4', lambda p, m: m['tipo_partita'] == 'aperta' and _categoria(p) == 'Alto Rendimento'),
    ('C4_5', lambda p, m: _fascia_oraria(m['match_time']) == 'sera' and _categoria(p) == 'Alto Rendimento'),
    ('C4_6', lambda p, m: _fascia_quota(p.get('quota')) == '3.00+' and _categoria(p) == 'Alto Rendimento'),
    ('C4_7', lambda p, m: _fascia_quota(p.get('quota')) == '2.50-2.99' and m['tipo_partita'] == 'aperta'),
]

def _fascia_quota(q):
    if q is None: return None
    try: q = float(q)
    except: return None
    if q < 1.50: return '<1.50'
    if q < 2.00: return '1.50-1.99'
    if q < 2.50: return '2.00-2.49'
    if q < 3.00: return '2.50-2.99'
    return '3.00+'

def _fascia_oraria(t):
    if not t or ':' not in str(t): return None
    try: h = int(str(t).split(':')[0])
    except: return None
    if h < 15: return 'pranzo'
    if h < 18: return 'pomeriggio'
    return 'sera'

def _categoria(p):
    # Alto Rendimento: quota > 2.50 (come notebook)
    q = p.get('quota')
    try: q = float(q)
    except: return 'Pronostici'
    return 'Alto Rendimento' if q > 2.50 else 'Pronostici'

def _tipo_partita(qmin):
    # Dal notebook: aperta = nessuna quota <1.80 (gara incerta/aperta)
    # equilibrata = quota_min in [1.80, 2.50]
    # squilibrata = quota_min < 1.80
    if qmin is None: return 'sconosciuta'
    if qmin < 1.80: return 'squilibrata'
    if qmin <= 2.50: return 'equilibrata'
    return 'aperta'


def match_foglia_A(ctx):
    q = ctx['quota']
    mc_ag = ctx['mc_avg_goals_away']
    sig_s = ctx['sig_strisce']
    if q is None or mc_ag is None or sig_s is None: return False
    return q <= 1.51 and mc_ag > 2.21 and sig_s <= 49.75

def match_foglia_B(ctx):
    q = ctx['quota']
    mc_hw = ctx['mc_home_win_pct']
    if q is None or mc_hw is None: return False
    return 1.51 < q <= 2.20 and mc_hw <= 49.50

def match_foglia_C(ctx):
    q = ctx['quota']
    qo25 = ctx['quota_over25']
    sig_a = ctx['sig_affidabilita']
    if q is None or qo25 is None or sig_a is None: return False
    return q > 2.20 and qo25 <= 1.81 and sig_a > 44.78

def match_foglia_D(ctx):
    q = ctx['quota']
    qo25 = ctx['quota_over25']
    if q is None or qo25 is None: return False
    return q > 2.20 and qo25 > 1.81


FOGLIE = [
    ('A', match_foglia_A, 'quota<=1.51 AND mc_avg_goals_away>2.21 AND sig_strisce<=49.75'),
    ('B', match_foglia_B, '1.51<quota<=2.20 AND mc_home_win_pct<=49.50'),
    ('C', match_foglia_C, 'quota>2.20 AND quota_over25<=1.81 AND sig_affidabilita>44.78'),
    ('D', match_foglia_D, 'quota>2.20 AND quota_over25>1.81'),
]


def main():
    print(f'[cerotto5] finestra {DATE_FROM} -> {DATE_TO}')

    # Indici sistema A ed engine C per lookup O(1)
    print('[cerotto5] caricamento sistema A...')
    sa_idx = {}
    for doc in db['daily_predictions'].find(
        {'date': {'$gte': DATE_FROM, '$lte': DATE_TO}},
        {'home': 1, 'away': 1, 'date': 1, 'segno_dettaglio': 1}
    ):
        key = f"{doc.get('home','')}__{doc.get('away','')}__{str(doc.get('date',''))[:10]}"
        sa_idx[key] = doc
    print(f'  -> {len(sa_idx)} doc sistema A')

    print('[cerotto5] caricamento engine C...')
    ec_idx = {}
    for doc in db['daily_predictions_engine_c'].find(
        {'date': {'$gte': DATE_FROM, '$lte': DATE_TO}},
        {'home': 1, 'away': 1, 'date': 1, 'simulation_data': 1}
    ):
        key = f"{doc.get('home','')}__{doc.get('away','')}__{str(doc.get('date',''))[:10]}"
        ec_idx[key] = doc
    print(f'  -> {len(ec_idx)} doc engine C')

    # Iterazione pronostici unified
    print('[cerotto5] scansione daily_predictions_unified...')
    stats = {fid: {'n': 0, 'hits': 0, 'pl': 0.0, 'quote': [],
                   'scatole': defaultdict(lambda: {'n': 0, 'hits': 0, 'pl': 0.0}),
                   'overlap_c4': defaultdict(int),
                   'overlap_foglie': defaultdict(int)}
             for fid in ['A', 'B', 'C', 'D']}
    total_pronostici = 0

    for doc in db['daily_predictions_unified'].find(
        {'date': {'$gte': DATE_FROM, '$lte': DATE_TO}},
        {'home': 1, 'away': 1, 'date': 1, 'match_time': 1, 'odds': 1, 'pronostici': 1}
    ):
        date_str = str(doc.get('date', ''))[:10]
        key = f"{doc.get('home','')}__{doc.get('away','')}__{date_str}"
        sa_doc = sa_idx.get(key, {})
        ec_doc = ec_idx.get(key, {})
        sim = ec_doc.get('simulation_data') or {}
        seg_det = sa_doc.get('segno_dettaglio') or {}
        odds = doc.get('odds') or {}

        # Match-level context
        qo25 = float(odds.get('over_25') or 0) or None
        mc_hw = sim.get('home_win_pct') or 0
        mc_dr = sim.get('draw_pct') or 0
        mc_aw = sim.get('away_win_pct') or 0
        mc_ag = sim.get('avg_goals_away') or 0
        sig_s = seg_det.get('strisce') or 0
        sig_a = seg_det.get('affidabilita') or 0

        q1 = float(odds.get('1') or 0) or None
        qX = float(odds.get('X') or 0) or None
        q2 = float(odds.get('2') or 0) or None
        quotes_1x2 = [q for q in (q1, qX, q2) if q]
        qmin = min(quotes_1x2) if quotes_1x2 else None
        tipo_partita = _tipo_partita(qmin)
        match_time = doc.get('match_time', '')

        for p in (doc.get('pronostici') or []):
            if p.get('esito') is None:
                continue
            if p.get('pronostico') == 'NO BET':
                continue
            total_pronostici += 1

            quota = p.get('quota')
            try: quota = float(quota) if quota else None
            except: quota = None

            ctx = {
                'quota': quota,
                'mc_avg_goals_away': mc_ag,
                'mc_home_win_pct': mc_hw,
                'quota_over25': qo25,
                'sig_strisce': sig_s,
                'sig_affidabilita': sig_a,
            }

            # Context per combo C4
            m_ctx = {
                'tipo_partita': tipo_partita,
                'match_time': match_time,
            }

            # Scatola
            scatola = 'PRONOSTICI'
            if p.get('mixer') is True: scatola = 'MIXER'
            elif p.get('elite') is True: scatola = 'ELITE'
            elif _categoria(p) == 'Alto Rendimento': scatola = 'AR'

            pl = float(p.get('profit_loss') or 0)
            hit = 1 if bool(p.get('esito')) else 0

            # Match foglie
            matched_foglie = []
            for fid, fn, _ in FOGLIE:
                if fn(ctx):
                    matched_foglie.append(fid)

            if not matched_foglie:
                continue

            # Match combo C4 (per sovrapposizione)
            matched_c4 = []
            for c4_id, c4_fn in CEROTTO4_COMBOS:
                try:
                    if c4_fn(p, m_ctx):
                        matched_c4.append(c4_id)
                except Exception:
                    pass

            for fid in matched_foglie:
                s = stats[fid]
                s['n'] += 1
                s['hits'] += hit
                s['pl'] += pl
                if quota: s['quote'].append(quota)
                s['scatole'][scatola]['n'] += 1
                s['scatole'][scatola]['hits'] += hit
                s['scatole'][scatola]['pl'] += pl
                if matched_c4:
                    s['overlap_c4']['ANY'] += 1
                    for c in matched_c4:
                        s['overlap_c4'][c] += 1
                else:
                    s['overlap_c4']['NONE'] += 1
                for other in matched_foglie:
                    if other != fid:
                        s['overlap_foglie'][other] += 1

    print(f'[cerotto5] pronostici scansionati (esito not None, no NO BET): {total_pronostici}')

    # --- Tabella riepilogativa globale (per context) ---
    # Calcola metriche globali su TUTTI i pronostici validi (non solo foglie) per baseline
    baseline_n = 0
    baseline_hits = 0
    baseline_pl = 0.0
    for doc in db['daily_predictions_unified'].find(
        {'date': {'$gte': DATE_FROM, '$lte': DATE_TO}},
        {'pronostici': 1}
    ):
        for p in (doc.get('pronostici') or []):
            if p.get('esito') is None: continue
            if p.get('pronostico') == 'NO BET': continue
            baseline_n += 1
            baseline_hits += 1 if bool(p.get('esito')) else 0
            baseline_pl += float(p.get('profit_loss') or 0)
    baseline_hr = baseline_hits / baseline_n * 100 if baseline_n else 0
    baseline_roi = baseline_pl / baseline_n * 100 if baseline_n else 0
    print(f'[cerotto5] baseline globale: n={baseline_n} HR={baseline_hr:.2f}% ROI={baseline_roi:+.2f}% PL={baseline_pl:+.2f}u')

    # --- Scrivi report ---
    out_dir = os.path.dirname(os.path.abspath(__file__))
    out_md = os.path.join(out_dir, 'foglie_verificate.md')

    md = []
    md.append('# Cerotto 5 — Verifica foglie Decision Tree')
    md.append('')
    md.append(f'**Finestra**: {DATE_FROM} → {DATE_TO}')
    md.append(f'**Metodo**: backend-aligned (no dedup, stake pesato, esito not None, esclusi NO BET)')
    md.append('')
    md.append('## Baseline globale')
    md.append('')
    md.append(f'- N pronostici validi: **{baseline_n}**')
    md.append(f'- HR globale: **{baseline_hr:.2f}%**')
    md.append(f'- ROI globale (su 1u stake): **{baseline_roi:+.2f}%**')
    md.append(f'- PL totale (stake pesato): **{baseline_pl:+.2f}u**')
    md.append('')
    md.append('## Riepilogo foglie')
    md.append('')
    md.append('| Foglia | Condizione | N | HR | Quota media | ROI (1u) | PL (stake pesato, u) | Volume |')
    md.append('|---|---|---:|---:|---:|---:|---:|:---:|')

    for fid, _, desc in FOGLIE:
        s = stats[fid]
        n = s['n']
        if n == 0:
            md.append(f'| {fid} | `{desc}` | 0 | — | — | — | 0.00 | ❌ VUOTA |')
            continue
        hr = s['hits'] / n * 100
        q_med = sum(s['quote']) / len(s['quote']) if s['quote'] else 0
        roi = s['pl'] / n * 100
        vol_flag = '⚠️ <50 (overfitting?)' if n < 50 else '✅'
        md.append(f'| {fid} | `{desc}` | {n} | {hr:.2f}% | {q_med:.2f} | {roi:+.2f}% | {s["pl"]:+.2f} | {vol_flag} |')

    md.append('')
    md.append('## Dettaglio per foglia')
    md.append('')

    for fid, _, desc in FOGLIE:
        s = stats[fid]
        md.append(f'### Foglia {fid}')
        md.append('')
        md.append(f'**Condizione**: `{desc}`')
        md.append('')
        md.append(f'- N = {s["n"]}')
        if s['n'] == 0:
            md.append('- Nessun pronostico matcha (foglia vuota nel dataset backend)')
            md.append('')
            continue
        md.append(f'- HR = {s["hits"] / s["n"] * 100:.2f}% (vs globale {baseline_hr:.2f}%, Δ = {s["hits"] / s["n"] * 100 - baseline_hr:+.2f}pp)')
        md.append(f'- Quota media = {sum(s["quote"]) / len(s["quote"]):.2f}')
        md.append(f'- ROI (1u) = {s["pl"] / s["n"] * 100:+.2f}%')
        md.append(f'- PL (stake pesato) = {s["pl"]:+.2f}u')
        md.append('')
        md.append('**Distribuzione per scatola**')
        md.append('')
        md.append('| Scatola | N | HR | PL (stake pesato) |')
        md.append('|---|---:|---:|---:|')
        for sc in ('MIXER', 'ELITE', 'AR', 'PRONOSTICI'):
            d = s['scatole'].get(sc, {'n': 0, 'hits': 0, 'pl': 0.0})
            if d['n'] == 0:
                md.append(f'| {sc} | 0 | — | 0.00 |')
            else:
                md.append(f'| {sc} | {d["n"]} | {d["hits"] / d["n"] * 100:.2f}% | {d["pl"]:+.2f}u |')
        md.append('')
        md.append('**Sovrapposizione con combo Cerotto 4**')
        md.append('')
        oc4 = s['overlap_c4']
        any_c4 = oc4.get('ANY', 0)
        no_c4 = oc4.get('NONE', 0)
        pct_any = any_c4 / s['n'] * 100 if s['n'] else 0
        md.append(f'- Pronostici già coperti da almeno una combo C4: **{any_c4}/{s["n"]}** ({pct_any:.1f}%)')
        md.append(f'- Pronostici NON coperti da C4 (net nuovo filtro): **{no_c4}/{s["n"]}** ({no_c4 / s["n"] * 100:.1f}%)')
        md.append('')
        md.append('Breakdown per combo C4:')
        for c4_id, _ in CEROTTO4_COMBOS:
            cnt = oc4.get(c4_id, 0)
            if cnt > 0:
                md.append(f'  - {c4_id}: {cnt}')
        md.append('')
        md.append('**Sovrapposizione con altre foglie DT**')
        md.append('')
        of = s['overlap_foglie']
        if not of:
            md.append('- Nessuna sovrapposizione con altre foglie')
        else:
            for other, cnt in sorted(of.items()):
                md.append(f'- Foglia {other}: {cnt}')
        md.append('')

    # --- Note finali ---
    md.append('## Note metodologiche')
    md.append('')
    md.append('- Foglie estratte da `DecisionTreeClassifier(max_depth=4, min_samples_leaf=20, class_weight=balanced)` addestrato nel notebook `analisi_professionale.ipynb` (cella 54)')
    md.append('- Campi `mc_*` da `daily_predictions_engine_c.simulation_data`')
    md.append('- Campi `sig_strisce`, `sig_affidabilita` da `daily_predictions.segno_dettaglio`')
    md.append('- Campo `quota_over25` da `daily_predictions_unified.odds.over_25`')
    md.append('- Metodo conforme a Cerotto 4: stake pesato, no dedup, pronostici con `esito not None` e diversi da NO BET')
    md.append('- Scatole non mutuamente esclusive: un pronostico MIXER può avere anche `elite=True`; la priorità qui è MIXER > ELITE > AR > PRONOSTICI')
    md.append('')
    md.append('## Soglie di valutazione (per decidere implementazione)')
    md.append('')
    md.append('Una foglia va implementata come filtro tossico se SIMULTANEAMENTE:')
    md.append('1. Volume N ≥ 50 (altrimenti overfitting DT, non generalizza)')
    md.append('2. ROI (1u) significativamente negativo (< -5%)')
    md.append('3. HR sotto globale con Δ ≥ -5pp')
    md.append('4. Sovrapposizione con C4 < 80% (altrimenti ridondante)')
    md.append('')
    md.append('Se una foglia è dominata da MIXER, ricorda che Cerotto 4 esclude MIXER — stessa logica qui.')
    md.append('')

    with open(out_md, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    print(f'[cerotto5] report scritto: {out_md}')


if __name__ == '__main__':
    main()
