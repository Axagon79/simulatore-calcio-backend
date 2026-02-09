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
        # Calcola prossimo orario
        target = prossimo_orario()
        secondi_attesa = (target - datetime.now()).total_seconds()

        if secondi_attesa > 0:
            print(f"\n ⏰ Prossimo run: {target.strftime('%H:%M')} (tra {int(secondi_attesa // 60)} min)")

            # Attesa con heartbeat (cicli da 10 sec)
            cicli = int(secondi_attesa / 10) + 1
            for i in range(cicli):
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

        # --- ESECUZIONE SCRAPER ---
        print(f"\n\n 🚀 Avvio scraper SNAI — {datetime.now().strftime('%H:%M:%S')}")
        try:
            run_scraper()
        except Exception as e:
            print(f"\n❌ Errore durante lo scarico SNAI: {e}")

        print(f" ✅ Scraper completato — {datetime.now().strftime('%H:%M:%S')}")


if __name__ == "__main__":
    run_snai_loop()
