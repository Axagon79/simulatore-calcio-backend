"""Cerotto 4 — analisi preview prima di disattivare combo tossiche.

Task 1: Per ciascuna delle 10 combo tossiche (da report globale sez. 6.1),
calcola volume / HR / quota media / ROI / PL sul dataset storico
19/02/2026 -> 18/04/2026.

Task 2: Matrice di intersezione tra combo e totale pronostici impattati.

Task 3: Simulazione dell'azione raccomandata (SCARTA o Dimezza) -> delta PL.

Output in 04_no_bet/cerotto4_preview/:
- combo_verificate.md
- sovrapposizioni.csv
- simulazione_impatto.md

Definizioni dei campi (dal notebook `c:/Progetti/analisi_professionale.ipynb`):
- tipo_partita: da qmin = min(quota_1, quota_X, quota_2)
    < 1.40    -> dominante
    1.40-1.79 -> favorita
    1.80-2.29 -> equilibrata
    >= 2.30   -> aperta
- fascia_oraria: da hour = int(match_time.split(':')[0])
    < 15  -> mattina
    15-17 -> pomeriggio
    18-20 -> sera
    >= 21 -> notte
- fascia_quota: sul campo `quota` del pronostico
    3.00+      -> '3.00+'
    2.50-2.99  -> '2.50-2.99'
- categoria: quota > 2.50 -> Alto Rendimento, altrimenti Pronostici
- giorno_settimana: nome inglese (Monday, Tuesday, ...)

Nessuna modifica al codice / DB.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from collections import Counter

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
BACKEND_ROOT = HERE.parent.parent.parent
CACHE = HERE.parent.parent / 'pattern_discovery' / 'dataset_cache.parquet'


def load_db():
    spec = importlib.util.spec_from_file_location('backend_config', BACKEND_ROOT / 'config.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.db


# === Definizioni dal notebook ===

def tipo_partita(qmin) -> str:
    if pd.isna(qmin) or qmin <= 0:
        return 'n/a'
    if qmin < 1.40:
        return 'dominante'
    if qmin < 1.80:
        return 'favorita'
    if qmin < 2.30:
        return 'equilibrata'
    return 'aperta'


def fascia_oraria(match_time) -> str:
    if not match_time or not isinstance(match_time, str):
        return 'sconosciuto'
    try:
        h = int(match_time.split(':')[0])
    except Exception:
        return 'sconosciuto'
    if h < 15:
        return 'mattina'
    if h < 18:
        return 'pomeriggio'
    if h < 21:
        return 'sera'
    return 'notte'


def fascia_quota(q) -> str:
    if q is None or q <= 0:
        return 'n/a'
    if q < 1.40:
        return '1.01-1.39'
    if q < 1.70:
        return '1.40-1.69'
    if q < 2.00:
        return '1.70-1.99'
    if q < 2.50:
        return '2.00-2.49'
    if q < 3.00:
        return '2.50-2.99'
    return '3.00+'


def categoria(q) -> str:
    if q is None:
        return 'n/a'
    return 'Alto Rendimento' if q > 2.50 else 'Pronostici'


# === Le 10 combo del report globale ===

COMBOS = [
    ('C1', 'SEGNO + fascia_quota=3.00+',
        lambda r: r['tipo'] == 'SEGNO' and r['fascia_quota'] == '3.00+',
        'Dimezza'),
    ('C2', 'SEGNO + tipo_partita=aperta',
        lambda r: r['tipo'] == 'SEGNO' and r['tipo_partita'] == 'aperta',
        'SCARTA'),
    ('C3', 'SEGNO + categoria=Alto Rendimento',
        lambda r: r['tipo'] == 'SEGNO' and r['categoria'] == 'Alto Rendimento',
        'Dimezza'),
    ('C4', 'tipo_partita=aperta + categoria=Alto Rendimento',
        lambda r: r['tipo_partita'] == 'aperta' and r['categoria'] == 'Alto Rendimento',
        'SCARTA'),
    ('C5', 'SEGNO + Monday + tipo_partita=aperta',
        lambda r: r['tipo'] == 'SEGNO' and r['giorno_settimana'] == 'Monday' and r['tipo_partita'] == 'aperta',
        'SCARTA'),
    ('C6', 'fascia_oraria=sera + categoria=Alto Rendimento',
        lambda r: r['fascia_oraria'] == 'sera' and r['categoria'] == 'Alto Rendimento',
        'SCARTA'),
    ('C7', 'fascia_quota=3.00+ + categoria=Alto Rendimento',
        lambda r: r['fascia_quota'] == '3.00+' and r['categoria'] == 'Alto Rendimento',
        'Dimezza'),
    ('C8', 'Friday + fascia_quota=3.00+ + tipo_partita=equilibrata',
        lambda r: r['giorno_settimana'] == 'Friday' and r['fascia_quota'] == '3.00+' and r['tipo_partita'] == 'equilibrata',
        'SCARTA'),
    ('C9', 'fascia_quota=2.50-2.99 + tipo_partita=aperta',
        lambda r: r['fascia_quota'] == '2.50-2.99' and r['tipo_partita'] == 'aperta',
        'SCARTA'),
    ('C10', 'Friday + categoria=Alto Rendimento',
        lambda r: r['giorno_settimana'] == 'Friday' and r['categoria'] == 'Alto Rendimento',
        'SCARTA'),
]


def main():
    print('Caricamento dataset...')
    df = pd.read_parquet(CACHE)
    df = df[df['quota'].notna()].copy()
    print(f'Dataset: {len(df)} pronostici')

    # Serve quota_1/quota_X/quota_2 dal DB — non è nel cache
    print('Connessione MongoDB per recuperare quote 1X2 + match_time...')
    db = load_db()
    q = {'date': {'$gte': '2026-02-19', '$lte': '2026-04-18'}}

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
        qmin = min(vals) if vals else None
        match_meta[key] = {
            'match_time': d.get('match_time', ''),
            'quota_1': q1, 'quota_X': qX, 'quota_2': q2,
            'quota_min_1x2': qmin,
        }
    print(f'  {len(match_meta)} match con metadata')

    # Il cache NON ha home/away. Ricarico i pronostici da MongoDB con stesso dedup.
    print('Ricarico pronostici con home/away per join metadata match...')
    GOL_MAP = {'Over 1.5': 'over_15', 'Under 1.5': 'under_15',
               'Over 2.5': 'over_25', 'Under 2.5': 'under_25',
               'Over 3.5': 'over_35', 'Under 3.5': 'under_35',
               'Goal': 'gg', 'NoGoal': 'ng'}
    SCATOLA_ORDER = {'MIXER': 0, 'ELITE': 1, 'ALTO_RENDIMENTO': 2, 'PRONOSTICI': 3}

    def get_q(p, odds):
        qv = p.get('quota')
        if qv:
            return qv
        if not odds:
            return None
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
        mk = (date_s, home, away)
        for p in doc.get('pronostici') or []:
            if p.get('tipo') not in ('SEGNO', 'DOPPIA_CHANCE', 'GOL'):
                continue
            if p.get('pronostico') == 'NO BET':
                continue
            quota = get_q(p, odds)
            if quota is None:
                continue
            if p.get('esito') is None:
                continue
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
                'esito': bool(p.get('esito')),
                'pl': p.get('profit_loss') if p.get('profit_loss') is not None
                    else (quota - 1 if p.get('esito') else -1),
                'scatola': scatola,
            }
            prev = rows_by_key.get(key)
            if prev is None or SCATOLA_ORDER[scatola] < SCATOLA_ORDER[prev['scatola']]:
                rows_by_key[key] = row
    df = pd.DataFrame(list(rows_by_key.values()))
    print(f'  Dataset dedupato: {len(df)} righe')

    # Arricchisci con metadata
    df['match_time'] = df.apply(
        lambda r: match_meta.get((r['date'], r['home'], r['away']), {}).get('match_time', ''),
        axis=1)
    df['quota_min_1x2'] = df.apply(
        lambda r: match_meta.get((r['date'], r['home'], r['away']), {}).get('quota_min_1x2'),
        axis=1)
    df['date_dt'] = pd.to_datetime(df['date'])
    df['giorno_settimana'] = df['date_dt'].dt.day_name()
    df['tipo_partita'] = df['quota_min_1x2'].apply(tipo_partita)
    df['fascia_oraria'] = df['match_time'].apply(fascia_oraria)
    df['fascia_quota'] = df['quota'].apply(fascia_quota)
    df['categoria'] = df['quota'].apply(categoria)

    print()
    print('=== Distribuzioni campi derivati ===')
    for c in ['tipo_partita', 'fascia_oraria', 'fascia_quota', 'categoria']:
        print(f'{c}: {df[c].value_counts().to_dict()}')

    # --- Globale: baseline ---
    n_tot = len(df)
    hr_globale = df['esito'].mean() * 100
    roi_globale = df['pl'].mean() * 100
    pl_globale = df['pl'].sum()
    print(f'\nBaseline globale: N={n_tot}, HR={hr_globale:.2f}%, ROI={roi_globale:+.2f}%, PL={pl_globale:+.2f}')

    # === TASK 1: stats per combo ===
    combo_rows = []
    masks = {}
    for cid, cname, cfun, caction in COMBOS:
        mask = df.apply(cfun, axis=1)
        masks[cid] = mask
        sub = df[mask]
        n = len(sub)
        if n == 0:
            combo_rows.append({
                'id': cid, 'combo': cname, 'azione_proposta': caction,
                'n': 0, 'hr': None, 'quota_media': None, 'roi': None, 'pl': 0,
                'verdetto': 'n/a (N=0)',
            })
            continue
        hr = sub['esito'].mean() * 100
        qm = sub['quota'].mean()
        roi = sub['pl'].mean() * 100
        pl = sub['pl'].sum()
        # Falso allarme se ROI > 0 nonostante HR bassa
        if roi > 0:
            verdetto = 'FALSO ALLARME (ROI positivo nonostante HR bassa)'
        elif roi > -5:
            verdetto = 'DUBBIO (ROI ~ 0)'
        else:
            verdetto = 'TOSSICA (ROI negativo netto)'
        combo_rows.append({
            'id': cid, 'combo': cname, 'azione_proposta': caction,
            'n': n, 'hr': round(hr, 2), 'quota_media': round(qm, 2),
            'roi': round(roi, 2), 'pl': round(pl, 2),
            'verdetto': verdetto,
        })
    combo_df = pd.DataFrame(combo_rows)

    # === TASK 2: sovrapposizioni ===
    # Matrice N x N: per ogni coppia (Ci, Cj) quanti pronostici sono colpiti da entrambe.
    ids = [cid for cid, _, _, _ in COMBOS]
    overlap = pd.DataFrame(index=ids, columns=ids, dtype=int)
    for i in ids:
        mi = masks[i]
        for j in ids:
            mj = masks[j]
            overlap.loc[i, j] = int((mi & mj).sum())

    # Totale pronostici univoci impattati da almeno una combo
    any_mask = pd.Series(False, index=df.index)
    for cid in ids:
        any_mask = any_mask | masks[cid]
    n_union = int(any_mask.sum())

    # Pronostici colpiti da solo 1 combo vs da multiple
    count_hit = pd.Series(0, index=df.index)
    for cid in ids:
        count_hit = count_hit + masks[cid].astype(int)
    dist_count = count_hit[count_hit > 0].value_counts().sort_index().to_dict()

    overlap.to_csv(HERE / 'sovrapposizioni.csv')

    # === TASK 3: simulazione impatto ===
    # Per pronostico: se appartiene ad almeno una SCARTA → stake 0 (PL 0)
    # Se appartiene SOLO a Dimezza (e nessuna SCARTA) → PL diviso 2
    # Altrimenti → PL invariato
    scarta_ids = [cid for cid, _, _, caction in COMBOS if caction == 'SCARTA']
    dimezza_ids = [cid for cid, _, _, caction in COMBOS if caction == 'Dimezza']

    scarta_mask = pd.Series(False, index=df.index)
    for cid in scarta_ids:
        scarta_mask = scarta_mask | masks[cid]

    dimezza_mask = pd.Series(False, index=df.index)
    for cid in dimezza_ids:
        dimezza_mask = dimezza_mask | masks[cid]

    # azione effettiva: SCARTA prevale su Dimezza
    effective_scarta = scarta_mask
    effective_dimezza = dimezza_mask & ~scarta_mask

    df['pl_sim'] = df['pl']
    df.loc[effective_scarta, 'pl_sim'] = 0.0
    df.loc[effective_dimezza, 'pl_sim'] = df.loc[effective_dimezza, 'pl'] / 2.0

    n_scarta = int(effective_scarta.sum())
    n_dimezza = int(effective_dimezza.sum())
    n_intact = n_tot - n_scarta - n_dimezza

    pl_sim_total = df['pl_sim'].sum()
    # Volume "residuo" = pronostici che finirebbero in bolletta (non scartati)
    # I dimezzati restano ma con 1/2 stake → li conto come 0.5 pronostici.
    vol_residuo = n_intact + 0.5 * n_dimezza
    hr_intact = df[~effective_scarta & ~effective_dimezza]['esito'].mean() * 100
    hr_intact_all = df[~effective_scarta]['esito'].mean() * 100  # include anche dimezzati

    # PL/ROI per segmento
    pl_scartati_originale = df.loc[effective_scarta, 'pl'].sum()
    pl_dimezzati_originale = df.loc[effective_dimezza, 'pl'].sum()
    pl_intact_originale = df.loc[~effective_scarta & ~effective_dimezza, 'pl'].sum()

    delta_scarti = -pl_scartati_originale   # se erano negativi, il delta è positivo
    delta_dimezzi = -pl_dimezzati_originale / 2.0
    delta_totale = delta_scarti + delta_dimezzi
    assert abs(delta_totale - (pl_sim_total - pl_globale)) < 0.01

    # === REPORT MD: combo_verificate.md ===
    md = ['# Cerotto 4 — Verifica 10 combo tossiche (preview)', '',
          f'Dataset: **{n_tot}** pronostici dedupati (MIXER>ELITE>AR>PRONOSTICI), '
          f'finestra 19/02/2026 → 18/04/2026.',
          '',
          '**Definizioni** (dal notebook `c:/Progetti/analisi_professionale.ipynb`, verificate):',
          '',
          '- `quota_min_1x2 = min(quota_1, quota_X, quota_2)` dalla partita',
          '- `tipo_partita`: <1.40 dominante, 1.40-1.79 favorita, 1.80-2.29 equilibrata, ≥2.30 aperta',
          '- `fascia_oraria`: hour<15 mattina, 15-17 pomeriggio, 18-20 sera, ≥21 notte',
          '- `categoria`: quota>2.50 Alto Rendimento, altrimenti Pronostici',
          '- `fascia_quota`: 3.00+ = quota≥3.00, 2.50-2.99 = 2.50≤quota<3.00',
          '',
          'Nota: il report originale sovrappone `categoria=Alto Rendimento` (quota>2.50) '
          'e `fascia_quota=3.00+` (quota≥3.00) — sono filtri quasi identici, '
          'molte combo risultano strettamente sovrapposte (vedi task 2).',
          '',
          '## Baseline globale',
          '',
          f'- N = {n_tot}',
          f'- HR = {hr_globale:.2f}%',
          f'- ROI = {roi_globale:+.2f}%',
          f'- PL totale = {pl_globale:+.2f}u',
          '',
          '## 1. Tabella combo (5 colonne richieste + verdetto)',
          '',
          '| ID | Combo | Azione | N | HR | Quota media | ROI | PL (u) | Verdetto |',
          '| --- | --- | :---: | ---: | ---: | ---: | ---: | ---: | --- |']
    for r in combo_rows:
        if r['n'] == 0:
            md.append(f'| {r["id"]} | {r["combo"]} | {r["azione_proposta"]} | 0 | — | — | — | 0 | {r["verdetto"]} |')
        else:
            md.append(f'| {r["id"]} | {r["combo"]} | {r["azione_proposta"]} | '
                      f'{r["n"]} | {r["hr"]:.2f}% | {r["quota_media"]:.2f} | '
                      f'{r["roi"]:+.2f}% | {r["pl"]:+.2f} | {r["verdetto"]} |')
    md.append('')
    md.append('**Soglia verdetto**: ROI > 0 → FALSO ALLARME. '
              'ROI in (-5%, 0] → DUBBIO. ROI ≤ -5% → TOSSICA.')
    md.append('')

    # === TASK 2: sovrapposizioni ===
    md.append('## 2. Sovrapposizione tra combo')
    md.append('')
    md.append(f'- Pronostici univoci colpiti da almeno 1 combo: **{n_union}** '
              f'({n_union / n_tot * 100:.1f}% del dataset)')
    md.append(f'- Distribuzione del numero di combo hit per pronostico:')
    for k, v in sorted(dist_count.items()):
        md.append(f'  - colpiti da {k} combo: {v} pronostici')
    md.append('')
    md.append('Matrice diagonale = N singolo (diagonale == task 1). '
              'Off-diagonale (i,j) = pronostici colpiti da entrambe Ci e Cj. '
              'Vedi file [`sovrapposizioni.csv`](sovrapposizioni.csv).')
    md.append('')

    # Evidenzia coppie altamente sovrapposte
    md.append('### Coppie più sovrapposte')
    md.append('')
    md.append('| Coppia | Intersezione | % su min(N_i,N_j) |')
    md.append('| --- | ---: | ---: |')
    rows_pair = []
    for i_idx, i in enumerate(ids):
        for j in ids[i_idx + 1:]:
            inter = int(overlap.loc[i, j])
            ni = int(overlap.loc[i, i])
            nj = int(overlap.loc[j, j])
            mn = min(ni, nj)
            if mn == 0:
                continue
            pct = inter / mn * 100
            if pct >= 50 and inter >= 5:
                rows_pair.append((i, j, inter, mn, pct))
    rows_pair.sort(key=lambda x: -x[4])
    for i, j, inter, mn, pct in rows_pair[:10]:
        md.append(f'| {i} ∩ {j} | {inter} | {pct:.1f}% |')
    if not rows_pair:
        md.append('| — | — | — |')
    md.append('')

    (HERE / 'combo_verificate.md').write_text('\n'.join(md), encoding='utf-8')

    # === REPORT MD: simulazione_impatto.md ===
    md2 = ['# Cerotto 4 — Simulazione impatto azioni', '',
           'Applicazione virtuale delle azioni `SCARTA` / `Dimezza` sul dataset storico.',
           '',
           'Regole:',
           '- Pronostico in almeno 1 combo SCARTA → PL = 0 (non giocato)',
           '- Pronostico SOLO in combo Dimezza → PL / 2',
           '- Pronostico in nessuna combo → PL invariato',
           '',
           'Se un pronostico è in entrambe SCARTA e Dimezza, SCARTA prevale.',
           '',
           '## Risultato simulazione',
           '',
           '| Metrica | Originale | Simulato | Delta |',
           '| --- | ---: | ---: | ---: |',
           f'| Volume | {n_tot} | {n_intact + n_dimezza} attivi ({n_scarta} scartati) | -{n_scarta} |',
           f'| Volume pesato (dimezzati = 0.5) | {n_tot:.1f} | {vol_residuo:.1f} | {vol_residuo - n_tot:+.1f} |',
           f'| HR | {hr_globale:.2f}% | {hr_intact_all:.2f}% (solo non scartati) | {hr_intact_all - hr_globale:+.2f}pp |',
           f'| PL totale | {pl_globale:+.2f}u | {pl_sim_total:+.2f}u | {delta_totale:+.2f}u |',
           f'| ROI per unità | {roi_globale:+.2f}% | {pl_sim_total / vol_residuo * 100 if vol_residuo > 0 else 0:+.2f}% | — |',
           '',
           '## Dettaglio per gruppo azione',
           '',
           '| Gruppo | N | PL originale | PL simulato | Δ |',
           '| --- | ---: | ---: | ---: | ---: |',
           f'| Pronostici in SCARTA | {n_scarta} | {pl_scartati_originale:+.2f}u | 0.00u | {-pl_scartati_originale:+.2f}u |',
           f'| Pronostici solo in Dimezza | {n_dimezza} | {pl_dimezzati_originale:+.2f}u | {pl_dimezzati_originale / 2:+.2f}u | {-pl_dimezzati_originale / 2:+.2f}u |',
           f'| Pronostici intatti | {n_intact} | {pl_intact_originale:+.2f}u | {pl_intact_originale:+.2f}u | 0.00u |',
           '',
           ]

    # Dettaglio per combo: quanto contribuisce ciascuna al delta
    md2.append('## Contributo per combo (PL originale dei pronostici unicamente coperti da questa combo)')
    md2.append('')
    md2.append('| ID | N esclusivi | PL originale esclusivi |')
    md2.append('| --- | ---: | ---: |')
    for cid, cname, cfun, caction in COMBOS:
        mask = masks[cid]
        # Pronostici coperti SOLO da questa combo (non da altre)
        others = pd.Series(False, index=df.index)
        for other_id in ids:
            if other_id != cid:
                others = others | masks[other_id]
        only_here = mask & ~others
        n_only = int(only_here.sum())
        pl_only = df.loc[only_here, 'pl'].sum() if n_only > 0 else 0
        md2.append(f'| {cid} | {n_only} | {pl_only:+.2f}u |')
    md2.append('')

    md2.append('## Warning metodologico')
    md2.append('')
    md2.append('Questa simulazione è post-hoc sullo stesso dataset che ha generato le '
               'combo tossiche (nel report originale). Quindi l\'impatto simulato è '
               'per costruzione favorevole: stiamo "togliendo" sullo stesso set dove '
               'abbiamo identificato l\'overfit. Un test out-of-sample su dati futuri '
               'potrebbe dare risultati diversi. Valutare prima di applicare in produzione.')

    (HERE / 'simulazione_impatto.md').write_text('\n'.join(md2), encoding='utf-8')

    print()
    print('Output generati in:', HERE)


if __name__ == '__main__':
    main()
