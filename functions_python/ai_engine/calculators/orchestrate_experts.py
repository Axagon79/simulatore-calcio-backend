"""
MIXTURE OF EXPERTS — Orchestratore
===================================
Legge pronostici dai 3 sistemi (A, C, S), applica routing per mercato,
scrive in daily_predictions_unified.

Ogni sistema è "esperto" solo nei mercati dove ha il miglior HR.
L'orchestratore NON calcola nulla — seleziona e combina.

Uso:
  python orchestrate_experts.py                    # oggi
  python orchestrate_experts.py 2026-02-18         # data specifica
  python orchestrate_experts.py --backfill 2026-02-11 2026-02-19  # range
"""

import sys
import os
import argparse
from datetime import datetime, timedelta, timezone
from copy import deepcopy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import db

# =====================================================
# CONFIGURAZIONE ROUTING
# =====================================================
COLLECTIONS = {
    'A': 'daily_predictions',
    'C': 'daily_predictions_engine_c',
    'S': 'daily_predictions_sandbox',
}

# Tabella routing definitiva (validata con analisi overlap 11-18 feb)
ROUTING = {
    '1X2':       {'systems': ['C'], 'rule': 'single'},
    'DC':        {'systems': ['A', 'S'], 'rule': 'consensus_both'},
    'OVER_1.5':  {'systems': ['A', 'S'], 'rule': 'consensus_both'},
    'OVER_2.5':  {'systems': ['A', 'S'], 'rule': 'consensus_both'},
    'OVER_3.5':  {'systems': ['C'], 'rule': 'single'},
    'UNDER_2.5': {'systems': ['A'], 'rule': 'single'},
    'UNDER_3.5': {'systems': ['A', 'S'], 'rule': 'union'},
    'GG':        {'systems': ['S', 'C'], 'rule': 'priority_chain'},
    'NG':        {'systems': ['A', 'C', 'S'], 'rule': 'combo_under_segno'},
}

# Campi da copiare dal documento sorgente (livello match)
MATCH_FIELDS = [
    'home', 'away', 'date', 'league', 'match_time',
    'home_mongo_id', 'away_mongo_id', 'is_cup', 'odds',
    'confidence_segno', 'confidence_gol', 'stars_segno', 'stars_gol',
]

ROUTING_VERSION = '1.0'


# =====================================================
# MAPPING PREDIZIONE → CHIAVE MERCATO
# =====================================================
def market_key(pred):
    """Mappa un pronostico alla chiave mercato del routing."""
    tipo = pred.get('tipo', '')
    pron = pred.get('pronostico', '')

    if tipo == 'SEGNO':
        return '1X2'
    if tipo == 'DOPPIA_CHANCE':
        return 'DC'
    if tipo == 'GOL':
        if 'Over' in pron:
            try:
                val = pron.split()[-1]
                return f'OVER_{val}'
            except:
                return None
        if 'Under' in pron:
            try:
                val = pron.split()[-1]
                return f'UNDER_{val}'
            except:
                return None
        if pron == 'Goal':
            return 'GG'
        if pron == 'NoGoal':
            return 'NG'
    # X_FACTOR e RISULTATO_ESATTO non sono nel routing
    return None


# =====================================================
# HELPERS PER NG COMBO
# =====================================================
def _has_under(preds_set):
    """True se il set contiene almeno un Under."""
    return any(mk.startswith('UNDER_') for mk in preds_set)


def _has_segno(preds_set):
    """True se il set contiene 1X2."""
    return '1X2' in preds_set


def _check_ng_combo(markets_by_sys):
    """
    Verifica le 6 condizioni Under+Segno cross-sistema.
    markets_by_sys: {'A': set di market_key, 'C': set, 'S': set}
    Restituisce True se almeno una condizione è soddisfatta.
    """
    a = markets_by_sys.get('A', set())
    c = markets_by_sys.get('C', set())
    s = markets_by_sys.get('S', set())

    # 1. A=Under + C=Segno
    if _has_under(a) and _has_segno(c):
        return True
    # 2. A=Under + S=Segno
    if _has_under(a) and _has_segno(s):
        return True
    # 3. A+S entrambi Under
    if _has_under(a) and _has_under(s):
        return True
    # 4. C=Under + A=Segno
    if _has_under(c) and _has_segno(a):
        return True
    # 5. S=Under + C=Segno
    if _has_under(s) and _has_segno(c):
        return True
    # 6. Almeno 2 sistemi Under
    under_count = sum(1 for sys_mks in [a, c, s] if _has_under(sys_mks))
    if under_count >= 2:
        return True

    return False


