"""Pipeline pattern discovery.

Split cronologico train/buffer/test → Random Forest feature importance →
Lasso con StandardScaler (feature "immortali") → Greedy con soglie umane →
Forward test con p-value e drawdown.

Uso:
    python -m ai_engine.pattern_discovery.pipeline
    python ai_engine/pattern_discovery/pipeline.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import ttest_1samp
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LassoCV
from sklearn.preprocessing import StandardScaler

# Config del modulo
_MODULE_DIR = Path(__file__).resolve().parent
if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))
import config as C  # noqa: E402

# Config globale MongoDB del backend (per caricare dati)
_BACKEND_ROOT = _MODULE_DIR.parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


GOL_MAP = {
    'Over 1.5': 'over_15', 'Under 1.5': 'under_15',
    'Over 2.5': 'over_25', 'Under 2.5': 'under_25',
    'Over 3.5': 'over_35', 'Under 3.5': 'under_35',
    'Goal': 'gg', 'NoGoal': 'ng',
}
SCATOLA_ORDER = {'MIXER': 0, 'ELITE': 1, 'ALTO_RENDIMENTO': 2, 'PRONOSTICI': 3}


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


def load_data(use_cache: bool = True) -> pd.DataFrame:
    """Carica il dataset dedupato dalla cache parquet o da MongoDB."""
    if use_cache and C.CACHE_FILE.exists():
        df = pd.read_parquet(C.CACHE_FILE)
        print(f'Cache caricata: {C.CACHE_FILE}  ({len(df)} righe)')
        return df

    # Import del config MongoDB del backend (evita conflitto col nostro 'config')
    import importlib.util
    backend_config_path = _BACKEND_ROOT / 'config.py'
    spec = importlib.util.spec_from_file_location('backend_config', backend_config_path)
    backend_config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backend_config)
    mongo_db = backend_config.db

    col = mongo_db['daily_predictions_unified']
    q = {'date': {'$gte': C.DATE_FROM, '$lte': C.DATE_TO}}
    rows_by_key = {}
    for doc in col.find(q):
        odds = doc.get('odds') or {}
        segd = doc.get('segno_dettaglio') or {}
        gold = doc.get('gol_dettaglio') or {}
        goldir = doc.get('gol_directions') or {}
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
                'stars': p.get('stars'),
                'confidence': p.get('confidence'),
                'quota': quota,
                'source': p.get('source'),
                'routing_rule': p.get('routing_rule'),
                'stake': p.get('stake'),
                'tipo': p['tipo'],
                'pronostico': p.get('pronostico'),
                'sd_campo': segd.get('campo'),
                'sd_bvs': segd.get('bvs'),
                'sd_affidabilita': segd.get('affidabilita'),
                'sd_lucifero': segd.get('lucifero'),
                'gd_att_vs_def': gold.get('att_vs_def'),
                'dir_dna': goldir.get('dna'),
                'prob_modello': p.get('prob_modello'),
                'probabilita_stimata': p.get('probabilita_stimata'),
                'scatola': scatola,
                'esito': bool(p.get('esito')),
                'pl': p.get('profit_loss') if p.get('profit_loss') is not None
                    else (quota - 1 if p.get('esito') else -1),
            }
            prev = rows_by_key.get(key)
            if prev is None or SCATOLA_ORDER[scatola] < SCATOLA_ORDER[prev['scatola']]:
                rows_by_key[key] = row

    df = pd.DataFrame(list(rows_by_key.values())).sort_values('date').reset_index(drop=True)
    df.to_parquet(C.CACHE_FILE, index=False)
    print(f'Dataset caricato da MongoDB e salvato in cache: {len(df)} righe')
    return df


def split_data(df: pd.DataFrame):
    """Split cronologico train/buffer/test in base a config."""
    needed = C.TRAIN_SIZE + C.BUFFER_SIZE + C.TEST_SIZE
    if len(df) < needed:
        raise ValueError(f'Dataset {len(df)} < richiesto {needed}')
    train = df.iloc[:C.TRAIN_SIZE].copy()
    buffer = df.iloc[C.TRAIN_SIZE:C.TRAIN_SIZE + C.BUFFER_SIZE].copy()
    test = df.iloc[C.TRAIN_SIZE + C.BUFFER_SIZE:
                   C.TRAIN_SIZE + C.BUFFER_SIZE + C.TEST_SIZE].copy()
    return train, buffer, test


def _aggregate_rare(series_train, others, min_count):
    """Rimpiazza valori con n<min_count in 'OTHER'."""
    counts = series_train.value_counts()
    keep = set(counts[counts >= min_count].index)
    mapped_train = series_train.where(series_train.isin(keep), 'OTHER')
    mapped_others = [s.where(s.isin(keep), 'OTHER') for s in others]
    return mapped_train, mapped_others


def _prepare_features(train, buffer, test, cat_vars):
    """Prepara matrici feature: numeriche con fillna(median), one-hot per cat."""
    med = train[C.NUM_VARS].median(numeric_only=True)
    X_train_num = train[C.NUM_VARS].fillna(med)
    X_buffer_num = buffer[C.NUM_VARS].fillna(med)
    X_test_num = test[C.NUM_VARS].fillna(med)

    X_train_cat = pd.get_dummies(train[cat_vars].astype(str), prefix=cat_vars)
    cols_cat = X_train_cat.columns.tolist()
    X_buffer_cat = pd.get_dummies(buffer[cat_vars].astype(str), prefix=cat_vars).reindex(columns=cols_cat, fill_value=0)
    X_test_cat = pd.get_dummies(test[cat_vars].astype(str), prefix=cat_vars).reindex(columns=cols_cat, fill_value=0)

    X_train = pd.concat([X_train_num.reset_index(drop=True), X_train_cat.reset_index(drop=True)], axis=1)
    X_buffer = pd.concat([X_buffer_num.reset_index(drop=True), X_buffer_cat.reset_index(drop=True)], axis=1)
    X_test = pd.concat([X_test_num.reset_index(drop=True), X_test_cat.reset_index(drop=True)], axis=1)
    return X_train, X_buffer, X_test


def run_random_forest(X_train, y_train) -> pd.Series:
    """Random Forest regressor su profit_loss → feature importance."""
    rf = RandomForestRegressor(
        n_estimators=C.RF_N_ESTIMATORS,
        min_samples_leaf=C.RF_MIN_SAMPLES_LEAF,
        max_features=C.RF_MAX_FEATURES,
        random_state=C.RF_RANDOM_STATE,
        n_jobs=-1,
    )
    rf.fit(X_train, y_train)
    fi = pd.Series(rf.feature_importances_, index=X_train.columns).sort_values(ascending=False)
    return fi


def run_lasso(X_train_sel, y_train) -> pd.Series:
    """Lasso con StandardScaler e alpha via CV → coefficienti non-zero."""
    scaler = StandardScaler()
    X_sc = scaler.fit_transform(X_train_sel)
    lasso = LassoCV(
        cv=C.LASSO_CV_FOLDS,
        random_state=C.LASSO_RANDOM_STATE,
        max_iter=C.LASSO_MAX_ITER,
        n_jobs=-1,
    )
    lasso.fit(X_sc, y_train)
    coef = pd.Series(lasso.coef_, index=X_train_sel.columns).sort_values(key=abs, ascending=False)
    return coef, lasso.alpha_


def _test_numeric_threshold(df_, var: str):
    """Cerca la miglior soglia umana per una variabile numerica."""
    best = None
    for thr in C.HUMAN_THRESHOLDS.get(var, []):
        for direction in ('ge', 'le'):
            if direction == 'ge':
                sub = df_[df_[var] >= thr]
            else:
                sub = df_[df_[var] <= thr]
            if len(sub) < C.GREEDY_MIN_VOL:
                continue
            n = len(sub)
            v = sub['esito'].sum()
            pl = sub['pl'].sum()
            roi = pl / n * 100
            if best is None or roi > best['roi']:
                best = {
                    'var': var, 'dir': direction, 'thr': thr,
                    'n': n, 'hr': v / n * 100, 'pl': pl, 'roi': roi,
                }
    return best


def _test_categorical_value(df_, catvar: str, val: str):
    sub = df_[df_[catvar].astype(str) == val]
    if len(sub) < C.GREEDY_MIN_VOL:
        return None
    n = len(sub)
    v = sub['esito'].sum()
    pl = sub['pl'].sum()
    return {
        'var': catvar, 'dir': 'eq', 'thr': val,
        'n': n, 'hr': v / n * 100, 'pl': pl, 'roi': pl / n * 100,
    }


def run_greedy(train_df: pd.DataFrame, cat_vars) -> list:
    """Greedy forward selection con soglie umane, ottimizza ROI."""
    cur = train_df
    baseline_roi = cur['pl'].sum() / len(cur) * 100
    print(f'Baseline training: n={len(cur)} HR={cur["esito"].mean()*100:.2f}% ROI={baseline_roi:+.2f}%')
    pattern = []
    prev_roi = baseline_roi
    steps = []
    for step in range(1, C.GREEDY_MAX_STEPS + 1):
        used = {v for v, _, _ in pattern}
        best = None
        for v in C.NUM_VARS:
            if v in used:
                continue
            b = _test_numeric_threshold(cur, v)
            if b and (best is None or b['roi'] > best['roi']):
                best = b
        for cv in cat_vars:
            if cv in used:
                continue
            vals = cur[cv].astype(str).value_counts()
            for val, cnt in vals.items():
                if cnt < C.GREEDY_MIN_VOL:
                    continue
                b = _test_categorical_value(cur, cv, val)
                if b and (best is None or b['roi'] > best['roi']):
                    best = b
        if best is None:
            print(f'STEP {step}: nessun candidato con volume>={C.GREEDY_MIN_VOL}. STOP.')
            break
        if best['roi'] <= prev_roi:
            print(f'STEP {step}: miglior candidato ROI={best["roi"]:+.2f}% non migliora vs {prev_roi:+.2f}%. STOP.')
            break
        pattern.append((best['var'], best['dir'], best['thr']))
        if best['dir'] == 'eq':
            cur = cur[cur[best['var']].astype(str) == best['thr']]
        elif best['dir'] == 'ge':
            cur = cur[cur[best['var']] >= best['thr']]
        else:
            cur = cur[cur[best['var']] <= best['thr']]
        prev_roi = best['roi']
        op = '=' if best['dir'] == 'eq' else (' >= ' if best['dir'] == 'ge' else ' <= ')
        print(f'STEP {step}: {best["var"]}{op}{best["thr"]}  n={best["n"]}  HR={best["hr"]:.2f}%  ROI={best["roi"]:+.2f}%')
        steps.append({
            'step': step, 'var': best['var'], 'direction': best['dir'], 'threshold': best['thr'],
            'n': best['n'], 'hr': round(best['hr'], 2), 'roi': round(best['roi'], 2), 'pl': round(best['pl'], 2),
        })
    return pattern, steps


def apply_pattern(df_: pd.DataFrame, pattern: list) -> pd.DataFrame:
    out = df_.copy()
    for var, direction, thr in pattern:
        if direction == 'eq':
            out = out[out[var].astype(str) == thr]
        elif direction == 'ge':
            out = out[out[var] >= thr]
        else:
            out = out[out[var] <= thr]
    return out


def run_forward_test(train_df, test_df, pattern):
    def _metrics(df_):
        n = len(df_)
        if n == 0:
            return {'n': 0, 'hr': 0, 'roi': 0, 'pl': 0, 'dd': 0, 't': float('nan'), 'p': float('nan')}
        v = df_['esito'].sum()
        pl = df_['pl'].sum()
        pls = df_.sort_values('date')['pl'].values
        cum = np.cumsum(pls)
        peak = np.maximum.accumulate(cum)
        dd = float((cum - peak).min()) if len(cum) > 0 else 0.0
        if n > 1:
            t_stat, p_val = ttest_1samp(pls, 0.0)
        else:
            t_stat, p_val = float('nan'), float('nan')
        return {
            'n': int(n), 'hr': float(v / n * 100), 'roi': float(pl / n * 100),
            'pl': float(pl), 'dd': dd, 't': float(t_stat), 'p': float(p_val),
        }

    tr_filtered = apply_pattern(train_df, pattern)
    te_filtered = apply_pattern(test_df, pattern)
    return _metrics(tr_filtered), _metrics(te_filtered)


def save_results(run_dir: Path, fi: pd.Series, lasso_coef: pd.Series, alpha: float,
                 greedy_steps: list, pattern: list,
                 train_m: dict, test_m: dict):
    """Salva tutti gli artefatti del run."""
    run_dir.mkdir(parents=True, exist_ok=True)
    fi.to_frame('importance').to_csv(run_dir / 'feature_importance.csv')
    lasso_nonzero = lasso_coef[lasso_coef != 0].to_frame('coefficient')
    lasso_nonzero.to_csv(run_dir / 'lasso_survivors.csv')
    pd.DataFrame(greedy_steps).to_csv(run_dir / 'greedy_steps.csv', index=False)
    final_pattern = {
        'pattern': [{'variable': v, 'direction': d, 'threshold': t} for v, d, t in pattern],
        'lasso_alpha': float(alpha),
    }
    (run_dir / 'final_pattern.json').write_text(json.dumps(final_pattern, indent=2, default=str))

    def _fmt_pattern(p):
        parts = []
        for v, d, t in p:
            op = '=' if d == 'eq' else (' >= ' if d == 'ge' else ' <= ')
            parts.append(f'{v}{op}{t}')
        return ' AND '.join(parts) if parts else '(vuoto)'

    metrics_md = (
        '# Metriche finali\n\n'
        f'**Pattern**: `{_fmt_pattern(pattern)}`\n\n'
        f'**Lasso alpha**: {alpha:.6f}\n\n'
        '| Metrica | Training | Test |\n'
        '| --- | ---: | ---: |\n'
        f'| Volume | {train_m["n"]} | {test_m["n"]} |\n'
        f'| HR | {train_m["hr"]:.2f}% | {test_m["hr"]:.2f}% |\n'
        f'| ROI | {train_m["roi"]:+.2f}% | {test_m["roi"]:+.2f}% |\n'
        f'| PL (u) | {train_m["pl"]:+.2f} | {test_m["pl"]:+.2f} |\n'
        f'| Max drawdown | {train_m["dd"]:+.2f} | {test_m["dd"]:+.2f} |\n'
        f'| t-statistic | {train_m["t"]:.3f} | {test_m["t"]:.3f} |\n'
        f'| p-value | {train_m["p"]:.4f} | {test_m["p"]:.4f} |\n'
    )
    (run_dir / 'metrics.md').write_text(metrics_md, encoding='utf-8')

    # Report sintetico
    target_met = (test_m['roi'] >= C.TARGET_ROI_TEST
                  and test_m['n'] >= C.TARGET_MIN_VOL_TEST
                  and test_m['p'] <= C.TARGET_MAX_PVALUE)
    report = (
        f'# Run {run_dir.name}\n\n'
        f'Pattern: `{_fmt_pattern(pattern)}`\n\n'
        f'ROI train: {train_m["roi"]:+.2f}% — ROI test: {test_m["roi"]:+.2f}%\n\n'
        f'HR train: {train_m["hr"]:.2f}% — HR test: {test_m["hr"]:.2f}%\n\n'
        f'Volumi: train={train_m["n"]}, test={test_m["n"]}\n\n'
        f'p-value test: {test_m["p"]:.4f}\n\n'
        f'Drawdown test: {test_m["dd"]:+.2f}u\n\n'
        f'**Obiettivi raggiunti**: {"✅" if target_met else "❌"}\n'
    )
    (run_dir / 'report.md').write_text(report, encoding='utf-8')
    return _fmt_pattern(pattern), target_met


def append_run_history(run_dir: Path, pattern_str: str, train_m, test_m, target_met):
    header_needed = not C.RUN_HISTORY_FILE.exists()
    lines = []
    if header_needed:
        lines.append('# Run history\n')
        lines.append('| Run | Pattern | ROI train | ROI test | p-value | Volumi (tr/te) | Target |\n')
        lines.append('| --- | --- | ---: | ---: | ---: | --- | :---: |\n')
    lines.append(
        f'| {run_dir.name} | `{pattern_str}` | {train_m["roi"]:+.2f}% | {test_m["roi"]:+.2f}% | '
        f'{test_m["p"]:.4f} | {train_m["n"]}/{test_m["n"]} | {"✅" if target_met else "❌"} |\n'
    )
    with C.RUN_HISTORY_FILE.open('a', encoding='utf-8') as f:
        f.writelines(lines)


def main():
    df = load_data(use_cache=True)
    train, buffer, test = split_data(df)
    print(f'Train: {len(train)} ({train.date.min()} → {train.date.max()})')
    print(f'Buffer: {len(buffer)}')
    print(f'Test: {len(test)} ({test.date.min()} → {test.date.max()})')

    # dir_dna include solo se popolata
    cat_vars = list(C.CAT_VARS)
    if df['dir_dna'].notna().sum() > 50:
        cat_vars.append('dir_dna')

    # Aggrega valori rari SOLO sulla base del training
    for catcol in ('source', 'routing_rule'):
        mtr, [mbuf, mte] = _aggregate_rare(train[catcol], [buffer[catcol], test[catcol]],
                                            C.RARE_CATEGORY_THRESHOLD)
        train[catcol] = mtr
        buffer[catcol] = mbuf
        test[catcol] = mte

    X_train, X_buffer, X_test = _prepare_features(train, buffer, test, cat_vars)
    y_train = train['pl'].values
    print(f'X_train shape: {X_train.shape}')

    print('\n### STEP 2: Random Forest ###')
    fi = run_random_forest(X_train, y_train)
    print(fi.head(20).to_string())
    fi_sel = fi[fi > C.RF_IMPORTANCE_THRESHOLD]
    print(f'Feature sopravvissute: {len(fi_sel)}')

    X_train_sel = X_train[fi_sel.index]

    print('\n### STEP 3: Lasso ###')
    lasso_coef, alpha = run_lasso(X_train_sel, y_train)
    print(f'Alpha ottimo: {alpha:.6f}')
    nonzero = lasso_coef[lasso_coef != 0]
    print(f'Coef non-zero: {len(nonzero)}/{len(lasso_coef)}')
    print(nonzero.to_string())

    print('\n### STEP 4: Greedy ###')
    pattern, steps = run_greedy(train, cat_vars)

    print('\n### STEP 5: Forward test ###')
    train_m, test_m = run_forward_test(train, test, pattern)
    print(f'TRAIN: n={train_m["n"]} HR={train_m["hr"]:.2f}% ROI={train_m["roi"]:+.2f}% PL={train_m["pl"]:+.2f} DD={train_m["dd"]:+.2f} t={train_m["t"]:.2f} p={train_m["p"]:.4f}')
    print(f'TEST:  n={test_m["n"]} HR={test_m["hr"]:.2f}% ROI={test_m["roi"]:+.2f}% PL={test_m["pl"]:+.2f} DD={test_m["dd"]:+.2f} t={test_m["t"]:.2f} p={test_m["p"]:.4f}')

    stamp = datetime.now().strftime('run_%Y-%m-%d_%H%M')
    run_dir = C.RESULTS_DIR / stamp
    pattern_str, target_met = save_results(run_dir, fi, lasso_coef, alpha, steps, pattern, train_m, test_m)
    append_run_history(run_dir, pattern_str, train_m, test_m, target_met)
    print(f'\nRisultati salvati in: {run_dir}')


if __name__ == '__main__':
    main()
