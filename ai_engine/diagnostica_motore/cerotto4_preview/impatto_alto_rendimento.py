"""Impatto del Cerotto 4 (7 combo tossiche SCARTA) sulla scatola Alto Rendimento.

Confronto tra due definizioni di "Alto Rendimento":
A) notebook analisi_professionale.ipynb: quota > 2.50
B) scatola AR del frontend (mutualmente esclusiva post dedup):
   elite=False AND mixer=False AND quota >= soglia (2.51 SEGNO/GOL, 2.00 DC)

7 combo (Cerotto 4 ridotto): C2, C4, C5, C6, C8, C9, C10.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
BACKEND_ROOT = HERE.parent.parent.parent


def load_db():
    spec = importlib.util.spec_from_file_location('backend_config', BACKEND_ROOT / 'config.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.db


# === Definizioni dal notebook (Cerotto 4) ===

def tipo_partita(qmin):
    if qmin is None or pd.isna(qmin) or qmin <= 0:
        return 'n/a'
    if qmin < 1.40: return 'dominante'
    if qmin < 1.80: return 'favorita'
    if qmin < 2.30: return 'equilibrata'
    return 'aperta'


def fascia_oraria(match_time):
    if not match_time or not isinstance(match_time, str):
        return 'sconosciuto'
    try:
        h = int(match_time.split(':')[0])
    except Exception:
        return 'sconosciuto'
    if h < 15: return 'mattina'
    if h < 18: return 'pomeriggio'
    if h < 21: return 'sera'
    return 'notte'


def fascia_quota(q):
    if q is None or q <= 0: return 'n/a'
    if q < 1.40: return '1.01-1.39'
    if q < 1.70: return '1.40-1.69'
    if q < 2.00: return '1.70-1.99'
    if q < 2.50: return '2.00-2.49'
    if q < 3.00: return '2.50-2.99'
    return '3.00+'


def categoria_notebook(q):
    """Definizione A: quota > 2.50 -> Alto Rendimento."""
    if q is None: return 'n/a'
    return 'Alto Rendimento' if q > 2.50 else 'Pronostici'


# === Le 7 combo del Cerotto 4 ridotto (SCARTA only) ===

COMBOS_7 = [
    ('C2', 'SEGNO + tipo_partita=aperta',
        lambda r: r['tipo'] == 'SEGNO' and r['tipo_partita'] == 'aperta'),
    ('C4', 'tipo_partita=aperta + categoria=Alto Rendimento',
        lambda r: r['tipo_partita'] == 'aperta' and r['categoria_a'] == 'Alto Rendimento'),
    ('C5', 'SEGNO + Monday + tipo_partita=aperta',
        lambda r: r['tipo'] == 'SEGNO' and r['giorno_settimana'] == 'Monday' and r['tipo_partita'] == 'aperta'),
    ('C6', 'fascia_oraria=sera + categoria=Alto Rendimento',
        lambda r: r['fascia_oraria'] == 'sera' and r['categoria_a'] == 'Alto Rendimento'),
    ('C8', 'Friday + fascia_quota=3.00+ + tipo_partita=equilibrata',
        lambda r: r['giorno_settimana'] == 'Friday' and r['fascia_quota'] == '3.00+' and r['tipo_partita'] == 'equilibrata'),
    ('C9', 'fascia_quota=2.50-2.99 + tipo_partita=aperta',
        lambda r: r['fascia_quota'] == '2.50-2.99' and r['tipo_partita'] == 'aperta'),
    ('C10', 'Friday + categoria=Alto Rendimento',
        lambda r: r['giorno_settimana'] == 'Friday' and r['categoria_a'] == 'Alto Rendimento'),
]


def load_df():
    """Ricostruisce il dataset dedupato da MongoDB con:
    - scatola mutuamente esclusiva (MIXER>ELITE>AR>PRONOSTICI)
    - flag elite, mixer
    - quota, tipo, pronostico, esito, pl
    - quota_min_1x2, match_time dalla partita
    """
    db = load_db()
    q = {'date': {'$gte': '2026-02-19', '$lte': '2026-04-18'}}

    # Metadata partita (odds 1X2 + match_time)
    match_meta = {}
    for d in db['daily_predictions_unified'].find(q, {
        'date': 1, 'home': 1, 'away': 1, 'match_time': 1,
        'odds.1': 1, 'odds.X': 1, 'odds.2': 1, '_id': 0
    }):
        key = (d['date'], d['home'], d['away'])
        odds = d.get('odds') or {}
        q1 = odds.get('1') or 0
        qX = odds.get('X') or 0
        q2 = odds.get('2') or 0
        vals = [v for v in (q1, qX, q2) if v and v > 0]
        match_meta[key] = {
            'match_time': d.get('match_time', ''),
            'quota_min_1x2': min(vals) if vals else None,
        }

    GOL_MAP = {'Over 1.5': 'over_15', 'Under 1.5': 'under_15',
               'Over 2.5': 'over_25', 'Under 2.5': 'under_25',
               'Over 3.5': 'over_35', 'Under 3.5': 'under_35',
               'Goal': 'gg', 'NoGoal': 'ng'}
    SCATOLA_ORDER = {'MIXER': 0, 'ELITE': 1, 'ALTO_RENDIMENTO': 2, 'PRONOSTICI': 3}

    def get_q(p, odds):
        qv = p.get('quota')
        if qv: return qv
        if not odds: return None
        if p.get('tipo') in ('SEGNO', 'DOPPIA_CHANCE'):
            return odds.get(p.get('pronostico'))
        if p.get('tipo') == 'GOL':
            k = GOL_MAP.get(p.get('pronostico'))
            return odds.get(k) if k else None
        return None

    rows_by_key = {}
    for doc in db['daily_predictions_unified'].find(q):
        odds = doc.get('odds') or {}
        home = doc.get('home'); away = doc.get('away'); date_s = doc.get('date')
        for p in doc.get('pronostici') or []:
            if p.get('tipo') not in ('SEGNO', 'DOPPIA_CHANCE', 'GOL'): continue
            if p.get('pronostico') == 'NO BET': continue
            quota = get_q(p, odds)
            if quota is None: continue
            if p.get('esito') is None: continue
            soglia = 2.00 if p['tipo'] == 'DOPPIA_CHANCE' else 2.51
            is_alta = quota >= soglia
            if p.get('mixer') is True: scatola = 'MIXER'
            elif p.get('elite') is True: scatola = 'ELITE'
            elif is_alta: scatola = 'ALTO_RENDIMENTO'
            else: scatola = 'PRONOSTICI'
            key = (date_s, home, away, p['tipo'], p['pronostico'])
            row = {
                'date': date_s, 'home': home, 'away': away,
                'tipo': p.get('tipo'), 'pronostico': p.get('pronostico'),
                'quota': quota,
                'is_elite': bool(p.get('elite')),
                'is_mixer': bool(p.get('mixer')),
                'scatola': scatola,
                'esito': bool(p.get('esito')),
                'pl': p.get('profit_loss') if p.get('profit_loss') is not None
                    else (quota - 1 if p.get('esito') else -1),
            }
            prev = rows_by_key.get(key)
            if prev is None or SCATOLA_ORDER[scatola] < SCATOLA_ORDER[prev['scatola']]:
                rows_by_key[key] = row
    df = pd.DataFrame(list(rows_by_key.values()))

    # Feature engineering
    df['match_time'] = df.apply(
        lambda r: match_meta.get((r['date'], r['home'], r['away']), {}).get('match_time', ''), axis=1)
    df['quota_min_1x2'] = df.apply(
        lambda r: match_meta.get((r['date'], r['home'], r['away']), {}).get('quota_min_1x2'), axis=1)
    df['date_dt'] = pd.to_datetime(df['date'])
    df['giorno_settimana'] = df['date_dt'].dt.day_name()
    df['tipo_partita'] = df['quota_min_1x2'].apply(tipo_partita)
    df['fascia_oraria'] = df['match_time'].apply(fascia_oraria)
    df['fascia_quota'] = df['quota'].apply(fascia_quota)
    df['categoria_a'] = df['quota'].apply(categoria_notebook)  # def A

    return df


def baseline_stats(sub, label):
    n = len(sub)
    if n == 0:
        return {'label': label, 'n': 0, 'hr': None, 'roi': None, 'pl': 0, 'quota_media': None}
    hr = sub['esito'].mean() * 100
    roi = sub['pl'].mean() * 100
    pl = sub['pl'].sum()
    qm = sub['quota'].mean()
    return {'label': label, 'n': n, 'hr': round(hr, 2),
            'roi': round(roi, 2), 'pl': round(pl, 2),
            'quota_media': round(qm, 2)}


def apply_combos_stats(df, ar_mask, ar_label):
    """Per ogni combo, calcola intersezione con ar_mask."""
    rows = []
    for cid, cname, cfun in COMBOS_7:
        mask_combo = df.apply(cfun, axis=1)
        sub = df[ar_mask & mask_combo]
        n = len(sub)
        if n == 0:
            rows.append({
                'id': cid, 'combo': cname, 'n_ar': 0,
                'wins': 0, 'losses': 0,
                'hr': None, 'quota_media': None, 'roi': None, 'pl': 0,
            })
            continue
        wins = int(sub['esito'].sum())
        losses = n - wins
        hr = sub['esito'].mean() * 100
        qm = sub['quota'].mean()
        roi = sub['pl'].mean() * 100
        pl = sub['pl'].sum()
        rows.append({
            'id': cid, 'combo': cname, 'n_ar': n,
            'wins': wins, 'losses': losses,
            'hr': round(hr, 2), 'quota_media': round(qm, 2),
            'roi': round(roi, 2), 'pl': round(pl, 2),
        })
    return rows


def main():
    print('Caricamento dataset...')
    df = load_df()
    print(f'Dataset: {len(df)} pronostici')

    # --- Mask AR secondo 2 definizioni ---
    mask_ar_A = df['categoria_a'] == 'Alto Rendimento'           # def A: quota > 2.50
    mask_ar_B = df['scatola'] == 'ALTO_RENDIMENTO'                # def B: scatola dedup

    n_A = int(mask_ar_A.sum())
    n_B = int(mask_ar_B.sum())
    print(f'AR def A (quota > 2.50): {n_A}')
    print(f'AR def B (scatola): {n_B}')

    # --- Mask "colpiti da almeno una delle 7 combo" ---
    any_combo = pd.Series(False, index=df.index)
    for cid, cname, cfun in COMBOS_7:
        any_combo = any_combo | df.apply(cfun, axis=1)
    n_any_combo = int(any_combo.sum())
    print(f'Pronostici colpiti da almeno 1 combo (globale): {n_any_combo}')

    # --- Baselines ---
    baseline_global = baseline_stats(df, 'Globale')
    baseline_A = baseline_stats(df[mask_ar_A], 'AR def A (quota > 2.50)')
    baseline_B = baseline_stats(df[mask_ar_B], 'AR def B (scatola)')

    # --- Per combo, stats su intersezione con AR ---
    stats_A = apply_combos_stats(df, mask_ar_A, 'AR def A')
    stats_B = apply_combos_stats(df, mask_ar_B, 'AR def B')

    # Univoci AR colpiti
    univoci_A = df[mask_ar_A & any_combo]
    univoci_B = df[mask_ar_B & any_combo]
    wins_univ_A = int(univoci_A['esito'].sum())
    loss_univ_A = len(univoci_A) - wins_univ_A
    wins_univ_B = int(univoci_B['esito'].sum())
    loss_univ_B = len(univoci_B) - wins_univ_B

    # --- Residuo dopo SCARTA ---
    def residuo(df_sub, combo_mask):
        surviv = df_sub[~combo_mask.loc[df_sub.index]]
        return baseline_stats(surviv, 'residuo')

    res_A = residuo(df[mask_ar_A], any_combo)
    res_B = residuo(df[mask_ar_B], any_combo)

    # --- Task 3: distribuzione per scatola frontend dei pronostici tossici def A ---
    tossici_A = df[mask_ar_A & any_combo]
    dist_scatola_tossici = tossici_A['scatola'].value_counts(dropna=False).to_dict()
    # Distribuzione per scatola di TUTTI i pronostici colpiti (indipendente da AR def A)
    tutti_tossici = df[any_combo]
    dist_tutti_tossici = tutti_tossici['scatola'].value_counts(dropna=False).to_dict()

    # --- Report MD ---
    md = ['# Impatto Cerotto 4 (7 combo SCARTA) sulla scatola Alto Rendimento',
          '',
          f'Dataset: **{len(df)}** pronostici dedupati, finestra 19/02/2026 → 18/04/2026.',
          '',
          'Le 7 combo del Cerotto 4 ridotto (solo SCARTA, senza le 3 "falsi allarme"): ',
          'C2, C4, C5, C6, C8, C9, C10 (vedi `combo_verificate.md`).',
          '',
          '## Due definizioni di Alto Rendimento a confronto',
          '',
          '| Definizione | Regola | N |',
          '| --- | --- | ---: |',
          f'| **A** (notebook / report globale) | `quota > 2.50` | **{n_A}** |',
          f'| **B** (scatola frontend) | `elite=False AND mixer=False AND quota >= 2.51 (2.00 DC)` | **{n_B}** |',
          '',
          f'Baseline globale: N={baseline_global["n"]}, HR={baseline_global["hr"]}%, '
          f'ROI={baseline_global["roi"]:+}%, PL={baseline_global["pl"]:+}u',
          '',
          '## Baseline AR per definizione',
          '',
          '| Metrica | Globale | AR def A | AR def B |',
          '| --- | ---: | ---: | ---: |',
          f'| N | {baseline_global["n"]} | {baseline_A["n"]} | {baseline_B["n"]} |',
          f'| HR | {baseline_global["hr"]}% | {baseline_A["hr"]}% | {baseline_B["hr"]}% |',
          f'| Quota media | {baseline_global["quota_media"]} | {baseline_A["quota_media"]} | {baseline_B["quota_media"]} |',
          f'| ROI | {baseline_global["roi"]:+}% | {baseline_A["roi"]:+}% | {baseline_B["roi"]:+}% |',
          f'| PL (u) | {baseline_global["pl"]:+.2f} | {baseline_A["pl"]:+.2f} | {baseline_B["pl"]:+.2f} |',
          '',
          '## Task 1 — Impatto 7 combo su AR def A (quota > 2.50)',
          '',
          '| ID | Combo | N in AR | Wins | Losses | HR | Quota media | ROI | PL (u) |',
          '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for r in stats_A:
        if r['n_ar'] == 0:
            md.append(f'| {r["id"]} | {r["combo"]} | 0 | 0 | 0 | — | — | — | 0 |')
        else:
            md.append(f'| {r["id"]} | {r["combo"]} | {r["n_ar"]} | {r["wins"]} | {r["losses"]} | '
                      f'{r["hr"]:.2f}% | {r["quota_media"]:.2f} | {r["roi"]:+.2f}% | {r["pl"]:+.2f} |')
    md.append('')
    md.append(f'**Pronostici AR def A univoci colpiti da almeno 1 combo**: {len(univoci_A)} '
              f'(di cui {wins_univ_A} vinti, {loss_univ_A} persi)')
    md.append('')

    md.append('## Task 2 — Impatto 7 combo su AR def B (scatola frontend)')
    md.append('')
    md.append('| ID | Combo | N in AR | Wins | Losses | HR | Quota media | ROI | PL (u) |')
    md.append('| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |')
    for r in stats_B:
        if r['n_ar'] == 0:
            md.append(f'| {r["id"]} | {r["combo"]} | 0 | 0 | 0 | — | — | — | 0 |')
        else:
            md.append(f'| {r["id"]} | {r["combo"]} | {r["n_ar"]} | {r["wins"]} | {r["losses"]} | '
                      f'{r["hr"]:.2f}% | {r["quota_media"]:.2f} | {r["roi"]:+.2f}% | {r["pl"]:+.2f} |')
    md.append('')
    md.append(f'**Pronostici AR def B univoci colpiti da almeno 1 combo**: {len(univoci_B)} '
              f'(di cui {wins_univ_B} vinti, {loss_univ_B} persi)')
    md.append('')

    md.append('## Confronto AR prima/dopo Cerotto 4')
    md.append('')
    md.append('| Metrica | AR def A prima | AR def A dopo | Δ | AR def B prima | AR def B dopo | Δ |')
    md.append('| --- | ---: | ---: | ---: | ---: | ---: | ---: |')
    md.append(f'| N | {baseline_A["n"]} | {res_A["n"]} | {res_A["n"] - baseline_A["n"]} | '
              f'{baseline_B["n"]} | {res_B["n"]} | {res_B["n"] - baseline_B["n"]} |')
    if baseline_A["hr"] is not None and res_A["hr"] is not None:
        md.append(f'| HR | {baseline_A["hr"]}% | {res_A["hr"]}% | {res_A["hr"] - baseline_A["hr"]:+.2f}pp | '
                  f'{baseline_B["hr"]}% | {res_B["hr"] or 0}% | '
                  f'{(res_B["hr"] or 0) - (baseline_B["hr"] or 0):+.2f}pp |')
    md.append(f'| ROI | {baseline_A["roi"]:+}% | {res_A["roi"]:+}% | {res_A["roi"] - baseline_A["roi"]:+.2f}pp | '
              f'{baseline_B["roi"]:+}% | {res_B["roi"] or 0:+}% | '
              f'{(res_B["roi"] or 0) - (baseline_B["roi"] or 0):+.2f}pp |')
    md.append(f'| PL (u) | {baseline_A["pl"]:+.2f} | {res_A["pl"]:+.2f} | {res_A["pl"] - baseline_A["pl"]:+.2f} | '
              f'{baseline_B["pl"]:+.2f} | {res_B["pl"]:+.2f} | {res_B["pl"] - baseline_B["pl"]:+.2f} |')
    md.append('')

    md.append('## Task 3 — Dove finiscono i pronostici tossici (frontend scatola)')
    md.append('')
    md.append('### Distribuzione per scatola frontend dei pronostici "AR def A colpiti da 7 combo"')
    md.append('')
    md.append('Questi sono i pronostici che def A classifica come AR (quota>2.50) e che sono toccati dal Cerotto 4. '
              'Dove vanno a finire nel frontend dopo dedup MIXER>ELITE>AR>PRONOSTICI?')
    md.append('')
    md.append('| Scatola frontend | N | % del totale AR def A colpiti |')
    md.append('| --- | ---: | ---: |')
    tot_a = len(univoci_A)
    for sc in ['MIXER', 'ELITE', 'ALTO_RENDIMENTO', 'PRONOSTICI']:
        n = int(dist_scatola_tossici.get(sc, 0))
        pct = n / tot_a * 100 if tot_a > 0 else 0
        md.append(f'| {sc} | {n} | {pct:.1f}% |')
    md.append('')

    md.append('### Distribuzione per scatola di TUTTI i pronostici colpiti dalle 7 combo')
    md.append('')
    md.append('(indipendentemente da quota>2.50: incluso quelli con quota bassa)')
    md.append('')
    md.append('| Scatola frontend | N | % |')
    md.append('| --- | ---: | ---: |')
    tot_all = int(any_combo.sum())
    for sc in ['MIXER', 'ELITE', 'ALTO_RENDIMENTO', 'PRONOSTICI']:
        n = int(dist_tutti_tossici.get(sc, 0))
        pct = n / tot_all * 100 if tot_all > 0 else 0
        md.append(f'| {sc} | {n} | {pct:.1f}% |')
    md.append('')

    md.append('## Lettura e criterio di decisione')
    md.append('')
    md.append('- Se usiamo **def A** (il filtro scatta quando `quota > 2.50`): colpiamo tutti i pronostici '
              'ad alta quota tossici, anche quelli che nel frontend finiscono in MIXER/ELITE/PRONOSTICI. '
              'Coerente col report globale.')
    md.append('- Se usiamo **def B** (il filtro scatta solo sulla scatola AR del frontend): colpiamo solo '
              'i pronostici che l\'utente vede sotto "Alto Rendimento". Lascia fuori eventuali '
              'MIXER/ELITE tossici che comunque verranno mostrati.')
    md.append('')
    md.append('Valuta: se AR def A post-cerotto scende sotto il +150u, fermati e discutiamo.')
    md.append('')
    md.append('## Warning metodologico')
    md.append('')
    md.append('L\'analisi è post-hoc sullo stesso dataset che ha generato le 10 combo. Il PL recuperato '
              'è per costruzione favorevole; un test out-of-sample potrebbe dare risultati diversi.')

    (HERE / 'impatto_alto_rendimento.md').write_text('\n'.join(md), encoding='utf-8')
    print('\nOutput:', HERE / 'impatto_alto_rendimento.md')


if __name__ == '__main__':
    main()
