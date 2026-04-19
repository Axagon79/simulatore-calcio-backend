"""Punto 1 (esteso) — Reliability diagram per gruppo × mercato.

Aggiunge la dimensione `tipo` (SEGNO, DOPPIA_CHANCE, GOL) al Punto 1.

Output:
- calibrazione_per_mercato.csv         (aggregato per mercato)
- calibrazione_matrice_completa.csv    (gruppo × mercato × bin)
- reliability_per_mercato.png          (3 pannelli)
- reliability_matrice.png              (6 gruppi × 3 mercati)
- report_per_mercato.md
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


def compute_table(df_grp: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for i, label in enumerate(BIN_LABELS):
        lo, hi = BINS[i], BINS[i + 1]
        sub = df_grp[(df_grp['probabilita_stimata'] >= lo) & (df_grp['probabilita_stimata'] < hi)]
        n = len(sub)
        if n == 0:
            rows.append({'bin': label, 'n': 0, 'prob_mean': np.nan,
                         'hr_reale': np.nan, 'delta': np.nan})
            continue
        prob_mean = sub['probabilita_stimata'].mean()
        hr_reale = sub['esito'].mean() * 100
        rows.append({
            'bin': label, 'n': n,
            'prob_mean': round(prob_mean, 2),
            'hr_reale': round(hr_reale, 2),
            'delta': round(hr_reale - prob_mean, 2),
        })
    return pd.DataFrame(rows)


def weighted_summary(t: pd.DataFrame):
    valid = t[t['n'] > 0]
    if valid['n'].sum() == 0:
        return 0, np.nan, np.nan, np.nan
    w = valid['n']
    pw = (valid['prob_mean'] * w).sum() / w.sum()
    hw = (valid['hr_reale'] * w).sum() / w.sum()
    return int(w.sum()), pw, hw, hw - pw


def fmt_table_md(title: str, t: pd.DataFrame) -> str:
    lines = [f'### {title}', '']
    lines.append('| Bin | N | Prob. media | HR reale | Delta |')
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


def plot_per_mercato(tables_mkt: dict, outpath: Path):
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    for ax, mkt in zip(axes, MERCATI):
        t = tables_mkt[mkt]
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
        ax.set_title(f'{mkt}  (N={int(t["n"].sum())})')
        ax.grid(True, alpha=0.3)
        ax.legend(loc='upper left', fontsize=8)
    plt.tight_layout()
    plt.savefig(outpath, dpi=120)
    plt.close()


def plot_matrice(matrix_tables: dict, outpath: Path):
    fig, axes = plt.subplots(len(GROUP_ORDER), len(MERCATI),
                             figsize=(14, 18), sharex=True, sharey=True)
    for i, grp in enumerate(GROUP_ORDER):
        for j, mkt in enumerate(MERCATI):
            ax = axes[i, j]
            t = matrix_tables[(grp, mkt)]
            valid = t.dropna(subset=['prob_mean', 'hr_reale'])
            ax.plot([30, 100], [30, 100], '--', color='gray', linewidth=0.8)
            if len(valid) > 0:
                sizes = np.clip(valid['n'].values * 4, 20, 300)
                ax.scatter(valid['prob_mean'], valid['hr_reale'], s=sizes,
                           alpha=0.7, edgecolor='black')
            ax.set_xlim(30, 100)
            ax.set_ylim(0, 100)
            if i == 0:
                ax.set_title(mkt, fontsize=10)
            if j == 0:
                ax.set_ylabel(f'{grp}\nHR %', fontsize=9)
            if i == len(GROUP_ORDER) - 1:
                ax.set_xlabel('Prob. media %', fontsize=9)
            ax.grid(True, alpha=0.3)
            ax.text(0.02, 0.95, f'N={int(t["n"].sum())}',
                    transform=ax.transAxes, fontsize=8, va='top',
                    bbox=dict(boxstyle='round', facecolor='white', alpha=0.7))
    plt.suptitle('Reliability diagram — Gruppo × Mercato', fontsize=13)
    plt.tight_layout()
    plt.savefig(outpath, dpi=120)
    plt.close()


def main():
    df = pd.read_parquet(CACHE)
    df = df[df['probabilita_stimata'].notna()].copy()
    df['gruppo'] = df['source'].apply(classify)
    print(f'Dataset: {len(df)} righe con prob stimata')
    print('\nDistribuzione mercato:')
    print(df['tipo'].value_counts().to_string())

    # -- 1) Calibrazione per mercato (ignorando gruppo) --
    tables_mkt = {mkt: compute_table(df[df['tipo'] == mkt]) for mkt in MERCATI}

    # CSV per mercato
    rows = []
    for mkt in MERCATI:
        t = tables_mkt[mkt].copy()
        t.insert(0, 'mercato', mkt)
        rows.append(t)
    pd.concat(rows, ignore_index=True).to_csv(HERE / 'calibrazione_per_mercato.csv', index=False)

    # -- 2) Matrice completa (gruppo × mercato × bin) --
    matrix_tables = {}
    for grp in GROUP_ORDER:
        for mkt in MERCATI:
            sub = df[(df['gruppo'] == grp) & (df['tipo'] == mkt)]
            matrix_tables[(grp, mkt)] = compute_table(sub)

    rows = []
    for grp in GROUP_ORDER:
        for mkt in MERCATI:
            t = matrix_tables[(grp, mkt)].copy()
            t.insert(0, 'gruppo', grp)
            t.insert(1, 'mercato', mkt)
            rows.append(t)
    pd.concat(rows, ignore_index=True).to_csv(HERE / 'calibrazione_matrice_completa.csv', index=False)

    # Plot
    plot_per_mercato(tables_mkt, HERE / 'reliability_per_mercato.png')
    plot_matrice(matrix_tables, HERE / 'reliability_matrice.png')

    # -- Report markdown --
    md = ['# Punto 1 (esteso) — Calibrazione per Gruppo × Mercato',
          '',
          f'Dataset: **{len(df)}** pronostici con `probabilita_stimata`.',
          '',
          '## 1. Calibrazione per mercato (ignorando gruppo source)',
          '']
    md.append('| Mercato | N tot | Prob. media pesata | HR pesata | Delta |')
    md.append('| --- | ---: | ---: | ---: | ---: |')
    for mkt in MERCATI:
        n, pw, hw, dw = weighted_summary(tables_mkt[mkt])
        if n == 0:
            md.append(f'| {mkt} | 0 | — | — | — |')
            continue
        sign = '+' if dw >= 0 else ''
        md.append(f'| {mkt} | {n} | {pw:.2f}% | {hw:.2f}% | {sign}{dw:.2f} |')
    md.append('')
    for mkt in MERCATI:
        md.append(fmt_table_md(f'Mercato {mkt}', tables_mkt[mkt]))

    md.append('## 2. Matrice completa: gruppo × mercato × bin')
    md.append('')
    md.append('### Riepilogo pesato (delta medio per cella gruppo × mercato)')
    md.append('')
    md.append('| Gruppo \\ Mercato | ' + ' | '.join(MERCATI) + ' |')
    md.append('| --- | ' + ' | '.join([':---:'] * len(MERCATI)) + ' |')
    for grp in GROUP_ORDER:
        cells = [grp]
        for mkt in MERCATI:
            n, pw, hw, dw = weighted_summary(matrix_tables[(grp, mkt)])
            if n == 0:
                cells.append('—')
            else:
                sign = '+' if dw >= 0 else ''
                cells.append(f'N={n}, Δ={sign}{dw:.2f}')
        md.append('| ' + ' | '.join(cells) + ' |')
    md.append('')

    md.append('### Tabelle dettagliate (ogni cella)')
    md.append('')
    for grp in GROUP_ORDER:
        for mkt in MERCATI:
            t = matrix_tables[(grp, mkt)]
            if t['n'].sum() == 0:
                continue
            md.append(fmt_table_md(f'{grp} × {mkt}', t))

    # -- Osservazioni oggettive --
    md.append('## Osservazioni oggettive')
    md.append('')
    md.append('### Bin con delta significativo (|delta| ≥ 5 e N ≥ 30)')
    md.append('')
    md.append('| Gruppo | Mercato | Bin | N | Prob. | HR | Delta | Tipo |')
    md.append('| --- | --- | --- | ---: | ---: | ---: | ---: | --- |')
    found_any = False
    for grp in GROUP_ORDER:
        for mkt in MERCATI:
            t = matrix_tables[(grp, mkt)]
            for _, r in t.iterrows():
                if r['n'] >= 30 and pd.notna(r['delta']) and abs(r['delta']) >= 5:
                    tipo_cal = 'overconfident' if r['delta'] < 0 else 'underconfident'
                    sign = '+' if r['delta'] >= 0 else ''
                    md.append(
                        f'| {grp} | {mkt} | {r["bin"]} | {int(r["n"])} | '
                        f'{r["prob_mean"]:.2f}% | {r["hr_reale"]:.2f}% | '
                        f'{sign}{r["delta"]:.2f} | {tipo_cal} |'
                    )
                    found_any = True
    if not found_any:
        md.append('| — | — | — | — | — | — | — | — |')
    md.append('')

    md.append('### Delta pesato per mercato (ordinamento per grandezza assoluta)')
    md.append('')
    mkt_delta = []
    for mkt in MERCATI:
        n, pw, hw, dw = weighted_summary(tables_mkt[mkt])
        mkt_delta.append((mkt, n, pw, hw, dw))
    mkt_delta.sort(key=lambda x: abs(x[4]) if pd.notna(x[4]) else 0, reverse=True)
    md.append('| Mercato | N | Prob. | HR | Delta | Natura |')
    md.append('| --- | ---: | ---: | ---: | ---: | --- |')
    for mkt, n, pw, hw, dw in mkt_delta:
        nat = 'overconfident' if dw < 0 else 'underconfident'
        sign = '+' if dw >= 0 else ''
        md.append(f'| {mkt} | {n} | {pw:.2f}% | {hw:.2f}% | {sign}{dw:.2f} | {nat} |')
    md.append('')

    md.append('## File generati')
    md.append('')
    md.append('- `calibrazione_per_mercato.csv`')
    md.append('- `calibrazione_matrice_completa.csv`')
    md.append('- `reliability_per_mercato.png`')
    md.append('- `reliability_matrice.png`')

    (HERE / 'report_per_mercato.md').write_text('\n'.join(md), encoding='utf-8')
    print(f'\nOutput salvati in: {HERE}')


if __name__ == '__main__':
    main()
