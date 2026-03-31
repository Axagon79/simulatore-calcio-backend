"""
pre_match_quote_anomale.py — Aggiornamento quote anomale

Due meccanismi di aggiornamento:

A) ORARI FISSI (senza logica blocchi):
   09:00, 12:00, 15:00, 18:00, 21:00, 23:00
   Scrapa TUTTE le partite del giorno → quote live + indicatori.
   L'utente ha sempre dati freschi a qualsiasi ora.

B) PRE-MATCH A BLOCCHI (-3h e -1h):
   Raggruppamento per blocchi orari (gap ≤30min, span ≤90min).
   Due run per blocco: -3h e -1h dal primo kickoff.
   Cattura gli ultimi movimenti pre-partita.

Chiamato da cron ogni 15 minuti (09:00-23:30).

Uso:
  python pre_match_quote_anomale.py              # oggi, ora corrente
  python pre_match_quote_anomale.py 2026-03-31   # data specifica
  python pre_match_quote_anomale.py 2026-03-31 17:45  # simula ora (test)
"""

import sys
import os
import argparse
import logging
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, 'pre_match_quote_anomale.log')

# Setup logging
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('pre_match_qa')

# Fix percorsi
ai_engine_dir = os.path.dirname(os.path.dirname(SCRIPT_DIR))
project_root = os.path.dirname(ai_engine_dir)
if ai_engine_dir not in sys.path:
    sys.path.insert(0, ai_engine_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config import db
from ai_engine.Aggiornamenti.frequenti.scraper_quote_anomale_lucksport import run_scraper
from ai_engine.Aggiornamenti.frequenti.calcola_indicatori_quote_anomale import calcola_e_aggiorna

# Collections
qa_collection = db['quote_anomale']
run_log_collection = db['pre_match_qa_run_log']

# --- CONFIGURAZIONE ---

# A) Orari fissi (minuti dall'inizio della giornata)
ORARI_FISSI = [
    9 * 60,       # 09:00
    12 * 60,      # 12:00
    15 * 60,      # 15:00
    18 * 60,      # 18:00
    21 * 60,      # 21:00
    23 * 60,      # 23:00
]

# B) Blocchi pre-match
MAX_CONSECUTIVE_GAP = 30   # Gap max tra orari consecutivi (minuti)
MAX_BLOCK_SPAN = 90        # Span max primo-ultimo nel blocco (minuti)
BLOCK_RUNS = [
    (180, 'block_3h'),     # -3h prima del primo kickoff
    (60, 'block_1h'),      # -1h prima del primo kickoff
]

TOLERANCE_MINUTES = 10     # Finestra ±10 min dal trigger


# =====================================================
# UTILITY
# =====================================================
def parse_match_time(time_str):
    """Converte 'HH:MM' in minuti dall'inizio della giornata."""
    try:
        parts = time_str.split(':')
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError, AttributeError):
        return None


def group_by_time_window(matches):
    """Raggruppa le partite per blocchi orari."""
    time_set = set()
    for m in matches:
        mt = m.get('match_time', '')
        if mt and parse_match_time(mt) is not None:
            time_set.add(mt)

    if not time_set:
        return []

    sorted_times = sorted(time_set, key=lambda t: parse_match_time(t))
    groups = []
    current_group = [sorted_times[0]]

    for t in sorted_times[1:]:
        t_min = parse_match_time(t)
        prev_min = parse_match_time(current_group[-1])
        first_min = parse_match_time(current_group[0])

        if (t_min - prev_min) <= MAX_CONSECUTIVE_GAP and (t_min - first_min) <= MAX_BLOCK_SPAN:
            current_group.append(t)
        else:
            groups.append(current_group)
            current_group = [t]

    groups.append(current_group)
    return groups


# =====================================================
# IDEMPOTENZA
# =====================================================
def is_already_run(date_str, run_key):
    """Controlla se questo run è già stato eseguito oggi."""
    return run_log_collection.find_one({
        'date': date_str,
        'run_key': run_key,
    }) is not None


def save_run_log(date_str, run_key, details=None):
    """Salva log del run eseguito."""
    run_log_collection.insert_one({
        'date': date_str,
        'run_key': run_key,
        'details': details,
        'created_at': datetime.now(timezone.utc),
    })


