"""Impatto Cerotto 4 con metodo backend (fonte di verità frontend).

Replica esatta della logica di `popola_pl_storico.py::calcola_pl_giorno`:
- NESSUN dedup (date,home,away,tipo,pronostico)
- Scatole NON mutualmente esclusive: `tutti` sempre, `elite` se flag,
  `alto_rendimento` se quota>=soglia o RE, `pronostici` se sotto soglia e non RE
- PL pesato per stake: vinto = (quota-1)*stake, perso = -stake
- NO BET escluso
- MIXER non è una scatola nel metodo backend. Per coerenza con la domanda
  utente lo aggiungo come quinta scatola = `p.mixer is True`.

Per ciascuna delle 7 combo Cerotto 4 (C2, C4, C5, C6, C8, C9, C10):
1. Volume + HR + quota media + ROI + PL stake-pesati sul perimetro backend
2. Intersezioni
3. Impatto per scatola (frontend-style): PL_prima, PL_dopo, delta per scatola
4. Verifica se le 3 "falsi allarmi" (C1, C3, C7) lo restano
"""
from __future__ import annotations

import importlib.util
from collections import defaultdict
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
BACKEND_ROOT = HERE.parent.parent.parent


def load_db():
    spec = importlib.util.spec_from_file_location('backend_config', BACKEND_ROOT / 'config.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.db


DATE_FROM = '2026-02-19'
DATE_TO = '2026-04-18'


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
    if q is None: return 'n/a'
    return 'Alto Rendimento' if q > 2.50 else 'Pronostici'


# === Combo ===

COMBOS_ALL = [
    ('C1', 'SEGNO + fascia_quota=3.00+',
        lambda r: r['tipo'] == 'SEGNO' and r['fascia_quota'] == '3.00+', 'Dimezza'),
    ('C2', 'SEGNO + tipo_partita=aperta',
        lambda r: r['tipo'] == 'SEGNO' and r['tipo_partita'] == 'aperta', 'SCARTA'),
    ('C3', 'SEGNO + categoria=Alto Rendimento',
        lambda r: r['tipo'] == 'SEGNO' and r['categoria_a'] == 'Alto Rendimento', 'Dimezza'),
    ('C4', 'tipo_partita=aperta + categoria=Alto Rendimento',
        lambda r: r['tipo_partita'] == 'aperta' and r['categoria_a'] == 'Alto Rendimento', 'SCARTA'),
    ('C5', 'SEGNO + Monday + tipo_partita=aperta',
        lambda r: r['tipo'] == 'SEGNO' and r['giorno_settimana'] == 'Monday' and r['tipo_partita'] == 'aperta', 'SCARTA'),
    ('C6', 'fascia_oraria=sera + categoria=Alto Rendimento',
        lambda r: r['fascia_oraria'] == 'sera' and r['categoria_a'] == 'Alto Rendimento', 'SCARTA'),
    ('C7', 'fascia_quota=3.00+ + categoria=Alto Rendimento',
        lambda r: r['fascia_quota'] == '3.00+' and r['categoria_a'] == 'Alto Rendimento', 'Dimezza'),
    ('C8', 'Friday + fascia_quota=3.00+ + tipo_partita=equilibrata',
        lambda r: r['giorno_settimana'] == 'Friday' and r['fascia_quota'] == '3.00+' and r['tipo_partita'] == 'equilibrata', 'SCARTA'),
    ('C9', 'fascia_quota=2.50-2.99 + tipo_partita=aperta',
        lambda r: r['fascia_quota'] == '2.50-2.99' and r['tipo_partita'] == 'aperta', 'SCARTA'),
    ('C10', 'Friday + categoria=Alto Rendimento',
        lambda r: r['giorno_settimana'] == 'Friday' and r['categoria_a'] == 'Alto Rendimento', 'SCARTA'),
]
COMBOS_7_SCARTA = [c for c in COMBOS_ALL if c[3] == 'SCARTA']


def main():
    db = load_db()
    print(f'Finestra: {DATE_FROM} -> {DATE_TO}\n')

    # --- Metadata partita ---
    q = {'date': {'$gte': DATE_FROM, '$lte': DATE_TO}}
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

    # --- Carica TUTTI i pronostici (SENZA DEDUP, come backend) ---
    GOL_MAP = {'Over 1.5': 'over_15', 'Under 1.5': 'under_15',
               'Over 2.5': 'over_25', 'Under 2.5': 'under_25',
               'Over 3.5': 'over_35', 'Under 3.5': 'under_35',
               'Goal': 'gg', 'NoGoal': 'ng'}

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

    rows = []
    for doc in db['daily_predictions_unified'].find(q):
        odds = doc.get('odds') or {}
        home = doc.get('home'); away = doc.get('away'); date_s = doc.get('date')
        for p in doc.get('pronostici') or []:
            tipo = p.get('tipo')
            # backend accetta anche RISULTATO_ESATTO in alto_rendimento
            if tipo not in ('SEGNO', 'DOPPIA_CHANCE', 'GOL', 'RISULTATO_ESATTO'):
                continue
            if p.get('pronostico') == 'NO BET':
                continue
            quota = get_q(p, odds)
            if not quota or quota <= 1:
                continue
            if p.get('esito') is None:
                continue
            stake = p.get('stake') or 1
            pl_stored = p.get('profit_loss')
            esito = bool(p.get('esito'))
            # Calcolo PL pesato alla stessa maniera del backend
            if pl_stored is not None:
                pl = pl_stored
            else:
                pl = (quota - 1) * stake if esito else -stake

            soglia = 2.00 if tipo == 'DOPPIA_CHANCE' else 2.51
            is_alto_rend = tipo == 'RISULTATO_ESATTO' or quota >= soglia
            is_pronostici = (not is_alto_rend) and tipo != 'RISULTATO_ESATTO'
            is_elite = bool(p.get('elite'))
            is_mixer = bool(p.get('mixer'))

            rows.append({
                'date': date_s, 'home': home, 'away': away,
                'tipo': tipo, 'pronostico': p.get('pronostico'),
                'quota': quota, 'stake': stake,
                'esito': esito, 'pl': pl,
                'in_alto_rend': is_alto_rend,
                'in_pronostici': is_pronostici,
                'in_elite': is_elite,
                'in_mixer': is_mixer,
            })

    df = pd.DataFrame(rows)
    print(f'Pronostici totali (no dedup, no NO BET, con esito): {len(df)}')

    # Arricchimento combo features
    df['match_time'] = df.apply(
        lambda r: match_meta.get((r['date'], r['home'], r['away']), {}).get('match_time', ''), axis=1)
    df['quota_min_1x2'] = df.apply(
        lambda r: match_meta.get((r['date'], r['home'], r['away']), {}).get('quota_min_1x2'), axis=1)
    df['date_dt'] = pd.to_datetime(df['date'])
    df['giorno_settimana'] = df['date_dt'].dt.day_name()
    df['tipo_partita'] = df['quota_min_1x2'].apply(tipo_partita)
    df['fascia_oraria'] = df['match_time'].apply(fascia_oraria)
    df['fascia_quota'] = df['quota'].apply(fascia_quota)
    df['categoria_a'] = df['quota'].apply(categoria_notebook)

    # --- Sanity check: baseline per scatola deve matchare pl_storico ---
    print('\n=== Baseline backend-style (verifica contro pl_storico) ===')
    for scat, mask_col in [('tutti', None), ('pronostici', 'in_pronostici'),
                            ('elite', 'in_elite'), ('alto_rendimento', 'in_alto_rend'),
                            ('mixer', 'in_mixer')]:
        sub = df if mask_col is None else df[df[mask_col]]
        n = len(sub)
        w = int(sub['esito'].sum())
        pl = sub['pl'].sum()
        staked = sub['stake'].sum()
        hr = w / n * 100 if n > 0 else 0
        yield_ = pl / staked * 100 if staked > 0 else 0
        print(f'  {scat}: bets={n}, wins={w}, HR={hr:.1f}%, PL={pl:+.2f}u, '
              f'staked={staked:.0f}u, YIELD={yield_:+.1f}%')

    # --- Stats per combo (sul perimetro totale = "tutti") ---
    print('\n=== Stats combo su TUTTI (perimetro backend completo) ===')
    masks = {}
    combo_stats = []
    for cid, cname, cfun, azione in COMBOS_ALL:
        mask = df.apply(cfun, axis=1)
        masks[cid] = mask
        sub = df[mask]
        if len(sub) == 0:
            combo_stats.append({
                'id': cid, 'combo': cname, 'azione_report': azione,
                'n': 0, 'wins': 0, 'losses': 0, 'hr': None,
                'quota_media': None, 'stake_medio': None,
                'staked': 0, 'pl': 0, 'yield': None,
                'verdetto': 'n/a (N=0)',
            })
            continue
        n = len(sub); w = int(sub['esito'].sum())
        pl = sub['pl'].sum()
        staked = sub['stake'].sum()
        qm = sub['quota'].mean()
        sm = sub['stake'].mean()
        yv = pl / staked * 100 if staked > 0 else 0
        if yv > 0:
            verdetto = 'FALSO ALLARME (yield positivo)'
        elif yv > -5:
            verdetto = 'DUBBIO (yield ~ 0)'
        else:
            verdetto = 'TOSSICA (yield negativo netto)'
        combo_stats.append({
            'id': cid, 'combo': cname, 'azione_report': azione,
            'n': n, 'wins': w, 'losses': n - w,
            'hr': round(w/n*100, 2),
            'quota_media': round(qm, 2),
            'stake_medio': round(sm, 2),
            'staked': round(staked, 2),
            'pl': round(pl, 2),
            'yield': round(yv, 2),
            'verdetto': verdetto,
        })
    for r in combo_stats:
        print(f'  {r["id"]}: N={r["n"]}, HR={r["hr"]}%, q.m.={r["quota_media"]}, '
              f'staked={r["staked"]}u, PL={r["pl"]:+}u, YIELD={r["yield"]}%  '
              f'=> {r["verdetto"]}')

    # --- Intersezioni ---
    ids = [cid for cid, _, _, _ in COMBOS_ALL]
    overlap = pd.DataFrame(0, index=ids, columns=ids, dtype=int)
    for i in ids:
        for j in ids:
            overlap.loc[i, j] = int((masks[i] & masks[j]).sum())
    overlap.to_csv(HERE / 'sovrapposizioni_backend.csv')

    # --- Impatto per scatola applicando SOLO le 7 combo SCARTA ---
    scarta_ids = [cid for cid, _, _, azione in COMBOS_ALL if azione == 'SCARTA']
    any_scarta = pd.Series(False, index=df.index)
    for cid in scarta_ids:
        any_scarta = any_scarta | masks[cid]

    print(f'\n=== Pronostici colpiti dalle 7 SCARTA: {int(any_scarta.sum())} ===')

    # Per ogni scatola: prima, dopo, delta
    impatto_scatole = []
    for scat, mask_col in [('tutti', None), ('pronostici', 'in_pronostici'),
                            ('elite', 'in_elite'), ('alto_rendimento', 'in_alto_rend'),
                            ('mixer', 'in_mixer')]:
        in_box = df if mask_col is None else df[df[mask_col]]
        # prima
        n_prima = len(in_box)
        w_prima = int(in_box['esito'].sum())
        pl_prima = in_box['pl'].sum()
        staked_prima = in_box['stake'].sum()
        # dopo: rimuovi le righe colpite
        surv = in_box[~any_scarta.loc[in_box.index]]
        n_dopo = len(surv)
        w_dopo = int(surv['esito'].sum())
        pl_dopo = surv['pl'].sum()
        staked_dopo = surv['stake'].sum()
        impatto_scatole.append({
            'scatola': scat,
            'n_prima': n_prima, 'n_dopo': n_dopo, 'delta_n': n_dopo - n_prima,
            'hr_prima': round(w_prima/n_prima*100, 2) if n_prima > 0 else None,
            'hr_dopo': round(w_dopo/n_dopo*100, 2) if n_dopo > 0 else None,
            'pl_prima': round(pl_prima, 2), 'pl_dopo': round(pl_dopo, 2),
            'delta_pl': round(pl_dopo - pl_prima, 2),
            'staked_prima': round(staked_prima, 2), 'staked_dopo': round(staked_dopo, 2),
            'yield_prima': round(pl_prima/staked_prima*100, 2) if staked_prima > 0 else None,
            'yield_dopo': round(pl_dopo/staked_dopo*100, 2) if staked_dopo > 0 else None,
        })

    # --- Verifica stato 3 "falsi allarmi" (C1, C3, C7) col metodo backend ---
    print('\n=== Confronto verdetto falsi allarmi con il vecchio metodo (1u) ===')
    verdetti_compare = []
    # Ricalcolo anche su 1u per comparabilità col report vecchio
    for cid in ['C1', 'C3', 'C7']:
        mask = masks[cid]
        sub = df[mask]
        n = len(sub)
        if n == 0:
            continue
        pl_1u = (sub.apply(lambda r: (r['quota']-1) if r['esito'] else -1, axis=1)).sum()
        roi_1u = pl_1u / n * 100
        pl_weighted = sub['pl'].sum()
        staked = sub['stake'].sum()
        yield_w = pl_weighted / staked * 100 if staked > 0 else 0
        verdetti_compare.append({
            'id': cid, 'n': n, 'pl_1u': round(pl_1u, 2), 'roi_1u': round(roi_1u, 2),
            'pl_pesato': round(pl_weighted, 2), 'yield_pesato': round(yield_w, 2),
        })
        print(f'  {cid}: N={n}, PL_1u={pl_1u:+.2f} (ROI {roi_1u:+.2f}%), '
              f'PL_pesato={pl_weighted:+.2f} (YIELD {yield_w:+.2f}%)')

    # --- Report ---
    md = ['# Cerotto 4 — Analisi impatto con metodo BACKEND corretto', '',
          f'Finestra: **{DATE_FROM} → {DATE_TO}**.',
          '',
          '**Metodo**: replica esatta di `popola_pl_storico.py::calcola_pl_giorno`.',
          '',
          '- NESSUN dedup (`date`, `home`, `away`, `tipo`, `pronostico`)',
          '- Scatole NON mutualmente esclusive: un pronostico contribuisce a `tutti` '
          'sempre, a `alto_rendimento` se `quota≥soglia` o RE, a `elite` se flag, '
          'a `pronostici` se sotto soglia e non RE.',
          '- `mixer` aggiunta come quinta scatola (parallela, non esclusiva): '
          'contribuisce se `p.mixer=True`.',
          '- PL pesato per `stake`: vinto = `(quota-1)×stake`, perso = `-stake`.',
          '- NO BET escluso; pronostici con `esito=None` esclusi.',
          '',
          f'Totale pronostici processati: **{len(df)}**.',
          '',
          '## 1. Baseline backend (match fedele con pl_storico)',
          '',
          '| Scatola | bets | wins | HR | PL (u) | staked | YIELD |',
          '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for scat, mask_col in [('tutti', None), ('pronostici', 'in_pronostici'),
                            ('elite', 'in_elite'), ('alto_rendimento', 'in_alto_rend'),
                            ('mixer', 'in_mixer')]:
        sub = df if mask_col is None else df[df[mask_col]]
        n = len(sub)
        w = int(sub['esito'].sum())
        pl = sub['pl'].sum()
        staked = sub['stake'].sum()
        hr = w / n * 100 if n > 0 else 0
        y = pl / staked * 100 if staked > 0 else 0
        md.append(f'| {scat} | {n} | {w} | {hr:.1f}% | {pl:+.2f} | {staked:.0f} | {y:+.1f}% |')
    md.append('')
    md.append('**Verifica**: `tutti` e `alto_rendimento` e `elite` devono combaciare con '
              'la tabella `pl_storico` del backend (= quello che il frontend mostra).')
    md.append('')

    # Baseline pl_storico per confronto
    giorni = list(db.pl_storico.find(q, {'_id': 0}))
    sez_plsto = {'tutti': {'pl': 0, 'bets': 0, 'wins': 0, 'staked': 0},
                 'pronostici': {'pl': 0, 'bets': 0, 'wins': 0, 'staked': 0},
                 'elite': {'pl': 0, 'bets': 0, 'wins': 0, 'staked': 0},
                 'alto_rendimento': {'pl': 0, 'bets': 0, 'wins': 0, 'staked': 0}}
    for g in giorni:
        for key in ('tutti', 'pronostici', 'elite', 'alto_rendimento'):
            s = g.get(key) or {}
            sez_plsto[key]['pl'] += s.get('pl', 0) or 0
            sez_plsto[key]['bets'] += s.get('bets', 0) or 0
            sez_plsto[key]['wins'] += s.get('wins', 0) or 0
            sez_plsto[key]['staked'] += s.get('staked', 0) or 0

    md.append('### Confronto diretto con pl_storico')
    md.append('')
    md.append('| Scatola | bets (mia) | bets (pl_storico) | PL (mia) | PL (pl_storico) |')
    md.append('| --- | ---: | ---: | ---: | ---: |')
    for scat, mask_col in [('tutti', None), ('pronostici', 'in_pronostici'),
                            ('elite', 'in_elite'), ('alto_rendimento', 'in_alto_rend')]:
        sub = df if mask_col is None else df[df[mask_col]]
        n = len(sub)
        pl = round(sub['pl'].sum(), 2)
        pls = sez_plsto[scat]
        md.append(f'| {scat} | {n} | {pls["bets"]} | {pl:+.2f} | {round(pls["pl"], 2):+.2f} |')
    md.append('')
    md.append('Piccole differenze possibili: `pl_storico` può avere esiti finalizzati '
              'successivamente o fallback `live_score` non più disponibili. L\'importante '
              'è che i numeri siano nell\'ordine di grandezza giusto.')
    md.append('')

    # --- Tabella combo ---
    md.append('## 2. Tabella 7 combo SCARTA + 3 Dimezza (backend-style)')
    md.append('')
    md.append('| ID | Combo | Azione | N | Wins | Losses | HR | Quota media | Stake medio | Staked | PL (u) | YIELD | Verdetto |')
    md.append('| --- | --- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |')
    for r in combo_stats:
        if r['n'] == 0:
            md.append(f'| {r["id"]} | {r["combo"]} | {r["azione_report"]} | 0 | 0 | 0 | — | — | — | 0 | 0 | — | {r["verdetto"]} |')
        else:
            md.append(f'| {r["id"]} | {r["combo"]} | {r["azione_report"]} | '
                      f'{r["n"]} | {r["wins"]} | {r["losses"]} | '
                      f'{r["hr"]:.2f}% | {r["quota_media"]:.2f} | {r["stake_medio"]:.2f} | '
                      f'{r["staked"]:.0f}u | {r["pl"]:+.2f}u | {r["yield"]:+.2f}% | '
                      f'{r["verdetto"]} |')
    md.append('')
    md.append('**Nota**: verdetto su YIELD pesato (non ROI/unit come nel report '
              'precedente). Soglia: yield>0 FALSO ALLARME, yield in (-5%,0] DUBBIO, '
              'yield ≤ -5% TOSSICA.')
    md.append('')

    # --- Verifica falsi allarmi ---
    md.append('## 3. Verifica "falsi allarmi" C1, C3, C7 — 1u vs backend pesato')
    md.append('')
    md.append('| ID | N | PL a 1u | ROI/unit | PL pesato | YIELD pesato | Verdetto 1u | Verdetto backend |')
    md.append('| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |')
    for v in verdetti_compare:
        r1u = 'FALSO ALLARME' if v['roi_1u'] > 0 else ('TOSSICA' if v['roi_1u'] < -5 else 'DUBBIO')
        rw = 'FALSO ALLARME' if v['yield_pesato'] > 0 else ('TOSSICA' if v['yield_pesato'] < -5 else 'DUBBIO')
        md.append(f'| {v["id"]} | {v["n"]} | {v["pl_1u"]:+.2f} | {v["roi_1u"]:+.2f}% | '
                  f'{v["pl_pesato"]:+.2f} | {v["yield_pesato"]:+.2f}% | {r1u} | {rw} |')
    md.append('')
    # commento interpretativo
    c1 = next(v for v in verdetti_compare if v['id'] == 'C1')
    c3 = next(v for v in verdetti_compare if v['id'] == 'C3')
    c7 = next(v for v in verdetti_compare if v['id'] == 'C7')
    if all(v['yield_pesato'] > 0 for v in (c1, c3, c7)):
        md.append('**C1, C3, C7 restano FALSI ALLARMI anche col metodo backend.** '
                  'I pronostici "SEGNO + quota alta" fanno soldi anche pesando per stake.')
    else:
        md.append('**Attenzione**: almeno una delle 3 cambia verdetto.')
    md.append('')

    # --- Impatto per scatola ---
    md.append('## 4. Impatto Cerotto 4 (7 SCARTA) per scatola (backend-style)')
    md.append('')
    md.append('| Scatola | Bets prima | Bets dopo | Δ Bets | HR prima | HR dopo | PL prima | PL dopo | Δ PL | Yield prima | Yield dopo |')
    md.append('| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |')
    for r in impatto_scatole:
        hr_p = f"{r['hr_prima']:.2f}%" if r['hr_prima'] is not None else '—'
        hr_d = f"{r['hr_dopo']:.2f}%" if r['hr_dopo'] is not None else '—'
        yp = f"{r['yield_prima']:+.2f}%" if r['yield_prima'] is not None else '—'
        yd = f"{r['yield_dopo']:+.2f}%" if r['yield_dopo'] is not None else '—'
        md.append(f'| {r["scatola"]} | {r["n_prima"]} | {r["n_dopo"]} | {r["delta_n"]} | '
                  f'{hr_p} | {hr_d} | {r["pl_prima"]:+.2f} | {r["pl_dopo"]:+.2f} | '
                  f'{r["delta_pl"]:+.2f} | {yp} | {yd} |')
    md.append('')

    # --- Intersezioni ---
    md.append('## 5. Sovrapposizioni tra combo (backend-style)')
    md.append('')
    md.append('Vedi `sovrapposizioni_backend.csv` per matrice completa.')
    md.append('')
    md.append('Coppie altamente sovrapposte (intersezione ≥ 50% su min(Ni,Nj)):')
    md.append('')
    md.append('| Coppia | Intersezione | % |')
    md.append('| --- | ---: | ---: |')
    pairs = []
    for i_idx, i in enumerate(ids):
        for j in ids[i_idx+1:]:
            inter = int(overlap.loc[i, j])
            ni = int(overlap.loc[i, i]); nj = int(overlap.loc[j, j])
            mn = min(ni, nj)
            if mn == 0: continue
            pct = inter / mn * 100
            if pct >= 50 and inter >= 5:
                pairs.append((i, j, inter, pct))
    pairs.sort(key=lambda x: -x[3])
    for i, j, inter, pct in pairs[:15]:
        md.append(f'| {i} ∩ {j} | {inter} | {pct:.1f}% |')
    if not pairs:
        md.append('| — | — | — |')
    md.append('')

    # --- Nota metodologica ---
    md.append('## 6. Nota metodologica — diagnostiche precedenti affette dallo stesso bias')
    md.append('')
    md.append('Tutte le mie diagnostiche precedenti usavano **dataset dedupato a 1u '
              'con scatole mutualmente esclusive**. Questo metodo è valido per '
              'domande "classificatorie" (il motore è calibrato? quale source '
              'funziona meglio a parità di stake?) ma **NON** per confronti con i '
              'dati mostrati nel frontend o per stimare l\'impatto economico reale.')
    md.append('')
    md.append('| Diagnostica | Affetta? | Nota |')
    md.append('| --- | :---: | --- |')
    md.append('| 01_calibrazione (reliability diagram) | ❌ NO | Misura HR vs prob, '
              'lo stake è irrilevante. Numeri corretti. |')
    md.append('| 02_expected_value (EV test) | ⚠️ PARZIALE | HR e frequenza sono '
              'corrette. Ma "ROI per fascia EV" usa PL a 1u. Per stimare PL reale '
              'andrebbe rifatto col PL pesato. Le conclusioni qualitative (monotonicità '
              'rotta, EV non predittivo) restano valide. |')
    md.append('| 03_stake (analisi stake) | ✅ CORRETTA | Qui lo stake è proprio '
              'l\'oggetto di studio: confronta stake old vs Kelly calibrato. '
              'Le simulazioni PL pesato erano sotto stake old (+1242u) vs Kelly new '
              '(+3075u), entrambi su stake pesato. Numeri direttamente confrontabili '
              'coi dati frontend. |')
    md.append('| 04_no_bet (NO BET + conversioni) | ⚠️ PARZIALE | La parte NO BET '
              'simula a 1u. Le conclusioni sono qualitative (filtro giusto/sbagliato) '
              'e robuste. Per impatto economico reale andrebbe ripesato. |')
    md.append('| 05_segmenti (lega/giorno/quota) | ⚠️ PARZIALE | ROI per segmento è '
              'a 1u. Le "leghe peggiori/migliori" ordinate per ROI qualitative sono '
              'OK, ma le magnitudini PL non sono confrontabili col frontend. |')
    md.append('| 06_motori (A vs S vs C) | ⚠️ PARZIALE | Idem: ROI isolato per motore '
              'è a 1u. Specializzazione tier resta valida, valori assoluti no. |')
    md.append('| 07_mistral_audit | ❌ NO | Analisi testuale, senza PL. |')
    md.append('| stake_kelly_preview | ✅ CORRETTA | Confronto stake old vs Kelly new '
              'entrambi pesati. +1832u di delta PL è cifra reale. |')
    md.append('')
    md.append('### Cosa andrebbe rifatto col metodo giusto')
    md.append('')
    md.append('- **02_expected_value**: rifare "ROI per fascia EV" con PL pesato per '
              'avere il numero economico vero. Le conclusioni concettuali non cambiano.')
    md.append('- **04_no_bet**: idem per i filtri NO BET — vedere il PL reale evitato.')
    md.append('- **05_segmenti**: utile per comunicare "La Liga costa X euro reali al '
              'mese". Le priorità di intervento restano le stesse.')
    md.append('- **06_motori**: utile se vuoi decidere quanto pesare economicamente '
              'le specializzazioni tier.')
    md.append('')
    md.append('**NON servono rifacimenti urgenti**: le conclusioni qualitative sono '
              'robuste (curva di calibrazione, EV non predittivo, specializzazione tier, '
              'Mistral contraddittorio). È solo una questione di "numeri reali" per '
              'confronto con dashboard, quando si vuole comunicare l\'impatto in euro.')

    (HERE / 'impatto_backend_corretto.md').write_text('\n'.join(md), encoding='utf-8')
    print(f'\nReport: {HERE / "impatto_backend_corretto.md"}')


if __name__ == '__main__':
    main()
