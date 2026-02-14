"""
DAEMON QUOTE SNAI — O/U + GG/NG
Gira ad orari fissi: 09, 12, 15, 18, 21, 23, 01.
Stesso pattern di debug_nowgoal_scraper.py.
"""
import os
import sys
import time
import ctypes
import msvcrt
from datetime import datetime, timedelta

# --- LOGGING: output su terminale + file log ---
class _TeeOutput:
    def __init__(self, log_path):
        self.terminal = sys.stdout
        self.log = open(log_path, 'w', encoding='utf-8')
    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
    def flush(self):
        self.terminal.flush()
        self.log.flush()

_log_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_log_root, 'log')):
    _p = os.path.dirname(_log_root)
    if _p == _log_root:
        break
    _log_root = _p
sys.stdout = _TeeOutput(os.path.join(_log_root, 'log', 'quote-snai-ou-gg.txt'))
sys.stderr = sys.stdout
print(f"{'='*50}")
print(f"AVVIO DAEMON QUOTE SNAI: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
print(f"{'='*50}\n")

# FIX PERCORSI
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_dir = os.path.dirname(os.path.dirname(current_dir))
project_root = os.path.dirname(ai_engine_dir)

if ai_engine_dir not in sys.path:
    sys.path.insert(0, ai_engine_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Import dello scraper SNAI esistente
from scrape_snai_odds import run_scraper

# CONFIGURAZIONE — Orari fissi di esecuzione (ore del giorno)
ORARI_RUN = [1, 9, 12, 15, 18, 21, 23]

# --- PAUSA PIPELINE NOTTURNA ---
PIPELINE_PAUSE_START_H = 3   # Ora inizio pausa
PIPELINE_PAUSE_START_M = 30  # Minuto inizio pausa
PIPELINE_PAUSE_END_H = 9     # Ora fine pausa

def is_pipeline_window():
    """Pausa durante la pipeline notturna (03:30-09:00) per evitare conflitti Chrome/chromedriver."""
    now = datetime.now()
    return (now.hour == PIPELINE_PAUSE_START_H and now.minute >= PIPELINE_PAUSE_START_M) or \
           (PIPELINE_PAUSE_START_H < now.hour < PIPELINE_PAUSE_END_H)


def prossimo_orario():
    """Calcola il prossimo orario di esecuzione."""
    now = datetime.now()
    ora_corrente = now.hour * 60 + now.minute  # minuti dalla mezzanotte

    for h in ORARI_RUN:
        target = h * 60  # minuti dalla mezzanotte
        if target > ora_corrente:
            return now.replace(hour=h, minute=0, second=0, microsecond=0)

    # Se tutti gli orari di oggi sono passati, prendi il primo di domani
    domani = now + timedelta(days=1)
    return domani.replace(hour=ORARI_RUN[0], minute=0, second=0, microsecond=0)


def run_snai_loop():
    orari_str = ", ".join(f"{h:02d}:00" for h in ORARI_RUN)
    print(f"\n{'='*55}")
    print(f" 🎰 DAEMON QUOTE SNAI — O/U + GG/NG")
    print(f" 📊 Orari fissi: {orari_str}")
    print(f"{'='*55}")
    print(" ⌨️  Premi 'H' per NASCONDERE questa finestra")
    print(" ⌨️  Premi 'CTRL+C' per terminare il processo\n")

    heartbeat = ["❤️", "   "]

    while True:
        # --- PAUSA PIPELINE NOTTURNA (03:30-09:00) ---
        if is_pipeline_window():
            sys.stdout.write(f"\r 💤 [PAUSA PIPELINE] {datetime.now().strftime('%H:%M:%S')} | Ripresa alle 09:00...          ")
            sys.stdout.flush()
            time.sleep(60)
            continue

        # Calcola prossimo orario
        target = prossimo_orario()
        secondi_attesa = (target - datetime.now()).total_seconds()

        if secondi_attesa > 0:
            print(f"\n ⏰ Prossimo run: {target.strftime('%H:%M')} (tra {int(secondi_attesa // 60)} min)")

            # Attesa con heartbeat (cicli da 10 sec)
            cicli = int(secondi_attesa / 10) + 1
            for i in range(cicli):
                # Check pausa pipeline durante l'attesa
                if is_pipeline_window():
                    break

                # Controllo pressione tasto H
                if msvcrt.kbhit():
                    tasto = msvcrt.getch().decode('utf-8').lower()
                    if tasto == 'h':
                        ctypes.windll.user32.ShowWindow(
                            ctypes.windll.kernel32.GetConsoleWindow(), 0
                        )
                        print("\n👻 Finestra nascosta! Il monitoraggio quote SNAI continua in background.")

                # Controlla se è ora di partire
                if datetime.now() >= target:
                    break

                h = heartbeat[i % 2]
                orario_live = datetime.now().strftime("%H:%M:%S")
                min_mancanti = max(0, int((target - datetime.now()).total_seconds() // 60))
                sys.stdout.write(f"\r 🎰 [SNAI] {h} {orario_live} | Prossimo run alle {target.strftime('%H:%M')} (tra {min_mancanti} min)  ")
                sys.stdout.flush()
                time.sleep(10)

            # Se siamo entrati nella pausa durante l'attesa, torna al while
            if is_pipeline_window():
                continue

        # --- ESECUZIONE SCRAPER ---
        print(f"\n\n 🚀 Avvio scraper SNAI — {datetime.now().strftime('%H:%M:%S')}")
        try:
            run_scraper()
        except Exception as e:
            print(f"\n❌ Errore durante lo scarico SNAI: {e}")

        print(f" ✅ Scraper completato — {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    run_snai_loop()