# =====================================================
# LOGICA ROUTING PER MERCATO
# =====================================================
def route_predictions(preds_by_sys, markets_by_sys):
    """
    Applica il routing e restituisce la lista di pronostici unified.

    preds_by_sys: {'A': {market_key: pred_dict}, 'C': {...}, 'S': {...}}
    markets_by_sys: {'A': set(market_keys), 'C': set, 'S': set}

    Restituisce: lista di pronostici con campo 'source' e 'routing_rule' aggiunti.
    """
    unified = []

    for mk, config in ROUTING.items():
        rule = config['rule']
        systems = config['systems']

        if rule == 'single':
            # Prendi dal sistema specificato
            sys_id = systems[0]
            pred = preds_by_sys.get(sys_id, {}).get(mk)
            if pred:
                p = deepcopy(pred)
                p['source'] = sys_id
                p['routing_rule'] = rule
                unified.append(p)

        elif rule == 'consensus_both':
            # Entrambi i sistemi devono emettere E concordare
            s1, s2 = systems[0], systems[1]
            p1 = preds_by_sys.get(s1, {}).get(mk)
            p2 = preds_by_sys.get(s2, {}).get(mk)
            if p1 and p2 and p1.get('pronostico') == p2.get('pronostico'):
                # Usa quello con confidence più alta
                winner = p1 if p1.get('confidence', 0) >= p2.get('confidence', 0) else p2
                source = s1 if winner is p1 else s2
                p = deepcopy(winner)
                p['source'] = f'{s1}+{s2}'
                p['routing_rule'] = rule
                unified.append(p)

        elif rule == 'union':
            # Pool: prendi da qualsiasi sistema nella lista (no duplicati per match)
            added = False
            for sys_id in systems:
                pred = preds_by_sys.get(sys_id, {}).get(mk)
                if pred and not added:
                    p = deepcopy(pred)
                    p['source'] = sys_id
                    p['routing_rule'] = rule
                    unified.append(p)
                    added = True

        elif rule == 'priority_chain':
            # Prova sistemi in ordine di priorità
            for sys_id in systems:
                pred = preds_by_sys.get(sys_id, {}).get(mk)
                if pred:
                    p = deepcopy(pred)
                    p['source'] = sys_id
                    p['routing_rule'] = rule
                    unified.append(p)
                    break

        elif rule == 'combo_under_segno':
            # Regola speciale NG: cross-sistema Under+Segno
            if _check_ng_combo(markets_by_sys):
                # NG combo attivata — crea pronostico derivato
                # Cerca quota NG dagli odds di qualsiasi sistema
                ng_quota = None
                for sys_id in ['A', 'C', 'S']:
                    pred = preds_by_sys.get(sys_id, {}).get('NG')
                    if pred and pred.get('quota'):
                        ng_quota = pred['quota']
                        break

                # NG combo DISABILITATO — HR troppo basso (37-42%)
                # TODO: creare algoritmo NG dedicato
                if True:  # sempre skip
                    continue

                p = {
                    'tipo': 'GOL',
                    'pronostico': 'NoGoal',
                    'confidence': 67,
                    'stars': 3.0,
                    'quota': ng_quota,
                    'probabilita_stimata': 67.0,
                    'has_odds': ng_quota is not None,
                    'source': 'MoE',
                    'routing_rule': rule,
                    'combo_detail': _get_combo_detail(markets_by_sys),
                }
                # Calcola stake se c'è quota
                if ng_quota and ng_quota > 1.0:
                    edge = (67.0 - (100.0 / ng_quota)) / 100.0
                    if edge > 0:
                        kelly_fraction = 0.75  # 3/4 Kelly
                        kelly = kelly_fraction * (edge * ng_quota - (1 - edge)) / (ng_quota - 1)
                        stake = max(1, min(10, round(kelly * 10)))
                        p['stake'] = stake
                        p['edge'] = round(edge * 100, 1)
                        p['prob_mercato'] = round(100.0 / ng_quota, 1)
                        p['prob_modello'] = 67.0
                    else:
                        p['stake'] = 1
                        p['edge'] = 0
                else:
                    p['stake'] = 1
                    p['edge'] = 0

                unified.append(p)

    # --- FLIP: Goal debole Sistema A → NoGoal ---
    # Se Sistema A ha Goal con confidence < 65, è segnale invertito (61.1% NoGoal reale)
    goal_a = preds_by_sys.get('A', {}).get('GG')
    if goal_a and goal_a.get('confidence', 0) < 65:
        # Rimuovi qualsiasi Goal dalla lista unified
        unified = [p for p in unified if p.get('pronostico') != 'Goal']
        # Cerca quota NoGoal dagli odds di qualsiasi sistema
        ng_quota = None
        for sys_id in ['A', 'C', 'S']:
            ng_pred = preds_by_sys.get(sys_id, {}).get('NG')
            if ng_pred and ng_pred.get('quota'):
                ng_quota = ng_pred['quota']
                break
        # Crea pronostico NoGoal derivato dal flip
        p = {
            'tipo': 'GOL',
            'pronostico': 'NoGoal',
            'confidence': 65,
            'stars': 3.0,
            'quota': ng_quota,
            'probabilita_stimata': 61.0,
            'has_odds': ng_quota is not None,
            'source': 'A_flip',
            'routing_rule': 'goal_flip',
        }
        # Calcola stake se c'è quota
        if ng_quota and ng_quota > 1.0:
            edge = (61.0 - (100.0 / ng_quota)) / 100.0
            if edge > 0:
                kelly_fraction = 0.75
                kelly = kelly_fraction * (edge * ng_quota - (1 - edge)) / (ng_quota - 1)
                stake = max(1, min(10, round(kelly * 10)))
                p['stake'] = stake
                p['edge'] = round(edge * 100, 1)
                p['prob_mercato'] = round(100.0 / ng_quota, 1)
                p['prob_modello'] = 61.0
            else:
                p['stake'] = 1
                p['edge'] = 0
        else:
            p['stake'] = 1
            p['edge'] = 0
        unified.append(p)

    # --- DEDUP: Goal vs NoGoal mutualmente esclusivi ---
    # Se entrambi presenti = conflitto → rimuovi ENTRAMBI (match incerto)
    gg_list = [p for p in unified if p.get('pronostico') == 'Goal']
    ng_list = [p for p in unified if p.get('pronostico') == 'NoGoal']
    if gg_list and ng_list:
        unified = [p for p in unified if p.get('pronostico') not in ('Goal', 'NoGoal')]

    return unified