# =====================================================
# ESECUZIONE SCRAPE + CALCOLO
# =====================================================
def esegui_aggiornamento(date_str, label):
    """Scrapa quote live + calcola indicatori."""
    print(f"   📊 [{label}] Scraping quote live...")
    run_scraper(target_date=date_str, mode='live', headless=True)

    print(f"   🔬 [{label}] Calcolo indicatori...")
    calcolati, errori = calcola_e_aggiorna(target_date=date_str)
    print(f"   ✅ [{label}] Calcolati: {calcolati}, errori: {errori}")
    return calcolati, errori


# =====================================================
# MAIN
# =====================================================
def main():
    parser = argparse.ArgumentParser(description='Pre-Match Quote Anomale')
    parser.add_argument('date', nargs='?', default=None, help='Data YYYY-MM-DD')
    parser.add_argument('time', nargs='?', default=None, help='Ora HH:MM (test)')
    args = parser.parse_args()

    # Data
    today = datetime.now()
    date_str = args.date or today.strftime('%Y-%m-%d')

    # Ora corrente (o simulata)
    if args.time:
        now_minutes = parse_match_time(args.time)
    else:
        now_minutes = today.hour * 60 + today.minute

    now_str = f"{now_minutes // 60:02d}:{now_minutes % 60:02d}"

    print(f"\n{'='*60}")
    print(f"⚡ QUOTE ANOMALE — Aggiornamento")
    print(f"   Data: {date_str}")
    print(f"   Ora:  {now_str}")
    print(f"{'='*60}")
    logger.info(f"Start — data={date_str}, ora={now_str}")

    executed = 0

    # ===================================================
    # A) ORARI FISSI
    # ===================================================
    for orario in ORARI_FISSI:
        if abs(now_minutes - orario) <= TOLERANCE_MINUTES:
            run_key = f"fisso_{orario // 60:02d}:{orario % 60:02d}"

            if is_already_run(date_str, run_key):
                print(f"\n   ⏭️  Orario fisso {orario // 60:02d}:00: già eseguito")
                continue

            print(f"\n   🕐 Orario fisso {orario // 60:02d}:00 — aggiornamento TUTTE le partite")
            logger.info(f"Orario fisso {run_key}")

            try:
                esegui_aggiornamento(date_str, run_key)
                save_run_log(date_str, run_key, {"tipo": "orario_fisso"})
                executed += 1
            except Exception as e:
                print(f"   ❌ Errore orario fisso: {e}")
                logger.error(f"Errore {run_key}: {e}")

            # Un solo orario fisso per invocazione
            break

    # ===================================================
    # B) BLOCCHI PRE-MATCH (-3h, -1h)
    # ===================================================
    docs = list(qa_collection.find({'date': date_str}, {'match_time': 1}))
    if docs:
        groups = group_by_time_window(docs)
        print(f"\n   Blocchi orari: {len(groups)}")

        for group_times in groups:
            first_kickoff = parse_match_time(group_times[0])
            block_id = group_times[0]

            for offset, run_label in BLOCK_RUNS:
                trigger_time = first_kickoff - offset

                if abs(now_minutes - trigger_time) <= TOLERANCE_MINUTES:
                    run_key = f"{run_label}_{block_id}"

                    if is_already_run(date_str, run_key):
                        print(f"   ⏭️  Blocco {block_id} ({run_label}): già eseguito")
                        continue

                    trigger_str = f"{trigger_time // 60:02d}:{trigger_time % 60:02d}"
                    print(f"\n   🎯 Blocco {block_id} ({run_label}) — trigger {trigger_str}")
                    logger.info(f"Blocco {run_key}, times={group_times}")

                    try:
                        esegui_aggiornamento(date_str, run_key)
                        save_run_log(date_str, run_key, {
                            "tipo": "blocco_prematch",
                            "block_times": group_times,
                        })
                        executed += 1
                    except Exception as e:
                        print(f"   ❌ Errore blocco {run_key}: {e}")
                        logger.error(f"Errore {run_key}: {e}")

    # ===================================================
    # RIEPILOGO
    # ===================================================
    if executed == 0:
        print(f"\n   Nessun aggiornamento da eseguire in questo momento.")
    else:
        print(f"\n   ✅ Aggiornamenti eseguiti: {executed}")

    logger.info(f"Fine — {executed} aggiornamenti eseguiti")


if __name__ == '__main__':
    main()
