"""Punto 4 (parte C) — Analisi conversioni di scrematura.

Per ogni pronostico in daily_predictions_unified con routing_rule
contenente `_conv` o `_rec` (conversioni/recuperi da scrematura):
- pronostico convertito (quello realmente giocato)
- original_pronostico + original_quota (quello che sarebbe stato giocato
  prima della conversione)
- calcola PL simulato dell'originale con real_score
- confronta PL convertito (reale, dal DB) vs PL originale (simulato)

Output in 04_no_bet/.
"""
from __future__ import annotations

import importlib.util
import re
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
BACKEND_ROOT = HERE.parent.parent.parent

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
    p = str(pronostico).strip()
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
        if p.lower() in ('goal', 'gg'): return parsed['btts']
        if p.lower() in ('nogoal', 'ng'): return not parsed['btts']
        mg = re.match(r'MG\s+(\d+)-(\d+)', p, re.IGNORECASE)
        if mg:
            return int(mg.group(1)) <= parsed['total'] <= int(mg.group(2))
    return None


def infer_tipo(pronostico) -> str | None:
    """Deduce il tipo di mercato dal pronostico."""
    if not pronostico:
        return None
    p = str(pronostico).strip()
    if p in ('1', 'X', '2'):
        return 'SEGNO'
    if p in ('1X', 'X2', '12'):
        return 'DOPPIA_CHANCE'
    if re.match(r'(Over|Under)\s+[\d.]+', p, re.IGNORECASE):
        return 'GOL'
    if p.lower() in ('goal', 'gg', 'nogoal', 'ng'):
        return 'GOL'
    if re.match(r'MG\s+\d+-\d+', p, re.IGNORECASE):
        return 'GOL'
    return None


