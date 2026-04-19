"""Punto 4 — Analisi NO BET ed esclusioni (scremati).

Per ogni pronostico NO BET in daily_predictions_unified:
- recupera original_pronostico, original_quota
- trova il real_score della partita (h2h_by_round + coppe)
- calcola esito reale e PL simulato
- segmenta: NO BET "puri" vs "scrematura" (via routing_rule)

Output in 04_no_bet/.
Segmentazione per mercato e per gruppo source.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
BACKEND_ROOT = HERE.parent.parent.parent  # .../simulatore-calcio-backend

DATE_FROM = '2026-02-19'
DATE_TO = '2026-04-18'

GROUP_ORDER = ['A', 'S', 'C', 'A+S', 'C-derivati', 'Altro']
MERCATI = ['SEGNO', 'DOPPIA_CHANCE', 'GOL']


def classify(src) -> str:
    if src is None or (isinstance(src, float) and np.isnan(src)):
        return 'Altro'
    s = str(src)
    if s == 'A':
        return 'A'
    if s == 'S':
        return 'S'
    if s == 'C':
        return 'C'
    if s == 'A+S' or s.startswith('A+S_'):
        return 'A+S'
    if s.startswith('C_') or s.startswith('MC_'):
        return 'C-derivati'
    return 'Altro'


def parse_score(real_score):
    if not real_score:
        return None
    parts = re.split(r'[:\-]', str(real_score).strip())
    if len(parts) != 2:
        return None
    try:
        h, a = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    return {'home': h, 'away': a, 'total': h + a,
            'sign': '1' if h > a else ('X' if h == a else '2'),
            'btts': h > 0 and a > 0}


def check_pronostico(pronostico, tipo, parsed):
    if not parsed or not pronostico:
        return None
    p = pronostico.strip()
    if tipo == 'SEGNO':
        return parsed['sign'] == p
    if tipo == 'DOPPIA_CHANCE':
        if p == '1X': return parsed['sign'] in ('1', 'X')
        if p == 'X2': return parsed['sign'] in ('X', '2')
        if p == '12': return parsed['sign'] in ('1', '2')
        return None
    if tipo == 'GOL':
        m = re.match(r'(Over|Under)\s+([\d.]+)', p, re.IGNORECASE)
        if m:
            return parsed['total'] > float(m.group(2)) if m.group(1).lower() == 'over' else parsed['total'] < float(m.group(2))
        if p.lower() == 'goal': return parsed['btts']
        if p.lower() == 'nogoal': return not parsed['btts']
        mg = re.match(r'MG\s+(\d+)-(\d+)', p, re.IGNORECASE)
        if mg:
            return int(mg.group(1)) <= parsed['total'] <= int(mg.group(2))
    return None


def load_db():
    backend_cfg = BACKEND_ROOT / 'config.py'
    spec = importlib.util.spec_from_file_location('backend_config', backend_cfg)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.db


def build_results_map(db):
    """Ritorna dict {'home|||away|||YYYY-MM-DD': 'H:A'}."""
    rmap = {}
    pipeline = [
        {"$unwind": "$matches"},
        {"$match": {"matches.real_score": {"$ne": None}}},
        {"$project": {
            "home": "$matches.home",
            "away": "$matches.away",
            "date": "$matches.date_obj",
            "score": "$matches.real_score",
        }},
    ]
    for d in db.h2h_by_round.aggregate(pipeline):
        dt = d.get('date')
        if not dt:
            continue
        ds = dt.strftime('%Y-%m-%d')
        key = f"{d['home']}|||{d['away']}|||{ds}"
        rmap[key] = d['score']
        for delta in (-1, 1):
            alt = (dt + timedelta(days=delta)).strftime('%Y-%m-%d')
            rmap.setdefault(f"{d['home']}|||{d['away']}|||{alt}", d['score'])
    # Coppe
    for coll_name in ('matches_champions_league', 'matches_europa_league'):
        if coll_name not in db.list_collection_names():
            continue
        for doc in db[coll_name].find(
            {"$or": [{"real_score": {"$ne": None}}, {"result": {"$exists": True}}]},
            {"home_team": 1, "away_team": 1, "match_date": 1,
             "real_score": 1, "result": 1, "status": 1}
        ):
            rs = doc.get('real_score')
            if not rs and doc.get('result'):
                r = doc['result']
                if r.get('home_score') is not None and r.get('away_score') is not None:
                    rs = f"{r['home_score']}:{r['away_score']}"
            if not rs:
                continue
            if (doc.get('status') or '').lower() not in ('finished', 'ft'):
                continue
            md = doc.get('match_date', '')
            if not md:
                continue
            try:
                parts = md.split(' ')[0].split('-')
                ds = md.split(' ')[0] if len(parts[0]) == 4 else f"{parts[2]}-{parts[1]}-{parts[0]}"
            except Exception:
                continue
            rmap[f"{doc['home_team']}|||{doc['away_team']}|||{ds}"] = rs
    return rmap


def extract_no_bets(db) -> pd.DataFrame:
    """Estrae TUTTI i pronostici NO BET dalla finestra temporale."""
    q = {'date': {'$gte': DATE_FROM, '$lte': DATE_TO}}
    rows = []
    for doc in db['daily_predictions_unified'].find(q):
        home = doc.get('home')
        away = doc.get('away')
        date_s = doc.get('date')
        live_score = doc.get('live_score')
        live_status = doc.get('live_status')
        for p in doc.get('pronostici', []):
            if p.get('pronostico') != 'NO BET':
                continue
            if p.get('tipo') not in MERCATI:
                continue
            rows.append({
                'date': date_s,
                'home': home, 'away': away,
                'tipo': p.get('tipo'),
                'original_pronostico': p.get('original_pronostico'),
                'original_quota': p.get('original_quota'),
                'source': p.get('source'),
                'routing_rule': p.get('routing_rule'),
                'confidence': p.get('confidence'),
                'stars': p.get('stars'),
                'probabilita_stimata': p.get('probabilita_stimata'),
                'live_score': live_score,
                'live_status': live_status,
            })
    return pd.DataFrame(rows)


def is_scrematura(routing_rule) -> bool:
    if not routing_rule or not isinstance(routing_rule, str):
        return False
    r = routing_rule.lower()
    keywords = ['screm', 'filter', 'low_q', 'toxic']
    return any(k in r for k in keywords)


def compute_roi(df: pd.DataFrame) -> dict:
    if len(df) == 0:
        return {'n': 0, 'hr': None, 'pl': 0, 'roi': None}
    valid = df[df['esito'].notna() & df['pl'].notna()]
    if len(valid) == 0:
        return {'n': len(df), 'hr': None, 'pl': 0, 'roi': None}
    n = len(valid)
    pl = valid['pl'].sum()
    hr = valid['esito'].mean() * 100
    return {'n': n, 'hr': round(hr, 2),
            'pl': round(pl, 2), 'roi': round(pl / n * 100, 2)}


def fmt_summary(label, s):
    if s['n'] == 0:
        return f'| {label} | 0 | — | — | — |'
    pl_s = '+' if s['pl'] >= 0 else ''
    roi_s = '+' if s['roi'] >= 0 else ''
    return f'| {label} | {s["n"]} | {s["hr"]:.2f}% | {pl_s}{s["pl"]:.2f} | {roi_s}{s["roi"]:.2f}% |'


def main():
    print('Connessione MongoDB...')
    db = load_db()

    print('Estrazione NO BET dalla finestra 2026-02-19 → 2026-04-18...')
    df = extract_no_bets(db)
    print(f'  Trovati: {len(df)} NO BET (prima della risoluzione esito)')

    print('Costruzione mappa risultati (h2h_by_round + coppe)...')
    rmap = build_results_map(db)
    print(f'  {len(rmap)} risultati indicizzati')

    print('Matching esiti reali...')
    def _resolve(row):
        key = f"{row['home']}|||{row['away']}|||{row['date']}"
        rs = rmap.get(key)
        if not rs and row['live_status'] == 'Finished' and row['live_score']:
            rs = row['live_score']
        return rs
    df['real_score'] = df.apply(_resolve, axis=1)

    # Calcolo esito/pl per ogni NO BET (simulando che fosse stato giocato a stake 1u)
    def _esito(row):
        if not row['real_score'] or not row['original_pronostico']:
            return None
        parsed = parse_score(row['real_score'])
        if not parsed:
            return None
        hit = check_pronostico(row['original_pronostico'], row['tipo'], parsed)
        return hit
    df['esito'] = df.apply(_esito, axis=1)

    def _pl(row):
        if row['esito'] is None:
            return None
        q = row['original_quota']
        if q is None or q <= 1:
            return None
        return (q - 1) if row['esito'] else -1.0
    df['pl'] = df.apply(_pl, axis=1)

    df['gruppo'] = df['source'].apply(classify)
    df['scrematura'] = df['routing_rule'].apply(is_scrematura)

    resolved = df[df['esito'].notna()].copy()
    unresolved = df[df['esito'].isna()].copy()
    print(f'  Risolti: {len(resolved)}, non risolti (no risultato): {len(unresolved)}')

    df.to_csv(HERE / 'no_bet_raw.csv', index=False)
    unresolved.to_csv(HERE / 'no_bet_unresolved.csv', index=False)

    # ============ Segmentazioni ============
    sections = []
    # Globale + split puri/scrematura
    glob = compute_roi(resolved)
    sec_scrematura = compute_roi(resolved[resolved['scrematura']])
    sec_puri = compute_roi(resolved[~resolved['scrematura']])
    sections.append(('GLOBALE — tutti NO BET', glob))
    sections.append(('NO BET da scrematura/filtro', sec_scrematura))
    sections.append(('NO BET puri (non scrematura)', sec_puri))

    # Per mercato
    per_mercato = {}
    for mkt in MERCATI:
        per_mercato[mkt] = {
            'tutti': compute_roi(resolved[resolved['tipo'] == mkt]),
            'scrematura': compute_roi(resolved[(resolved['tipo'] == mkt) & (resolved['scrematura'])]),
            'puri': compute_roi(resolved[(resolved['tipo'] == mkt) & (~resolved['scrematura'])]),
        }

    # Per gruppo
    per_gruppo = {}
    for grp in GROUP_ORDER:
        sub = resolved[resolved['gruppo'] == grp]
        per_gruppo[grp] = {
            'tutti': compute_roi(sub),
            'scrematura': compute_roi(sub[sub['scrematura']]),
            'puri': compute_roi(sub[~sub['scrematura']]),
        }

    # Matrice gruppo × mercato
    matrix = {}
    for grp in GROUP_ORDER:
        for mkt in MERCATI:
            sub = resolved[(resolved['gruppo'] == grp) & (resolved['tipo'] == mkt)]
            matrix[(grp, mkt)] = compute_roi(sub)

    # Top routing_rule per volume e ROI
    routing_stats = []
    for rr, sub in resolved.groupby('routing_rule', dropna=False):
        s = compute_roi(sub)
        if s['n'] == 0:
            continue
        routing_stats.append({
            'routing_rule': str(rr),
            'n': s['n'], 'hr': s['hr'], 'pl': s['pl'], 'roi': s['roi'],
        })
    routing_df = pd.DataFrame(routing_stats).sort_values('n', ascending=False)
    routing_df.to_csv(HERE / 'no_bet_per_routing_rule.csv', index=False)

    # CSV aggregati
    rows_mkt = []
    for mkt in MERCATI:
        for k, s in per_mercato[mkt].items():
            rows_mkt.append({'mercato': mkt, 'scope': k, **s})
    pd.DataFrame(rows_mkt).to_csv(HERE / 'no_bet_per_mercato.csv', index=False)

    rows_grp = []
    for grp in GROUP_ORDER:
        for k, s in per_gruppo[grp].items():
            rows_grp.append({'gruppo': grp, 'scope': k, **s})
    pd.DataFrame(rows_grp).to_csv(HERE / 'no_bet_per_gruppo.csv', index=False)

    rows_mat = []
    for (grp, mkt), s in matrix.items():
        rows_mat.append({'gruppo': grp, 'mercato': mkt, **s})
    pd.DataFrame(rows_mat).to_csv(HERE / 'no_bet_matrice.csv', index=False)

    # Plot: ROI barre per mercato (tutti/scrematura/puri)
    fig, ax = plt.subplots(figsize=(10, 6))
    cats = MERCATI + ['GLOBALE']
    xs = np.arange(len(cats))
    width = 0.28
    vals_all, vals_scr, vals_pur = [], [], []
    counts_all = []
    for mkt in MERCATI:
        vals_all.append(per_mercato[mkt]['tutti']['roi'] or 0)
        vals_scr.append(per_mercato[mkt]['scrematura']['roi'] or 0)
        vals_pur.append(per_mercato[mkt]['puri']['roi'] or 0)
        counts_all.append(per_mercato[mkt]['tutti']['n'])
    vals_all.append(glob['roi'] or 0)
    vals_scr.append(sec_scrematura['roi'] or 0)
    vals_pur.append(sec_puri['roi'] or 0)
    counts_all.append(glob['n'])
    ax.bar(xs - width, vals_all, width, label='Tutti', color='#666')
    ax.bar(xs, vals_scr, width, label='Scrematura/filtro', color='#d6604d')
    ax.bar(xs + width, vals_pur, width, label='NO BET puri', color='#4393c3')
    for i, n in enumerate(counts_all):
        ax.text(xs[i] - width, vals_all[i] + (1 if vals_all[i] >= 0 else -2),
                f'N={n}', ha='center', fontsize=8)
    ax.axhline(0, color='black', linewidth=0.7)
    ax.set_xticks(xs)
    ax.set_xticklabels(cats)
    ax.set_ylabel('ROI simulato (%)')
    ax.set_title('NO BET simulati — ROI per mercato')
    ax.grid(True, alpha=0.3, axis='y')
    ax.legend()
    plt.tight_layout()
    plt.savefig(HERE / 'no_bet_roi_per_mercato.png', dpi=120)
    plt.close()

    # ============ Report ============
    md = ['# Punto 4 — Analisi NO BET ed esclusioni', '',
          f'Finestra: {DATE_FROM} → {DATE_TO}.',
          f'NO BET estratti: **{len(df)}**. Risolti con esito reale: **{len(resolved)}** ({len(resolved)/max(1,len(df))*100:.1f}%).',
          f'Non risolti (mancava real_score): {len(unresolved)}.',
          '',
          'Simulazione: ogni NO BET viene "giocato" a 1 unità con `original_pronostico` e `original_quota`.',
          'Classificazione scrematura = routing_rule contiene `screm`, `filter`, `low_q` o `toxic`.',
          '',
          '## 1. Riepilogo globale',
          '',
          '| Scope | N | HR | PL | ROI |',
          '| --- | ---: | ---: | ---: | ---: |']
    for lbl, s in sections:
        md.append(fmt_summary(lbl, s))
    md.append('')

    md.append('## 2. NO BET per mercato')
    md.append('')
    md.append('| Mercato | Scope | N | HR | PL | ROI |')
    md.append('| --- | --- | ---: | ---: | ---: | ---: |')
    for mkt in MERCATI:
        for k, s in per_mercato[mkt].items():
            if s['n'] == 0:
                md.append(f'| {mkt} | {k} | 0 | — | — | — |')
            else:
                pl_s = '+' if s['pl'] >= 0 else ''
                roi_s = '+' if s['roi'] >= 0 else ''
                md.append(f'| {mkt} | {k} | {s["n"]} | {s["hr"]:.2f}% | {pl_s}{s["pl"]:.2f} | {roi_s}{s["roi"]:.2f}% |')
    md.append('')

    md.append('## 3. NO BET per gruppo source')
    md.append('')
    md.append('| Gruppo | Scope | N | HR | PL | ROI |')
    md.append('| --- | --- | ---: | ---: | ---: | ---: |')
    for grp in GROUP_ORDER:
        for k, s in per_gruppo[grp].items():
            if s['n'] == 0:
                md.append(f'| {grp} | {k} | 0 | — | — | — |')
            else:
                pl_s = '+' if s['pl'] >= 0 else ''
                roi_s = '+' if s['roi'] >= 0 else ''
                md.append(f'| {grp} | {k} | {s["n"]} | {s["hr"]:.2f}% | {pl_s}{s["pl"]:.2f} | {roi_s}{s["roi"]:.2f}% |')
    md.append('')

    md.append('## 4. Matrice gruppo × mercato')
    md.append('')
    md.append('| Gruppo \\ Mercato | ' + ' | '.join(MERCATI) + ' |')
    md.append('| --- | ' + ' | '.join([':---:'] * len(MERCATI)) + ' |')
    for grp in GROUP_ORDER:
        cells = [grp]
        for mkt in MERCATI:
            s = matrix[(grp, mkt)]
            if s['n'] == 0:
                cells.append('—')
            else:
                roi_s = '+' if s['roi'] >= 0 else ''
                cells.append(f'N={s["n"]}, ROI={roi_s}{s["roi"]:.2f}%')
        md.append('| ' + ' | '.join(cells) + ' |')
    md.append('')

    md.append('## 5. Top routing_rule (per volume)')
    md.append('')
    md.append('| Routing rule | N | HR | PL | ROI |')
    md.append('| --- | ---: | ---: | ---: | ---: |')
    for _, r in routing_df.head(25).iterrows():
        pl_s = '+' if r['pl'] >= 0 else ''
        roi_s = '+' if r['roi'] >= 0 else ''
        md.append(
            f'| `{r["routing_rule"]}` | {int(r["n"])} | {r["hr"]:.2f}% | '
            f'{pl_s}{r["pl"]:.2f} | {roi_s}{r["roi"]:.2f}% |'
        )
    md.append('')

    md.append('## 6. Osservazioni oggettive')
    md.append('')
    md.append('### Interpretazione')
    md.append('')
    md.append('- ROI < 0 su NO BET = **filtro giusto** (avrebbero perso soldi se giocati).')
    md.append('- ROI > 0 su NO BET = **filtro troppo aggressivo** (erano profittevoli).')
    md.append('- ROI ~ 0 = filtro neutro.')
    md.append('')

    # Filtri troppo aggressivi
    md.append('### Filtri potenzialmente da rivedere (ROI > +5% e N ≥ 30)')
    md.append('')
    md.append('| Scope | N | HR | ROI |')
    md.append('| --- | ---: | ---: | ---: |')
    fl = False
    for _, r in routing_df.iterrows():
        if r['n'] >= 30 and r['roi'] is not None and r['roi'] >= 5:
            md.append(f'| rule=`{r["routing_rule"]}` | {int(r["n"])} | {r["hr"]:.2f}% | +{r["roi"]:.2f}% |')
            fl = True
    for mkt in MERCATI:
        s = per_mercato[mkt]['scrematura']
        if s['n'] >= 30 and s['roi'] is not None and s['roi'] >= 5:
            md.append(f'| mercato={mkt} scrematura | {s["n"]} | {s["hr"]:.2f}% | +{s["roi"]:.2f}% |')
            fl = True
    if not fl:
        md.append('| — | — | — | — |')
    md.append('')

    md.append('### Filtri che funzionano (ROI ≤ -5% e N ≥ 30)')
    md.append('')
    md.append('| Scope | N | HR | ROI |')
    md.append('| --- | ---: | ---: | ---: |')
    fl = False
    for _, r in routing_df.iterrows():
        if r['n'] >= 30 and r['roi'] is not None and r['roi'] <= -5:
            md.append(f'| rule=`{r["routing_rule"]}` | {int(r["n"])} | {r["hr"]:.2f}% | {r["roi"]:.2f}% |')
            fl = True
    if not fl:
        md.append('| — | — | — | — |')
    md.append('')

    md.append('## 7. File generati')
    md.append('')
    md.append('- `no_bet_raw.csv` — tutti i NO BET con esito+PL simulato')
    md.append('- `no_bet_unresolved.csv` — NO BET senza real_score disponibile')
    md.append('- `no_bet_per_mercato.csv`')
    md.append('- `no_bet_per_gruppo.csv`')
    md.append('- `no_bet_matrice.csv` (gruppo × mercato)')
    md.append('- `no_bet_per_routing_rule.csv` — breakdown per regola')
    md.append('- `no_bet_roi_per_mercato.png`')

    (HERE / 'report.md').write_text('\n'.join(md), encoding='utf-8')
    print(f'Output in: {HERE}')


if __name__ == '__main__':
    main()
