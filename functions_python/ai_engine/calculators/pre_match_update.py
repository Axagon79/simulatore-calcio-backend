"""
pre_match_update.py — Aggiornamento pre-match dei pronostici

Chiamato da cron ogni 15 minuti (es. 10:00-23:00).
Per ogni gruppo orario di partite, esegue il ciclo completo (A→S→C→MoE)
esattamente due volte: a -3h e -1h dall'inizio del blocco.

Uso:
  python pre_match_update.py              # oggi, ora corrente
  python pre_match_update.py 2026-03-12   # data specifica
  python pre_match_update.py 2026-03-12 17:45  # simula ora specifica (test)
"""

import sys
import os
import argparse
import time
import logging
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, 'pre_match_update.log')

# Setup logging su file
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('pre_match_update')

sys.path.insert(0, os.path.join(SCRIPT_DIR, '..'))
from config import db

# Import funzioni dai sistemi
from run_daily_predictions import run_daily_predictions as run_system_a
from run_daily_predictions_sandbox import run_daily_predictions as run_system_s
from run_daily_predictions_engine_c import run_engine_c as run_system_c
from orchestrate_experts import orchestrate_date as run_orchestrator
from snapshot_nightly import normalize_match_key, get_all_matches

# Collections
h2h_collection = db['h2h_by_round']
unified_collection = db['daily_predictions_unified']
versions_collection = db['prediction_versions']
run_log_collection = db['pre_match_run_log']
notification_collection = db['notification_queue']

# Configurazione
TOLERANCE_MINUTES = 10  # Finestra ±10 min dal trigger
MAX_CONSECUTIVE_GAP = 30  # Gap max tra orari consecutivi (minuti)
MAX_BLOCK_SPAN = 90  # Span max primo-ultimo nel blocco (minuti)

# Run da eseguire: (offset_minuti_prima, label)
RUNS = [
    (180, 'update_3h'),
    (60, 'update_1h'),
]


# =====================================================
# RAGGRUPPAMENTO PER ORARIO
# =====================================================
def parse_match_time(time_str):
    """Converte 'HH:MM' in minuti dall'inizio della giornata."""
    try:
        parts = time_str.split(':')
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError, AttributeError):
        return None


def group_by_time_window(matches):
    """
    Raggruppa le partite per blocchi orari.
    Regole:
    - Gap consecutivo ≤ 30 min
    - Span primo-ultimo ≤ 90 min

    Ritorna: lista di gruppi, ogni gruppo = lista di orari unici (stringhe HH:MM)
    """
    # Estrai orari unici e validi
    time_set = set()
    for m in matches:
        mt = m.get('match_time', '')
        if mt and parse_match_time(mt) is not None:
            time_set.add(mt)

    if not time_set:
        return []

    # Ordina per minuti
    sorted_times = sorted(time_set, key=lambda t: parse_match_time(t))

    groups = []
    current_group = [sorted_times[0]]

    for t in sorted_times[1:]:
        t_min = parse_match_time(t)
        prev_min = parse_match_time(current_group[-1])
        first_min = parse_match_time(current_group[0])

        consecutive_gap = t_min - prev_min
        block_span = t_min - first_min

        if consecutive_gap <= MAX_CONSECUTIVE_GAP and block_span <= MAX_BLOCK_SPAN:
            current_group.append(t)
        else:
            groups.append(current_group)
            current_group = [t]

    groups.append(current_group)
    return groups


# =====================================================
# CHECK RUN GIÀ ESEGUITO
# =====================================================
def is_already_run(date_str, block_key, run_label):
    """Controlla se questo run è già stato eseguito oggi."""
    return run_log_collection.find_one({
        'date': date_str,
        'block_key': block_key,
        'run_label': run_label
    }) is not None


def save_run_log(date_str, block_key, run_label, block_times, ran_at):
    """Salva log del run eseguito."""
    run_log_collection.insert_one({
        'date': date_str,
        'block_key': block_key,
        'run_label': run_label,
        'block_times': block_times,
        'ran_at': ran_at,
        'created_at': datetime.now(timezone.utc)
    })