def load_db():
    spec = importlib.util.spec_from_file_location('backend_config', BACKEND_ROOT / 'config.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.db


def build_results_map(db):
    rmap = {}
    pipe = [
        {"$unwind": "$matches"},
        {"$match": {"matches.real_score": {"$ne": None}}},
        {"$project": {"home": "$matches.home", "away": "$matches.away",
                      "date": "$matches.date_obj", "score": "$matches.real_score"}},
    ]
    for d in db.h2h_by_round.aggregate(pipe):
        dt = d.get('date')
        if not dt:
            continue
        ds = dt.strftime('%Y-%m-%d')
        rmap[f"{d['home']}|||{d['away']}|||{ds}"] = d['score']
        for delta in (-1, 1):
            alt = (dt + timedelta(days=delta)).strftime('%Y-%m-%d')
            rmap.setdefault(f"{d['home']}|||{d['away']}|||{alt}", d['score'])
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


def extract_conversions(db) -> pd.DataFrame:
    """Estrae pronostici con routing_rule indicativa di conversione."""
    q = {'date': {'$gte': DATE_FROM, '$lte': DATE_TO}}
    rows = []
    for doc in db['daily_predictions_unified'].find(q):
        home = doc.get('home')
        away = doc.get('away')
        date_s = doc.get('date')
        live_score = doc.get('live_score')
        live_status = doc.get('live_status')
        for p in doc.get('pronostici', []):
            rr = p.get('routing_rule') or ''
            src = p.get('source') or ''
            is_conv = ('_conv' in rr) or ('_conv' in src) or ('_rec' in rr) or ('_rec' in src)
            if not is_conv:
                continue
            if p.get('pronostico') == 'NO BET':
                continue
            op = p.get('original_pronostico')
            oq = p.get('original_quota')
            if op in (None, '', '?') or oq in (None, 0):
                continue
            rows.append({
                'date': date_s, 'home': home, 'away': away,
                'tipo_conv': p.get('tipo'),
                'pronostico_conv': p.get('pronostico'),
                'quota_conv': p.get('quota'),
                'pl_conv_real': p.get('profit_loss'),
                'esito_conv_real': p.get('esito'),
                'stake_conv': p.get('stake'),
                'original_pronostico': op,
                'original_quota': oq,
                'source': src,
                'routing_rule': rr,
                'live_score': live_score,
                'live_status': live_status,
            })
    return pd.DataFrame(rows)


def compute_roi(df: pd.DataFrame, pl_col: str) -> dict:
    if len(df) == 0:
        return {'n': 0, 'hr': None, 'pl': 0, 'roi': None}
    valid = df[df[pl_col].notna()]
    if len(valid) == 0:
        return {'n': 0, 'hr': None, 'pl': 0, 'roi': None}
    n = len(valid)
    pl = valid[pl_col].sum()
    # HR sulla colonna hit_col correlata? Ricavo dal pl stesso: pl>0 = win
    wins = (valid[pl_col] > 0).sum()
    return {'n': n, 'hr': round(wins / n * 100, 2),
            'pl': round(pl, 2), 'roi': round(pl / n * 100, 2)}


def main():
    print('Connessione MongoDB...')
    db = load_db()

    print('Estrazione conversioni...')
    df = extract_conversions(db)
    print(f'  {len(df)} righe raw')

    print('Mappa risultati...')
    rmap = build_results_map(db)

    # Risolvi real_score
    def _resolve(r):
        key = f"{r['home']}|||{r['away']}|||{r['date']}"
        rs = rmap.get(key)
        if not rs and r['live_status'] == 'Finished' and r['live_score']:
            rs = r['live_score']
        return rs
    df['real_score'] = df.apply(_resolve, axis=1)

    # Deduci tipo originale
    df['tipo_orig'] = df['original_pronostico'].apply(infer_tipo)

    # Esito + PL simulato dell'originale a 1u
    def _esito_orig(r):
        if not r['real_score'] or not r['tipo_orig']:
            return None
        parsed = parse_score(r['real_score'])
        if not parsed:
            return None
        return check_pronostico(r['original_pronostico'], r['tipo_orig'], parsed)
    df['esito_orig'] = df.apply(_esito_orig, axis=1)

    def _pl_orig(r):
        if r['esito_orig'] is None:
            return None
        q = r['original_quota']
        if q is None or q <= 1:
            return None
        return (q - 1) if r['esito_orig'] else -1.0
    df['pl_orig_sim_1u'] = df.apply(_pl_orig, axis=1)

    # PL convertito ricondotto a 1u per confronto equo
    def _pl_conv_unit(r):
        if r['pl_conv_real'] is None or r['stake_conv'] in (None, 0):
            return None
        return r['pl_conv_real'] / r['stake_conv']
    df['pl_conv_1u'] = df.apply(_pl_conv_unit, axis=1)

    # Delta: se >0 la conversione ha fatto MEGLIO del pronostico originale
    df['delta_1u'] = df['pl_conv_1u'] - df['pl_orig_sim_1u']
    df['gruppo'] = df['source'].apply(classify)

    df.to_csv(HERE / 'conversioni_raw.csv', index=False)

    resolved = df[df['pl_orig_sim_1u'].notna() & df['pl_conv_1u'].notna()].copy()
    print(f'  Risolti (entrambi i PL disponibili): {len(resolved)} / {len(df)}')

    # ============ Segmentazioni ============
    def summary(sub):
        if len(sub) == 0:
            return {'n': 0, 'pl_conv_1u': 0, 'pl_orig_1u': 0, 'delta': 0,
                    'roi_conv': None, 'roi_orig': None,
                    'hr_conv': None, 'hr_orig': None,
                    'hit_improvement': 0}
        pl_c = sub['pl_conv_1u'].sum()
        pl_o = sub['pl_orig_sim_1u'].sum()
        hr_c = (sub['pl_conv_1u'] > 0).mean() * 100
        hr_o = (sub['pl_orig_sim_1u'] > 0).mean() * 100
        improv = int(((sub['pl_conv_1u'] > 0) & (sub['pl_orig_sim_1u'] <= 0)).sum())
        worse = int(((sub['pl_conv_1u'] <= 0) & (sub['pl_orig_sim_1u'] > 0)).sum())
        return {
            'n': len(sub),
            'pl_conv_1u': round(pl_c, 2),
            'pl_orig_1u': round(pl_o, 2),
            'delta': round(pl_c - pl_o, 2),
            'roi_conv': round(pl_c / len(sub) * 100, 2),
            'roi_orig': round(pl_o / len(sub) * 100, 2),
            'hr_conv': round(hr_c, 2),
            'hr_orig': round(hr_o, 2),
            'salvate_da_conv': improv,   # conv vince dove originale perdeva
            'peggiorate_da_conv': worse, # conv perde dove originale vinceva
        }

    s_global = summary(resolved)
    # Per conversione (mercato originale → mercato convertito)
    resolved['conv_type'] = resolved['tipo_orig'].astype(str) + ' → ' + resolved['tipo_conv'].astype(str)
    per_conv = {ct: summary(resolved[resolved['conv_type'] == ct])
                for ct in sorted(resolved['conv_type'].unique())}
    # Per mercato convertito
    per_mkt_conv = {mkt: summary(resolved[resolved['tipo_conv'] == mkt]) for mkt in MERCATI}
    # Per mercato originale
    per_mkt_orig = {mkt: summary(resolved[resolved['tipo_orig'] == mkt]) for mkt in MERCATI}
    # Per gruppo source
    per_grp = {grp: summary(resolved[resolved['gruppo'] == grp]) for grp in GROUP_ORDER}
    # Per routing rule
    per_rr = {}
    for rr, sub in resolved.groupby('routing_rule'):
        per_rr[rr] = summary(sub)

    # CSV aggregati
    rows_conv = [{'conv_type': k, **v} for k, v in per_conv.items()]
    pd.DataFrame(rows_conv).to_csv(HERE / 'conversioni_per_tipo.csv', index=False)
    rows_rr = [{'routing_rule': k, **v} for k, v in per_rr.items()]
    pd.DataFrame(rows_rr).sort_values('n', ascending=False).to_csv(
        HERE / 'conversioni_per_routing_rule.csv', index=False)

    # ============ Report ============
    md = ['# Punto 4 (parte C) — Analisi conversioni di scrematura', '',
          f'Finestra: {DATE_FROM} → {DATE_TO}.',
          f'Pronostici convertiti (routing_rule/source contiene `_conv` o `_rec`,',
          f'con `original_pronostico` e `original_quota` valorizzati): **{len(df)}**.',
          f'Risolti (entrambi i PL disponibili): **{len(resolved)}**.',
          '',
          'Confronto per unità (1u stake):',
          '- `pl_conv_1u`: PL reale del pronostico convertito, diviso lo stake.',
          '- `pl_orig_1u`: PL simulato del pronostico originale (prima della conversione) a 1u.',
          '- `delta`: pl_conv − pl_orig. Positivo = la conversione ha migliorato.',
          '',
          '## 1. Riepilogo globale', '',
          '| N | PL conv (1u) | PL orig (1u) | Δ | ROI conv | ROI orig | HR conv | HR orig | Salvate | Peggiorate |',
          '| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |',
          (f'| {s_global["n"]} | '
           f'{s_global["pl_conv_1u"]:+.2f} | {s_global["pl_orig_1u"]:+.2f} | '
           f'{s_global["delta"]:+.2f} | '
           f'{s_global["roi_conv"]:+.2f}% | {s_global["roi_orig"]:+.2f}% | '
           f'{s_global["hr_conv"]:.2f}% | {s_global["hr_orig"]:.2f}% | '
           f'{s_global["salvate_da_conv"]} | {s_global["peggiorate_da_conv"]} |'),
          '',
          '## 2. Per tipo di conversione (mercato orig → mercato conv)', '',
          '| Conversione | N | PL conv (1u) | PL orig (1u) | Δ | ROI conv | ROI orig | Salvate | Peggiorate |',
          '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for ct, s in sorted(per_conv.items(), key=lambda x: -x[1]['n']):
        md.append(
            f'| {ct} | {s["n"]} | '
            f'{s["pl_conv_1u"]:+.2f} | {s["pl_orig_1u"]:+.2f} | '
            f'{s["delta"]:+.2f} | {s["roi_conv"]:+.2f}% | {s["roi_orig"]:+.2f}% | '
            f'{s["salvate_da_conv"]} | {s["peggiorate_da_conv"]} |'
        )
    md.append('')

    md.append('## 3. Per routing_rule (top 20 per volume)')
    md.append('')
    md.append('| Routing rule | N | PL conv | PL orig | Δ | ROI conv | ROI orig | Salv | Peggior |')
    md.append('| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |')
    for rr, s in sorted(per_rr.items(), key=lambda x: -x[1]['n'])[:20]:
        md.append(
            f'| `{rr}` | {s["n"]} | '
            f'{s["pl_conv_1u"]:+.2f} | {s["pl_orig_1u"]:+.2f} | '
            f'{s["delta"]:+.2f} | {s["roi_conv"]:+.2f}% | {s["roi_orig"]:+.2f}% | '
            f'{s["salvate_da_conv"]} | {s["peggiorate_da_conv"]} |'
        )
    md.append('')

    md.append('## 4. Per mercato convertito (quello realmente giocato)')
    md.append('')
    md.append('| Mercato conv | N | PL conv (1u) | PL orig (1u) | Δ | ROI conv | ROI orig |')
    md.append('| --- | ---: | ---: | ---: | ---: | ---: | ---: |')
    for mkt in MERCATI:
        s = per_mkt_conv[mkt]
        if s['n'] == 0:
            md.append(f'| {mkt} | 0 | — | — | — | — | — |')
        else:
            md.append(
                f'| {mkt} | {s["n"]} | {s["pl_conv_1u"]:+.2f} | {s["pl_orig_1u"]:+.2f} | '
                f'{s["delta"]:+.2f} | {s["roi_conv"]:+.2f}% | {s["roi_orig"]:+.2f}% |'
            )
    md.append('')

    md.append('## 5. Per mercato originale (quello previsto prima della conversione)')
    md.append('')
    md.append('| Mercato orig | N | PL conv (1u) | PL orig (1u) | Δ | ROI conv | ROI orig |')
    md.append('| --- | ---: | ---: | ---: | ---: | ---: | ---: |')
    for mkt in MERCATI:
        s = per_mkt_orig[mkt]
        if s['n'] == 0:
            md.append(f'| {mkt} | 0 | — | — | — | — | — |')
        else:
            md.append(
                f'| {mkt} | {s["n"]} | {s["pl_conv_1u"]:+.2f} | {s["pl_orig_1u"]:+.2f} | '
                f'{s["delta"]:+.2f} | {s["roi_conv"]:+.2f}% | {s["roi_orig"]:+.2f}% |'
            )
    md.append('')

    md.append('## 6. Per gruppo source')
    md.append('')
    md.append('| Gruppo | N | PL conv (1u) | PL orig (1u) | Δ | ROI conv | ROI orig |')
    md.append('| --- | ---: | ---: | ---: | ---: | ---: | ---: |')
    for grp in GROUP_ORDER:
        s = per_grp[grp]
        if s['n'] == 0:
            md.append(f'| {grp} | 0 | — | — | — | — | — |')
        else:
            md.append(
                f'| {grp} | {s["n"]} | {s["pl_conv_1u"]:+.2f} | {s["pl_orig_1u"]:+.2f} | '
                f'{s["delta"]:+.2f} | {s["roi_conv"]:+.2f}% | {s["roi_orig"]:+.2f}% |'
            )
    md.append('')

    md.append('## 7. File generati')
    md.append('')
    md.append('- `conversioni_raw.csv`')
    md.append('- `conversioni_per_tipo.csv`')
    md.append('- `conversioni_per_routing_rule.csv`')

    (HERE / 'report_conversioni.md').write_text('\n'.join(md), encoding='utf-8')
    print(f'Output in: {HERE}')


if __name__ == '__main__':
    main()
