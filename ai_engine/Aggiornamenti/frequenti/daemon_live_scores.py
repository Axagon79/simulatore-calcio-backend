"""
DAEMON LIVE SCORES — Scraping NowGoal Live Page
Aggiorna live_score, live_status e live_minute in h2h_by_round ogni 2 minuti.
Usa campi SEPARATI da real_score/status per evitare conflitti con gli altri scraper.
"""
import os
import sys
import time
import re
import ctypes
ctypes.windll.kernel32.SetConsoleTitleW("Daemon Risultati Live (daemon_live_scores.py)")
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
sys.stdout = _TeeOutput(os.path.join(_log_root, 'log', 'risultati-live-nowgoal.txt'))
sys.stderr = sys.stdout
print(f"{'='*50}")
print(f"AVVIO DAEMON LIVE SCORES (NowGoal): {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
print(f"{'='*50}\n")

from typing import Dict, List, Optional

# FIX PERCORSI
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_dir = os.path.dirname(os.path.dirname(current_dir))
project_root = os.path.dirname(ai_engine_dir)

if ai_engine_dir not in sys.path: sys.path.insert(0, ai_engine_dir)
if project_root not in sys.path: sys.path.insert(0, project_root)

try:
    from config import db
    print(f"DB Connesso: {db.name}")
except ImportError:
    sys.path.append(r"C:\Progetti\simulatore-calcio-backend\ai_engine")
    try:
        from config import db
    except:
        sys.exit(1)

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    print("Errore: Selenium non installato.")
    sys.exit(1)

# --- CONFIG ---
LIVE_URL = "https://live4.nowgoal26.com/"
CYCLE_SECONDS = 120       # Ogni 2 minuti
_leagues_selected = False  # Flag: "Select All" leagues già cliccato
PAGE_LOAD_WAIT = 5        # Secondi di attesa dopo navigazione
RESTART_EVERY_N_CYCLES = 50  # Restart preventivo del driver ogni N cicli
_cycle_count = 0          # Contatore cicli per restart periodico
HOUR_START = 10            # Inizio finestra operativa
HOUR_END = 1               # Fine (giorno dopo, 01:00)

# --- PAUSA PIPELINE NOTTURNA ---
PIPELINE_PAUSE_START_H = 3   # Ora inizio pausa
PIPELINE_PAUSE_START_M = 30  # Minuto inizio pausa
PIPELINE_PAUSE_END_H = 9     # Ora fine pausa

def is_pipeline_window():
    """Pausa durante la pipeline notturna (03:30-09:00) per evitare conflitti Chrome/chromedriver."""
    now = datetime.now()
    return (now.hour == PIPELINE_PAUSE_START_H and now.minute >= PIPELINE_PAUSE_START_M) or \
           (PIPELINE_PAUSE_START_H < now.hour < PIPELINE_PAUSE_END_H)

# --- FUNZIONI MATCHING (copiate da debug_nowgoal_scraper.py) ---

def normalize_name(name: str) -> str:
    if not name:
        return ""
    name = name.lower().strip()

    replacements = {
        "ü": "u", "ö": "o", "é": "e", "è": "e", "à": "a",
        "ñ": "n", "ã": "a", "ç": "c", "á": "a", "í": "i",
        "ó": "o", "ú": "u", "ê": "e", "ô": "o", "â": "a",
    }
    for old, new in replacements.items():
        name = name.replace(old, new)

    prefixes = ["fc ", "cf ", "ac ", "as ", "sc ", "us ", "ss ", "asd ", "asc "]
    for prefix in prefixes:
        if name.startswith(prefix):
            name = name[len(prefix):]

    suffixes = [" fc", " cf", " ac", " calcio", " 1913", " 1928", " 1918", " united", " city"]
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]

    specific_mappings = {
        "inter milan": "inter", "inter milano": "inter",
        "juve next gen": "juventus u23", "juventus ng": "juventus u23",
        "hellas verona": "verona", "giana erminio": "giana",
        "manchester utd": "manchester united", "man utd": "manchester united",
        "man city": "manchester city", "nott'm forest": "nottingham forest",
        "nottingham": "nottingham forest", "west ham utd": "west ham",
        "brighton": "brighton hove albion", "wolves": "wolverhampton",
        "atletico": "atletico madrid", "barcellona": "barcelona",
        "siviglia": "sevilla", "celta de vigo": "celta vigo",
        "celta": "celta vigo", "athletic club": "athletic bilbao",
        "bayern": "bayern munchen", "bayern monaco": "bayern munchen",
        "leverkusen": "bayer leverkusen", "dortmund": "borussia dortmund",
        "leipzig": "rb leipzig", "lipsia": "rb leipzig",
        "gladbach": "monchengladbach", "m'gladbach": "monchengladbach",
        "marsiglia": "marseille", "nizza": "nice", "lione": "lyon",
        "psg": "paris saint germain",
        "sporting cp": "sporting", "sporting lisbona": "sporting",
    }
    for old, new in specific_mappings.items():
        if old in name:
            name = name.replace(old, new)
    return name.strip()