# =====================================================
# SNAPSHOT + CHANGE DETECTION
# =====================================================
def save_snapshot_and_detect_changes(date_str, match_time_filter, version_label):
    """
    Salva snapshot in prediction_versions e rileva cambiamenti
    rispetto alla versione precedente.

    Ritorna: lista di dict {match_key, changes[]}
    """
    # 1. Tutti i match del giorno con gli orari del blocco
    all_matches = get_all_matches()
    block_matches = [m for m in all_matches
                     if m.get('match_time', '') in match_time_filter]

    # 2. Pronostici unified attuali (appena ricalcolati)
    unified_filter = {'date': date_str, 'match_time': {'$in': match_time_filter}}
    unified_docs = list(unified_collection.find(unified_filter))
    unified_index = {}
    for doc in unified_docs:
        key = normalize_match_key(date_str, doc['home'], doc['away'])
        unified_index[key] = doc

    # 3. Versioni precedenti (per change detection)
    # Ordine: nightly → update_3h → update_1h
    version_order = ['nightly', 'update_3h', 'update_1h']
    current_idx = version_order.index(version_label) if version_label in version_order else -1
    previous_versions = version_order[:current_idx] if current_idx > 0 else []

    prev_index = {}
    if previous_versions:
        # Prendi la versione più recente disponibile per ogni match
        for prev_ver in reversed(previous_versions):
            prev_docs = list(versions_collection.find({
                'date': date_str,
                'match_time': {'$in': match_time_filter},
                'version': prev_ver
            }))
            for doc in prev_docs:
                mk = doc.get('match_key', '')
                if mk and mk not in prev_index:
                    prev_index[mk] = doc

    # 4. Elimina snapshot precedenti con stessa versione per questi orari
    versions_collection.delete_many({
        'date': date_str,
        'match_time': {'$in': match_time_filter},
        'version': version_label
    })

    # 5. Crea snapshot per ogni match del blocco
    snapshots = []
    all_changes = []

    for match in block_matches:
        home = match.get('home', '')
        away = match.get('away', '')
        if not home or not away:
            continue

        match_key = normalize_match_key(date_str, home, away)
        unified_doc = unified_index.get(match_key)

        new_pronostici = unified_doc.get('pronostici', []) if unified_doc else []

        # Change detection
        changes = []
        prev_doc = prev_index.get(match_key)
        if prev_doc:
            old_pronostici = prev_doc.get('pronostici', [])
            changes = detect_changes(old_pronostici, new_pronostici)

        # Recupera mongo_id da unified_doc o dal match h2h
        home_mongo_id = (unified_doc or {}).get('home_mongo_id') or match.get('home_mongo_id', '')
        away_mongo_id = (unified_doc or {}).get('away_mongo_id') or match.get('away_mongo_id', '')

        snapshot = {
            'match_key': match_key,
            'date': date_str,
            'home': home,
            'away': away,
            'league': match.get('_league', ''),
            'match_time': match.get('match_time', ''),
            'home_mongo_id': home_mongo_id,
            'away_mongo_id': away_mongo_id,
            'version': version_label,
            'created_at': datetime.now(timezone.utc),
            'pronostici': new_pronostici,
            'changes': changes,
        }

        if unified_doc:
            snapshot['odds'] = unified_doc.get('odds', {})
        else:
            snapshot['odds'] = match.get('odds', {})

        snapshots.append(snapshot)

        if changes:
            all_changes.append({
                'match_key': match_key,
                'home': home,
                'away': away,
                'changes': changes
            })

    if snapshots:
        versions_collection.insert_many(snapshots)

    no_bet = sum(1 for s in snapshots if not s['pronostici'])
    print(f"   📸 Snapshot '{version_label}': {len(snapshots)} match ({no_bet} NO BET)")

    return all_changes


