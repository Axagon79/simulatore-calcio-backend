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
from tag_elite import get_matched_patterns
from tag_mixer import get_matched_mixer_patterns

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
# WHITELIST -1h: filtra i tip NUOVI che il -1h aggiunge su partite
# che erano vuote al passo precedente (update_3h o nightly).
# Analisi storica (40 giorni, 118 tip "nuovi puri"): -13.91u senza filtro,
# +2.84u con whitelist. Accetta solo tip che matchano almeno 1 dei 10 pattern.
# =====================================================
def _matches_whitelist_1h(tip):
    tipo = tip.get('tipo')
    pron = tip.get('pronostico')
    quota = tip.get('quota')
    source = tip.get('source') or ''
    # 1. DC 1X
    if tipo == 'DOPPIA_CHANCE' and pron == '1X':
        return True
    # 2. SEGNO quota 1.50-1.69
    if tipo == 'SEGNO' and quota is not None and 1.50 <= quota < 1.70:
        return True
    # 3. DC quota 1.30-1.49
    if tipo == 'DOPPIA_CHANCE' and quota is not None and 1.30 <= quota < 1.50:
        return True
    # 4. flag MIXER
    if tip.get('mixer') is True:
        return True
    # 5. flag ELITE
    if tip.get('elite') is True:
        return True
    # 6. source A+S
    if source == 'A+S':
        return True
    # 7. DC + source A+S (ridondante con 6 ma esplicito)
    if tipo == 'DOPPIA_CHANCE' and source == 'A+S':
        return True
    # 8. GOL Over 2.5
    if tipo == 'GOL' and pron == 'Over 2.5':
        return True
    # 9. GOL NoGoal
    if tipo == 'GOL' and pron and pron.lower() == 'nogoal':
        return True
    # 10. SEGNO 1
    if tipo == 'SEGNO' and pron == '1':
        return True
    return False


# =====================================================
# WHITELIST PROTEZIONE -1h: impedisce al -1h di TOGLIERE tip che matchano
# pattern storicamente vincenti. Analisi storica: 250 tip tolti con 49% vincenti.
# Con questa whitelist salviamo 47 tip (74.5% vincenti) → +14.14u su 37 giorni.
# Un tip "era al mattino" se 'tip_era_al_mattino' è True.
# =====================================================
def _matches_protezione_1h(tip, tip_era_al_mattino):
    tipo = tip.get('tipo')
    q = tip.get('quota') or 0
    src = tip.get('source') or ''
    elite = tip.get('elite') is True
    mixer = tip.get('mixer') is True
    low = tip.get('low_value') is True
    # 1. Elite + Mixer + noLow
    if elite and mixer and not low:
        return True
    # 2. Quota 1.50-1.69 + Mixer + noLow
    if 1.50 <= q < 1.70 and mixer and not low:
        return True
    # 3. Mixer + noLow + origine_mattino
    if mixer and not low and tip_era_al_mattino:
        return True
    # 4. GOL + quota 1.50-1.69 + source C_screm
    if tipo == 'GOL' and 1.50 <= q < 1.70 and src == 'C_screm':
        return True
    # 5. SEGNO + Mixer + origine_mattino
    if tipo == 'SEGNO' and mixer and tip_era_al_mattino:
        return True
    # 6. source C_goal_conv
    if src == 'C_goal_conv':
        return True
    return False


# =====================================================
# WHITELIST PROTEZIONE -3h: impedisce al -3h di ELIMINARE tip del mattino
# che matchano pattern vincenti. Analisi storica (101 tip eliminati dal -3h):
# 8 pattern salvano 57 tip (80.7% vincenti, +18.25u). Questi tip sono protetti
# ANCHE dal -1h (non possono essere eliminati a cascata).
# =====================================================
def _matches_protezione_3h(tip):
    tipo = tip.get('tipo')
    pron = tip.get('pronostico')
    q = tip.get('quota') or 0
    s = tip.get('stars') or 0
    src = tip.get('source') or ''
    elite = tip.get('elite') is True
    mixer = tip.get('mixer') is True
    low = tip.get('low_value') is True
    # 1. DC X2 + quota 1.50-1.69
    if tipo == 'DOPPIA_CHANCE' and pron == 'X2' and 1.50 <= q < 1.70:
        return True
    # 2. Quota 1.30-1.49 + Elite
    if 1.30 <= q < 1.50 and elite:
        return True
    # 3. Quota 1.50-1.69 + stelle 2.5-2.9
    if 1.50 <= q < 1.70 and 2.5 <= s < 3.0:
        return True
    # 4. Quota 1.50-1.69 + source C
    if 1.50 <= q < 1.70 and src == 'C':
        return True
    # 5. Quota 1.90-2.19 + non Elite + non Mixer + non Low
    if 1.90 <= q < 2.20 and not elite and not mixer and not low:
        return True
    # 6. GOL Over 2.5
    if tipo == 'GOL' and pron == 'Over 2.5':
        return True
    # 7. SEGNO 1 + quota 1.90-2.19
    if tipo == 'SEGNO' and pron == '1' and 1.90 <= q < 2.20:
        return True
    # 8. Qualunque Elite
    if elite:
        return True
    return False


