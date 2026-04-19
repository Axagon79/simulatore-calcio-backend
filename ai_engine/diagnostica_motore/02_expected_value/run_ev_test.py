"""Punto 2 — Expected Value Test.

EV = (probabilita_stimata/100 × quota) - 1.
Fasce: <0, 0-5%, 5-10%, 10-20%, 20-40%, 40%+.
Dimensioni: gruppo source (A, S, C, A+S, C-derivati, Altro) × mercato
(SEGNO, DOPPIA_CHANCE, GOL).

Output:
- ev_per_mercato.csv
- ev_per_gruppo.csv
- ev_matrice_gruppo_mercato.csv
- ev_globale.csv
- correlazione.csv (correlazione EV vs ROI per gruppo/mercato)
- report.md
- ev_vs_roi.png
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

EV_EDGES = [-1.01, 0.0, 0.05, 0.10, 0.20, 0.40, 100.0]
EV_LABELS = ['<0', '0-5%', '5-10%', '10-20%', '20-40%', '40%+']

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


def ev_bin(ev: float) -> str:
    for i in range(len(EV_EDGES) - 1):
        if EV_EDGES[i] <= ev < EV_EDGES[i + 1]:
            return EV_LABELS[i]
    return EV_LABELS[-1]


def compute_table(df_sub: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for lab in EV_LABELS:
        sub = df_sub[df_sub['ev_bin'] == lab]
        n = len(sub)
        if n == 0:
            rows.append({'ev_bin': lab, 'n': 0, 'ev_mean': np.nan,
                         'hr': np.nan, 'roi': np.nan, 'pl': np.nan})
            continue
        rows.append({
            'ev_bin': lab, 'n': n,
            'ev_mean': round(sub['ev'].mean() * 100, 2),
            'hr': round(sub['esito'].mean() * 100, 2),
            'roi': round(sub['pl'].sum() / n * 100, 2),
            'pl': round(sub['pl'].sum(), 2),
        })
    return pd.DataFrame(rows)


def correlation(df_sub: pd.DataFrame) -> dict:
    if len(df_sub) < 10:
        return {'n': len(df_sub), 'pearson': np.nan, 'spearman': np.nan}
    # Correlazione singole righe: EV vs PL
    pear = df_sub[['ev', 'pl']].corr(method='pearson').iloc[0, 1]
    spear = df_sub[['ev', 'pl']].corr(method='spearman').iloc[0, 1]
    return {'n': len(df_sub), 'pearson': round(pear, 4), 'spearman': round(spear, 4)}


def fmt_table_md(title: str, t: pd.DataFrame) -> str:
    lines = [f'### {title}', '']
    lines.append('| Fascia EV | N | EV medio | HR | ROI | PL |')
    lines.append('| --- | ---: | ---: | ---: | ---: | ---: |')
    for _, r in t.iterrows():
        if r['n'] == 0:
            lines.append(f'| {r["ev_bin"]} | 0 | — | — | — | — |')
        else:
            roi_s = '+' if r['roi'] >= 0 else ''
            pl_s = '+' if r['pl'] >= 0 else ''
            lines.append(
                f'| {r["ev_bin"]} | {int(r["n"])} | {r["ev_mean"]:+.2f}% | '
                f'{r["hr"]:.2f}% | {roi_s}{r["roi"]:.2f}% | {pl_s}{r["pl"]:.2f} |'
            )
    lines.append('')
    return '\n'.join(lines)


def plot_ev_vs_roi(tables: dict, outpath: Path):
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    for ax, mkt in zip(axes, MERCATI):
        t = tables[mkt]
        valid = t[t['n'] > 0]
        if len(valid) == 0:
            ax.set_title(f'{mkt} (vuoto)')
            continue
        x = np.arange(len(valid))
        colors = ['tomato' if v < 0 else 'seagreen' for v in valid['roi']]
        bars = ax.bar(x, valid['roi'], color=colors, alpha=0.75, edgecolor='black')
        for bar, n in zip(bars, valid['n']):
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2,
                    h + (1 if h >= 0 else -2),
                    f'N={int(n)}', ha='center', va='bottom' if h >= 0 else 'top', fontsize=8)
        ax.axhline(0, color='black', linewidth=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(valid['ev_bin'], rotation=0)
        ax.set_xlabel('Fascia EV')
        ax.set_ylabel('ROI (%)')
        ax.set_title(f'{mkt}  (N={int(t["n"].sum())})')
        ax.grid(True, alpha=0.3, axis='y')
    plt.suptitle('ROI per fascia EV — per mercato', fontsize=12)
    plt.tight_layout()
    plt.savefig(outpath, dpi=120)
    plt.close()


def plot_scatter(df: pd.DataFrame, outpath: Path):
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    for ax, mkt in zip(axes, MERCATI):
        sub = df[df['tipo'] == mkt]
        if len(sub) == 0:
            continue
        # Bin EV × valore medio PL, per visualizzare trend
        bin_stats = sub.groupby('ev_bin').agg(
            ev_mean=('ev', 'mean'),
            pl_mean=('pl', 'mean'),
            n=('pl', 'size'),
        ).reindex(EV_LABELS).dropna()
        ax.axhline(0, color='gray', linewidth=0.7)
        ax.axvline(0, color='gray', linewidth=0.7)
        sizes = np.clip(bin_stats['n'] * 3, 30, 400)
        ax.scatter(bin_stats['ev_mean'] * 100, bin_stats['pl_mean'] * 100,
                   s=sizes, alpha=0.7, edgecolor='black')
        for lab, r in bin_stats.iterrows():
            ax.annotate(f'{lab}\n(n={int(r["n"])})',
                        (r['ev_mean'] * 100, r['pl_mean'] * 100),
                        textcoords='offset points', xytext=(8, 4), fontsize=7)
        # Retta bisettrice: EV = ROI atteso se la prob fosse vera
        xs = np.linspace(bin_stats['ev_mean'].min() * 100,
                         bin_stats['ev_mean'].max() * 100, 2)
        ax.plot(xs, xs, '--', color='gray', linewidth=1, label='ROI = EV (ideale)')
        ax.set_xlabel('EV medio (%)')
        ax.set_ylabel('ROI effettivo (%)')
        ax.set_title(mkt)
        ax.grid(True, alpha=0.3)
        ax.legend(loc='upper left', fontsize=8)
    plt.suptitle('EV teorico vs ROI effettivo (per mercato)', fontsize=12)
    plt.tight_layout()
    plt.savefig(outpath, dpi=120)
    plt.close()


def main():
    df = pd.read_parquet(CACHE)
    df = df[df['probabilita_stimata'].notna()].copy()
    df = df[df['quota'].notna()].copy()
    df['gruppo'] = df['source'].apply(classify)
    df['ev'] = (df['probabilita_stimata'] / 100.0) * df['quota'] - 1.0
    df['ev_bin'] = df['ev'].apply(ev_bin)
    print(f'Dataset EV test: {len(df)} righe')
    print(f'EV min={df["ev"].min()*100:.2f}%  max={df["ev"].max()*100:.2f}%  mean={df["ev"].mean()*100:.2f}%')

    # -- 1) Globale
    t_glob = compute_table(df)
    t_glob.insert(0, 'scope', 'GLOBALE')
    t_glob.to_csv(HERE / 'ev_globale.csv', index=False)

    # -- 2) Per mercato
    tables_mkt = {mkt: compute_table(df[df['tipo'] == mkt]) for mkt in MERCATI}
    rows = []
    for mkt in MERCATI:
        t = tables_mkt[mkt].copy()
        t.insert(0, 'mercato', mkt)
        rows.append(t)
    pd.concat(rows, ignore_index=True).to_csv(HERE / 'ev_per_mercato.csv', index=False)

    # -- 3) Per gruppo
    tables_grp = {grp: compute_table(df[df['gruppo'] == grp]) for grp in GROUP_ORDER}
    rows = []
    for grp in GROUP_ORDER:
        t = tables_grp[grp].copy()
        t.insert(0, 'gruppo', grp)
        rows.append(t)
    pd.concat(rows, ignore_index=True).to_csv(HERE / 'ev_per_gruppo.csv', index=False)

    # -- 4) Matrice gruppo × mercato
    matrix_tables = {}
    for grp in GROUP_ORDER:
        for mkt in MERCATI:
            matrix_tables[(grp, mkt)] = compute_table(df[(df['gruppo'] == grp) & (df['tipo'] == mkt)])
    rows = []
    for grp in GROUP_ORDER:
        for mkt in MERCATI:
            t = matrix_tables[(grp, mkt)].copy()
            t.insert(0, 'gruppo', grp)
            t.insert(1, 'mercato', mkt)
            rows.append(t)
    pd.concat(rows, ignore_index=True).to_csv(HERE / 'ev_matrice_gruppo_mercato.csv', index=False)

    # -- 5) Correlazione EV↔PL (sia globale che per gruppo/mercato)
    corr_rows = []
    c_all = correlation(df)
    corr_rows.append({'scope': 'GLOBALE', **c_all})
    for mkt in MERCATI:
        corr_rows.append({'scope': f'MERCATO={mkt}',
                          **correlation(df[df['tipo'] == mkt])})
    for grp in GROUP_ORDER:
        corr_rows.append({'scope': f'GRUPPO={grp}',
                          **correlation(df[df['gruppo'] == grp])})
    for grp in GROUP_ORDER:
        for mkt in MERCATI:
            sub = df[(df['gruppo'] == grp) & (df['tipo'] == mkt)]
            corr_rows.append({'scope': f'{grp} × {mkt}', **correlation(sub)})
    pd.DataFrame(corr_rows).to_csv(HERE / 'correlazione.csv', index=False)

    # -- 6) Plot
    plot_ev_vs_roi(tables_mkt, HERE / 'ev_vs_roi_per_mercato.png')
    plot_scatter(df, HERE / 'ev_teorico_vs_roi_effettivo.png')

    # -- 7) Report
    md = ['# Punto 2 — Expected Value Test', '',
          f'Dataset: **{len(df)}** pronostici (prob stimata + quota).',
          '',
          'EV = (probabilità_stimata × quota) − 1.',
          'Fasce: <0, 0-5%, 5-10%, 10-20%, 20-40%, 40%+.',
          '',
          'Se l\'EV riflettesse davvero il valore sul book, il ROI dovrebbe crescere ',
          'al crescere della fascia EV e avvicinarsi al valore di EV medio della fascia.',
          '',
          '## 1. EV globale (intero dataset)',
          '']
    md.append(fmt_table_md('Globale', t_glob.drop(columns='scope')))

    md.append('## 2. EV per mercato (ignorando gruppo)')
    md.append('')
    for mkt in MERCATI:
        md.append(fmt_table_md(f'Mercato {mkt}', tables_mkt[mkt]))

    md.append('## 3. EV per gruppo source (ignorando mercato)')
    md.append('')
    for grp in GROUP_ORDER:
        md.append(fmt_table_md(f'Gruppo {grp}', tables_grp[grp]))

    md.append('## 4. Matrice completa gruppo × mercato × fascia EV')
    md.append('')
    md.append('### Riepilogo pesato (ROI medio per cella)')
    md.append('')
    md.append('| Gruppo \\ Mercato | ' + ' | '.join(MERCATI) + ' |')
    md.append('| --- | ' + ' | '.join([':---:'] * len(MERCATI)) + ' |')
    for grp in GROUP_ORDER:
        cells = [grp]
        for mkt in MERCATI:
            t = matrix_tables[(grp, mkt)]
            if t['n'].sum() == 0:
                cells.append('—')
            else:
                n_tot = int(t['n'].sum())
                pl_tot = t['pl'].sum()
                roi_tot = pl_tot / n_tot * 100
                sign = '+' if roi_tot >= 0 else ''
                cells.append(f'N={n_tot}, ROI={sign}{roi_tot:.2f}%')
        md.append('| ' + ' | '.join(cells) + ' |')
    md.append('')

    md.append('### Tabelle dettagliate (ogni cella con N ≥ 20)')
    md.append('')
    for grp in GROUP_ORDER:
        for mkt in MERCATI:
            t = matrix_tables[(grp, mkt)]
            if t['n'].sum() < 20:
                continue
            md.append(fmt_table_md(f'{grp} × {mkt}', t))

    # -- Osservazioni oggettive --
    md.append('## 5. Osservazioni oggettive')
    md.append('')

    # Correlazione EV→PL
    md.append('### Correlazione EV ↔ PL (singola riga)')
    md.append('')
    md.append('| Scope | N | Pearson | Spearman |')
    md.append('| --- | ---: | ---: | ---: |')
    for r in corr_rows:
        if pd.isna(r['pearson']):
            md.append(f'| {r["scope"]} | {r["n"]} | — | — |')
        else:
            md.append(f'| {r["scope"]} | {r["n"]} | {r["pearson"]:+.4f} | {r["spearman"]:+.4f} |')
    md.append('')

    # Test monotonicità: ROI cresce con EV?
    md.append('### Monotonicità ROI al crescere di EV (per mercato)')
    md.append('')
    md.append('Se EV cattura il vantaggio, ROI dovrebbe essere monotono crescente sui bin.')
    md.append('')
    md.append('| Mercato | Fascia <0 | 0-5% | 5-10% | 10-20% | 20-40% | 40%+ | Monotono? |')
    md.append('| --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: |')
    for mkt in MERCATI:
        t = tables_mkt[mkt]
        rois = []
        for lab in EV_LABELS:
            r = t[t['ev_bin'] == lab].iloc[0]
            if r['n'] == 0:
                rois.append(None)
            else:
                rois.append(r['roi'])
        valid = [x for x in rois if x is not None]
        mono = all(valid[i] <= valid[i + 1] for i in range(len(valid) - 1)) if len(valid) >= 2 else None
        cells = [mkt]
        for v in rois:
            if v is None:
                cells.append('—')
            else:
                s = '+' if v >= 0 else ''
                cells.append(f'{s}{v:.2f}%')
        cells.append('✅' if mono else '❌')
        md.append('| ' + ' | '.join(cells) + ' |')
    md.append('')

    # Fasce con ROI negativo e volume significativo
    md.append('### Fasce EV con ROI ≤ 0 e N ≥ 30 (EV positivo teorico, ROI negativo effettivo)')
    md.append('')
    md.append('| Scope | Fascia | N | EV medio | HR | ROI |')
    md.append('| --- | --- | ---: | ---: | ---: | ---: |')
    found = False
    for mkt in MERCATI:
        t = tables_mkt[mkt]
        for _, r in t.iterrows():
            if r['n'] >= 30 and pd.notna(r['roi']) and r['roi'] <= 0 and r['ev_bin'] != '<0':
                md.append(
                    f'| MERCATO={mkt} | {r["ev_bin"]} | {int(r["n"])} | '
                    f'{r["ev_mean"]:+.2f}% | {r["hr"]:.2f}% | {r["roi"]:+.2f}% |'
                )
                found = True
    for grp in GROUP_ORDER:
        t = tables_grp[grp]
        for _, r in t.iterrows():
            if r['n'] >= 30 and pd.notna(r['roi']) and r['roi'] <= 0 and r['ev_bin'] != '<0':
                md.append(
                    f'| GRUPPO={grp} | {r["ev_bin"]} | {int(r["n"])} | '
                    f'{r["ev_mean"]:+.2f}% | {r["hr"]:.2f}% | {r["roi"]:+.2f}% |'
                )
                found = True
    if not found:
        md.append('| — | — | — | — | — | — |')
    md.append('')

    # Valore di EV<0 (se il motore capisce il valore negativo, queste dovrebbero perdere)
    md.append('### Fasce EV < 0 (dovrebbero perdere)')
    md.append('')
    md.append('| Scope | N | ROI effettivo |')
    md.append('| --- | ---: | ---: |')
    for mkt in MERCATI:
        t = tables_mkt[mkt]
        r = t[t['ev_bin'] == '<0'].iloc[0]
        if r['n'] == 0:
            continue
        s = '+' if r['roi'] >= 0 else ''
        md.append(f'| MERCATO={mkt} | {int(r["n"])} | {s}{r["roi"]:.2f}% |')
    for grp in GROUP_ORDER:
        t = tables_grp[grp]
        r = t[t['ev_bin'] == '<0'].iloc[0]
        if r['n'] == 0:
            continue
        s = '+' if r['roi'] >= 0 else ''
        md.append(f'| GRUPPO={grp} | {int(r["n"])} | {s}{r["roi"]:.2f}% |')
    md.append('')

    md.append('## 6. File generati')
    md.append('')
    md.append('- `ev_globale.csv`')
    md.append('- `ev_per_mercato.csv`')
    md.append('- `ev_per_gruppo.csv`')
    md.append('- `ev_matrice_gruppo_mercato.csv`')
    md.append('- `correlazione.csv`')
    md.append('- `ev_vs_roi_per_mercato.png`')
    md.append('- `ev_teorico_vs_roi_effettivo.png`')

    (HERE / 'report.md').write_text('\n'.join(md), encoding='utf-8')
    print(f'\nOutput in: {HERE}')


if __name__ == '__main__':
    main()
