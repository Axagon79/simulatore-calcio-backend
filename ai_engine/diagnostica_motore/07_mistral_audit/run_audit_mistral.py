"""Audit qualità analisi Mistral in prediction_errors.

Analisi 1: campione stratificato di 30 documenti (10 recenti, 10 metà, 10 vecchi)
  → CSV campione_30.csv per lettura umana.

Analisi 2: distribuzioni temporali (root_cause, pattern_tags, severity per settimana,
  sub-motori più suggeriti).

Output in 07_mistral_audit/.
"""
from __future__ import annotations

import importlib.util
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
BACKEND_ROOT = HERE.parent.parent.parent


def load_db():
    spec = importlib.util.spec_from_file_location('backend_config', BACKEND_ROOT / 'config.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.db


def fetch_docs(db):
    """Fetch all prediction_errors with relevant fields."""
    rows = []
    for d in db.prediction_errors.find({}, {
        '_id': 1,
        'created_at': 1, 'match_date': 1, 'home_team': 1, 'away_team': 1,
        'prediction_type': 1, 'prediction_value': 1, 'probabilita_stimata': 1,
        'confidence': 1, 'quota': 1, 'stake': 1, 'profit_loss': 1,
        'source': 1, 'league': 1, 'actual_outcome': 1, 'actual_result': 1,
        'severity': 1, 'root_cause': 1, 'ai_analysis': 1,
        'suggested_adjustment': 1, 'pattern_tags': 1,
        'variables_impact': 1,
    }):
        rows.append(d)
    return rows


SUBMOTORI_SEGNO = ['bvs', 'quote', 'lucifero', 'affidabilita', 'dna',
                    'motivazioni', 'h2h', 'campo', 'strisce']
SUBMOTORI_GOL = ['media_gol', 'att_vs_def', 'xg', 'h2h_gol',
                  'media_lega', 'dna_off_def', 'strisce']
SUBMOTORI_ALL = set(SUBMOTORI_SEGNO + SUBMOTORI_GOL + [
    'confidence', 'stars', 'probabilita_stimata', 'edge'])

KEYWORDS_AUMENTA = ['aument', 'rafforz', 'increment', 'potenziare', 'alzare', 'maggior']
KEYWORDS_RIDUCI = ['ridur', 'ridimens', 'diminuir', 'abbass', 'depoten', 'minor']


def extract_submotori_from_text(txt: str):
    """Dato un testo suggested_adjustment, estrae i sub-motori citati."""
    if not txt:
        return []
    tl = txt.lower()
    found = []
    for sm in SUBMOTORI_ALL:
        if re.search(rf"\b{re.escape(sm)}\b", tl):
            found.append(sm)
    return found


def direction_of(txt: str) -> str:
    """Stabilisce se il suggerimento è 'aumenta', 'riduci' o 'altro'."""
    if not txt:
        return 'altro'
    tl = txt.lower()
    has_aum = any(k in tl for k in KEYWORDS_AUMENTA)
    has_rid = any(k in tl for k in KEYWORDS_RIDUCI)
    if has_rid and not has_aum:
        return 'riduci'
    if has_aum and not has_rid:
        return 'aumenta'
    if has_aum and has_rid:
        return 'misto'
    return 'altro'


def week_of(d: datetime) -> str:
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def build_sample_30(docs):
    """Stratificato: 10 più recenti, 10 metà periodo, 10 più vecchi."""
    sorted_docs = sorted(docs, key=lambda x: x.get('created_at') or datetime.min)
    n = len(sorted_docs)
    if n < 30:
        return sorted_docs
    oldest = sorted_docs[:10]
    mid_center = n // 2
    mid = sorted_docs[mid_center - 5:mid_center + 5]
    recent = sorted_docs[-10:]
    return oldest + mid + recent


def doc_to_row(d):
    vi = d.get('variables_impact') or {}
    tags = d.get('pattern_tags') or []
    return {
        'created_at': d.get('created_at'),
        'match_date': d.get('match_date'),
        'home': d.get('home_team'),
        'away': d.get('away_team'),
        'league': d.get('league'),
        'tipo': d.get('prediction_type'),
        'pronostico': d.get('prediction_value'),
        'source': d.get('source'),
        'quota': d.get('quota'),
        'probabilita_stimata': d.get('probabilita_stimata'),
        'confidence': d.get('confidence'),
        'stake': d.get('stake'),
        'profit_loss': d.get('profit_loss'),
        'actual_outcome': d.get('actual_outcome'),
        'actual_result': d.get('actual_result'),
        'severity': d.get('severity'),
        'pattern_tags': '|'.join(tags) if tags else '',
        'root_cause': d.get('root_cause'),
        'ai_analysis': d.get('ai_analysis'),
        'suggested_adjustment': d.get('suggested_adjustment'),
        'vi_form': vi.get('form'),
        'vi_motivation': vi.get('motivation'),
        'vi_home_advantage': vi.get('home_advantage'),
        'vi_market_odds': vi.get('market_odds'),
        'vi_h2h': vi.get('h2h'),
        'vi_fatigue': vi.get('fatigue'),
        'vi_streaks': vi.get('streaks'),
        'vi_tactical_dna': vi.get('tactical_dna'),
    }


def main():
    print('Connessione MongoDB...')
    db = load_db()
    print('Fetch prediction_errors...')
    docs = fetch_docs(db)
    print(f'  {len(docs)} documenti')

    # === Analisi 1: campione 30 ===
    sample = build_sample_30(docs)
    df_sample = pd.DataFrame([doc_to_row(d) for d in sample])
    df_sample.to_csv(HERE / 'campione_30.csv', index=False, encoding='utf-8-sig')
    print(f'Campione 30 salvato: {len(df_sample)} righe')

    # === Analisi 2: distribuzioni temporali ===
    rows_all = [doc_to_row(d) for d in docs]
    df = pd.DataFrame(rows_all)
    df['week'] = df['created_at'].apply(
        lambda d: week_of(d) if isinstance(d, datetime) else None)

    # 2a) root_cause per settimana (top 5 per settimana)
    week_rc = defaultdict(Counter)
    for _, r in df.iterrows():
        if r['week'] and r['root_cause']:
            # raggruppo per prime 4 parole (per evitare stringhe tutte uniche)
            words = str(r['root_cause']).split()
            key = ' '.join(words[:4]).lower()
            week_rc[r['week']][key] += 1

    rc_rows = []
    for w in sorted(week_rc.keys()):
        for phrase, cnt in week_rc[w].most_common(5):
            rc_rows.append({'week': w, 'root_cause_prefix': phrase, 'n': cnt})
    pd.DataFrame(rc_rows).to_csv(HERE / 'root_cause_per_settimana.csv', index=False, encoding='utf-8-sig')

    # 2b) pattern_tags per settimana
    week_tags = defaultdict(Counter)
    for _, r in df.iterrows():
        if r['week'] and r['pattern_tags']:
            for tag in str(r['pattern_tags']).split('|'):
                if tag:
                    week_tags[r['week']][tag] += 1
    tag_rows = []
    for w in sorted(week_tags.keys()):
        for tag, cnt in week_tags[w].most_common():
            tag_rows.append({'week': w, 'tag': tag, 'n': cnt})
    pd.DataFrame(tag_rows).to_csv(HERE / 'pattern_tags_per_settimana.csv', index=False, encoding='utf-8-sig')

    # 2c) severity per settimana
    sev_rows = []
    for w in sorted(df['week'].dropna().unique()):
        sub = df[df['week'] == w]
        counts = sub['severity'].value_counts(dropna=False).to_dict()
        sev_rows.append({'week': w, 'total': len(sub),
                         'low': counts.get('low', 0),
                         'medium': counts.get('medium', 0),
                         'high': counts.get('high', 0),
                         'null': int(sub['severity'].isna().sum())})
    pd.DataFrame(sev_rows).to_csv(HERE / 'severity_per_settimana.csv', index=False, encoding='utf-8-sig')

    # 2d) sub-motori più suggeriti (direzione)
    sm_counter = Counter()
    sm_direction = defaultdict(Counter)
    for _, r in df.iterrows():
        txt = r['suggested_adjustment']
        if not txt:
            continue
        submotori = extract_submotori_from_text(txt)
        dir_ = direction_of(txt)
        for sm in submotori:
            sm_counter[sm] += 1
            sm_direction[sm][dir_] += 1
    sm_rows = []
    for sm, cnt in sm_counter.most_common():
        dirs = sm_direction[sm]
        sm_rows.append({
            'sub_motore': sm, 'n_totale': cnt,
            'aumenta': dirs.get('aumenta', 0),
            'riduci': dirs.get('riduci', 0),
            'misto': dirs.get('misto', 0),
            'altro': dirs.get('altro', 0),
        })
    pd.DataFrame(sm_rows).to_csv(HERE / 'submotori_suggeriti.csv', index=False, encoding='utf-8-sig')

    # 2e) Coerenza interna settimanale: lo stesso sub-motore ha direzioni
    # contraddittorie nella stessa settimana?
    week_sm_dir = defaultdict(lambda: defaultdict(Counter))
    for _, r in df.iterrows():
        if not r['week'] or not r['suggested_adjustment']:
            continue
        submotori = extract_submotori_from_text(r['suggested_adjustment'])
        dir_ = direction_of(r['suggested_adjustment'])
        for sm in submotori:
            week_sm_dir[r['week']][sm][dir_] += 1
    coh_rows = []
    for w in sorted(week_sm_dir.keys()):
        for sm, dirs in week_sm_dir[w].items():
            total = sum(dirs.values())
            if total < 2:
                continue
            aum = dirs.get('aumenta', 0)
            rid = dirs.get('riduci', 0)
            if aum > 0 and rid > 0:
                coh_rows.append({
                    'week': w, 'sub_motore': sm, 'total': total,
                    'aumenta': aum, 'riduci': rid,
                    'contraddittorio': True,
                })
    pd.DataFrame(coh_rows).to_csv(HERE / 'contraddizioni_settimanali.csv', index=False, encoding='utf-8-sig')

    # === Analisi 3: 5 suggested_adjustment più specifici ===
    # "Specificità" = contiene un numero e un nome sub-motore
    def specificity(txt):
        if not txt:
            return 0
        score = 0
        if extract_submotori_from_text(txt):
            score += 1
        if re.search(r'\d+\.?\d*', txt):
            score += 1
        if 'quando' in txt.lower() or 'se' in txt.lower().split():
            score += 1  # condizionale
        return score + len(extract_submotori_from_text(txt)) * 0.5

    df['spec_score'] = df['suggested_adjustment'].apply(specificity)
    top5 = df.nlargest(5, 'spec_score')[[
        'created_at', 'home', 'away', 'tipo', 'pronostico',
        'suggested_adjustment', 'spec_score']]
    top5.to_csv(HERE / 'top5_suggerimenti_specifici.csv', index=False, encoding='utf-8-sig')

    # === Statistiche aggregate ===
    stats = {
        'totale_docs': len(df),
        'finestra_date': f"{df['created_at'].min()} → {df['created_at'].max()}",
        'con_variables_impact': int(df['vi_form'].notna().sum()),
        'con_root_cause': int(df['root_cause'].notna().sum()),
        'con_ai_analysis': int(df['ai_analysis'].notna().sum()),
        'con_suggested_adjustment': int(df['suggested_adjustment'].notna().sum()),
        'con_pattern_tags': int((df['pattern_tags'] != '').sum()),
        'severity_high': int((df['severity'] == 'high').sum()),
        'severity_medium': int((df['severity'] == 'medium').sum()),
        'severity_low': int((df['severity'] == 'low').sum()),
        'severity_null': int(df['severity'].isna().sum()),
    }
    # Media dei variables_impact (quali sono dominanti globalmente?)
    vi_cols = [c for c in df.columns if c.startswith('vi_')]
    for c in vi_cols:
        stats[f'{c}_mean'] = round(df[c].mean(skipna=True), 3) if df[c].notna().any() else None

    with open(HERE / 'stats_globali.json', 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, default=str, ensure_ascii=False)

    print('Output generati:')
    print('  campione_30.csv')
    print('  root_cause_per_settimana.csv')
    print('  pattern_tags_per_settimana.csv')
    print('  severity_per_settimana.csv')
    print('  submotori_suggeriti.csv')
    print('  contraddizioni_settimanali.csv')
    print('  top5_suggerimenti_specifici.csv')
    print('  stats_globali.json')

    return df, sm_rows, coh_rows, stats, sev_rows, tag_rows


if __name__ == '__main__':
    df, sm_rows, coh_rows, stats, sev_rows, tag_rows = main()
    # piccolo riepilogo a schermo
    print()
    print('=== STATS GLOBALI ===')
    for k, v in stats.items():
        print(f'  {k}: {v}')
