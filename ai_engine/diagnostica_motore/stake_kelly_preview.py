"""Confronto stake vecchio vs nuovo (kelly_unified) sui pronostici storici.

Output:
- `stake_kelly_preview.csv` — 10 pronostici campione (stratificati)
- `stake_kelly_simulazione.csv` — dataset completo con colonne
  stake_old / stake_new / prob_calibrata / edge / low_value
- `report.md` — sintesi con HR/ROI per gruppo low_value, delta PL simulato.

Nessuna modifica al DB. Nessun effetto sulla produzione.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
BACKEND_ROOT = HERE.parent.parent
CACHE = HERE.parent / 'pattern_discovery' / 'dataset_cache.parquet'


def load_db():
    spec = importlib.util.spec_from_file_location(
        'backend_config', BACKEND_ROOT / 'config.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.db


def main():
    import sys
    fp_path = BACKEND_ROOT / 'functions_python'
    if str(fp_path) not in sys.path:
        sys.path.insert(0, str(fp_path))
    from ai_engine.stake_kelly import kelly_unified, invalidate_cache

    print(f'Cache dataset: {CACHE}')
    df = pd.read_parquet(CACHE)
    df = df[df['probabilita_stimata'].notna() & df['quota'].notna()].copy()
    print(f'Dataset: {len(df)} pronostici')

    print('Connessione MongoDB...')
    db = load_db()
    invalidate_cache()  # forza reload calibration_table

    # --- Applica Kelly unificato ---
    def _kelly(r):
        res = kelly_unified(db, r['probabilita_stimata'], r['quota'],
                            r['source'], r['tipo'], kelly_fraction=0.25)
        return pd.Series({
            'stake_new': res['stake'],
            'edge_new': res['edge_pct'],
            'low_value': res['low_value'],
            'prob_calibrata': res['prob_calibrata'],
            'source_group': res['source_group'],
        })

    print('Calcolo Kelly unificato per ogni riga...')
    kelly_cols = df.apply(_kelly, axis=1)
    out = pd.concat([df, kelly_cols], axis=1)
    out = out.rename(columns={'stake': 'stake_old'})

    out['delta_stake'] = out['stake_new'] - out['stake_old']
    out['pl_old'] = out['stake_old'] * out['pl']
    out['pl_new'] = out['stake_new'] * out['pl']
    out['delta_pl'] = out['pl_new'] - out['pl_old']

    # --- Campione 10 stratificato per bin prob ---
    bins = [(35, 50), (50, 60), (60, 70), (70, 80), (80, 101)]
    sample_parts = []
    for lo, hi in bins:
        sub = out[(out['probabilita_stimata'] >= lo) & (out['probabilita_stimata'] < hi)]
        if len(sub) >= 2:
            sample_parts.append(sub.sample(2, random_state=42))
    sample = pd.concat(sample_parts, ignore_index=True) if sample_parts else out.head(10)
    sample_cols = ['date', 'source', 'source_group', 'tipo', 'pronostico',
                   'quota', 'probabilita_stimata', 'prob_calibrata',
                   'stake_old', 'stake_new', 'delta_stake', 'edge_new',
                   'low_value', 'esito', 'pl', 'pl_old', 'pl_new', 'delta_pl']
    sample[sample_cols].to_csv(HERE / 'stake_kelly_preview.csv', index=False)

    # --- Simulazione completa ---
    sim_cols = ['date', 'source', 'source_group', 'tipo', 'pronostico',
                'quota', 'probabilita_stimata', 'prob_calibrata',
                'stake_old', 'stake_new', 'edge_new', 'low_value',
                'esito', 'pl', 'pl_old', 'pl_new', 'delta_pl']
    out[sim_cols].to_csv(HERE / 'stake_kelly_simulazione.csv', index=False)

    # --- Statistiche aggregate ---
    n_total = len(out)
    n_lv = int(out['low_value'].sum())
    n_not_lv = n_total - n_lv

    sub_lv = out[out['low_value']]
    sub_no_lv = out[~out['low_value']]

    def _stats(sub):
        if len(sub) == 0:
            return {'n': 0, 'hr': None, 'roi_per_unit': None,
                    'pl_old_tot': 0, 'pl_new_tot': 0, 'delta_pl': 0}
        return {
            'n': len(sub),
            'hr': round(sub['esito'].mean() * 100, 2),
            'roi_per_unit': round(sub['pl'].mean() * 100, 2),  # ROI per stake 1u
            'pl_old_tot': round(sub['pl_old'].sum(), 2),
            'pl_new_tot': round(sub['pl_new'].sum(), 2),
            'delta_pl': round(sub['delta_pl'].sum(), 2),
            'stake_medio_old': round(sub['stake_old'].mean(), 2),
            'stake_medio_new': round(sub['stake_new'].mean(), 2),
            'unita_risk_old': int(sub['stake_old'].sum()),
            'unita_risk_new': int(sub['stake_new'].sum()),
        }

    stats = {
        'totale': _stats(out),
        'low_value (edge <= 0)': _stats(sub_lv),
        'positive_edge': _stats(sub_no_lv),
    }

    # Distribuzione delta stake
    delta_counts = out['delta_stake'].value_counts().sort_index()

    # Per gruppo
    per_group = {}
    for g in ['A', 'S', 'C', 'A+S', 'C-derivati', 'Altro']:
        sub = out[out['source_group'] == g]
        per_group[g] = _stats(sub)

    # --- Report MD ---
    md = ['# Preview Kelly unificato — Confronto stake vecchio vs nuovo', '',
          f'Dataset: {n_total} pronostici storici (19/02 → 18/04/2026).',
          f'Letta `calibration_table._id=current` da MongoDB.',
          '',
          '## 1. Statistiche globali', '',
          '| Scope | N | HR | Stake medio old | Stake medio new | PL old tot | PL new tot | Δ PL |',
          '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for k, s in stats.items():
        if s['n'] == 0:
            md.append(f'| {k} | 0 | — | — | — | — | — | — |')
        else:
            md.append(f'| {k} | {s["n"]} | {s["hr"]:.2f}% | {s["stake_medio_old"]} | '
                      f'{s["stake_medio_new"]} | {s["pl_old_tot"]:+.2f} | '
                      f'{s["pl_new_tot"]:+.2f} | {s["delta_pl"]:+.2f} |')
    md.append('')
    md.append(f'**Pronostici flaggati low_value**: {n_lv} su {n_total} '
              f'({n_lv / n_total * 100:.1f}%)')
    md.append('')

    md.append('## 2. Distribuzione delta stake (new - old)')
    md.append('')
    md.append('| Δ | N |')
    md.append('| ---: | ---: |')
    for d, n in delta_counts.items():
        md.append(f'| {int(d):+d} | {int(n)} |')
    md.append('')

    md.append('## 3. Per gruppo source')
    md.append('')
    md.append('| Gruppo | N | HR | Stake old | Stake new | PL old | PL new | Δ PL |')
    md.append('| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |')
    for g, s in per_group.items():
        if s['n'] == 0:
            md.append(f'| {g} | 0 | — | — | — | — | — | — |')
        else:
            md.append(f'| {g} | {s["n"]} | {s["hr"]:.2f}% | {s["stake_medio_old"]} | '
                      f'{s["stake_medio_new"]} | {s["pl_old_tot"]:+.2f} | '
                      f'{s["pl_new_tot"]:+.2f} | {s["delta_pl"]:+.2f} |')
    md.append('')

    md.append('## 4. Low value — HR e PL dei pronostici flaggati')
    md.append('')
    md.append('Un "low_value" è un pronostico per cui Kelly unificato ha calcolato '
              'edge <= 0 dopo calibrazione. Stake impostato a 1 (niente NO BET automatico).')
    md.append('')
    s = stats['low_value (edge <= 0)']
    if s['n'] > 0:
        md.append(f'- Volume low_value: **{s["n"]}** ({s["n"] / n_total * 100:.1f}% del dataset)')
        md.append(f'- HR storico low_value: **{s["hr"]:.2f}%**')
        md.append(f'- ROI/unit (PL medio a stake 1): **{s["roi_per_unit"]:+.2f}%**')
        md.append(f'- Con stake vecchio avrebbero contribuito: **PL {s["pl_old_tot"]:+.2f}u**')
        md.append(f'- Con stake nuovo (=1 forzato): **PL {s["pl_new_tot"]:+.2f}u**')
        md.append(f'- Delta: **{s["delta_pl"]:+.2f}u**')
    md.append('')

    md.append('## 5. File')
    md.append('')
    md.append('- `stake_kelly_preview.csv` — 10 righe campione stratificato per bin prob')
    md.append('- `stake_kelly_simulazione.csv` — dataset intero')

    (HERE / 'stake_kelly_report.md').write_text('\n'.join(md), encoding='utf-8')
    print(f'Output in: {HERE}')


if __name__ == '__main__':
    main()