def get_team_aliases(team_name: str, team_doc: Optional[Dict] = None) -> List[str]:
    aliases = set()
    aliases.add(team_name.lower().strip())
    normalized = normalize_name(team_name)
    if normalized:
        aliases.add(normalized)
    if team_doc and 'aliases' in team_doc:
        for alias in team_doc['aliases']:
            if alias and alias.strip():
                aliases.add(alias.lower().strip())
                normalized_alias = normalize_name(alias)
                if normalized_alias:
                    aliases.add(normalized_alias)
    words = team_name.lower().split()
    if len(words) > 1:
        for word in words:
            if len(word) >= 4:
                aliases.add(word)
    if normalized:
        words_norm = normalized.split()
        if len(words_norm) > 1:
            for word in words_norm:
                if len(word) >= 4:
                    aliases.add(word)
    aliases.discard("")
    return list(aliases)


def strip_ranking(name: str) -> str:
    """Rimuove il numero di ranking iniziale (es. '2 Chelsea' -> 'Chelsea')"""
    return re.sub(r'^\d+\s+', '', name.strip())


# --- FUNZIONI CORE ---

def get_today_matches_from_db():
    """Carica le partite di oggi da h2h_by_round con aggregation pipeline."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)

    pipeline = [
        {"$unwind": "$matches"},
        {"$match": {"matches.date_obj": {"$gte": today, "$lt": tomorrow}}},
        {"$project": {
            "league": 1,
            "round_id": "$_id",
            "match": "$matches"
        }}
    ]

    matches = []
    for doc in db.h2h_by_round.aggregate(pipeline):
        m = doc['match']
        m['_league'] = doc.get('league', 'Unknown')
        m['_round_id'] = doc.get('round_id')
        matches.append(m)

    return matches


def load_team_docs_batch(matches):
    """Pre-carica tutti i team doc dal DB in un'unica query."""
    team_names = set()
    for m in matches:
        team_names.add(m.get('home', ''))
        team_names.add(m.get('away', ''))
    team_names.discard('')

    team_docs = {}
    for doc in db.teams.find({"name": {"$in": list(team_names)}}):
        team_docs[doc['name']] = doc
    return team_docs


def parse_nowgoal_live_page(driver) -> List[Dict]:
    """Estrae tutte le partite dalla pagina live di NowGoal."""
    nowgoal_matches = []

    try:
        rows = driver.find_elements(By.CSS_SELECTOR, "tr.tds")
    except Exception as e:
        print(f"   Errore ricerca righe: {e}")
        return []

    for row in rows:
        try:
            tds = row.find_elements(By.TAG_NAME, "td")
            if len(tds) < 8:
                continue

            # TD[3] = status/minuto, TD[5] = home, TD[6] = score, TD[7] = away
            status_text = tds[3].text.strip()
            home_text = strip_ranking(tds[5].text.strip())
            score_text = tds[6].text.strip()
            away_text = strip_ranking(tds[7].text.strip())

            if not home_text or not away_text:
                continue

            # Determina stato
            if status_text.isdigit():
                minute = int(status_text)
                status = "Live"
            elif status_text.upper() in ("HT", "HALF"):
                minute = 45
                status = "HT"
            elif status_text.upper() in ("FT", "AET"):
                minute = 90
                status = "Finished"
            elif "+" in status_text:
                # Recupero extra (es. "45+2", "90+3")
                parts = status_text.split("+")
                try:
                    minute = int(parts[0]) + int(parts[1])
                except:
                    minute = int(parts[0]) if parts[0].isdigit() else 0
                status = "Live"
            else:
                # Partita non ancora iniziata o stato sconosciuto
                continue

            # Parse score: "1 - 0" -> "1:0"
            score_match = re.match(r'(\d+)\s*-\s*(\d+)', score_text)
            if not score_match:
                continue
            score = f"{score_match.group(1)}:{score_match.group(2)}"

            nowgoal_matches.append({
                "home": home_text,
                "away": away_text,
                "score": score,
                "minute": minute,
                "status": status,
                "home_normalized": normalize_name(home_text),
                "away_normalized": normalize_name(away_text),
            })

        except Exception:
            continue

    return nowgoal_matches