def detect_changes(old_pronostici, new_pronostici):
    """
    Confronta vecchi e nuovi pronostici per rilevare cambiamenti.

    Tipi: updated, stake_changed, removed, added
    """
    changes = []

    # Indice per tipo
    old_by_tipo = {p['tipo']: p for p in old_pronostici}
    new_by_tipo = {p['tipo']: p for p in new_pronostici}

    all_tipi = set(list(old_by_tipo.keys()) + list(new_by_tipo.keys()))

    for tipo in all_tipi:
        old_p = old_by_tipo.get(tipo)
        new_p = new_by_tipo.get(tipo)

        if old_p and not new_p:
            # Rimosso (NO BET per questo tipo)
            changes.append({
                'tipo': tipo,
                'change_type': 'removed',
                'old_pronostico': old_p.get('pronostico'),
                'new_pronostico': None,
                'old_stake': old_p.get('stake'),
                'new_stake': None,
            })
        elif not old_p and new_p:
            # Aggiunto (nuovo pronostico)
            changes.append({
                'tipo': tipo,
                'change_type': 'added',
                'old_pronostico': None,
                'new_pronostico': new_p.get('pronostico'),
                'old_stake': None,
                'new_stake': new_p.get('stake'),
            })
        elif old_p and new_p:
            old_tip = old_p.get('pronostico')
            new_tip = new_p.get('pronostico')
            old_stake = old_p.get('stake')
            new_stake = new_p.get('stake')

            if old_tip != new_tip:
                changes.append({
                    'tipo': tipo,
                    'change_type': 'updated',
                    'old_pronostico': old_tip,
                    'new_pronostico': new_tip,
                    'old_stake': old_stake,
                    'new_stake': new_stake,
                })
            elif old_stake != new_stake:
                changes.append({
                    'tipo': tipo,
                    'change_type': 'stake_changed',
                    'old_pronostico': old_tip,
                    'new_pronostico': new_tip,
                    'old_stake': old_stake,
                    'new_stake': new_stake,
                })

    return changes


# =====================================================
# RIMBORSI (SOLO RUN -1h, SOLO REMOVED)
# =====================================================
def handle_refunds(all_changes, date_str, run_label):
    """
    Gestisce rimborsi automatici.
    Solo al run update_1h, solo per change_type='removed'.
    """
    if run_label != 'update_1h':
        return

    user_purchases = db['user_purchases']
    users_collection = db['users']

    refund_count = 0
    for match_change in all_changes:
        match_key = match_change['match_key']
        for change in match_change['changes']:
            if change['change_type'] != 'removed':
                continue

            tipo = change['tipo']

            # Trova acquisti per questo match/tipo non ancora rimborsati
            purchases = list(user_purchases.find({
                'match_key': match_key,
                'prediction_tipo': tipo,
                'refunded': {'$ne': True}
            }))

            for purchase in purchases:
                user_id = purchase['user_id']
                credits_to_refund = purchase.get('credits_spent', 3)

                # Rimborsa crediti
                users_collection.update_one(
                    {'_id': user_id},
                    {'$inc': {'credits': credits_to_refund}}
                )

                # Aggiorna acquisto
                user_purchases.update_one(
                    {'_id': purchase['_id']},
                    {'$set': {
                        'refunded': True,
                        'refund_reason': 'pronostico_ritirato',
                        'refunded_at': datetime.now(timezone.utc)
                    }}
                )

                refund_count += 1

    if refund_count > 0:
        print(f"   💰 Rimborsi effettuati: {refund_count}")


