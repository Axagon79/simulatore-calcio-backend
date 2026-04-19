"""Punto 3 — Analisi Stake.

A. Performance per livello stake 1-10 (globale, per mercato, per gruppo).
B. Simulazione Kelly 0.10 e 0.25 su probabilità dichiarata.
C. Simulazione Kelly 0.10 e 0.25 su probabilità calibrata (shrinkage bin).
D. Identificazione pronostici incoerenti (stake attuale vs Kelly calibrato).

Tutti i PL sono normalizzati "per unità": moltiplicando per lo stake si
ottiene l'impatto reale sul bankroll. Nel dataset cache `pl` è già per-unit.

Output in 03_stake/.
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

GROUP_ORDER = ['A', 'S', 'C', 'A+S', 'C-derivati', 'Altro']
MERCATI = ['SEGNO', 'DOPPIA_CHANCE', 'GOL']

# Bin probabilità (stessi del Punto 1)
BINS = [35, 50, 60, 70, 80, 101]
BIN_LABELS = ['35-50', '50-60', '60-70', '70-80', '80+']

SHRINK_MIN_N = 30   # sotto questa soglia, fallback al mercato × bin
KELLY_FRACTIONS = [0.10, 0.25]


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


def bin_label(p: float) -> str:
    for i in range(len(BINS) - 1):
        if BINS[i] <= p < BINS[i + 1]:
            return BIN_LABELS[i]
    return BIN_LABELS[-1]


# ====== A. Performance per stake ======

def performance_by_stake(df: pd.DataFrame, extra_groupcol: str | None = None) -> pd.DataFrame:
    rows = []
    groupcols = ['stake'] if extra_groupcol is None else [extra_groupcol, 'stake']
    for key, sub in df.groupby(groupcols):
        n = len(sub)
        v = int(sub['esito'].sum())
        pl = sub['pl'].sum()
        pl_weighted = (sub['pl'] * sub['stake']).sum()
        row = {
            'n': n,
            'hr': round(v / n * 100, 2),
            'roi_unit': round(pl / n * 100, 2),
            'pl_unit': round(pl, 2),
            'pl_ponderato': round(pl_weighted, 2),
        }
        if extra_groupcol is None:
            key_val = key[0] if isinstance(key, tuple) else key
            row['stake'] = int(key_val)
        else:
            row[extra_groupcol] = key[0]
            row['stake'] = int(key[1])
        rows.append(row)
    out = pd.DataFrame(rows)
    cols_order = ([extra_groupcol] if extra_groupcol else []) + ['stake', 'n', 'hr', 'roi_unit', 'pl_unit', 'pl_ponderato']
    return out[cols_order].sort_values(cols_order[:-4] + ['stake']).reset_index(drop=True)


# ====== Calibrazione con shrinkage ======

def build_calibration_map(df: pd.DataFrame) -> dict:
    """Per ogni cella (gruppo, mercato, bin) restituisce HR reale shrinkata.

    Se N cella >= SHRINK_MIN_N → HR cella.
    Se N cella < SHRINK_MIN_N → weighted average fra HR cella e HR mercato×bin.
    Se N cella == 0 → HR mercato×bin (o prob dichiarata come ultima risorsa).
    """
    cal = {}
    # Prima: HR per mercato × bin (fallback)
    mkt_bin_hr = {}
    for mkt in MERCATI:
        for lab in BIN_LABELS:
            sub = df[(df['tipo'] == mkt) & (df['bin_prob'] == lab)]
            if len(sub) > 0:
                mkt_bin_hr[(mkt, lab)] = {
                    'n': len(sub),
                    'hr': sub['esito'].mean() * 100,
                }

    for grp in GROUP_ORDER + [None]:
        for mkt in MERCATI:
            for lab in BIN_LABELS:
                if grp is None:
                    mask = (df['tipo'] == mkt) & (df['bin_prob'] == lab)
                else:
                    mask = (df['gruppo'] == grp) & (df['tipo'] == mkt) & (df['bin_prob'] == lab)
                sub = df[mask]
                n_cell = len(sub)
                fb = mkt_bin_hr.get((mkt, lab))
                if n_cell == 0:
                    if fb is None:
                        continue
                    cal[(grp, mkt, lab)] = {'n_cell': 0, 'p_cal': fb['hr'], 'source': 'fallback_market_bin'}
                elif n_cell >= SHRINK_MIN_N:
                    cal[(grp, mkt, lab)] = {
                        'n_cell': n_cell,
                        'p_cal': sub['esito'].mean() * 100,
                        'source': 'cell',
                    }
                else:
                    # shrinkage: peso cella + peso fallback
                    hr_cell = sub['esito'].mean() * 100
                    if fb is None or fb['n'] == 0:
                        cal[(grp, mkt, lab)] = {'n_cell': n_cell, 'p_cal': hr_cell, 'source': 'cell_only_no_fb'}
                    else:
                        w_cell = n_cell
                        w_fb = SHRINK_MIN_N - n_cell
                        p_cal = (hr_cell * w_cell + fb['hr'] * w_fb) / (w_cell + w_fb)
                        cal[(grp, mkt, lab)] = {
                            'n_cell': n_cell,
                            'p_cal': p_cal,
                            'source': f'shrink(cell={w_cell}, fb={w_fb})',
                        }
    return cal


def apply_calibration(df: pd.DataFrame, cal: dict) -> pd.Series:
    """Restituisce la probabilità calibrata per ogni riga."""
    def _lookup(row):
        key = (row['gruppo'], row['tipo'], row['bin_prob'])
        entry = cal.get(key)
        if entry is not None:
            return entry['p_cal']
        # fallback globale al mercato × bin (grp=None)
        entry2 = cal.get((None, row['tipo'], row['bin_prob']))
        if entry2 is not None:
            return entry2['p_cal']
        return row['probabilita_stimata']  # ultima risorsa
    return df.apply(_lookup, axis=1)


# ====== Kelly ======

def kelly_stake(p_pct: float, quota: float, fraction: float) -> int:
    """Kelly frazionario scala 1-10. p_pct in [0,100]."""
    p = p_pct / 100.0
    if quota is None or quota <= 1:
        return 1
    b = quota - 1
    edge = p * quota - 1
    if edge <= 0:
        return 1
    f = edge / b
    # fraction * f è la quota del bankroll. Moltiplico *100 per scala 1-10
    raw = fraction * f * 100
    return int(max(1, min(10, round(raw))))


def apply_kelly_column(df: pd.DataFrame, p_col: str, fraction: float) -> pd.Series:
    return df.apply(lambda r: kelly_stake(r[p_col], r['quota'], fraction), axis=1)


def equity_curves(df: pd.DataFrame, stake_cols: list[str]) -> pd.DataFrame:
    """Costruisce l'equity cumulata per ciascuna colonna di stake.

    Equity per scommessa: stake × pl_unit (pl_unit = quota-1 se vinta, -1 se persa).
    """
    df_sorted = df.sort_values(['date']).reset_index(drop=True)
    out = pd.DataFrame({'date': df_sorted['date']})
    for col in stake_cols:
        eq = (df_sorted[col] * df_sorted['pl']).cumsum()
        out[col] = eq
    return out


def max_drawdown(series: pd.Series) -> float:
    arr = series.values
    peak = np.maximum.accumulate(arr)
    return float((arr - peak).min())


# ====== Formatter markdown ======

def fmt_stake_table(t: pd.DataFrame) -> str:
    lines = ['| Stake | N | HR | ROI (per unit) | PL (unit) | PL (ponderato) |',
             '| ---: | ---: | ---: | ---: | ---: | ---: |']
    for _, r in t.iterrows():
        roi_s = '+' if r['roi_unit'] >= 0 else ''
        pl_s = '+' if r['pl_unit'] >= 0 else ''
        plw_s = '+' if r['pl_ponderato'] >= 0 else ''
        lines.append(
            f'| {int(r["stake"])} | {int(r["n"])} | {r["hr"]:.2f}% | '
            f'{roi_s}{r["roi_unit"]:.2f}% | {pl_s}{r["pl_unit"]:.2f} | '
            f'{plw_s}{r["pl_ponderato"]:.2f} |'
        )
    return '\n'.join(lines)


def summary_strategy(df: pd.DataFrame, stake_col: str) -> dict:
    total_risk = df[stake_col].sum()
    total_pl = (df[stake_col] * df['pl']).sum()
    wins = df['esito'].sum()
    eq = (df.sort_values('date')[stake_col] * df.sort_values('date')['pl']).cumsum()
    dd = max_drawdown(eq)
    return {
        'volume': len(df),
        'unita_rischiate': round(total_risk, 2),
        'hr': round(df['esito'].mean() * 100, 2),
        'pl_ponderato': round(total_pl, 2),
        'roi_per_unita_rischiata': round(total_pl / total_risk * 100, 2) if total_risk > 0 else 0,
        'max_drawdown': round(dd, 2),
        'stake_medio': round(df[stake_col].mean(), 2),
    }


def plot_equity(eq_df: pd.DataFrame, stake_cols: list[str], outpath: Path):
    fig, ax = plt.subplots(figsize=(13, 7))
    x = range(len(eq_df))
    for col in stake_cols:
        ax.plot(x, eq_df[col], label=col, linewidth=1.4)
    ax.axhline(0, color='black', linewidth=0.7)
    ax.set_xlabel('Pronostico (ordinato per data)')
    ax.set_ylabel('Equity cumulata (unità)')
    ax.set_title('Equity cumulata per strategia di stake')
    ax.grid(True, alpha=0.3)
    ax.legend(loc='best', fontsize=9)
    plt.tight_layout()
    plt.savefig(outpath, dpi=120)
    plt.close()


# ====== Main ======

def main():
    df = pd.read_parquet(CACHE)
    df = df[df['probabilita_stimata'].notna() & df['quota'].notna() & df['stake'].notna()].copy()
    df['gruppo'] = df['source'].apply(classify)
    df['bin_prob'] = df['probabilita_stimata'].apply(bin_label)
    df['stake'] = df['stake'].astype(int)
    print(f'Dataset stake: {len(df)} righe')

    # ===== A. Performance per stake =====
    perf_global = performance_by_stake(df)
    perf_mercato = performance_by_stake(df, extra_groupcol='tipo')
    perf_gruppo = performance_by_stake(df, extra_groupcol='gruppo')

    perf_global.to_csv(HERE / 'stake_performance_globale.csv', index=False)
    perf_mercato.to_csv(HERE / 'stake_performance_per_mercato.csv', index=False)
    perf_gruppo.to_csv(HERE / 'stake_performance_per_gruppo.csv', index=False)

    # ===== B. Calibrazione + Kelly calibrato =====
    cal_map = build_calibration_map(df)
    # Serializza la mappa di calibrazione in CSV
    cal_rows = []
    for (grp, mkt, lab), v in cal_map.items():
        cal_rows.append({
            'gruppo': 'GLOBALE' if grp is None else grp,
            'mercato': mkt, 'bin': lab,
            'n_cell': v['n_cell'],
            'p_calibrata': round(v['p_cal'], 2),
            'source': v['source'],
        })
    pd.DataFrame(cal_rows).to_csv(HERE / 'mappa_calibrazione.csv', index=False)

    df['prob_calibrata'] = apply_calibration(df, cal_map)

    # ===== C. Stake Kelly (dichiarata e calibrata) =====
    for f in KELLY_FRACTIONS:
        df[f'stake_kelly_dich_{f}'] = apply_kelly_column(df, 'probabilita_stimata', f)
        df[f'stake_kelly_cal_{f}'] = apply_kelly_column(df, 'prob_calibrata', f)

    stake_strategies = ['stake',
                        'stake_kelly_dich_0.1', 'stake_kelly_dich_0.25',
                        'stake_kelly_cal_0.1', 'stake_kelly_cal_0.25']

    # Riepilogo strategie
    summary = {s: summary_strategy(df, s) for s in stake_strategies}
    summary_df = pd.DataFrame(summary).T
    summary_df.index.name = 'strategia'
    summary_df.to_csv(HERE / 'riepilogo_strategie.csv')

    # Equity curves
    eq = equity_curves(df, stake_strategies)
    eq.to_csv(HERE / 'equity_curves.csv', index=False)
    plot_equity(eq, stake_strategies, HERE / 'equity_curves.png')

    # ===== D. Pronostici incoerenti =====
    df['delta_vs_kelly_cal_0.25'] = df['stake'] - df['stake_kelly_cal_0.25']
    # top overbet: stake attuale molto sopra Kelly calibrato
    overbet = df.nlargest(100, 'delta_vs_kelly_cal_0.25')[
        ['date', 'tipo', 'pronostico', 'source', 'gruppo', 'quota',
         'probabilita_stimata', 'prob_calibrata', 'stake',
         'stake_kelly_cal_0.25', 'delta_vs_kelly_cal_0.25',
         'esito', 'pl']
    ].copy()
    overbet.to_csv(HERE / 'top100_overbet.csv', index=False)

    underbet = df.nsmallest(100, 'delta_vs_kelly_cal_0.25')[
        ['date', 'tipo', 'pronostico', 'source', 'gruppo', 'quota',
         'probabilita_stimata', 'prob_calibrata', 'stake',
         'stake_kelly_cal_0.25', 'delta_vs_kelly_cal_0.25',
         'esito', 'pl']
    ].copy()
    underbet.to_csv(HERE / 'top100_underbet.csv', index=False)

    # Conteggi incoerenza
    diff = df['delta_vs_kelly_cal_0.25']
    incoherence = {
        'overbet_>=_+3': int((diff >= 3).sum()),
        'overbet_+2': int((diff == 2).sum()),
        'overbet_+1': int((diff == 1).sum()),
        'uguale_0': int((diff == 0).sum()),
        'underbet_-1': int((diff == -1).sum()),
        'underbet_-2': int((diff == -2).sum()),
        'underbet_<=_-3': int((diff <= -3).sum()),
    }
    pd.Series(incoherence).to_csv(HERE / 'incoerenza_stake.csv', header=['n'])

    # ===== REPORT MD =====
    md = ['# Punto 3 — Analisi Stake', '',
          f'Dataset: **{len(df)}** pronostici (prob+quota+stake valorizzati).',
          '',
          '## Formula stake attuale (sintesi)',
          '',
          '1. Base: Quarter Kelly (0.25f), floor 1, cap 10.',
          '2. Protezioni tipo-specifiche (SEGNO quota<1.50 → cap stake, prob>85% → cap 3, quota>5 → cap 2).',
          '3. Post-processing **Fattore Quota a Fasce**: moltiplicatori per fascia quota.',
          '   - q<1.50: fattore 2.00/q',
          '   - q<2.00: 1.0',
          '   - q<2.50: 2.20/q',
          '   - q<3.50: 2.00/q',
          '   - q<5.00: 3.50/q',
          '   - q>=5.00: 1.0',
          '',
          'Riferimento: `backfill_stakes.py::calcola_stake_kelly`, `orchestrate_experts.py::_apply_fattore_quota`.',
          '',
          '## A. Performance per livello di stake', '',
          '### Globale', fmt_stake_table(perf_global), '',
          '### Per mercato', '']
    for mkt in MERCATI:
        md.append(f'#### {mkt}')
        md.append(fmt_stake_table(perf_mercato[perf_mercato['tipo'] == mkt]))
        md.append('')
    md.append('### Per gruppo source')
    md.append('')
    for grp in GROUP_ORDER:
        sub = perf_gruppo[perf_gruppo['gruppo'] == grp]
        if len(sub) == 0:
            continue
        md.append(f'#### {grp}')
        md.append(fmt_stake_table(sub))
        md.append('')

    md.append('## B. Confronto strategie di stake')
    md.append('')
    md.append('Equity cumulata = somma di (stake × pl_unit) lungo il tempo.')
    md.append('"ROI per unità rischiata" = PL_ponderato / unità_rischiate_tot.')
    md.append('')
    md.append('| Strategia | Volume | Stake medio | Unità rischiate | HR | PL ponderato | ROI/unità | Max DD |')
    md.append('| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |')
    for s in stake_strategies:
        r = summary[s]
        pl_s = '+' if r['pl_ponderato'] >= 0 else ''
        roi_s = '+' if r['roi_per_unita_rischiata'] >= 0 else ''
        md.append(
            f'| {s} | {r["volume"]} | {r["stake_medio"]} | {r["unita_rischiate"]} | '
            f'{r["hr"]}% | {pl_s}{r["pl_ponderato"]} | {roi_s}{r["roi_per_unita_rischiata"]}% | '
            f'{r["max_drawdown"]} |'
        )
    md.append('')

    # ===== Osservazioni =====
    md.append('## C. Osservazioni oggettive')
    md.append('')

    # Stake level più profittevoli/deficitari
    md.append('### Livelli di stake con ROI estremi (N >= 50, globali)')
    md.append('')
    md.append('| Stake | N | HR | ROI (unit) | PL (ponderato) |')
    md.append('| ---: | ---: | ---: | ---: | ---: |')
    filtered = perf_global[perf_global['n'] >= 50].copy()
    filtered = filtered.sort_values('roi_unit', ascending=False)
    for _, r in filtered.iterrows():
        roi_s = '+' if r['roi_unit'] >= 0 else ''
        plw_s = '+' if r['pl_ponderato'] >= 0 else ''
        md.append(
            f'| {int(r["stake"])} | {int(r["n"])} | {r["hr"]:.2f}% | '
            f'{roi_s}{r["roi_unit"]:.2f}% | {plw_s}{r["pl_ponderato"]:.2f} |'
        )
    md.append('')

    md.append('### Incoerenza stake attuale vs Kelly calibrato 0.25')
    md.append('')
    md.append('| Delta (stake - kelly_cal) | N |')
    md.append('| --- | ---: |')
    for k, v in incoherence.items():
        md.append(f'| {k} | {v} |')
    md.append('')

    md.append('### PL per classe di incoerenza')
    md.append('')
    md.append('| Delta | N | HR | PL ponderato (attuale) | PL ponderato (Kelly cal 0.25) | Δ PL |')
    md.append('| --- | ---: | ---: | ---: | ---: | ---: |')
    for lo, hi, lbl in [(3, 99, 'overbet >= +3'),
                        (1, 2, 'overbet +1/+2'),
                        (0, 0, 'uguale'),
                        (-2, -1, 'underbet -1/-2'),
                        (-99, -3, 'underbet <= -3')]:
        mask = (df['delta_vs_kelly_cal_0.25'] >= lo) & (df['delta_vs_kelly_cal_0.25'] <= hi)
        sub = df[mask]
        if len(sub) == 0:
            continue
        pl_act = (sub['stake'] * sub['pl']).sum()
        pl_kel = (sub['stake_kelly_cal_0.25'] * sub['pl']).sum()
        hr = sub['esito'].mean() * 100
        s1 = '+' if pl_act >= 0 else ''
        s2 = '+' if pl_kel >= 0 else ''
        sd = '+' if (pl_kel - pl_act) >= 0 else ''
        md.append(f'| {lbl} | {len(sub)} | {hr:.2f}% | {s1}{pl_act:.2f} | {s2}{pl_kel:.2f} | {sd}{pl_kel - pl_act:.2f} |')
    md.append('')

    # Bin probabilità dove Kelly calibrato differisce più da stake attuale
    md.append('### Media stake per bin probabilità (attuale vs Kelly calibrato 0.25)')
    md.append('')
    md.append('| Bin prob | N | Stake attuale medio | Kelly cal 0.25 medio | Delta |')
    md.append('| --- | ---: | ---: | ---: | ---: |')
    for lab in BIN_LABELS:
        sub = df[df['bin_prob'] == lab]
        if len(sub) == 0:
            md.append(f'| {lab} | 0 | — | — | — |')
            continue
        sa = sub['stake'].mean()
        sk = sub['stake_kelly_cal_0.25'].mean()
        delta = sa - sk
        sign = '+' if delta >= 0 else ''
        md.append(f'| {lab} | {len(sub)} | {sa:.2f} | {sk:.2f} | {sign}{delta:.2f} |')
    md.append('')

    md.append('## D. File generati')
    md.append('')
    md.append('- `stake_performance_globale.csv`')
    md.append('- `stake_performance_per_mercato.csv`')
    md.append('- `stake_performance_per_gruppo.csv`')
    md.append('- `mappa_calibrazione.csv` (shrinkage gruppo × mercato × bin)')
    md.append('- `riepilogo_strategie.csv`')
    md.append('- `equity_curves.csv` + `equity_curves.png`')
    md.append('- `top100_overbet.csv`, `top100_underbet.csv`')
    md.append('- `incoerenza_stake.csv`')

    (HERE / 'report.md').write_text('\n'.join(md), encoding='utf-8')
    print(f'Output in: {HERE}')


if __name__ == '__main__':
    main()
