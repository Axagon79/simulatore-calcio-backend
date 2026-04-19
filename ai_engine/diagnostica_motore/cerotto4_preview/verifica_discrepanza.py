"""Verifica discrepanza P/L AR frontend vs mio calcolo.

Replica esatta della logica in `popola_pl_storico.py::calcola_pl_giorno`
(sorgente di verità per il frontend) e la confronta con la mia query
del Cerotto 4 preview (dataset dedupato).
"""
from __future__ import annotations

import importlib.util
import re
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND_ROOT = HERE.parent.parent.parent


def load_db():
    spec = importlib.util.spec_from_file_location('backend_config', BACKEND_ROOT / 'config.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.db


DATE_FROM = '2026-02-19'
DATE_TO = '2026-04-18'


def main():
    db = load_db()
    print(f'Finestra: {DATE_FROM} -> {DATE_TO}\n')

    # === Metodo 1: Replica fedele di popola_pl_storico.py ===
    # Non dedupa. Scatole non esclusive. PL pesato per stake. RE conta in AR.
    sez_frontend = {
        'tutti': {'pl': 0, 'bets': 0, 'wins': 0, 'staked': 0},
        'pronostici': {'pl': 0, 'bets': 0, 'wins': 0, 'staked': 0},
        'elite': {'pl': 0, 'bets': 0, 'wins': 0, 'staked': 0},
        'alto_rendimento': {'pl': 0, 'bets': 0, 'wins': 0, 'staked': 0},
    }

    # Carico direttamente da pl_storico se esiste (più fedele: è la tabella
    # che il frontend legge davvero, con eventuali valori void/finalizzati già
    # gestiti dal backend).
    q = {'date': {'$gte': DATE_FROM, '$lte': DATE_TO}}
    giorni = list(db.pl_storico.find(q, {'_id': 0}))
    print(f'Giorni in pl_storico (finestra): {len(giorni)}')

    for g in giorni:
        for key in ('tutti', 'pronostici', 'elite', 'alto_rendimento'):
            s = g.get(key) or {}
            sez_frontend[key]['pl'] += s.get('pl', 0) or 0
            sez_frontend[key]['bets'] += s.get('bets', 0) or 0
            sez_frontend[key]['wins'] += s.get('wins', 0) or 0
            sez_frontend[key]['staked'] += s.get('staked', 0) or 0

    for s in sez_frontend.values():
        s['pl'] = round(s['pl'], 2)
        s['staked'] = round(s['staked'], 2)
        s['hr'] = round((s['wins'] / s['bets']) * 100, 1) if s['bets'] > 0 else 0
        s['roi_yield'] = round((s['pl'] / s['staked']) * 100, 1) if s['staked'] > 0 else 0

    print('\n=== METODO FRONTEND (pl_storico, identica logica popola_pl_storico.py) ===')
    for key, s in sez_frontend.items():
        print(f'  {key}: bets={s["bets"]}, wins={s["wins"]}, HR={s["hr"]}%, '
              f'PL={s["pl"]:+.2f}u, staked={s["staked"]}u, YIELD={s["roi_yield"]:+.1f}%')

    # === Metodo 2: Mia query del Cerotto 4 (dedup + stake=1u + scatole esclusive) ===
    print('\n=== METODO MIO (dedup + a 1u + scatole esclusive) ===')
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
                'scatola': scatola,
                'esito': bool(p.get('esito')),
                'pl_1u': (quota - 1) if p.get('esito') else -1.0,
            }
            prev = rows_by_key.get(key)
            if prev is None or SCATOLA_ORDER[scatola] < SCATOLA_ORDER[prev['scatola']]:
                rows_by_key[key] = row

    from collections import Counter
    scat_totals = {'MIXER': {'n': 0, 'w': 0, 'pl': 0},
                   'ELITE': {'n': 0, 'w': 0, 'pl': 0},
                   'ALTO_RENDIMENTO': {'n': 0, 'w': 0, 'pl': 0},
                   'PRONOSTICI': {'n': 0, 'w': 0, 'pl': 0}}
    for r in rows_by_key.values():
        s = r['scatola']
        scat_totals[s]['n'] += 1
        if r['esito']:
            scat_totals[s]['w'] += 1
        scat_totals[s]['pl'] += r['pl_1u']
    print(f'  Dataset dedupato: {len(rows_by_key)} righe')
    for s, v in scat_totals.items():
        hr = (v['w'] / v['n'] * 100) if v['n'] > 0 else 0
        roi = (v['pl'] / v['n'] * 100) if v['n'] > 0 else 0
        print(f'  {s}: N={v["n"]}, HR={hr:.2f}%, PL_a_1u={v["pl"]:+.2f}u, ROI/unit={roi:+.2f}%')

    # === Metodo 3: Replica logica backend MA su dataset dedupato (per isolare
    # l'effetto "dedup" dall'effetto "stake pesato") ===
    print('\n=== METODO 3: stake pesato ma su dataset dedupato ===')
    print('  (per isolare l\'effetto dedup dall\'effetto stake)')
    # Ricarico con campo stake incluso
    deduped_stake = {}
    for doc in db['daily_predictions_unified'].find(q):
        odds = doc.get('odds') or {}
        home = doc.get('home'); away = doc.get('away'); date_s = doc.get('date')
        for p in doc.get('pronostici') or []:
            if p.get('tipo') not in ('SEGNO', 'DOPPIA_CHANCE', 'GOL'): continue
            if p.get('pronostico') == 'NO BET': continue
            quota = get_q(p, odds)
            if quota is None: continue
            if p.get('esito') is None: continue
            stake = p.get('stake') or 1
            pl_real = p.get('profit_loss')
            if pl_real is None:
                pl_real = (quota - 1) * stake if p.get('esito') else -stake
            soglia = 2.00 if p['tipo'] == 'DOPPIA_CHANCE' else 2.51
            is_alta = quota >= soglia
            if p.get('mixer') is True: scatola = 'MIXER'
            elif p.get('elite') is True: scatola = 'ELITE'
            elif is_alta: scatola = 'ALTO_RENDIMENTO'
            else: scatola = 'PRONOSTICI'
            key = (date_s, home, away, p['tipo'], p['pronostico'])
            row = {
                'scatola': scatola,
                'esito': bool(p.get('esito')),
                'pl_weighted': pl_real,
                'stake': stake,
            }
            prev = deduped_stake.get(key)
            if prev is None or SCATOLA_ORDER[scatola] < SCATOLA_ORDER[prev['scatola']]:
                deduped_stake[key] = row

    scat3 = {'MIXER': {'n': 0, 'w': 0, 'pl': 0, 'staked': 0},
             'ELITE': {'n': 0, 'w': 0, 'pl': 0, 'staked': 0},
             'ALTO_RENDIMENTO': {'n': 0, 'w': 0, 'pl': 0, 'staked': 0},
             'PRONOSTICI': {'n': 0, 'w': 0, 'pl': 0, 'staked': 0}}
    for r in deduped_stake.values():
        s = r['scatola']
        scat3[s]['n'] += 1
        scat3[s]['pl'] += r['pl_weighted']
        scat3[s]['staked'] += r['stake']
        if r['esito']:
            scat3[s]['w'] += 1
    for s, v in scat3.items():
        hr = (v['w'] / v['n'] * 100) if v['n'] > 0 else 0
        roi = (v['pl'] / v['staked'] * 100) if v['staked'] > 0 else 0
        print(f'  {s}: N={v["n"]}, HR={hr:.2f}%, PL_pesato={v["pl"]:+.2f}u, '
              f'staked={v["staked"]:.0f}u, YIELD={roi:+.1f}%')

    # Export risultati in dict per report
    return sez_frontend, scat_totals, scat3, len(rows_by_key)


if __name__ == '__main__':
    main()
