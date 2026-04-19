"""Punto 5 — Analisi per segmento.

Riestrae il dataset dedupato da MongoDB includendo `league`, `is_cup`,
`home`, `away` e aggiunge segmentazione per:
- Lega
- Coppa vs campionato
- Fascia quota
- Giorno settimana
- Fascia probabilità stimata
- Tipo mercato × gruppo source

Per ogni segmento: volume, HR, ROI, PL, delta vs baseline globale.

Mistral vs no: skip documentato (zero documenti con ai_analysis valorizzato).

Output in 05_segmenti/.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
BACKEND_ROOT = HERE.parent.parent.parent

DATE_FROM = '2026-02-19'
DATE_TO = '2026-04-18'

GROUP_ORDER = ['A', 'S', 'C', 'A+S', 'C-derivati', 'Altro']
MERCATI = ['SEGNO', 'DOPPIA_CHANCE', 'GOL']

QUOTA_BINS = [0, 1.30, 1.50, 1.80, 2.00, 2.50, 3.50, 100]
QUOTA_LABELS = ['<1.30', '1.30-1.50', '1.50-1.80', '1.80-2.00',
                '2.00-2.50', '2.50-3.50', '3.50+']

PROB_BINS = [35, 50, 60, 70, 80, 101]
PROB_LABELS = ['35-50', '50-60', '60-70', '70-80', '80+']

DAYS_IT = ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì',
           'Venerdì', 'Sabato', 'Domenica']

GOL_MAP = {
    'Over 1.5': 'over_15', 'Under 1.5': 'under_15',
    'Over 2.5': 'over_25', 'Under 2.5': 'under_25',
    'Over 3.5': 'over_35', 'Under 3.5': 'under_35',
    'Goal': 'gg', 'NoGoal': 'ng',
}
SCATOLA_ORDER = {'MIXER': 0, 'ELITE': 1, 'ALTO_RENDIMENTO': 2, 'PRONOSTICI': 3}


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


def quota_bin(q):
    if q is None or (isinstance(q, float) and np.isnan(q)):
        return None
    for i in range(len(QUOTA_BINS) - 1):
        if QUOTA_BINS[i] <= q < QUOTA_BINS[i + 1]:
            return QUOTA_LABELS[i]
    return QUOTA_LABELS[-1]


def prob_bin(p):
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return None
    for i in range(len(PROB_BINS) - 1):
        if PROB_BINS[i] <= p < PROB_BINS[i + 1]:
            return PROB_LABELS[i]
    return PROB_LABELS[-1]


def _get_quota(p, odds):
    qv = p.get('quota')
    if qv:
        return qv
    t = p.get('tipo')
    pr = p.get('pronostico')
    if not odds:
        return None
    if t in ('SEGNO', 'DOPPIA_CHANCE'):
        return odds.get(pr)
    if t == 'GOL':
        k = GOL_MAP.get(pr)
        return odds.get(k) if k else None
    return None


def load_db():
    spec = importlib.util.spec_from_file_location('backend_config', BACKEND_ROOT / 'config.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.db


def load_dataset(db) -> pd.DataFrame:
    """Riestrae il dataset con gli stessi filtri della pipeline originale,
    aggiungendo league/is_cup/home/away."""
    col = db['daily_predictions_unified']
    q = {'date': {'$gte': DATE_FROM, '$lte': DATE_TO}}
    rows_by_key = {}
    for doc in col.find(q):
        odds = doc.get('odds') or {}
        league = doc.get('league')
        is_cup = bool(doc.get('is_cup', False))
        home = doc.get('home')
        away = doc.get('away')
        for p in doc.get('pronostici', []):
            if p.get('tipo') not in ('SEGNO', 'DOPPIA_CHANCE', 'GOL'):
                continue
            if p.get('pronostico') == 'NO BET':
                continue
            quota = _get_quota(p, odds)
            if quota is None:
                continue
            if p.get('esito') is None:
                continue
            soglia = 2.00 if p['tipo'] == 'DOPPIA_CHANCE' else 2.51
            is_alta = quota >= soglia
            if p.get('mixer') is True:
                scatola = 'MIXER'
            elif p.get('elite') is True:
                scatola = 'ELITE'
            elif is_alta:
                scatola = 'ALTO_RENDIMENTO'
            else:
                scatola = 'PRONOSTICI'
            key = (doc['date'], doc['home'], doc['away'], p['tipo'], p['pronostico'])
            row = {
                'date': doc['date'],
                'home': home, 'away': away,
                'league': league, 'is_cup': is_cup,
                'source': p.get('source'),
                'routing_rule': p.get('routing_rule'),
                'stake': p.get('stake'),
                'tipo': p['tipo'],
                'pronostico': p.get('pronostico'),
                'quota': quota,
                'probabilita_stimata': p.get('probabilita_stimata'),
                'scatola': scatola,
                'esito': bool(p.get('esito')),
                'pl': p.get('profit_loss') if p.get('profit_loss') is not None
                    else (quota - 1 if p.get('esito') else -1),
            }
            prev = rows_by_key.get(key)
            if prev is None or SCATOLA_ORDER[scatola] < SCATOLA_ORDER[prev['scatola']]:
                rows_by_key[key] = row
    return pd.DataFrame(list(rows_by_key.values())).sort_values('date').reset_index(drop=True)


def metrics(df: pd.DataFrame) -> dict:
    n = len(df)
    if n == 0:
        return {'n': 0, 'hr': None, 'pl': 0, 'roi': None}
    return {
        'n': n,
        'hr': round(df['esito'].mean() * 100, 2),
        'pl': round(df['pl'].sum(), 2),
        'roi': round(df['pl'].sum() / n * 100, 2),
    }


def segmentation_table(df: pd.DataFrame, by: str, min_n: int = 0) -> pd.DataFrame:
    rows = []
    for val, sub in df.groupby(by, dropna=False):
        m = metrics(sub)
        if m['n'] < min_n:
            continue
        rows.append({by: '(null)' if val is None or (isinstance(val, float) and np.isnan(val)) else val,
                     **m})
    out = pd.DataFrame(rows)
    if len(out) == 0:
        return out
    return out.sort_values('n', ascending=False).reset_index(drop=True)


def fmt_seg_table(title: str, t: pd.DataFrame, baseline_roi: float) -> str:
    if len(t) == 0:
        return f'### {title}\n\n(nessun dato)\n\n'
    lines = [f'### {title}', '',
             f'Baseline globale ROI = {baseline_roi:+.2f}%. Δ = ROI − baseline.',
             '',
             f'| {t.columns[0]} | N | HR | PL | ROI | Δ vs baseline |',
             '| --- | ---: | ---: | ---: | ---: | ---: |']
    for _, r in t.iterrows():
        pl_s = '+' if r['pl'] >= 0 else ''
        roi_s = '+' if r['roi'] >= 0 else ''
        delta = r['roi'] - baseline_roi
        d_s = '+' if delta >= 0 else ''
        lines.append(
            f'| {r[t.columns[0]]} | {int(r["n"])} | {r["hr"]:.2f}% | '
            f'{pl_s}{r["pl"]:.2f} | {roi_s}{r["roi"]:.2f}% | {d_s}{delta:.2f} |'
        )
    lines.append('')
    return '\n'.join(lines)


def plot_segmentation(t: pd.DataFrame, col: str, outpath: Path, title: str,
                       baseline_roi: float, max_rows: int = 20):
    sub = t.head(max_rows).copy()
    if len(sub) == 0:
        return
    fig, ax = plt.subplots(figsize=(12, max(0.4 * len(sub) + 2, 4)))
    colors = ['seagreen' if r >= 0 else 'tomato' for r in sub['roi']]
    y = np.arange(len(sub))
    ax.barh(y, sub['roi'], color=colors, edgecolor='black', alpha=0.8)
    for i, (_, r) in enumerate(sub.iterrows()):
        ax.text(r['roi'] + (1 if r['roi'] >= 0 else -1),
                i, f'N={int(r["n"])}  HR={r["hr"]:.1f}%',
                va='center', ha='left' if r['roi'] >= 0 else 'right', fontsize=8)
    ax.axvline(baseline_roi, color='black', linestyle='--', linewidth=0.8,
               label=f'Baseline {baseline_roi:+.2f}%')
    ax.axvline(0, color='gray', linewidth=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels(sub[col])
    ax.invert_yaxis()
    ax.set_xlabel('ROI (%)')
    ax.set_title(title)
    ax.grid(True, alpha=0.3, axis='x')
    ax.legend(loc='lower right', fontsize=8)
    plt.tight_layout()
    plt.savefig(outpath, dpi=120)
    plt.close()


def main():
    print('Connessione MongoDB...')
    db = load_db()
    print('Caricamento dataset con league/is_cup...')
    df = load_dataset(db)
    print(f'  {len(df)} righe')

    df['gruppo'] = df['source'].apply(classify)
    df['quota_bin'] = df['quota'].apply(quota_bin)
    df['prob_bin'] = df['probabilita_stimata'].apply(prob_bin)
    df['date_dt'] = pd.to_datetime(df['date'])
    df['giorno'] = df['date_dt'].dt.dayofweek.apply(lambda i: DAYS_IT[i])
    df['cup_vs_league'] = df['is_cup'].map({True: 'Coppa', False: 'Campionato'})

    baseline = metrics(df)
    baseline_roi = baseline['roi']

    print(f'Baseline globale: N={baseline["n"]}, HR={baseline["hr"]}%, ROI={baseline["roi"]}%, PL={baseline["pl"]}')

    # Segmentazioni
    seg_league = segmentation_table(df, 'league', min_n=20)
    seg_cup = segmentation_table(df, 'cup_vs_league')
    seg_quota = segmentation_table(df, 'quota_bin')
    seg_prob = segmentation_table(df, 'prob_bin')
    seg_day = segmentation_table(df, 'giorno')
    seg_mkt = segmentation_table(df, 'tipo')
    seg_grp = segmentation_table(df, 'gruppo')

    # Ordino quota_bin e prob_bin per fascia e non per N, altrimenti è disordinato
    seg_quota['_order'] = seg_quota['quota_bin'].apply(
        lambda x: QUOTA_LABELS.index(x) if x in QUOTA_LABELS else 99)
    seg_quota = seg_quota.sort_values('_order').drop(columns='_order').reset_index(drop=True)
    seg_prob['_order'] = seg_prob['prob_bin'].apply(
        lambda x: PROB_LABELS.index(x) if x in PROB_LABELS else 99)
    seg_prob = seg_prob.sort_values('_order').drop(columns='_order').reset_index(drop=True)
    seg_day['_order'] = seg_day['giorno'].apply(
        lambda x: DAYS_IT.index(x) if x in DAYS_IT else 99)
    seg_day = seg_day.sort_values('_order').drop(columns='_order').reset_index(drop=True)

    # Matrice gruppo × mercato
    rows = []
    for grp in GROUP_ORDER:
        for mkt in MERCATI:
            sub = df[(df['gruppo'] == grp) & (df['tipo'] == mkt)]
            rows.append({'gruppo': grp, 'mercato': mkt, **metrics(sub)})
    seg_gm = pd.DataFrame(rows)

    # Salva CSV
    seg_league.to_csv(HERE / 'segmento_league.csv', index=False)
    seg_cup.to_csv(HERE / 'segmento_cup_vs_campionato.csv', index=False)
    seg_quota.to_csv(HERE / 'segmento_quota.csv', index=False)
    seg_prob.to_csv(HERE / 'segmento_prob.csv', index=False)
    seg_day.to_csv(HERE / 'segmento_giorno.csv', index=False)
    seg_mkt.to_csv(HERE / 'segmento_mercato.csv', index=False)
    seg_grp.to_csv(HERE / 'segmento_gruppo.csv', index=False)
    seg_gm.to_csv(HERE / 'segmento_gruppo_x_mercato.csv', index=False)

    # Plot (quelli utili a vista)
    plot_segmentation(seg_league, 'league', HERE / 'plot_league.png',
                      'ROI per lega (top 20 per volume)', baseline_roi, max_rows=20)
    plot_segmentation(seg_quota, 'quota_bin', HERE / 'plot_quota.png',
                      'ROI per fascia quota', baseline_roi)
    plot_segmentation(seg_prob, 'prob_bin', HERE / 'plot_prob.png',
                      'ROI per fascia probabilità stimata', baseline_roi)
    plot_segmentation(seg_day, 'giorno', HERE / 'plot_giorno.png',
                      'ROI per giorno settimana', baseline_roi)

    # ================ Report ================
    md = ['# Punto 5 — Analisi per segmento', '',
          f'Dataset rigenerato da MongoDB (stesso dedup della pipeline originale):',
          f'**{len(df)}** pronostici, {DATE_FROM} → {DATE_TO}.',
          '',
          f'Baseline globale: N={baseline["n"]}, HR={baseline["hr"]}%, '
          f'ROI={baseline["roi"]}%, PL={baseline["pl"]}.',
          '',
          '**Nota Mistral**: il campo `post_match_stats.ai_analysis` esiste a schema ma',
          'è valorizzato in 0 documenti nella finestra → segmentazione "Mistral vs no"',
          'non eseguibile con i dati attuali.',
          '',
          '## 1. Lega (min N=20)', '']
    md.append(fmt_seg_table('Segmentazione per lega', seg_league, baseline_roi))
    md.append('## 2. Coppa vs Campionato')
    md.append('')
    md.append(fmt_seg_table('', seg_cup, baseline_roi))
    md.append('## 3. Fascia quota')
    md.append('')
    md.append(fmt_seg_table('', seg_quota, baseline_roi))
    md.append('## 4. Fascia probabilità stimata')
    md.append('')
    md.append(fmt_seg_table('', seg_prob, baseline_roi))
    md.append('## 5. Giorno della settimana')
    md.append('')
    md.append(fmt_seg_table('', seg_day, baseline_roi))
    md.append('## 6. Tipo mercato')
    md.append('')
    md.append(fmt_seg_table('', seg_mkt, baseline_roi))
    md.append('## 7. Gruppo source')
    md.append('')
    md.append(fmt_seg_table('', seg_grp, baseline_roi))

    md.append('## 8. Matrice gruppo × mercato')
    md.append('')
    md.append('| Gruppo \\ Mercato | ' + ' | '.join(MERCATI) + ' |')
    md.append('| --- | ' + ' | '.join([':---:'] * len(MERCATI)) + ' |')
    for grp in GROUP_ORDER:
        cells = [grp]
        for mkt in MERCATI:
            r = seg_gm[(seg_gm['gruppo'] == grp) & (seg_gm['mercato'] == mkt)].iloc[0]
            if r['n'] == 0:
                cells.append('—')
            else:
                roi_s = '+' if r['roi'] >= 0 else ''
                cells.append(f'N={int(r["n"])}, ROI={roi_s}{r["roi"]:.2f}%')
        md.append('| ' + ' | '.join(cells) + ' |')
    md.append('')

    # ================ Osservazioni oggettive ================
    md.append('## 9. Osservazioni oggettive')
    md.append('')

    # Top 5 peggiori / migliori leghe (N>=30)
    md.append('### Leghe peggiori (N≥30, ordinate per ROI crescente)')
    md.append('')
    md.append('| League | N | HR | ROI | Δ vs baseline |')
    md.append('| --- | ---: | ---: | ---: | ---: |')
    bad = seg_league[seg_league['n'] >= 30].sort_values('roi').head(5)
    for _, r in bad.iterrows():
        delta = r['roi'] - baseline_roi
        md.append(f'| {r["league"]} | {int(r["n"])} | {r["hr"]:.2f}% | {r["roi"]:+.2f}% | {delta:+.2f} |')
    md.append('')

    md.append('### Leghe migliori (N≥30, ordinate per ROI decrescente)')
    md.append('')
    md.append('| League | N | HR | ROI | Δ vs baseline |')
    md.append('| --- | ---: | ---: | ---: | ---: |')
    good = seg_league[seg_league['n'] >= 30].sort_values('roi', ascending=False).head(5)
    for _, r in good.iterrows():
        delta = r['roi'] - baseline_roi
        md.append(f'| {r["league"]} | {int(r["n"])} | {r["hr"]:.2f}% | {r["roi"]:+.2f}% | {delta:+.2f} |')
    md.append('')

    # Combinazioni peggiori: gruppo × mercato con ROI negativo alto
    md.append('### Celle gruppo × mercato peggiori (N≥30, ROI < -10%)')
    md.append('')
    md.append('| Gruppo | Mercato | N | HR | ROI |')
    md.append('| --- | --- | ---: | ---: | ---: |')
    bad_cells = seg_gm[(seg_gm['n'] >= 30) & (seg_gm['roi'] < -10)].sort_values('roi')
    if len(bad_cells) == 0:
        md.append('| — | — | — | — | — |')
    else:
        for _, r in bad_cells.iterrows():
            md.append(f'| {r["gruppo"]} | {r["mercato"]} | {int(r["n"])} | {r["hr"]:.2f}% | {r["roi"]:+.2f}% |')
    md.append('')

    md.append('### Celle gruppo × mercato migliori (N≥30, ROI > +10%)')
    md.append('')
    md.append('| Gruppo | Mercato | N | HR | ROI |')
    md.append('| --- | --- | ---: | ---: | ---: |')
    good_cells = seg_gm[(seg_gm['n'] >= 30) & (seg_gm['roi'] > 10)].sort_values('roi', ascending=False)
    if len(good_cells) == 0:
        md.append('| — | — | — | — | — |')
    else:
        for _, r in good_cells.iterrows():
            md.append(f'| {r["gruppo"]} | {r["mercato"]} | {int(r["n"])} | {r["hr"]:.2f}% | {r["roi"]:+.2f}% |')
    md.append('')

    md.append('## 10. File generati')
    md.append('')
    md.append('- `segmento_league.csv`')
    md.append('- `segmento_cup_vs_campionato.csv`')
    md.append('- `segmento_quota.csv`')
    md.append('- `segmento_prob.csv`')
    md.append('- `segmento_giorno.csv`')
    md.append('- `segmento_mercato.csv`')
    md.append('- `segmento_gruppo.csv`')
    md.append('- `segmento_gruppo_x_mercato.csv`')
    md.append('- `plot_league.png`, `plot_quota.png`, `plot_prob.png`, `plot_giorno.png`')

    (HERE / 'report.md').write_text('\n'.join(md), encoding='utf-8')
    print(f'Output in: {HERE}')


if __name__ == '__main__':
    main()