# =====================================================
# NOTIFICHE
# =====================================================
def queue_notifications(all_changes, date_str, run_label):
    """Accoda notifiche per utenti che hanno acquistato pronostici modificati."""
    user_purchases = db['user_purchases']
    notifications = []

    for match_change in all_changes:
        match_key = match_change['match_key']
        match_label = f"{match_change['home']} vs {match_change['away']}"

        for change in match_change['changes']:
            tipo = change['tipo']

            # Trova utenti che hanno acquistato questo pronostico
            purchases = list(user_purchases.find({
                'match_key': match_key,
                'prediction_tipo': tipo,
            }))

            # Tipo notifica
            if change['change_type'] == 'removed':
                notif_type = 'pronostico_ritirato'
            elif change['change_type'] == 'stake_changed':
                notif_type = 'stake_variato'
            else:
                notif_type = 'pronostico_aggiornato'

            for purchase in purchases:
                notifications.append({
                    'user_id': purchase['user_id'],
                    'type': notif_type,
                    'match_key': match_key,
                    'match_label': match_label,
                    'run': run_label,
                    'payload': {
                        'tipo': tipo,
                        'old_pronostico': change.get('old_pronostico'),
                        'new_pronostico': change.get('new_pronostico'),
                        'old_stake': change.get('old_stake'),
                        'new_stake': change.get('new_stake'),
                        'refunded': change['change_type'] == 'removed' and run_label == 'update_1h',
                    },
                    'created_at': datetime.now(timezone.utc),
                    'sent': False,
                    'sent_at': None,
                })

    if notifications:
        notification_collection.insert_many(notifications)
        print(f"   🔔 Notifiche accodate: {len(notifications)}")


# =====================================================
# CICLO COMPLETO PER UN BLOCCO
# =====================================================
def get_active_match_times(date_str, block_times):
    """
    Ritorna gli orari del blocco che hanno avuto almeno un pronostico attivo
    in qualsiasi versione della giornata (prediction_versions), non solo attualmente.
    Così anche partite diventate NO BET al -3h vengono ricalcolate al -1h.
    """
    active_docs = list(versions_collection.find({
        'date': date_str,
        'match_time': {'$in': block_times},
        'pronostici': {'$exists': True, '$ne': []}
    }, {'match_time': 1}))

    active_times = list(set(doc['match_time'] for doc in active_docs if doc.get('match_time')))
    return sorted(active_times)


def run_full_cycle(date_str, target_date, block_times, run_label):
    """
    Esegue il ciclo A→S→C→MoE per un gruppo orario.
    - update_3h: ciclo completo su TUTTE le partite del blocco (incluse scartate)
    - update_1h: rifinitura chirurgica solo su partite con pronostici attivi
    """
    print(f"\n{'=' * 60}")
    print(f"🔄 PRE-MATCH UPDATE — {run_label} per blocco {block_times}")
    print(f"{'=' * 60}")

    t_start = time.time()

    # Filtra partite già iniziate
    now_mins = int(datetime.now().hour * 60 + datetime.now().minute)
    effective_times = [t for t in block_times if parse_match_time(t) > now_mins]
    if not effective_times:
        print(f"   ⏭️  Tutte le partite del blocco sono già iniziate — skip")
        return
    skipped_started = len(block_times) - len(effective_times)
    if skipped_started > 0:
        print(f"   ⏩ {skipped_started} partite già iniziate — skip, aggiorno le restanti {len(effective_times)}")

    # Per il run -1h, filtra solo partite con pronostici attivi
    if run_label == 'update_1h':
        effective_times = get_active_match_times(date_str, block_times)
        if not effective_times:
            print(f"   ⏭️  Nessuna partita con pronostici attivi nel blocco — skip")
            # Salva comunque snapshot vuoto per completezza
            save_snapshot_and_detect_changes(date_str, block_times, run_label)
            elapsed = time.time() - t_start
            logger.info(f"{run_label} skip (0 attive) in {elapsed:.1f}s — blocco {block_times}")
            print(f"\n✅ {run_label} completato in {elapsed:.1f}s (nessuna partita attiva)")
            return
        skipped = len(block_times) - len(effective_times)
        if skipped > 0:
            print(f"   🎯 Rifinitura: {len(effective_times)} partite attive, {skipped} scartate (skip)")

    # 1. Esegui i 4 sistemi con filtro orario
    print(f"\n--- Sistema A ---")
    run_system_a(target_date=target_date, match_time_filter=effective_times)

    print(f"\n--- Sistema S ---")
    run_system_s(target_date=target_date, match_time_filter=effective_times)

    print(f"\n--- Sistema C ---")
    run_system_c(target_date=target_date, match_time_filter=effective_times)

    print(f"\n--- Orchestratore MoE ---")
    run_orchestrator(date_str, dry_run=False, match_time_filter=effective_times)

    # 2. Snapshot + change detection
    all_changes = save_snapshot_and_detect_changes(date_str, block_times, run_label)

    # 3. Rimborsi (solo update_1h)
    if all_changes:
        handle_refunds(all_changes, date_str, run_label)
        queue_notifications(all_changes, date_str, run_label)

    elapsed = time.time() - t_start
    n_changes = sum(len(c['changes']) for c in all_changes)
    logger.info(f"{run_label} completato in {elapsed:.1f}s — {n_changes} cambiamenti — blocco {block_times}")
    print(f"\n✅ {run_label} completato in {elapsed:.1f}s")
    print(f"   Cambiamenti rilevati: {n_changes}")