# =====================================================
# WHITELIST -3h: filtra i tip NUOVI che il -3h aggiunge su partite che al
# mattino erano NO BET (nessun tip attivo). Analisi storica (37 giorni, 122 tip):
# senza filtro -16.94u, con filtro +9.47u (delta +26.41u).
# Accetta solo i tip che matchano almeno 1 dei 6 pattern.
# =====================================================
def _matches_whitelist_3h(tip):
    tipo = tip.get('tipo')
    pron = tip.get('pronostico')
    q = tip.get('quota') or 0
    s = tip.get('stars') or 0
    src = tip.get('source') or ''
    # 1. Stelle ≥ 4.0
    if s >= 4.0:
        return True
    # 2. GOL + quota 1.50-1.69
    if tipo == 'GOL' and 1.50 <= q < 1.70:
        return True
    # 3. Quota 1.90-2.19 + source C + non Mixer
    if 1.90 <= q < 2.20 and src == 'C' and not (tip.get('mixer') is True):
        return True
    # 4. SEGNO + quota 1.90-2.19 + source C
    if tipo == 'SEGNO' and 1.90 <= q < 2.20 and src == 'C':
        return True
    # 5. DC X2 + quota 1.30-1.49
    if tipo == 'DOPPIA_CHANCE' and pron == 'X2' and 1.30 <= q < 1.50:
        return True
    # 6. GOL NoGoal
    if tipo == 'GOL' and pron and pron.lower() == 'nogoal':
        return True
    return False


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

    # Per il run -1h, filtra solo partite con pronostici attivi (tra quelle non ancora iniziate)
    if run_label == 'update_1h':
        effective_times = get_active_match_times(date_str, effective_times)
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

    # 0a. (SOLO update_3h) Salva snapshot dei tip del MATTINO (nightly)
    # per poter ripristinare quelli protetti se il -3h li elimina.
    tip_pre_3h = {}  # match_key -> list of tip dicts attivi al mattino
    if run_label == 'update_3h':
        nightly_versions_0 = list(versions_collection.find({
            'date': date_str,
            'match_time': {'$in': effective_times},
            'version': 'nightly'
        }))
        for nv in nightly_versions_0:
            mk = nv.get('match_key', '')
            active = []
            for t in (nv.get('tips') or []):
                if t.get('pronostico') and t.get('pronostico') != 'NO BET' and (t.get('stake') or 0) > 0:
                    active.append(dict(t))
            if active:
                tip_pre_3h[mk] = active

    # 0b. (SOLO update_1h) Salva snapshot "pre-orchestratore" dei tip attivi
    # per poter eventualmente ripristinare quelli protetti dopo l'esecuzione.
    tip_pre_1h = {}  # match_key -> list of tip dicts con campo _era_al_mattino
    if run_label == 'update_1h':
        # Stato corrente (= intermedio = post update_3h)
        pre_docs = list(unified_collection.find(
            {'date': date_str, 'match_time': {'$in': effective_times}},
            {'home': 1, 'away': 1, 'pronostici': 1}
        ))
        # Recupera anche i tip del mattino (nightly) per sapere l'origine
        mattino_versions = list(versions_collection.find({
            'date': date_str,
            'match_time': {'$in': effective_times},
            'version': 'nightly'
        }))
        mattino_tips_map = {}  # mk -> set di (tipo, pronostico) attivi al mattino
        for pv in mattino_versions:
            mk = pv.get('match_key', '')
            active = set()
            for t in (pv.get('tips') or []):
                if t.get('pronostico') and t.get('pronostico') != 'NO BET' and (t.get('stake') or 0) > 0:
                    active.add((t.get('tipo'), t.get('pronostico')))
            mattino_tips_map[mk] = active

        for doc in pre_docs:
            mk = normalize_match_key(date_str, doc.get('home', ''), doc.get('away', ''))
            matt_active = mattino_tips_map.get(mk, set())
            active_tips = []
            for p in (doc.get('pronostici') or []):
                if not p.get('pronostico') or p.get('pronostico') == 'NO BET':
                    continue
                if (p.get('stake') or 0) <= 0:
                    continue
                tip_copy = dict(p)
                tip_copy['_era_al_mattino'] = (p.get('tipo'), p.get('pronostico')) in matt_active
                active_tips.append(tip_copy)
            if active_tips:
                tip_pre_1h[mk] = active_tips

    # 1. Esegui i 4 sistemi con filtro orario
    print(f"\n--- Sistema A ---")
    run_system_a(target_date=target_date, match_time_filter=effective_times)

    print(f"\n--- Sistema S ---")
    run_system_s(target_date=target_date, match_time_filter=effective_times)

    print(f"\n--- Sistema C ---")
    run_system_c(target_date=target_date, match_time_filter=effective_times)

    print(f"\n--- Orchestratore MoE ---")
    run_orchestrator(date_str, dry_run=False, match_time_filter=effective_times, preserve_analysis=True)

    # 1b. Ri-tagging Elite dopo orchestratore
    elite_count = 0
    elite_docs = list(unified_collection.find(
        {'date': date_str, 'match_time': {'$in': effective_times}},
        {'_id': 1, 'pronostici': 1}
    ))
    for doc in elite_docs:
        pronostici = doc.get('pronostici', [])
        changed_elite = False
        for p in pronostici:
            is_elite = len(get_matched_patterns(p)) > 0
            if p.get('elite') != is_elite:
                p['elite'] = is_elite
                changed_elite = True
            if is_elite:
                elite_count += 1
        if changed_elite:
            unified_collection.update_one({'_id': doc['_id']}, {'$set': {'pronostici': pronostici}})
    print(f"   👑 Elite ri-taggati: {elite_count} pronostici")

    # 1c. Ri-tagging Mixer dopo orchestratore
    mixer_count = 0
    mixer_docs = list(unified_collection.find(
        {'date': date_str, 'match_time': {'$in': effective_times}},
        {'_id': 1, 'pronostici': 1}
    ))
    for doc in mixer_docs:
        pronostici = doc.get('pronostici', [])
        changed_mixer = False
        for p in pronostici:
            matched = get_matched_mixer_patterns(p)
            is_mixer = len(matched) > 0
            if p.get('mixer') != is_mixer or sorted(matched) != sorted(p.get('mixer_patterns', [])):
                p['mixer'] = is_mixer
                p['mixer_patterns'] = sorted(matched)
                changed_mixer = True
            if is_mixer:
                mixer_count += 1
        if changed_mixer:
            unified_collection.update_one({'_id': doc['_id']}, {'$set': {'pronostici': pronostici}})
    print(f"   🎛️ Mixer ri-taggati: {mixer_count} pronostici")

    # 1c-ter. PROTEZIONE -3h: ripristina tip del mattino che matchano la whitelist
    # di protezione se il -3h li ha eliminati. Marca i tip ripristinati con
    # _protected_3h=True così il -1h non li potrà eliminare.
    if run_label == 'update_3h' and tip_pre_3h:
        restored_3h = 0
        docs_3h = list(unified_collection.find(
            {'date': date_str, 'match_time': {'$in': effective_times}},
            {'_id': 1, 'home': 1, 'away': 1, 'pronostici': 1}
        ))
        for doc in docs_3h:
            mk = normalize_match_key(date_str, doc.get('home', ''), doc.get('away', ''))
            pre_tips = tip_pre_3h.get(mk, [])
            if not pre_tips:
                continue
            pronostici = doc.get('pronostici') or []
            changed = False
            for pre_t in pre_tips:
                pre_tipo = pre_t.get('tipo')
                pre_pron = pre_t.get('pronostico')
                # Cerca corrispondente nello stato post-orchestratore
                found_active = False
                idx_nobet = None
                for i, p in enumerate(pronostici):
                    if p.get('tipo') == pre_tipo and p.get('pronostico') == pre_pron:
                        if (p.get('stake') or 0) > 0:
                            found_active = True
                        break
                    if p.get('tipo') == pre_tipo and (p.get('pronostico') == 'NO BET' or (p.get('stake') or 0) <= 0):
                        idx_nobet = i
                if found_active:
                    continue  # tip ancora attivo
                if not _matches_protezione_3h(pre_t):
                    continue
                # Ripristino con marker di protezione
                pre_clean = dict(pre_t)
                pre_clean['_protected_3h'] = True
                if idx_nobet is not None:
                    pronostici[idx_nobet] = pre_clean
                else:
                    pronostici.append(pre_clean)
                restored_3h += 1
                changed = True
            if changed:
                unified_collection.update_one({'_id': doc['_id']}, {'$set': {'pronostici': pronostici}})
        print(f"   🛡️ Protezione -3h: {restored_3h} tip ripristinati (matchavano whitelist protezione)")

    # 1c-bis. PROTEZIONE -1h: ripristina tip che matchano la whitelist di protezione
    # Se il -1h ha tolto un tip (attivo all'intermedio, ora NO BET/stake=0) che
    # matcha i pattern di protezione, lo rimettiamo come era.
    if run_label == 'update_1h' and tip_pre_1h:
        restored_count = 0
        restored_docs = list(unified_collection.find(
            {'date': date_str, 'match_time': {'$in': effective_times}},
            {'_id': 1, 'home': 1, 'away': 1, 'pronostici': 1}
        ))
        for doc in restored_docs:
            mk = normalize_match_key(date_str, doc.get('home', ''), doc.get('away', ''))
            pre_tips = tip_pre_1h.get(mk, [])
            if not pre_tips:
                continue
            pronostici = doc.get('pronostici') or []
            changed = False
            # Per ogni tip attivo all'intermedio, verifica se è stato rimosso e se è protetto
            for pre_t in pre_tips:
                pre_tipo = pre_t.get('tipo')
                pre_pron = pre_t.get('pronostico')
                era_matt = pre_t.get('_era_al_mattino', False)
                # Cerca il corrispondente nello stato post-orchestratore
                found_active = False
                idx_nobet = None
                for i, p in enumerate(pronostici):
                    if p.get('tipo') == pre_tipo and p.get('pronostico') == pre_pron:
                        if (p.get('stake') or 0) > 0:
                            found_active = True
                        break
                    if p.get('tipo') == pre_tipo and (p.get('pronostico') == 'NO BET' or (p.get('stake') or 0) <= 0):
                        idx_nobet = i
                if found_active:
                    continue  # tip ancora attivo → nulla da ripristinare
                # Tip è stato rimosso: ripristina SE protetto dal -3h O se matcha whitelist -1h
                is_protected_3h = pre_t.get('_protected_3h') is True
                if not is_protected_3h and not _matches_protezione_1h(pre_t, era_matt):
                    continue
                # Ripristino: rimetti il tip pre come era (mantiene _protected_3h se presente)
                pre_clean = {k: v for k, v in pre_t.items() if k != '_era_al_mattino'}
                if idx_nobet is not None:
                    pronostici[idx_nobet] = pre_clean
                else:
                    pronostici.append(pre_clean)
                restored_count += 1
                changed = True
            if changed:
                unified_collection.update_one({'_id': doc['_id']}, {'$set': {'pronostici': pronostici}})
        print(f"   🛡️ Protezione -1h: {restored_count} tip ripristinati (matchavano whitelist protezione)")

    # 1d-bis. WHITELIST FILTER (solo su update_3h)
    # Se il -3h sta aggiungendo un tip su una partita che al mattino era NO BET
    # (nessun tip attivo in 'nightly'), accetta il tip solo se matcha la whitelist.
    # Altrimenti rimuovi il tip (NO BET + stake=0). Il -1h può comunque riattivarlo.
    if run_label == 'update_3h':
        # Recupera la versione nightly per capire quali partite erano NO BET al mattino
        nightly_versions = list(versions_collection.find({
            'date': date_str,
            'match_time': {'$in': effective_times},
            'version': 'nightly'
        }))
        had_tip_at_nightly = set()
        for nv in nightly_versions:
            mk = nv.get('match_key', '')
            for t in (nv.get('tips') or []):
                if t.get('pronostico') and t.get('pronostico') != 'NO BET' and (t.get('stake') or 0) > 0:
                    had_tip_at_nightly.add(mk)
                    break

        kept_3h = 0
        removed_3h = 0
        current_docs_3h = list(unified_collection.find(
            {'date': date_str, 'match_time': {'$in': effective_times}},
            {'_id': 1, 'home': 1, 'away': 1, 'pronostici': 1}
        ))
        for doc in current_docs_3h:
            mk = normalize_match_key(date_str, doc.get('home', ''), doc.get('away', ''))
            if mk in had_tip_at_nightly:
                continue  # partita aveva già tip al mattino: non filtro
            pronostici = doc.get('pronostici') or []
            changed = False
            for p in pronostici:
                if not p.get('pronostico') or p.get('pronostico') == 'NO BET':
                    continue
                if (p.get('stake') or 0) <= 0:
                    continue
                if _matches_whitelist_3h(p):
                    kept_3h += 1
                else:
                    p['pronostico'] = 'NO BET'
                    p['stake'] = 0
                    p['stake_min'] = 0
                    p['stake_max'] = 0
                    removed_3h += 1
                    changed = True
            if changed:
                unified_collection.update_one({'_id': doc['_id']}, {'$set': {'pronostici': pronostici}})
        print(f"   🎯 Whitelist -3h: {kept_3h} tip tenuti, {removed_3h} tip filtrati (partite NO BET al mattino)")

    # 1d. WHITELIST FILTER (solo su update_1h)
    # Se il -1h sta aggiungendo un tip su una partita che era VUOTA alla versione
    # precedente (update_3h), accetta il tip solo se matcha la whitelist storica.
    # Altrimenti rimuovi il tip (metti pronostico='NO BET' + stake=0).
    if run_label == 'update_1h':
        # Recupera la versione precedente (update_3h) per capire quali partite erano vuote
        prev_versions = list(versions_collection.find({
            'date': date_str,
            'match_time': {'$in': effective_times},
            'version': 'update_3h'
        }))
        # Set di match_key che alla versione precedente avevano ALMENO un tip attivo
        had_tip_at_3h = set()
        for pv in prev_versions:
            mk = pv.get('match_key', '')
            for t in (pv.get('tips') or []):
                if t.get('pronostico') and t.get('pronostico') != 'NO BET' and (t.get('stake') or 0) > 0:
                    had_tip_at_3h.add(mk)
                    break

        filter_count_kept = 0
        filter_count_removed = 0
        current_docs = list(unified_collection.find(
            {'date': date_str, 'match_time': {'$in': effective_times}},
            {'_id': 1, 'home': 1, 'away': 1, 'pronostici': 1}
        ))
        for doc in current_docs:
            mk = normalize_match_key(date_str, doc.get('home', ''), doc.get('away', ''))
            # Filtro solo se la partita era vuota a update_3h
            if mk in had_tip_at_3h:
                continue  # partita aveva già tip prima: non toccare
            pronostici = doc.get('pronostici') or []
            changed = False
            for p in pronostici:
                # Tip "attivo" = non NO BET e stake > 0
                if not p.get('pronostico') or p.get('pronostico') == 'NO BET':
                    continue
                if (p.get('stake') or 0) <= 0:
                    continue
                # Applica whitelist (ma NON toccare tip protetti dal -3h)
                if p.get('_protected_3h') is True:
                    filter_count_kept += 1
                elif _matches_whitelist_1h(p):
                    filter_count_kept += 1
                else:
                    # Rimuovi tip: NO BET + stake=0
                    p['pronostico'] = 'NO BET'
                    p['stake'] = 0
                    p['stake_min'] = 0
                    p['stake_max'] = 0
                    filter_count_removed += 1
                    changed = True
            if changed:
                unified_collection.update_one({'_id': doc['_id']}, {'$set': {'pronostici': pronostici}})
        print(f"   🎯 Whitelist -1h: {filter_count_kept} tip tenuti, {filter_count_removed} tip filtrati (partite vuote a -3h)")

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