def find_nowgoal_match(db_match, nowgoal_matches, team_docs):
    """Cerca una partita del DB nella lista NowGoal usando alias matching."""
    home_name = db_match.get('home', '')
    away_name = db_match.get('away', '')

    home_doc = team_docs.get(home_name)
    away_doc = team_docs.get(away_name)

    home_aliases = set(get_team_aliases(home_name, home_doc))
    away_aliases = set(get_team_aliases(away_name, away_doc))

    for ng in nowgoal_matches:
        ng_home_aliases = {ng['home'].lower(), ng['home_normalized']}
        ng_away_aliases = {ng['away'].lower(), ng['away_normalized']}

        # Aggiungi parole singole del nome NowGoal (per match parziale)
        for word in ng['home'].lower().split():
            if len(word) >= 4:
                ng_home_aliases.add(word)
        for word in ng['away'].lower().split():
            if len(word) >= 4:
                ng_away_aliases.add(word)

        # Check intersezione alias
        home_match = bool(home_aliases & ng_home_aliases)
        away_match = bool(away_aliases & ng_away_aliases)

        if home_match and away_match:
            return ng

    return None


def run_cycle(driver):
    """Esegue un ciclo completo: fetch DB -> scrape NowGoal -> update DB."""
    cycle_start = datetime.now()
    print(f"\n{'='*50}")
    print(f"CICLO LIVE: {cycle_start.strftime('%H:%M:%S')}")
    print(f"{'='*50}")

    # 1. Carica partite di oggi dal DB
    db_matches = get_today_matches_from_db()
    if not db_matches:
        print("   Nessuna partita oggi nel DB.")
        return

    print(f"   Partite nel DB: {len(db_matches)}")

    # 2. Pre-carica team docs
    team_docs = load_team_docs_batch(db_matches)
    print(f"   Team docs caricati: {len(team_docs)}")

    # 3. Scrape NowGoal
    try:
        driver.get(LIVE_URL)
        time.sleep(PAGE_LOAD_WAIT)
    except Exception as e:
        print(f"   Errore navigazione: {e}")
        raise  # Propaga l'errore per triggerare il restart del driver nel main loop

    # 3b. Al primo ciclo, clicca "Select All" per mostrare tutte le leghe
    global _leagues_selected
    if not _leagues_selected:
        try:
            filter_btn = driver.find_element(By.ID, "li_FilterLea")
            filter_btn.click()
            time.sleep(1)
            links = driver.find_elements(By.CSS_SELECTOR, "#FilterLeaPop a, #FilterLeaPop span")
            for link in links:
                if "Select All" in link.text:
                    link.click()
                    break
            time.sleep(0.5)
            for link in links:
                if "Confirm" in link.text:
                    link.click()
                    break
            time.sleep(2)
            _leagues_selected = True
            print("   Filtro leghe: Select All applicato")
        except Exception as e:
            print(f"   Filtro leghe non trovato (proseguo): {e}")
            _leagues_selected = True  # Non riprovare ogni ciclo

    nowgoal_matches = parse_nowgoal_live_page(driver)
    live_count = sum(1 for m in nowgoal_matches if m['status'] == 'Live')
    ht_count = sum(1 for m in nowgoal_matches if m['status'] == 'HT')
    ft_count = sum(1 for m in nowgoal_matches if m['status'] == 'Finished')
    print(f"   NowGoal: {len(nowgoal_matches)} partite (Live:{live_count} HT:{ht_count} FT:{ft_count})")

    if not nowgoal_matches:
        print("   Nessuna partita attiva su NowGoal.")
        return

    # 4. Matching e aggiornamento atomico (positional operator $)
    updated_count = 0
    matched_count = 0

    for db_match in db_matches:
        round_id = db_match.get('_round_id')
        if not round_id:
            continue

        ng_match = find_nowgoal_match(db_match, nowgoal_matches, team_docs)
        if not ng_match:
            continue

        matched_count += 1

        # Verifica se ci sono cambiamenti
        old_score = db_match.get('live_score')
        old_status = db_match.get('live_status')
        old_minute = db_match.get('live_minute')

        new_score = ng_match['score']
        new_status = ng_match['status']
        new_minute = ng_match['minute']

        if old_score == new_score and old_status == new_status and old_minute == new_minute:
            continue  # Nessun cambiamento

        home = db_match.get('home', '?')
        away = db_match.get('away', '?')

        # Update atomico con positional operator $
        update_fields = {
            "matches.$.live_score": new_score,
            "matches.$.live_status": new_status,
            "matches.$.live_minute": new_minute
        }
        # Se FT, scrivi anche real_score e status per risultato immediato
        if new_status == "Finished":
            update_fields["matches.$.real_score"] = new_score
            update_fields["matches.$.status"] = "Finished"

        result = db.h2h_by_round.update_one(
            {"_id": round_id, "matches.home": home, "matches.away": away},
            {"$set": update_fields}
        )

        if result.modified_count > 0:
            updated_count += 1
            print(f"   {new_status:8s} {new_minute:3d}' | {home} {new_score} {away}")

    print(f"\n   Matched: {matched_count} | Aggiornati: {updated_count}")

    elapsed = (datetime.now() - cycle_start).total_seconds()
    print(f"   Ciclo completato in {elapsed:.1f}s")