# =====================================================
# MAIN
# =====================================================
def main():
    parser = argparse.ArgumentParser(description='Pre-Match Update — Aggiornamento pronostici')
    parser.add_argument('date', nargs='?', help='Data YYYY-MM-DD (default: oggi)')
    parser.add_argument('time', nargs='?', help='Ora HH:MM per simulare (default: ora corrente)')
    args = parser.parse_args()

    # Data target
    if args.date:
        target_date = datetime.strptime(args.date, '%Y-%m-%d')
        date_str = args.date
    else:
        target_date = datetime.now()
        date_str = target_date.strftime('%Y-%m-%d')

    # Ora corrente (o simulata per test)
    if args.time:
        now_minutes = parse_match_time(args.time)
        print(f"⏰ Simulazione ora: {args.time}")
    else:
        now = datetime.now()
        now_minutes = now.hour * 60 + now.minute

    now_str = f"{now_minutes // 60:02d}:{now_minutes % 60:02d}"
    logger.info(f"Avvio — {date_str} alle {now_str}")
    print(f"\n🕐 Pre-Match Update — {date_str} alle {now_str}")

    # 1. Recupera partite del giorno
    all_matches = get_all_matches(target_date)
    if not all_matches:
        logger.info("Nessuna partita oggi")
        print("   Nessuna partita oggi. Uscita.")
        return

    print(f"   Partite totali: {len(all_matches)}")

    # 2. Raggruppa per blocchi orari
    groups = group_by_time_window(all_matches)
    print(f"   Blocchi orari: {len(groups)}")
    for i, g in enumerate(groups):
        print(f"     Blocco {i+1}: {g}")

    # 3. Per ogni blocco, controlla i trigger
    runs_executed = 0

    for group_times in groups:
        first_time = group_times[0]
        last_time = group_times[-1]
        first_minutes = parse_match_time(first_time)
        last_minutes = parse_match_time(last_time)
        block_key = '_'.join(group_times)

        for offset_minutes, run_label in RUNS:
            trigger_minutes = first_minutes - offset_minutes

            # Esegui se l'ora trigger è passata (ma non oltre l'ultima partita del blocco)
            if now_minutes < trigger_minutes or now_minutes >= last_minutes:
                continue

            # Controlla se già eseguito
            if is_already_run(date_str, block_key, run_label):
                print(f"   ⏭️  {run_label} per blocco {group_times} — già eseguito, skip")
                continue

            # Esegui il ciclo completo
            run_full_cycle(date_str, target_date, group_times, run_label)

            # Salva log
            save_run_log(date_str, block_key, run_label, group_times,
                        datetime.now(timezone.utc))
            runs_executed += 1

    if runs_executed == 0:
        logger.info("Nessun blocco pronto — skip")
        print("   Nessun blocco pronto per l'aggiornamento in questo momento.")
    else:
        logger.info(f"Run eseguiti: {runs_executed}")
        print(f"\n🏁 Totale run eseguiti: {runs_executed}")


if __name__ == '__main__':
    try:
        main()
        logger.info("Esecuzione completata OK")
    except Exception as e:
        logger.error(f"CRASH: {e}", exc_info=True)
        print(f"❌ ERRORE: {e}")
        sys.exit(1)
