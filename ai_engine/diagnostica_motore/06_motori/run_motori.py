"""Punto 6 — A vs S vs C: performance isolate, concordanza, specializzazione.

- Performance motore isolata (su daily_predictions / sandbox / engine_c).
- Matrice concordanza (sugli stessi match × mercato, quale combinazione di
  pronostici propongono i 3 motori? performance di ciascuno su consenso/dissenso).
- Motore superiore per (mercato × lega × quota).
- Tier lega (TOP / Seconde / Altro).
- Sovrapposizione "buchi neri": C-derivati in TOP + quota 1.50-2.00.

Output in 06_motori/.
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

MERCATI = ['SEGNO', 'DOPPIA_CHANCE', 'GOL']
GROUP_ORDER = ['A', 'S', 'C', 'A+S', 'C-derivati', 'Altro']

QUOTA_BINS = [0, 1.30, 1.50, 1.80, 2.00, 2.50, 3.50, 100]
QUOTA_LABELS = ['<1.30', '1.30-1.50', '1.50-1.80', '1.80-2.00',
                '2.00-2.50', '2.50-3.50', '3.50+']

TIER_TOP = {'La Liga', 'Premier League', 'Serie A', 'Bundesliga', 'Ligue 1'}
TIER_SECONDE = {
    'LaLiga 2', 'Serie B', 'Championship',
    'Serie C - Girone A', 'Serie C - Girone B', 'Serie C - Girone C',
    'League One', 'League Two', '2. Bundesliga', 'Ligue 2',
}

GOL_MAP = {
    'Over 1.5': 'over_15', 'Under 1.5': 'under_15',
    'Over 2.5': 'over_25', 'Under 2.5': 'under_25',
    'Over 3.5': 'over_35', 'Under 3.5': 'under_35',
    'Goal': 'gg', 'NoGoal': 'ng',
}


def classify_src(src) -> str:
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


def tier(league) -> str:
    if league in TIER_TOP:
        return 'TOP'
    if league in TIER_SECONDE:
        return 'Seconde'
    return 'Altro'


def quota_bin(q):
    if q is None or (isinstance(q, float) and np.isnan(q)):
        return None
    for i in range(len(QUOTA_BINS) - 1):
        if QUOTA_BINS[i] <= q < QUOTA_BINS[i + 1]:
            return QUOTA_LABELS[i]
    return QUOTA_LABELS[-1]


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


def load_engine_predictions(db, coll_name: str, rmap: dict) -> pd.DataFrame:
    """Estrae tutti i pronostici di un motore e ne calcola esito/pl reale.

    Ritorna un DataFrame con una riga per (match, tipo, pronostico) non-NO BET.
    """
    col = db[coll_name]
    q = {'date': {'$gte': DATE_FROM, '$lte': DATE_TO}}
    rows = []
    for doc in col.find(q):
        home = doc.get('home')
        away = doc.get('away')
        date_s = doc.get('date')
        league = doc.get('league')
        is_cup = bool(doc.get('is_cup', False))
        odds = doc.get('odds') or {}
        key_r = f"{home}|||{away}|||{date_s}"
        real_score = rmap.get(key_r)
        parsed = parse_score(real_score) if real_score else None
        for p in doc.get('pronostici', []):
            if p.get('tipo') not in MERCATI:
                continue
            if p.get('pronostico') == 'NO BET':
                continue
            quota = _get_quota(p, odds)
            if quota is None:
                continue
            esito = None
            pl = None
            if parsed:
                esito = check_pronostico(p.get('pronostico'), p.get('tipo'), parsed)
                if esito is not None:
                    pl = (quota - 1) if esito else -1.0
            rows.append({
                'date': date_s,
                'home': home, 'away': away,
                'league': league, 'is_cup': is_cup,
                'tipo': p.get('tipo'),
                'pronostico': p.get('pronostico'),
                'quota': quota,
                'stake': p.get('stake'),
                'esito': esito,
                'pl': pl,
            })
    return pd.DataFrame(rows)


def load_unified_predictions(db, rmap: dict) -> pd.DataFrame:
    """Stesso formato ma da daily_predictions_unified, con dedup e source."""
    col = db['daily_predictions_unified']
    q = {'date': {'$gte': DATE_FROM, '$lte': DATE_TO}}
    SCATOLA_ORDER = {'MIXER': 0, 'ELITE': 1, 'ALTO_RENDIMENTO': 2, 'PRONOSTICI': 3}
    rows_by_key = {}
    for doc in col.find(q):
        odds = doc.get('odds') or {}
        league = doc.get('league')
        home = doc.get('home'); away = doc.get('away')
        date_s = doc.get('date')
        is_cup = bool(doc.get('is_cup', False))
        key_r = f"{home}|||{away}|||{date_s}"
        real_score = rmap.get(key_r)
        parsed = parse_score(real_score) if real_score else None
        for p in doc.get('pronostici', []):
            if p.get('tipo') not in MERCATI: continue
            if p.get('pronostico') == 'NO BET': continue
            quota = _get_quota(p, odds)
            if quota is None: continue
            soglia = 2.00 if p['tipo'] == 'DOPPIA_CHANCE' else 2.51
            is_alta = quota >= soglia
            if p.get('mixer') is True: scatola = 'MIXER'
            elif p.get('elite') is True: scatola = 'ELITE'
            elif is_alta: scatola = 'ALTO_RENDIMENTO'
            else: scatola = 'PRONOSTICI'
            esito = None; pl = None
            if parsed:
                esito = check_pronostico(p.get('pronostico'), p.get('tipo'), parsed)
                if esito is not None:
                    pl = (quota - 1) if esito else -1.0
            key = (date_s, home, away, p['tipo'], p['pronostico'])
            row = {
                'date': date_s, 'home': home, 'away': away,
                'league': league, 'is_cup': is_cup,
                'tipo': p.get('tipo'), 'pronostico': p.get('pronostico'),
                'quota': quota,
                'source': p.get('source'),
                'esito': esito, 'pl': pl,
            }
            prev = rows_by_key.get(key)
            if prev is None or SCATOLA_ORDER[scatola] < SCATOLA_ORDER[prev['scatola']]:
                row['scatola'] = scatola
                rows_by_key[key] = row
    return pd.DataFrame(list(rows_by_key.values()))


def metrics(df: pd.DataFrame) -> dict:
    valid = df[df['esito'].notna() & df['pl'].notna()]
    n = len(valid)
    if n == 0:
        return {'n': 0, 'hr': None, 'pl': 0, 'roi': None}
    return {
        'n': n,
        'hr': round(valid['esito'].astype(bool).mean() * 100, 2),
        'pl': round(valid['pl'].sum(), 2),
        'roi': round(valid['pl'].sum() / n * 100, 2),
    }


def fmt_row(label, m):
    if m['n'] == 0:
        return f'| {label} | 0 | — | — | — |'
    pl_s = '+' if m['pl'] >= 0 else ''
    roi_s = '+' if m['roi'] >= 0 else ''
    return f'| {label} | {m["n"]} | {m["hr"]:.2f}% | {pl_s}{m["pl"]:.2f} | {roi_s}{m["roi"]:.2f}% |'


def build_concordance(df_a, df_s, df_c):
    """Unisce per (date, home, away, tipo). Per ogni chiave confronta i 3
    pronostici e classifica la configurazione."""
    # Seleziona un solo pronostico per (match, tipo) per motore:
    # se ci sono più righe stesso mercato (raro ma possibile), prendo la prima.
    def _dedup(df):
        return df.drop_duplicates(subset=['date', 'home', 'away', 'tipo'], keep='first')

    a = _dedup(df_a).rename(columns={
        'pronostico': 'prono_a', 'quota': 'quota_a',
        'esito': 'esito_a', 'pl': 'pl_a'})
    s = _dedup(df_s).rename(columns={
        'pronostico': 'prono_s', 'quota': 'quota_s',
        'esito': 'esito_s', 'pl': 'pl_s'})
    c = _dedup(df_c).rename(columns={
        'pronostico': 'prono_c', 'quota': 'quota_c',
        'esito': 'esito_c', 'pl': 'pl_c'})

    keys = ['date', 'home', 'away', 'tipo']
    merged = a[keys + ['league', 'prono_a', 'quota_a', 'esito_a', 'pl_a']].merge(
        s[keys + ['prono_s', 'quota_s', 'esito_s', 'pl_s']],
        on=keys, how='outer'
    ).merge(
        c[keys + ['prono_c', 'quota_c', 'esito_c', 'pl_c']],
        on=keys, how='outer'
    )
    # La league potrebbe essere persa su chi non ha row A → fallback
    # Usare la league del motore che ha la riga
    merged['league'] = merged['league'].where(
        merged['league'].notna(),
        None
    )

    # Categoria concordanza
    def _cat(r):
        ps = [r.get('prono_a'), r.get('prono_s'), r.get('prono_c')]
        present = [p for p in ps if pd.notna(p) and p is not None]
        if len(present) < 2:
            # Almeno 2 motori mancano, non classifico
            return f'solo_{"A" if pd.notna(r["prono_a"]) else ("S" if pd.notna(r["prono_s"]) else "C")}'
        if len(present) == 2:
            # quale coppia?
            if pd.notna(r['prono_a']) and pd.notna(r['prono_s']):
                return 'conc_AS' if r['prono_a'] == r['prono_s'] else 'disc_AS'
            if pd.notna(r['prono_a']) and pd.notna(r['prono_c']):
                return 'conc_AC' if r['prono_a'] == r['prono_c'] else 'disc_AC'
            if pd.notna(r['prono_s']) and pd.notna(r['prono_c']):
                return 'conc_SC' if r['prono_s'] == r['prono_c'] else 'disc_SC'
        # len == 3
        if r['prono_a'] == r['prono_s'] == r['prono_c']:
            return 'tutti_3'
        if r['prono_a'] == r['prono_s']:
            return 'AS_vs_C'
        if r['prono_a'] == r['prono_c']:
            return 'AC_vs_S'
        if r['prono_s'] == r['prono_c']:
            return 'SC_vs_A'
        return 'tutti_diversi'
    merged['concordanza'] = merged.apply(_cat, axis=1)
    return merged


def main():
    print('Connessione MongoDB...')
    db = load_db()

    print('Mappa risultati...')
    rmap = build_results_map(db)

    print('Carico pronostici motori...')
    df_a = load_engine_predictions(db, 'daily_predictions', rmap)
    df_s = load_engine_predictions(db, 'daily_predictions_sandbox', rmap)
    df_c = load_engine_predictions(db, 'daily_predictions_engine_c', rmap)
    print(f'  A: {len(df_a)} righe (risolte: {df_a["esito"].notna().sum()})')
    print(f'  S: {len(df_s)} righe (risolte: {df_s["esito"].notna().sum()})')
    print(f'  C: {len(df_c)} righe (risolte: {df_c["esito"].notna().sum()})')

    print('Carico unified (per validazione)...')
    df_u = load_unified_predictions(db, rmap)
    print(f'  Unified dedup: {len(df_u)} righe')

    # Annotazioni comuni
    for d in (df_a, df_s, df_c, df_u):
        d['tier'] = d['league'].apply(tier)
        d['quota_bin'] = d['quota'].apply(quota_bin)

    # =========== 1. Performance motore isolata ===========
    isol_rows = []
    for name, d in [('A (daily_predictions)', df_a),
                    ('S (daily_predictions_sandbox)', df_s),
                    ('C (daily_predictions_engine_c)', df_c)]:
        m = metrics(d)
        isol_rows.append({'motore': name, **m})
    isol_df = pd.DataFrame(isol_rows)
    isol_df.to_csv(HERE / 'performance_isolata.csv', index=False)

    # Per mercato
    isol_mkt = []
    for name, d in [('A', df_a), ('S', df_s), ('C', df_c)]:
        for mkt in MERCATI:
            m = metrics(d[d['tipo'] == mkt])
            isol_mkt.append({'motore': name, 'mercato': mkt, **m})
    pd.DataFrame(isol_mkt).to_csv(HERE / 'performance_isolata_per_mercato.csv', index=False)

    # =========== 2. Matrice concordanza ===========
    print('Costruzione matrice concordanza...')
    conc = build_concordance(df_a, df_s, df_c)
    conc.to_csv(HERE / 'concordanza_raw.csv', index=False)

    # Per ogni categoria concordanza calcolo:
    # - Volume
    # - Se concordanza (tutti_3 o conc_XY o AS_vs_C/AC_vs_S/SC_vs_A):
    #     ROI del pronostico "consensus" (quello maggioritario)
    # - Se discordanza (tutti_diversi): ROI per ciascun motore sul sottoinsieme
    conc_rows = []

    def _consensus_pl(r):
        """Per concordanze parziali, restituisce il PL del pronostico
        concorde (preso da uno dei motori che concorda)."""
        cat = r['concordanza']
        if cat == 'tutti_3':
            # prendo quello di A (tanto sono uguali)
            return r['pl_a']
        if cat == 'conc_AS':
            return r['pl_a']
        if cat == 'conc_AC':
            return r['pl_a']
        if cat == 'conc_SC':
            return r['pl_s']
        if cat == 'AS_vs_C':
            return r['pl_a']   # coppia A+S concordano, gioco A
        if cat == 'AC_vs_S':
            return r['pl_a']
        if cat == 'SC_vs_A':
            return r['pl_s']
        return None

    conc['pl_consensus'] = conc.apply(_consensus_pl, axis=1)

    cat_order = ['tutti_3', 'conc_AS', 'conc_AC', 'conc_SC',
                 'AS_vs_C', 'AC_vs_S', 'SC_vs_A',
                 'disc_AS', 'disc_AC', 'disc_SC', 'tutti_diversi',
                 'solo_A', 'solo_S', 'solo_C']
    for cat in cat_order:
        sub = conc[conc['concordanza'] == cat]
        n = len(sub)
        if n == 0:
            conc_rows.append({'concordanza': cat, 'n': 0})
            continue
        row = {'concordanza': cat, 'n': n}
        # ROI del consensus (se definito)
        if cat in ('tutti_3', 'conc_AS', 'conc_AC', 'conc_SC',
                   'AS_vs_C', 'AC_vs_S', 'SC_vs_A'):
            valid = sub[sub['pl_consensus'].notna()]
            if len(valid) > 0:
                pl = valid['pl_consensus'].sum()
                wins = (valid['pl_consensus'] > 0).sum()
                row['n_consensus'] = len(valid)
                row['hr_consensus'] = round(wins / len(valid) * 100, 2)
                row['pl_consensus'] = round(pl, 2)
                row['roi_consensus'] = round(pl / len(valid) * 100, 2)
        # ROI motore-per-motore
        for m in ('a', 's', 'c'):
            valid = sub[sub[f'pl_{m}'].notna()]
            if len(valid) > 0:
                pl = valid[f'pl_{m}'].sum()
                wins = (valid[f'pl_{m}'] > 0).sum()
                row[f'n_{m}'] = len(valid)
                row[f'hr_{m}'] = round(wins / len(valid) * 100, 2)
                row[f'roi_{m}'] = round(pl / len(valid) * 100, 2)
        conc_rows.append(row)
    conc_df = pd.DataFrame(conc_rows)
    conc_df.to_csv(HERE / 'concordanza_summary.csv', index=False)

    # =========== 3. Motore superiore per segmento ===========
    # Per ogni (mercato × tier × quota_bin): ROI A vs S vs C, identifico il vincitore
    specs_rows = []
    for mkt in MERCATI:
        for t in ('TOP', 'Seconde', 'Altro'):
            for qb in QUOTA_LABELS:
                row = {'mercato': mkt, 'tier': t, 'quota_bin': qb}
                for name, d in [('A', df_a), ('S', df_s), ('C', df_c)]:
                    sub = d[(d['tipo'] == mkt) & (d['tier'] == t) & (d['quota_bin'] == qb)]
                    m = metrics(sub)
                    row[f'{name}_n'] = m['n']
                    row[f'{name}_roi'] = m['roi']
                specs_rows.append(row)
    specs_df = pd.DataFrame(specs_rows)
    specs_df.to_csv(HERE / 'motore_superiore_per_segmento.csv', index=False)

    # =========== 4. Tier lega × motore ===========
    tier_rows = []
    for name, d in [('A', df_a), ('S', df_s), ('C', df_c)]:
        for t in ('TOP', 'Seconde', 'Altro'):
            m = metrics(d[d['tier'] == t])
            tier_rows.append({'motore': name, 'tier': t, **m})
    tier_df = pd.DataFrame(tier_rows)
    tier_df.to_csv(HERE / 'motore_per_tier_lega.csv', index=False)

    # Aggiungo anche split motore × tier × mercato
    tier_mkt_rows = []
    for name, d in [('A', df_a), ('S', df_s), ('C', df_c)]:
        for t in ('TOP', 'Seconde', 'Altro'):
            for mkt in MERCATI:
                m = metrics(d[(d['tier'] == t) & (d['tipo'] == mkt)])
                tier_mkt_rows.append({'motore': name, 'tier': t, 'mercato': mkt, **m})
    tier_mkt_df = pd.DataFrame(tier_mkt_rows)
    tier_mkt_df.to_csv(HERE / 'motore_per_tier_mercato.csv', index=False)

    # =========== 5. Buchi neri: C-derivati × TOP × quota 1.50-2.00 ===========
    df_u_cd = df_u[df_u['source'].apply(classify_src) == 'C-derivati'].copy()
    tot_cd = len(df_u_cd)
    cd_in_top = df_u_cd[df_u_cd['tier'] == 'TOP']
    cd_in_mid_q = df_u_cd[df_u_cd['quota_bin'].isin(['1.50-1.80', '1.80-2.00'])]
    cd_top_q = df_u_cd[(df_u_cd['tier'] == 'TOP') &
                       (df_u_cd['quota_bin'].isin(['1.50-1.80', '1.80-2.00']))]

    buchi = {
        'C-derivati_totale': metrics(df_u_cd) | {'quota_check': tot_cd},
        'C-derivati_in_TOP': metrics(cd_in_top),
        'C-derivati_in_quota_150_200': metrics(cd_in_mid_q),
        'C-derivati_in_TOP_AND_quota_150_200': metrics(cd_top_q),
    }
    # Distribuzione C-derivati per tier (% sul totale)
    tier_dist_cd = df_u_cd['tier'].value_counts(normalize=True).to_dict()
    quota_dist_cd = df_u_cd['quota_bin'].value_counts(normalize=True).to_dict()

    pd.DataFrame([
        {'scope': k, **v} for k, v in buchi.items()
    ]).to_csv(HERE / 'buchi_neri.csv', index=False)

    # =========== REPORT MD ===========
    md = ['# Punto 6 — A vs S vs C: performance, concordanza, specializzazione', '',
          f'Finestra: {DATE_FROM} → {DATE_TO}.',
          '',
          '## ⚠️ Caveat metodologico',
          '',
          'Le performance isolate dei motori sono calcolate sulle rispettive',
          'collection complete (`daily_predictions`, `daily_predictions_sandbox`,',
          '`daily_predictions_engine_c`), NON sul sottoinsieme che finisce nello',
          'unified. I volumi dei tre motori sono quindi diversi fra loro e diversi',
          'dallo unified (1501 righe):',
          '',
          f'- A: {len(df_a)} righe (risolte: {df_a["esito"].notna().sum()})',
          f'- S: {len(df_s)} righe (risolte: {df_s["esito"].notna().sum()})',
          f'- C: {len(df_c)} righe (risolte: {df_c["esito"].notna().sum()})',
          '- Unified (riferimento): {n_u} righe'.format(n_u=len(df_u)),
          '',
          'Questo caveat va tenuto presente nel confronto: un motore con volume',
          'maggiore probabilmente emette anche pronostici che il MoE poi scarta.',
          '',
          '## 1. Performance motore isolata (globale)',
          '',
          '| Motore | N | HR | PL | ROI |',
          '| --- | ---: | ---: | ---: | ---: |']
    for _, r in isol_df.iterrows():
        m = {'n': r['n'], 'hr': r['hr'], 'pl': r['pl'], 'roi': r['roi']}
        md.append(fmt_row(r['motore'], m))
    md.append('')

    md.append('### Per mercato')
    md.append('')
    md.append('| Motore | Mercato | N | HR | PL | ROI |')
    md.append('| --- | --- | ---: | ---: | ---: | ---: |')
    for _, r in pd.DataFrame(isol_mkt).iterrows():
        m = {'n': r['n'], 'hr': r['hr'], 'pl': r['pl'], 'roi': r['roi']}
        if m['n'] == 0:
            md.append(f'| {r["motore"]} | {r["mercato"]} | 0 | — | — | — |')
        else:
            pl_s = '+' if m['pl'] >= 0 else ''
            roi_s = '+' if m['roi'] >= 0 else ''
            md.append(f'| {r["motore"]} | {r["mercato"]} | {m["n"]} | {m["hr"]:.2f}% | {pl_s}{m["pl"]:.2f} | {roi_s}{m["roi"]:.2f}% |')
    md.append('')

    # ===== Concordanza =====
    md.append('## 2. Matrice di concordanza')
    md.append('')
    md.append('Chiave: (date, home, away, mercato). Per ogni chiave recupero il')
    md.append('pronostico proposto da A, S, C (uno per motore, dopo dedup).')
    md.append('')
    md.append('Categorie:')
    md.append('')
    md.append('- `tutti_3`: A=S=C (unanimità)')
    md.append('- `conc_XY`: solo 2 motori presenti e concordi')
    md.append('- `XY_vs_Z`: 3 motori, 2 concordano e uno dissente')
    md.append('- `disc_XY`: solo 2 motori presenti e discordi')
    md.append('- `tutti_diversi`: 3 motori, 3 pronostici diversi')
    md.append('- `solo_X`: solo un motore propone pronostico')
    md.append('')
    md.append('Quando c\'è un consenso, il PL "consensus" è quello del pronostico concorde.')
    md.append('Quando c\'è discordanza, riporto ROI per motore sul sottoinsieme.')
    md.append('')
    md.append('| Categoria | N | HR conc | ROI conc | N_A | HR_A | ROI_A | N_S | HR_S | ROI_S | N_C | HR_C | ROI_C |')
    md.append('| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |')
    for _, r in conc_df.iterrows():
        cells = [r['concordanza'], str(int(r.get('n', 0)))]
        # Consensus
        if 'hr_consensus' in r and pd.notna(r.get('hr_consensus')):
            cells.append(f'{r["hr_consensus"]:.2f}%')
            cells.append(f'{r["roi_consensus"]:+.2f}%')
        else:
            cells += ['—', '—']
        for m in ('a', 's', 'c'):
            if f'n_{m}' in r and pd.notna(r.get(f'n_{m}')):
                cells.append(str(int(r[f'n_{m}'])))
                cells.append(f'{r[f"hr_{m}"]:.2f}%')
                cells.append(f'{r[f"roi_{m}"]:+.2f}%')
            else:
                cells += ['—', '—', '—']
        md.append('| ' + ' | '.join(cells) + ' |')
    md.append('')

    # ===== Tier lega =====
    md.append('## 3. Performance motore per tier di lega')
    md.append('')
    md.append(f'**Tier TOP** ({len(TIER_TOP)} leghe): {", ".join(sorted(TIER_TOP))}')
    md.append('')
    md.append(f'**Tier Seconde** ({len(TIER_SECONDE)} leghe): {", ".join(sorted(TIER_SECONDE))}')
    md.append('')
    md.append('**Tier Altro**: tutto il resto (MLS, sudamericane, nordiche, Portogallo, Scozia, ecc.)')
    md.append('')
    md.append('| Motore | Tier | N | HR | PL | ROI |')
    md.append('| --- | --- | ---: | ---: | ---: | ---: |')
    for _, r in tier_df.iterrows():
        m = {'n': r['n'], 'hr': r['hr'], 'pl': r['pl'], 'roi': r['roi']}
        if m['n'] == 0:
            md.append(f'| {r["motore"]} | {r["tier"]} | 0 | — | — | — |')
        else:
            pl_s = '+' if m['pl'] >= 0 else ''
            roi_s = '+' if m['roi'] >= 0 else ''
            md.append(f'| {r["motore"]} | {r["tier"]} | {m["n"]} | {m["hr"]:.2f}% | {pl_s}{m["pl"]:.2f} | {roi_s}{m["roi"]:.2f}% |')
    md.append('')

    md.append('### Motore × tier × mercato')
    md.append('')
    md.append('| Motore | Tier | Mercato | N | HR | ROI |')
    md.append('| --- | --- | --- | ---: | ---: | ---: |')
    for _, r in tier_mkt_df.iterrows():
        m = {'n': r['n'], 'hr': r['hr'], 'pl': r['pl'], 'roi': r['roi']}
        if m['n'] == 0:
            continue
        roi_s = '+' if m['roi'] >= 0 else ''
        md.append(f'| {r["motore"]} | {r["tier"]} | {r["mercato"]} | {m["n"]} | {m["hr"]:.2f}% | {roi_s}{m["roi"]:.2f}% |')
    md.append('')

    # ===== Motore superiore per segmento =====
    md.append('## 4. Motore superiore per segmento (mercato × tier × quota)')
    md.append('')
    md.append('Solo celle con N ≥ 30 in almeno un motore. Evidenzio il motore con ROI più alto.')
    md.append('')
    md.append('| Mercato | Tier | Quota | A (n/ROI) | S (n/ROI) | C (n/ROI) | Vincitore |')
    md.append('| --- | --- | --- | ---: | ---: | ---: | --- |')
    for _, r in specs_df.iterrows():
        if max(r['A_n'] or 0, r['S_n'] or 0, r['C_n'] or 0) < 30:
            continue
        a_s = f'{int(r["A_n"])}/{r["A_roi"]:+.1f}%' if r['A_n'] > 0 and r['A_roi'] is not None else '—'
        s_s = f'{int(r["S_n"])}/{r["S_roi"]:+.1f}%' if r['S_n'] > 0 and r['S_roi'] is not None else '—'
        c_s = f'{int(r["C_n"])}/{r["C_roi"]:+.1f}%' if r['C_n'] > 0 and r['C_roi'] is not None else '—'
        # Vincitore
        opts = [('A', r['A_roi'], r['A_n']),
                ('S', r['S_roi'], r['S_n']),
                ('C', r['C_roi'], r['C_n'])]
        opts = [o for o in opts if o[1] is not None and o[2] >= 30]
        win = max(opts, key=lambda x: x[1])[0] if opts else '—'
        md.append(f'| {r["mercato"]} | {r["tier"]} | {r["quota_bin"]} | {a_s} | {s_s} | {c_s} | {win} |')
    md.append('')

    # ===== Buchi neri =====
    md.append('## 5. Sovrapposizione "buchi neri" (bonus)')
    md.append('')
    md.append('Verifico la concentrazione di C-derivati nei segmenti peggiori del Punto 5.')
    md.append('')
    md.append('| Scope | N | HR | PL | ROI |')
    md.append('| --- | ---: | ---: | ---: | ---: |')
    for k, v in buchi.items():
        m = {'n': v['n'], 'hr': v['hr'], 'pl': v['pl'], 'roi': v['roi']}
        md.append(fmt_row(k, m))
    md.append('')
    md.append('### Distribuzione C-derivati per tier')
    md.append('')
    md.append('| Tier | Quota del totale C-derivati |')
    md.append('| --- | ---: |')
    for t in ('TOP', 'Seconde', 'Altro'):
        pct = tier_dist_cd.get(t, 0) * 100
        md.append(f'| {t} | {pct:.2f}% |')
    md.append('')
    md.append('### Distribuzione C-derivati per fascia quota')
    md.append('')
    md.append('| Quota | Quota del totale C-derivati |')
    md.append('| --- | ---: |')
    for qb in QUOTA_LABELS:
        pct = quota_dist_cd.get(qb, 0) * 100
        md.append(f'| {qb} | {pct:.2f}% |')
    md.append('')

    md.append('## 6. Osservazioni oggettive')
    md.append('')
    # Top vs Seconde per ciascun motore
    md.append('### Δ ROI tra tier per ciascun motore')
    md.append('')
    md.append('| Motore | ROI TOP | ROI Seconde | ROI Altro | Δ (Altro - TOP) |')
    md.append('| --- | ---: | ---: | ---: | ---: |')
    pivot = tier_df.pivot(index='motore', columns='tier', values='roi')
    for m_name in ('A', 'S', 'C'):
        if m_name not in pivot.index:
            continue
        top_r = pivot.loc[m_name, 'TOP'] if 'TOP' in pivot.columns else None
        sec_r = pivot.loc[m_name, 'Seconde'] if 'Seconde' in pivot.columns else None
        oth_r = pivot.loc[m_name, 'Altro'] if 'Altro' in pivot.columns else None
        fmt = lambda v: f'{v:+.2f}%' if v is not None and pd.notna(v) else '—'
        delta = (oth_r - top_r) if (oth_r is not None and top_r is not None and
                                    pd.notna(oth_r) and pd.notna(top_r)) else None
        md.append(f'| {m_name} | {fmt(top_r)} | {fmt(sec_r)} | {fmt(oth_r)} | {fmt(delta)} |')
    md.append('')

    md.append('## 7. File generati')
    md.append('')
    md.append('- `performance_isolata.csv`, `performance_isolata_per_mercato.csv`')
    md.append('- `concordanza_raw.csv`, `concordanza_summary.csv`')
    md.append('- `motore_per_tier_lega.csv`, `motore_per_tier_mercato.csv`')
    md.append('- `motore_superiore_per_segmento.csv`')
    md.append('- `buchi_neri.csv`')

    (HERE / 'report.md').write_text('\n'.join(md), encoding='utf-8')
    print(f'Output in: {HERE}')


if __name__ == '__main__':
    main()