def _get_combo_detail(markets_by_sys):
    """Restituisce quali condizioni NG combo sono attive."""
    a = markets_by_sys.get('A', set())
    c = markets_by_sys.get('C', set())
    s = markets_by_sys.get('S', set())
    details = []
    if _has_under(a) and _has_segno(c): details.append('A=Under+C=Segno')
    if _has_under(a) and _has_segno(s): details.append('A=Under+S=Segno')
    if _has_under(a) and _has_under(s): details.append('A+S=Under')
    if _has_under(c) and _has_segno(a): details.append('C=Under+A=Segno')
    if _has_under(s) and _has_segno(c): details.append('S=Under+C=Segno')
    under_count = sum(1 for sys_mks in [a, c, s] if _has_under(sys_mks))
    if under_count >= 2: details.append('2+Under')
    return details


# =====================================================
# ORCHESTRAZIONE PRINCIPALE
# =====================================================
def orchestrate_date(date_str, dry_run=False):
    """
    Orchestrazione per una singola data.
    Ritorna il numero di documenti scritti.
    """
    # 1. Carica pronostici dai 3 sistemi
    docs_by_sys = {}
    for sys_id, coll_name in COLLECTIONS.items():
        docs = list(db[coll_name].find({'date': date_str}))
        idx = {}
        for doc in docs:
            # Salta documenti RISULTATO_ESATTO (duplicati con comment stringa)
            if doc.get('decision') == 'RISULTATO_ESATTO':
                continue
            key = doc.get('home', '') + '__' + doc.get('away', '')
            if key in idx:
                # Mergia pronostici da documenti multipli della stessa partita
                idx[key]['pronostici'].extend(doc.get('pronostici', []))
            else:
                idx[key] = doc
        docs_by_sys[sys_id] = idx

    # 2. Trova tutte le partite uniche
    all_match_keys = set()
    for idx in docs_by_sys.values():
        all_match_keys.update(idx.keys())

    if not all_match_keys:
        return 0

    # 3. Per ogni partita, applica routing
    unified_docs = []
    for match_key in sorted(all_match_keys):
        # Trova documento base (preferenza: A > S > C)
        base_doc = None
        for sys_id in ['A', 'S', 'C']:
            if match_key in docs_by_sys[sys_id]:
                base_doc = docs_by_sys[sys_id][match_key]
                break

        if not base_doc:
            continue

        # Costruisci indice pronostici per sistema
        preds_by_sys = {}  # sys_id -> {market_key: pred_dict}
        markets_by_sys = {}  # sys_id -> set(market_keys)

        for sys_id in ['A', 'C', 'S']:
            doc = docs_by_sys[sys_id].get(match_key)
            if not doc:
                preds_by_sys[sys_id] = {}
                markets_by_sys[sys_id] = set()
                continue

            pred_idx = {}
            mk_set = set()
            for p in doc.get('pronostici', []):
                mk = market_key(p)
                if mk:
                    pred_idx[mk] = p
                    mk_set.add(mk)

            preds_by_sys[sys_id] = pred_idx
            markets_by_sys[sys_id] = mk_set

        # Applica routing
        unified_pronostici = route_predictions(preds_by_sys, markets_by_sys)

        if not unified_pronostici:
            continue

        # Costruisci documento unified
        unified_doc = {}
        for field in MATCH_FIELDS:
            if field in base_doc:
                unified_doc[field] = base_doc[field]

        unified_doc['pronostici'] = unified_pronostici
        unified_doc['routing_version'] = ROUTING_VERSION
        unified_doc['created_at'] = datetime.now(timezone.utc)

        # Aggiungi statistiche
        unified_doc['stats'] = {
            'total_predictions': len(unified_pronostici),
            'sources': list(set(p.get('source', '?') for p in unified_pronostici)),
            'markets': list(set(market_key(p) or '?' for p in unified_pronostici)),
        }

        # --- Campi extra da sistemi specifici ---

        # simulation_data: SOLO da Sistema C (Monte Carlo)
        c_doc = docs_by_sys['C'].get(match_key)
        if c_doc and 'simulation_data' in c_doc:
            unified_doc['simulation_data'] = c_doc['simulation_data']

        # comment, dettagli, strisce: preferenza A > S > C
        EXTRA_FIELDS = [
            'comment', 'segno_dettaglio', 'gol_dettaglio',
            'streak_home', 'streak_away',
            'streak_home_context', 'streak_away_context',
            'gol_directions', 'expected_total_goals',
        ]
        for field in EXTRA_FIELDS:
            for sys_id in ['A', 'S', 'C']:
                doc = docs_by_sys[sys_id].get(match_key)
                if doc and field in doc and doc[field]:
                    unified_doc[field] = doc[field]
                    break

        unified_docs.append(unified_doc)

    if not unified_docs:
        return 0

    # 4. Scrivi in daily_predictions_unified
    coll = db['daily_predictions_unified']

    if not dry_run:
        # Rimuovi vecchi documenti per questa data
        coll.delete_many({'date': date_str})
        # Inserisci nuovi
        coll.insert_many(unified_docs)

    return len(unified_docs)


