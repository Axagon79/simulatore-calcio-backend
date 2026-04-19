"""Punto 1 — Reliability diagram.

Calcola la calibrazione di `probabilita_stimata` vs HR reale su 6 gruppi
mutuamente esclusivi (A, S, C, A+S, C-derivati, Altro) e 5 bin
(35-50, 50-60, 60-70, 70-80, 80+).

Solo lettura. Output in 01_calibrazione/.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
CACHE = HERE.parent.parent / 'pattern_discovery' / 'dataset_cache.parquet'

BINS = [35, 50, 60, 70, 80, 101]
BIN_LABELS = ['35-50', '50-60', '60-70', '70-80', '80+']

GROUP_ORDER = ['A', 'S', 'C', 'A+S', 'C-derivati', 'Altro']


def classify(src: str) -> str:
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


def compute_table(df_grp: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for i, label in enumerate(BIN_LABELS):
        lo, hi = BINS[i], BINS[i + 1]
        sub = df_grp[(df_grp['probabilita_stimata'] >= lo) & (df_grp['probabilita_stimata'] < hi)]
        n = len(sub)
        if n == 0:
            rows.append({
                'bin': label, 'n': 0, 'prob_mean': np.nan,
                'hr_reale': np.nan, 'delta': np.nan,
            })
            continue
        prob_mean = sub['probabilita_stimata'].mean()
        hr_reale = sub['esito'].mean() * 100
        rows.append({
            'bin': label,
            'n': n,
            'prob_mean': round(prob_mean, 2),
            'hr_reale': round(hr_reale, 2),
            'delta': round(hr_reale - prob_mean, 2),
        })
    return pd.DataFrame(rows)


def plot_reliability(tables: dict[str, pd.DataFrame], outpath: Path) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    axes = axes.flatten()
    for ax, grp in zip(axes, GROUP_ORDER):
        t = tables[grp]
        valid = t.dropna(subset=['prob_mean', 'hr_reale'])
        ax.plot([30, 100], [30, 100], '--', color='gray', linewidth=1, label='Ideale')
        if len(valid) > 0:
            sizes = np.clip(valid['n'].values * 3, 20, 400)
            ax.scatter(valid['prob_mean'], valid['hr_reale'], s=sizes,
                       alpha=0.7, edgecolor='black')
            for _, r in valid.iterrows():
                ax.annotate(f"{r['bin']}\n(n={int(r['n'])})",
                            (r['prob_mean'], r['hr_reale']),
                            textcoords='offset points', xytext=(8, 4), fontsize=7)
        ax.set_xlim(30, 100)
        ax.set_ylim(0, 100)
        ax.set_xlabel('Probabilità stimata (media bin)')
        ax.set_ylabel('HR reale (%)')
        ax.set_title(f'Gruppo {grp}  (N tot={int(t["n"].sum())})')
        ax.grid(True, alpha=0.3)
        ax.legend(loc='upper left', fontsize=8)
    plt.tight_layout()
    plt.savefig(outpath, dpi=120)
    plt.close()


def plot_combined(tables: dict[str, pd.DataFrame], outpath: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.plot([30, 100], [30, 100], '--', color='gray', linewidth=1, label='Ideale')
    colors = plt.cm.tab10(np.linspace(0, 1, len(GROUP_ORDER)))
    for grp, color in zip(GROUP_ORDER, colors):
        t = tables[grp].dropna(subset=['prob_mean', 'hr_reale'])
        if len(t) == 0:
            continue
        ax.plot(t['prob_mean'], t['hr_reale'], '-o', color=color,
                label=f'{grp} (N={int(tables[grp]["n"].sum())})',
                markersize=6)
    ax.set_xlim(30, 100)
    ax.set_ylim(0, 100)
    ax.set_xlabel('Probabilità stimata (media bin)')
    ax.set_ylabel('HR reale (%)')
    ax.set_title('Reliability diagram — 6 gruppi a confronto')
    ax.grid(True, alpha=0.3)
    ax.legend(loc='lower right', fontsize=9)
    plt.tight_layout()
    plt.savefig(outpath, dpi=120)
    plt.close()


def fmt_table_md(grp: str, t: pd.DataFrame) -> str:
    lines = [f'### Gruppo {grp}', '']
    lines.append('| Bin | N | Prob. media | HR reale | Delta (HR - prob) |')
    lines.append('| --- | ---: | ---: | ---: | ---: |')
    for _, r in t.iterrows():
        if r['n'] == 0:
            lines.append(f'| {r["bin"]} | 0 | — | — | — |')
        else:
            sign = '+' if r['delta'] >= 0 else ''
            lines.append(
                f'| {r["bin"]} | {int(r["n"])} | {r["prob_mean"]:.2f}% | '
                f'{r["hr_reale"]:.2f}% | {sign}{r["delta"]:.2f} |'
            )
    lines.append('')
    return '\n'.join(lines)


def observations(tables: dict[str, pd.DataFrame]) -> str:
    lines = ['## Osservazioni oggettive', '']
    # Delta totale pesato per gruppo
    lines.append('### Delta medio pesato per gruppo (HR reale - probabilità stimata)')
    lines.append('')
    lines.append('| Gruppo | N totale | Prob. media pesata | HR media | Delta |')
    lines.append('| --- | ---: | ---: | ---: | ---: |')
    for grp in GROUP_ORDER:
        t = tables[grp]
        valid = t[t['n'] > 0]
        if valid['n'].sum() == 0:
            lines.append(f'| {grp} | 0 | — | — | — |')
            continue
        w = valid['n']
        prob_w = (valid['prob_mean'] * w).sum() / w.sum()
        hr_w = (valid['hr_reale'] * w).sum() / w.sum()
        delta_w = hr_w - prob_w
        sign = '+' if delta_w >= 0 else ''
        lines.append(
            f'| {grp} | {int(w.sum())} | {prob_w:.2f}% | {hr_w:.2f}% | {sign}{delta_w:.2f} |'
        )
    lines.append('')

    # Bin problematici: delta < -5 oppure > +5 con n >= 30
    lines.append('### Bin con delta significativo (|delta| >= 5 e N >= 30)')
    lines.append('')
    lines.append('| Gruppo | Bin | N | Prob. media | HR | Delta | Tipo |')
    lines.append('| --- | --- | ---: | ---: | ---: | ---: | --- |')
    found = False
    for grp in GROUP_ORDER:
        t = tables[grp]
        for _, r in t.iterrows():
            if r['n'] >= 30 and pd.notna(r['delta']) and abs(r['delta']) >= 5:
                tipo = 'overconfident' if r['delta'] < 0 else 'underconfident'
                sign = '+' if r['delta'] >= 0 else ''
                lines.append(
                    f'| {grp} | {r["bin"]} | {int(r["n"])} | {r["prob_mean"]:.2f}% | '
                    f'{r["hr_reale"]:.2f}% | {sign}{r["delta"]:.2f} | {tipo} |'
                )
                found = True
    if not found:
        lines.append('| — | — | — | — | — | — | (nessuno) |')
    lines.append('')
    return '\n'.join(lines)


def main():
    df = pd.read_parquet(CACHE)
    print(f'Dataset: {len(df)} righe')
    df = df[df['probabilita_stimata'].notna()].copy()
    print(f'Con probabilita_stimata: {len(df)}')
    df['gruppo'] = df['source'].apply(classify)

    # Distribuzione gruppi
    print('\nDistribuzione gruppi:')
    print(df['gruppo'].value_counts().reindex(GROUP_ORDER, fill_value=0).to_string())

    tables = {}
    for grp in GROUP_ORDER:
        sub = df[df['gruppo'] == grp]
        tables[grp] = compute_table(sub)

    # CSV combinato
    csv_rows = []
    for grp in GROUP_ORDER:
        t = tables[grp].copy()
        t.insert(0, 'gruppo', grp)
        csv_rows.append(t)
    big = pd.concat(csv_rows, ignore_index=True)
    big.to_csv(HERE / 'calibrazione_per_gruppo.csv', index=False)

    # PNG
    plot_reliability(tables, HERE / 'reliability_diagram_6gruppi.png')
    plot_combined(tables, HERE / 'reliability_diagram_combined.png')

    # Report markdown
    md = ['# Punto 1 — Reliability Diagram (Calibrazione)',
          '',
          f'Dataset: **{len(df)}** pronostici con `probabilita_stimata` valorizzata',
          f'(su {1501} totali), finestra 2026-02-19 → 2026-04-18.',
          '',
          'Bin usati: 35-50, 50-60, 60-70, 70-80, 80+.',
          '',
          'Delta = HR reale − probabilità media stimata nel bin.',
          'Delta negativo = overconfident. Delta positivo = underconfident.',
          '',
          '## Distribuzione gruppi',
          '',
          '| Gruppo | N |',
          '| --- | ---: |']
    counts = df['gruppo'].value_counts().reindex(GROUP_ORDER, fill_value=0)
    for grp in GROUP_ORDER:
        md.append(f'| {grp} | {int(counts[grp])} |')
    md.append('')
    md.append('## Tabelle per gruppo')
    md.append('')
    for grp in GROUP_ORDER:
        md.append(fmt_table_md(grp, tables[grp]))
    md.append(observations(tables))
    md.append('## File generati')
    md.append('')
    md.append('- `calibrazione_per_gruppo.csv` — dati raw')
    md.append('- `reliability_diagram_6gruppi.png` — 6 pannelli')
    md.append('- `reliability_diagram_combined.png` — tutti i gruppi sovrapposti')
    (HERE / 'report.md').write_text('\n'.join(md), encoding='utf-8')
    print(f'\nOutput salvati in: {HERE}')


if __name__ == '__main__':
    main()
