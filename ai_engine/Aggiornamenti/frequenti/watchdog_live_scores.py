"""
WATCHDOG LIVE SCORES — Monitora il daemon e lo riavvia se si blocca.
Controlla il file heartbeat ogni 60 secondi.
Se il heartbeat è fermo da più di 5 minuti, killa il processo e lo rilancia.

Uso: python watchdog_live_scores.py
Metti in Task Scheduler di Windows per avvio automatico.
"""
import os
import sys
import time
import subprocess
import ctypes
ctypes.windll.kernel32.SetConsoleTitleW("Watchdog Live Scores")
from datetime import datetime, timedelta

# --- CONFIG ---
DAEMON_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daemon_live_scores.py")
HEARTBEAT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "heartbeat_live_scores.txt")
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchdog_log.txt")
CHECK_INTERVAL = 60       # Controlla ogni 60 secondi
STALE_THRESHOLD = 300     # 5 minuti senza heartbeat = riavvia
STARTUP_GRACE = 180       # 3 minuti di grazia dopo avvio prima di controllare

daemon_process = None
last_start_time = None


def log(msg):
    """Scrive nel log e stampa a console."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + "\n")
    except:
        pass


def read_heartbeat():
    """Legge il timestamp dal file heartbeat. Ritorna None se non esiste o errore."""
    try:
        with open(HEARTBEAT_FILE, 'r') as f:
            ts_str = f.read().strip()
        return datetime.fromisoformat(ts_str)
    except:
        return None


def kill_daemon():
    """Termina il processo daemon e tutti i Chrome orfani."""
    global daemon_process
    if daemon_process and daemon_process.poll() is None:
        log("Terminazione daemon in corso...")
        try:
            daemon_process.terminate()
            daemon_process.wait(timeout=10)
        except:
            try:
                daemon_process.kill()
            except:
                pass
    daemon_process = None

    # Killa eventuali Chrome zombie
    try:
        subprocess.run(
            ['taskkill', '/F', '/IM', 'chrome.exe', '/FI', 'WINDOWTITLE eq '],
            capture_output=True, timeout=10
        )
    except:
        pass


def start_daemon():
    """Avvia il daemon come subprocess."""
    global daemon_process, last_start_time
    log(f"Avvio daemon: {DAEMON_SCRIPT}")
    daemon_process = subprocess.Popen(
        [sys.executable, DAEMON_SCRIPT],
        cwd=os.path.dirname(DAEMON_SCRIPT),
    )
    last_start_time = datetime.now()
    log(f"Daemon avviato (PID: {daemon_process.pid})")


def main():
    global daemon_process

    log("=" * 60)
    log("WATCHDOG LIVE SCORES — Avviato")
    log(f"Daemon: {DAEMON_SCRIPT}")
    log(f"Heartbeat: {HEARTBEAT_FILE}")
    log(f"Soglia stale: {STALE_THRESHOLD}s ({STALE_THRESHOLD // 60} min)")
    log("=" * 60)

    # Avvia il daemon
    start_daemon()

    restart_count = 0

    try:
        while True:
            time.sleep(CHECK_INTERVAL)

            # 1. Check se il processo è ancora vivo
            if daemon_process and daemon_process.poll() is not None:
                exit_code = daemon_process.returncode
                restart_count += 1
                log(f"Daemon crashato (exit code: {exit_code}). Restart #{restart_count}...")
                kill_daemon()
                time.sleep(10)
                start_daemon()
                continue

            # 2. Check heartbeat (solo dopo il periodo di grazia)
            if last_start_time and (datetime.now() - last_start_time).total_seconds() < STARTUP_GRACE:
                continue  # Ancora in fase di avvio

            hb = read_heartbeat()
            if hb is None:
                log("Heartbeat non trovato — daemon potrebbe essere in avvio, attendo...")
                continue

            age = (datetime.now() - hb).total_seconds()

            if age > STALE_THRESHOLD:
                restart_count += 1
                log(f"HEARTBEAT STALE ({int(age)}s fa). Daemon bloccato! Restart #{restart_count}...")
                kill_daemon()
                time.sleep(10)
                start_daemon()
            else:
                # Heartbeat OK — stampa stato compatto
                print(f"\r   [Watchdog] OK — heartbeat {int(age)}s fa | PID {daemon_process.pid} | restart: {restart_count}", end='')

    except KeyboardInterrupt:
        log("\nWatchdog interrotto dall'utente.")
        kill_daemon()
        log("Daemon terminato. Bye!")


if __name__ == "__main__":
    main()