# =====================================================
# MAIN
# =====================================================
def main():
    parser = argparse.ArgumentParser(description='Mixture of Experts — Orchestratore')
    parser.add_argument('date', nargs='?', help='Data YYYY-MM-DD (default: oggi)')
    parser.add_argument('--backfill', nargs=2, metavar=('START', 'END'),
                        help='Range date per backfill')
    parser.add_argument('--dry-run', action='store_true',
                        help='Simula senza scrivere')
    args = parser.parse_args()

    if args.backfill:
        start_str, end_str = args.backfill
        start = datetime.strptime(start_str, '%Y-%m-%d')
        end = datetime.strptime(end_str, '%Y-%m-%d')
        dates = []
        d = start
        while d <= end:
            dates.append(d.strftime('%Y-%m-%d'))
            d += timedelta(days=1)

        print(f"\n  MoE Backfill: {start_str} -> {end_str} ({len(dates)} giorni)")
        if args.dry_run:
            print("  [DRY RUN — nessuna scrittura]")
        print()

        total = 0
        for dt in dates:
            count = orchestrate_date(dt, dry_run=args.dry_run)
            total += count
            status = '[DRY]' if args.dry_run else '[OK]'
            print(f"  {dt}: {count} partite {status}")

        print(f"\n  Totale: {total} partite su {len(dates)} giorni")

    else:
        if args.date:
            # Data specifica passata da CLI
            date_str = args.date
            print(f"\n  MoE Orchestratore — Data: {date_str}")
            if args.dry_run:
                print("  [DRY RUN — nessuna scrittura]")
            count = orchestrate_date(date_str, dry_run=args.dry_run)
            print(f"  Partite scritte: {count}")
        else:
            # Nessun argomento → 7 giorni (oggi + 6 futuri), come Sistema A e C
            print(f"\n  MoE Orchestratore — 7 giorni (oggi + 6 futuri)")
            if args.dry_run:
                print("  [DRY RUN — nessuna scrittura]")
            total = 0
            for i in range(7):
                target = datetime.now() + timedelta(days=i)
                date_str = target.strftime('%Y-%m-%d')
                count = orchestrate_date(date_str, dry_run=args.dry_run)
                total += count
                status = '[DRY]' if args.dry_run else '[OK]'
                print(f"  {date_str}: {count} partite {status}")
            print(f"\n  Totale: {total} partite su 7 giorni")

    print()


if __name__ == '__main__':
    main()