def is_in_operating_window():
    """Verifica se siamo nella finestra operativa (10:00 - 01:00)."""
    hour = datetime.now().hour
    return hour >= HOUR_START or hour < HOUR_END


def create_driver(service, chrome_options):
    """Crea un nuovo Chrome driver con timeout configurati."""
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(30)  # Max 30s per caricare una pagina
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def restart_driver(driver, service, chrome_options, reason="periodico"):
    """Chiude e ricrea il driver Chrome."""
    global _leagues_selected
    print(f"   Restart driver ({reason})...")
    try: driver.quit()
    except: pass
    new_driver = create_driver(service, chrome_options)
    _leagues_selected = False  # Deve rifare "Select All" sul nuovo browser
    print(f"   Nuovo driver avviato.")
    return new_driver


def main():
    global _cycle_count
    print(f"Configurazione: ciclo ogni {CYCLE_SECONDS}s, finestra {HOUR_START}:00-{HOUR_END}:00")
    print(f"Restart driver ogni {RESTART_EVERY_N_CYCLES} cicli")
    print(f"URL: {LIVE_URL}\n")

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)")

    driver = None

    try:
        service = Service(ChromeDriverManager().install())
        driver = create_driver(service, chrome_options)
        print("Chrome driver avviato.\n")

        while True:
            # --- PAUSA PIPELINE NOTTURNA (03:30-09:00) ---
            if is_pipeline_window():
                if driver is not None:
                    try: driver.quit()
                    except: pass
                    driver = None
                    _cycle_count = 0
                    print(f"\n   💤 [PAUSA PIPELINE] Chrome chiuso alle {datetime.now().strftime('%H:%M')}. Ripresa alle 09:00...")
                time.sleep(60)
                continue

            # Riavvia driver se era stato chiuso dalla pausa pipeline
            if driver is None:
                print(f"\n   🔄 Ripresa dopo pausa pipeline — riavvio Chrome...")
                driver = create_driver(service, chrome_options)
                _cycle_count = 0

            if is_in_operating_window():
                # Restart preventivo ogni N cicli per evitare memory leak
                _cycle_count += 1
                if _cycle_count >= RESTART_EVERY_N_CYCLES:
                    driver = restart_driver(driver, service, chrome_options, f"preventivo dopo {_cycle_count} cicli")
                    _cycle_count = 0

                try:
                    run_cycle(driver)
                except Exception as e:
                    print(f"\n   ERRORE nel ciclo: {e}")
                    import traceback
                    traceback.print_exc()
                    # Se il driver e' crashato, ricrealo
                    try:
                        driver.title  # Test se il driver e' ancora vivo
                    except:
                        driver = restart_driver(driver, service, chrome_options, "driver crashato")
                        _cycle_count = 0
            else:
                now = datetime.now()
                print(f"\r   Fuori finestra operativa ({now.strftime('%H:%M')}). Prossimo check tra {CYCLE_SECONDS}s...", end='')

            time.sleep(CYCLE_SECONDS)

    except KeyboardInterrupt:
        print("\n\nDaemon fermato dall'utente.")
    finally:
        if driver:
            try: driver.quit()
            except: pass
        print("Driver chiuso.")


if __name__ == "__main__":
    main()
