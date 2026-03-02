import os
import sys
import time

import ctypes  # // aggiunto per: nascondere la finestra
ctypes.windll.kernel32.SetConsoleTitleW("Direttore Live Risultati (aggiorna_risultati_mirati.py)")
import msvcrt  # // aggiunto per: leggere i tasti senza bloccare il ciclo
import importlib.util
import re
from datetime import datetime, timedelta
import atexit
import signal
import subprocess

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
sys.stdout = _TeeOutput(os.path.join(_log_root, 'log', 'risultati-live.txt'))
sys.stderr = sys.stdout
print(f"{'='*50}")
print(f"AVVIO DIRETTORE RISULTATI: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
print(f"{'='*50}\n")

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- CONFIGURAZIONE PERCORSI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.append(project_root)

# --- ANTI-ZOMBIE: cleanup Chrome orfani all'avvio e all'uscita ---
_current_driver = None

def _cleanup_chrome():
    """Chiude il Chrome driver corrente all'uscita del processo."""
    global _current_driver
    if _current_driver is not None:
        try:
            _current_driver.quit()
            print(f"   [CLEANUP] Chrome chiuso via atexit handler")
        except:
            pass
        _current_driver = None

def _kill_orphan_chrome():
    """All'avvio, killa Chrome zombie (scoped_dir con parent morto)."""
    try:
        r = subprocess.run(
            ['powershell', '-Command',
             '$k=0; Get-CimInstance Win32_Process | Where-Object { $_.Name -eq "chrome.exe" -and $_.CommandLine -match "scoped_dir" } | ForEach-Object { $p=Get-Process -Id $_.ParentProcessId -EA SilentlyContinue; if(-not $p){Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue; $k++} }; if($k -gt 0){Write-Host "Killati $k Chrome zombie"}'],
            capture_output=True, text=True, timeout=30
        )
        if r.stdout.strip():
            print(f"   [CLEANUP] {r.stdout.strip()}")
    except:
        pass

atexit.register(_cleanup_chrome)
try:
    signal.signal(signal.SIGTERM, lambda s, f: (_cleanup_chrome(), sys.exit(0)))
except:
    pass

_kill_orphan_chrome()

try:
    spec = importlib.util.spec_from_file_location("config", os.path.join(project_root, "config.py"))
    config_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_module)
    db = config_module.db
except Exception as e:
    print(f"❌ Errore Config: {e}")
    sys.exit()

# --- SYNC RISULTATI → COLLECTION PRONOSTICI ---
# Quando il daemon scrive un risultato in h2h_by_round, lo propaga anche
# alle collection pronostici come live_score + live_status='Finished'.
# Così il frontend mostra subito il risultato senza aspettare il P/L notturno.
# NON tocca real_score né hit (quelli li calcola il P/L con la logica completa).
PREDICTION_COLLECTIONS_SYNC = [
    'daily_predictions_unified',
    'daily_predictions',
    'daily_predictions_engine_c',
]

def _sync_results_to_predictions(updated_results):
    """Propaga risultati appena trovati alle collection pronostici.
    updated_results: lista di (home, away, date_str, score)
    Scrive live_score + live_status='Finished' SOLO dove real_score è assente.
    """
    if not updated_results:
        return
    total_synced = 0
    for home, away, date_str, score in updated_results:
        # Genera date da provare: esatta + ±1 giorno (timezone mismatch h2h vs predictions)
        dates_to_try = [date_str]
        try:
            d = datetime.strptime(date_str, '%Y-%m-%d')
            dates_to_try.append((d - timedelta(days=1)).strftime('%Y-%m-%d'))
            dates_to_try.append((d + timedelta(days=1)).strftime('%Y-%m-%d'))
        except ValueError:
            pass
        for coll_name in PREDICTION_COLLECTIONS_SYNC:
            try:
                result = db[coll_name].update_many(
                    {
                        'home': home,
                        'away': away,
                        'date': {'$in': dates_to_try},
                        '$or': [
                            {'real_score': None},
                            {'real_score': {'$exists': False}},
                        ],
                    },
                    {'$set': {'live_score': score, 'live_status': 'Finished'}}
                )
                total_synced += result.modified_count
            except Exception:
                pass
    if total_synced > 0:
        print(f"   📋 Sync: {total_synced} pronostici aggiornati con risultati")

# --- TARGET_CONFIG UNIFICATO ---
# // modificato per: contenere tutte le chiavi richieste dalle funzioni originali
TARGET_CONFIG = {
    "Serie A": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/italy/serie-a/results/", "id_prefix": "SerieA", "league_name": "Serie A"},
    "Serie B": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/italy/serie-b/results/", "id_prefix": "SerieB", "league_name": "Serie B"},
    "Serie C - Girone A": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/italy/serie-c-group-a/results/", "id_prefix": "SerieC-GironeA", "league_name": "Serie C - Girone A"},
    "Serie C - Girone B": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/italy/serie-c-group-b/results/", "id_prefix": "SerieC-GironeB", "league_name": "Serie C - Girone B"},
    "Serie C - Girone C": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/italy/serie-c-group-c/results/", "id_prefix": "SerieC-GironeC", "league_name": "Serie C - Girone C"},
    "Premier League": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/england/premier-league/results/", "id_prefix": "PremierLeague", "league_name": "Premier League"},
    "La Liga": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/spain/laliga/results/", "id_prefix": "LaLiga", "league_name": "La Liga"},
    "Bundesliga": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/germany/bundesliga/results/", "id_prefix": "Bundesliga", "league_name": "Bundesliga"},
    "Ligue 1": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/france/ligue-1/results/", "id_prefix": "Ligue1", "league_name": "Ligue 1"},
    "Eredivisie": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/netherlands/eredivisie/results/", "id_prefix": "Eredivisie", "league_name": "Eredivisie"},
    "Liga Portugal": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/portugal/liga-portugal/results/", "id_prefix": "LigaPortugal", "league_name": "Liga Portugal"},
    "Championship": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/england/championship/results/", "id_prefix": "Championship", "league_name": "Championship"},
    "LaLiga 2": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/spain/laliga2/results/", "id_prefix": "LaLiga2", "league_name": "LaLiga 2"},
    "2. Bundesliga": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/germany/2-bundesliga/results/", "id_prefix": "2.Bundesliga", "league_name": "2. Bundesliga"},
    "Ligue 2": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/france/ligue-2/results/", "id_prefix": "Ligue2", "league_name": "Ligue 2"},
    "Scottish Premiership": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/scotland/premiership/results/", "id_prefix": "ScottishPremiership", "league_name": "Scottish Premiership"},
    "Allsvenskan": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/sweden/allsvenskan/results/", "id_prefix": "Allsvenskan", "league_name": "Allsvenskan"},
    "Eliteserien": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/norway/eliteserien/results/", "id_prefix": "Eliteserien", "league_name": "Eliteserien"},
    "Superligaen": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/denmark/superliga/results/", "id_prefix": "Superligaen", "league_name": "Superligaen"},
    "Jupiler Pro League": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/belgium/jupiler-pro-league/results/", "id_prefix": "JupilerProLeague", "league_name": "Jupiler Pro League"},
    "Süper Lig": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/turkey/super-lig/results/", "id_prefix": "SüperLig", "league_name": "Süper Lig"},
    "League of Ireland Premier Division": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/ireland/premier-division/results/", "id_prefix": "LeagueOfIreland", "league_name": "League of Ireland Premier Division"},
    "Brasileirão Serie A": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/brazil/serie-a-betano/results/", "id_prefix": "Brasileirao", "league_name": "Brasileirão Serie A"},
    "Primera División": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/argentina/liga-profesional/results//", "id_prefix": "PrimeraDivisión", "league_name": "Primera División"},
    "J1 League": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/japan/j1-league/results/", "id_prefix": "J1League", "league_name": "J1 League"},
    "UCL": {"tipo": "coppa", "matches_collection": "matches_champions_league", "nowgoal_url": "https://football.nowgoal26.com/cupmatch/103", "name": "Champions League", "season": "2025-2026"},
    "UEL": {"tipo": "coppa", "matches_collection": "matches_europa_league", "nowgoal_url": "https://football.nowgoal26.com/cupmatch/113", "name": "Europa League", "season": "2025-2026"},
    # -------------------------------------------------------------------
    # LEGHE VIA NOWGOAL (tipo: "lega_nowgoal")
    # BetExplorer per alcune leghe (es. MLS) non mostra gli header "Giornata"
    # nella pagina risultati, quindi il parser standard fallisce.
    # Soluzione: scrapare i risultati da NowGoal (stesso formato delle coppe)
    # e salvarli in h2h_by_round matchando per transfermarkt_id.
    # -------------------------------------------------------------------
    "Major League Soccer": {"tipo": "lega_nowgoal", "nowgoal_url": "https://football.nowgoal26.com/subleague/21", "id_prefix": "MajorLeagueSoccer", "league_name": "Major League Soccer"},
}

# --- FUNZIONI ORIGINALI CAMPIONATI (da per_agg_pianificato_update_results_only.py) ---

def find_team_tm_id(team_name):
    teams_col = db["teams"]
    team = teams_col.find_one({"$or": [{"name": team_name}, {"aliases": team_name}, {"aliases_transfermarkt": team_name}]})
    return str(team["transfermarkt_id"]) if team and "transfermarkt_id" in team else None

def extract_round_number(text):
    if not text: return None
    match = re.search(r'(\d+)', text)
    return match.group(1) if match else None

def parse_betexplorer_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    results_by_round = {}
    current_round = None
    rows = soup.find_all('tr')
    for row in rows:
        th = row.find('th', class_='h-text-left')
        if th:
            round_num = extract_round_number(th.get_text(strip=True))
            if round_num:
                current_round = round_num
                if current_round not in results_by_round: results_by_round[current_round] = []
            continue
        if current_round is None: continue
        cells = row.find_all('td')
        if len(cells) < 2: continue
        first_cell = cells[0]
        match_link = first_cell.find('a')
        if not match_link: continue
        spans = match_link.find_all('span')
        if len(spans) < 2: continue
        home_team, away_team = spans[0].get_text(strip=True), spans[-1].get_text(strip=True)
        score_link = cells[1].find('a')
        if not score_link: continue
        score_text = score_link.get_text(strip=True)
        if not re.match(r'^\d+:\d+$', score_text): continue
        results_by_round[current_round].append({"home": home_team, "away": away_team, "score": score_text})
    return results_by_round

def process_league(driver, league_config):
    # // modificato per: distinguere tra scansione a vuoto e aggiornamento reale
    h2h_col = db["h2h_by_round"]
    driver.get(league_config['url'])
    time.sleep(2)
    results = parse_betexplorer_html(driver.page_source)
    
    totale_aggiornati = 0  # Contatore globale per la lega
    updated_for_sync = []  # Risultati da propagare alle collection pronostici

    for round_num, matches in results.items():
        doc_id = f"{league_config['id_prefix']}_{round_num}Giornata"
        db_doc = h2h_col.find_one({"_id": doc_id})
        if not db_doc: continue

        db_matches = db_doc.get("matches", [])
        modified = False

        for be_match in matches:
            h_id, a_id = find_team_tm_id(be_match["home"]), find_team_tm_id(be_match["away"])
            if not h_id or not a_id: continue

            for db_m in db_matches:
                if str(db_m.get('home_tm_id')) == h_id and str(db_m.get('away_tm_id')) == a_id:
                    # Verifica se il punteggio è cambiato o se lo stato non è ancora 'Finished'
                    if db_m.get('real_score') != be_match["score"] or db_m.get('status') != "Finished":
                        db_m['real_score'] = be_match["score"]
                        db_m['status'] = "Finished"
                        db_m['live_status'] = "Finished"
                        db_m['live_minute'] = None
                        modified = True
                        totale_aggiornati += 1
                        # Raccogli per sync a collection pronostici
                        date_obj = db_m.get('date_obj')
                        if date_obj:
                            ds = date_obj.strftime('%Y-%m-%d') if hasattr(date_obj, 'strftime') else str(date_obj)[:10]
                            updated_for_sync.append((db_m.get('home', ''), db_m.get('away', ''), ds, be_match["score"]))
                    break

        if modified:
            h2h_col.update_one(
                {"_id": doc_id},
                {"$set": {"matches": db_matches, "last_updated": datetime.now()}}
            )

    # Sync risultati alle collection pronostici (live_score + live_status)
    _sync_results_to_predictions(updated_for_sync)

    # Log differenziato in base all'attività svolta
    if totale_aggiornati > 0:
        print(f"✅ {league_config['league_name']}: Aggiornati {totale_aggiornati} risultati nel database.")
    else:
        print(f"☕ {league_config['league_name']}: Nessun nuovo risultato.")

    return totale_aggiornati

# --- FUNZIONI ORIGINALI COPPE (da update_cups_data.py) ---

def scrape_nowgoal_matches(config):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    driver = webdriver.Chrome(options=chrome_options)
    driver.get(config['nowgoal_url'])
    time.sleep(5)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    table = soup.find("table", id="Table3")
    if not table: return
    rows = table.find_all("tr")
    matches_data = []
    for row in rows:
        team_links = row.find_all("a", href=re.compile(r"/team/"))
        if len(team_links) < 2: continue
        home, away = team_links[0].get_text(strip=True), team_links[1].get_text(strip=True)
        score_cell = row.find("div", class_="point")
        if score_cell:
            fonts = score_cell.find_all("font")
            if len(fonts) >= 2:
                h_s, a_s = fonts[0].get_text(strip=True).replace("-",""), fonts[1].get_text(strip=True).replace("-","")
                matches_data.append({"home_team": home, "away_team": away, "status": "finished", "result": {"home_score": int(h_s), "away_score": int(a_s)}})
    if matches_data:
        coll = db[config['matches_collection']]
        for m in matches_data:
            coll.update_one({"home_team": m['home_team'], "away_team": m['away_team'], "season": config['season']}, {"$set": m}, upsert=True)
    driver.quit()
    print(f"✅ Risultati {config['name']} aggiornati.")


def _ng_get_current_round(driver):
    """Legge il numero della giornata corrente dalla pagina NowGoal subleague."""
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "tr[id]"))
        )
        first_row = driver.find_element(By.CSS_SELECTOR, "tr[id]")
        m = re.match(r'^(\d+)', first_row.text.strip())
        return int(m.group(1)) if m else None
    except Exception:
        return None


def _ng_click_round(driver, round_num):
    """Clicca sulla giornata indicata e attende il caricamento."""
    try:
        for xpath in [
            f"//div[contains(@class,'subLeague_round')]//a[text()='{round_num}']",
            f"//td[text()='{round_num}']",
            f"//li[text()='{round_num}']",
            f"//a[normalize-space()='{round_num}']",
        ]:
            try:
                el = driver.find_element(By.XPATH, xpath)
                if el:
                    driver.execute_script("arguments[0].click();", el)
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "tr[id]"))
                    )
                    time.sleep(1)
                    return True
            except Exception:
                pass
        return False
    except Exception:
        return False


def _ng_extract_scores(driver):
    """Estrai risultati (score) dalla pagina NowGoal corrente.
    Strategia 1: BeautifulSoup su Table3 (formato coppe: div.point > font).
    Strategia 2: Selenium text parsing sulle righe tr[id].
    Strategia 3: BeautifulSoup su TD con classe specifica score.
    Debug: stampa info su cosa trova per diagnosi.
    """
    results = []
    soup = BeautifulSoup(driver.page_source, "html.parser")

    # --- Strategia 1: Table3 > div.point > font ---
    table = soup.find("table", id="Table3")
    if table:
        rows_with_teams = 0
        rows_with_point = 0
        for row in table.find_all("tr"):
            team_links = row.find_all("a", href=re.compile(r"/team/"))
            if len(team_links) < 2:
                continue
            rows_with_teams += 1
            home = team_links[0].get_text(strip=True)
            away = team_links[1].get_text(strip=True)
            # Prova div.point > font (formato coppe)
            score_cell = row.find("div", class_="point")
            if score_cell:
                rows_with_point += 1
                fonts = score_cell.find_all("font")
                if len(fonts) >= 2:
                    h_s = fonts[0].get_text(strip=True).replace("-", "")
                    a_s = fonts[1].get_text(strip=True).replace("-", "")
                    if h_s.isdigit() and a_s.isdigit():
                        results.append({"home": home, "away": away, "score": f"{h_s}:{a_s}"})
                        continue
            # Prova: qualsiasi TD con testo che sembra uno score (es. "1 - 0", "2:1")
            for td in row.find_all("td"):
                td_text = td.get_text(strip=True)
                m = re.match(r'^(\d+)\s*[-:]\s*(\d+)$', td_text)
                if m:
                    results.append({"home": home, "away": away, "score": f"{m.group(1)}:{m.group(2)}"})
                    break
    else:
        pass

    if results:
        return results

    # --- Strategia 2: Selenium tr[id] — parsing testo righe ---
    try:
        sel_rows = driver.find_elements(By.CSS_SELECTOR, "tr[id]")
        for row in sel_rows:
            try:
                row_text = row.text.strip()
                if not row_text:
                    continue
                team_links = row.find_elements(By.CSS_SELECTOR, "a[href*='/team/']")
                if len(team_links) < 2:
                    continue
                home = team_links[0].text.strip()
                away = team_links[1].text.strip()
                if not home or not away:
                    continue
                # Cerca score: "H - A" nel testo, ma DOPO la data (evita match su "03-01")
                # Rimuovi la parte data/ora all'inizio, poi cerca score
                # Formato tipico: "round_num date time Home Away H - A odds..."
                text_after_away = row_text.split(away)[-1] if away in row_text else row_text
                score_match = re.search(r'(\d+)\s*-\s*(\d+)', text_after_away)
                if score_match:
                    h_s, a_s = score_match.group(1), score_match.group(2)
                    results.append({"home": home, "away": away, "score": f"{h_s}:{a_s}"})
            except Exception:
                continue
    except Exception:
        pass

    return results


def scrape_nowgoal_league(config):
    """
    Scrapa risultati da NowGoal per leghe che non funzionano su BetExplorer
    (es. MLS: BetExplorer non ha header "Giornata", il parser standard fallisce).
    check_previous_round=True → naviga anche alla giornata precedente (catch-up post-pausa).
    Match: nome NowGoal → cerca in teams (name/aliases) → ottiene tm_id →
    trova la partita in h2h_by_round (home_tm_id/away_tm_id).
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(30)
        driver.get(config['nowgoal_url'])
        time.sleep(5)

        # Determina giornata corrente
        current_round = _ng_get_current_round(driver)
        if not current_round:
            print(f"⚠️ {config['league_name']}: Impossibile determinare giornata NowGoal")
            return 0

        # NowGoal subleague: la giornata "corrente" mostra partite FUTURE (senza score).
        # I risultati sono SEMPRE nella giornata precedente → controlliamo sempre entrambe.
        rounds_to_check = [current_round]
        if current_round > 1:
            rounds_to_check.append(current_round - 1)

        ng_results = []
        for round_num in rounds_to_check:
            if round_num != current_round:
                if not _ng_click_round(driver, round_num):
                    print(f"   ⚠️ {config['league_name']}: Navigazione giornata {round_num} fallita")
                    continue
            scores = _ng_extract_scores(driver)
            if scores:
                print(f"   📊 {config['league_name']} Giornata {round_num}: {len(scores)} risultati trovati")
                ng_results.extend(scores)

        if not ng_results:
            print(f"☕ {config['league_name']}: Nessun risultato su NowGoal (giornate {current_round}, {current_round - 1}).")
            return 0

    except Exception as e:
        print(f"⚠️ {config['league_name']}: Errore scraping NowGoal: {e}")
        return 0
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    # Carica documenti h2h_by_round della lega (per league name, più robusto del prefix)
    h2h_col = db["h2h_by_round"]
    all_docs = list(h2h_col.find({"league": config['league_name']}))
    if not all_docs:
        # Fallback: cerca per id_prefix
        all_docs = list(h2h_col.find({"_id": {"$regex": f"^{config['id_prefix']}_"}}))
    if not all_docs:
        print(f"⚠️ {config['league_name']}: Nessun documento h2h_by_round")
        return 0

    # Matcha risultati NowGoal → h2h_by_round via transfermarkt_id
    totale_aggiornati = 0
    docs_modificati = set()
    updated_for_sync = []  # Risultati da propagare alle collection pronostici

    for ng in ng_results:
        h_id = find_team_tm_id(ng["home"])
        a_id = find_team_tm_id(ng["away"])
        if not h_id or not a_id:
            continue

        for doc in all_docs:
            found = False
            for db_m in doc.get("matches", []):
                if str(db_m.get("home_tm_id")) == h_id and str(db_m.get("away_tm_id")) == a_id:
                    if db_m.get("real_score") != ng["score"] or db_m.get("status") != "Finished":
                        db_m["real_score"] = ng["score"]
                        db_m["status"] = "Finished"
                        db_m["live_status"] = "Finished"
                        db_m["live_minute"] = None
                        docs_modificati.add(doc["_id"])
                        totale_aggiornati += 1
                        # Raccogli per sync a collection pronostici
                        date_obj = db_m.get('date_obj')
                        if date_obj:
                            ds = date_obj.strftime('%Y-%m-%d') if hasattr(date_obj, 'strftime') else str(date_obj)[:10]
                            updated_for_sync.append((db_m.get('home', ''), db_m.get('away', ''), ds, ng["score"]))
                    found = True
                    break
            if found:
                break

    # Salva i documenti modificati
    for doc in all_docs:
        if doc["_id"] in docs_modificati:
            h2h_col.update_one(
                {"_id": doc["_id"]},
                {"$set": {"matches": doc["matches"], "last_updated": datetime.now()}}
            )

    # Sync risultati alle collection pronostici (live_score + live_status)
    _sync_results_to_predictions(updated_for_sync)

    if totale_aggiornati > 0:
        print(f"✅ {config['league_name']}: Aggiornati {totale_aggiornati} risultati (via NowGoal).")
    else:
        print(f"☕ {config['league_name']}: Nessun nuovo risultato (via NowGoal).")

    return totale_aggiornati


# --- LOGICA DIRETTORE AGGIORNATA ---

def run_director_loop():
    global _current_driver
    print(f"\n{'='*50}")
    print(f" 🚀 DIRETTORE RISULTATI - SISTEMA ATTIVO ")
    print(f"{'='*50}")
    print(" ⌨️  Premi 'H' per NASCONDERE questa finestra")

    heartbeat = ["❤️", "   "]
    last_empty_check = {}  # {league_name: datetime} — cooldown per leghe senza risultati
    COOLDOWN_MIN = 30  # Minuti di attesa dopo check vuoto
    _was_paused = False  # Flag per catch-up post-pausa

    while True:
        ora_attuale = datetime.now()

        # Gestione Pausa Notturna + Pipeline (03:00-09:00 per evitare conflitti Chrome)
        if 3 <= ora_attuale.hour < 9:
            sys.stdout.write(f"\r 💤 [PAUSA] Il Direttore riposa. Sveglia alle 09:00...          ")
            sys.stdout.flush()
            _was_paused = True
            time.sleep(1800)
            continue

        # --- CATCH-UP POST-PAUSA ---
        # Al primo ciclo dopo la sveglia, azzera il cooldown per verificare tutte le leghe.
        if _was_paused:
            print(f"\n🌅 [CATCH-UP] Primo ciclo dopo pausa — cooldown azzerato")
            last_empty_check.clear()
            _was_paused = False

        agenda = set()

        # --- DEFINIZIONE FINESTRA TEMPORALE ---
        # Finestra fissa 24h: copre partite sudamericane (01:00-03:00 CET)
        # che altrimenti uscivano dalla finestra 10h di sera.
        lookback_hours = 24
        soglia_fine = ora_attuale - timedelta(hours=2)   # Iniziata da almeno 2 ore
        soglia_inizio = ora_attuale - timedelta(hours=lookback_hours)

        # Check campionati
        query_leagues = {
            "matches.status": "Scheduled",
            "matches.date_obj": {"$gte": soglia_inizio, "$lte": soglia_fine}
        }

        for doc in db["h2h_by_round"].find(query_leagues):
            for m in doc.get("matches", []):
                if (m.get("status") == "Scheduled" and
                    m.get("date_obj") and
                    soglia_inizio <= m["date_obj"] <= soglia_fine):
                    agenda.add(doc.get("league"))
                    break

        # Check coppe
        for name, cfg in TARGET_CONFIG.items():
            if cfg['tipo'] == "coppa":
                for p in db[cfg['matches_collection']].find({"status": {"$ne": "finished"}}):
                    try:
                        match_date = datetime.strptime(p.get("match_date", "01-01-2000 00:00"), "%d-%m-%Y %H:%M")
                        if soglia_inizio <= match_date <= soglia_fine:
                            agenda.add(name)
                            break
                    except:
                        continue

        # Filtra per cooldown: skip leghe controllate di recente senza risultati
        agenda_filtrata = set()
        for target in agenda:
            last = last_empty_check.get(target)
            if last and (ora_attuale - last).total_seconds() < COOLDOWN_MIN * 60:
                continue
            agenda_filtrata.add(target)

        # Esecuzione con SINGOLO Chrome driver (no subprocess)
        if agenda_filtrata:
            leghe = [t for t in agenda_filtrata if t in TARGET_CONFIG and TARGET_CONFIG[t]['tipo'] == 'lega']
            coppe = [t for t in agenda_filtrata if t in TARGET_CONFIG and TARGET_CONFIG[t]['tipo'] == 'coppa']
            leghe_nowgoal = [t for t in agenda_filtrata if t in TARGET_CONFIG and TARGET_CONFIG[t]['tipo'] == 'lega_nowgoal']

            print(f"\n🎯 Aggiornamento: {list(agenda_filtrata)}")

            # Leghe: un solo Chrome driver per tutte
            if leghe:
                driver = None
                chrome_options = Options()
                chrome_options.add_argument("--headless")
                try:
                    driver = webdriver.Chrome(options=chrome_options)
                    _current_driver = driver
                    driver.set_page_load_timeout(30)

                    for target in leghe:
                        cfg = TARGET_CONFIG[target]
                        try:
                            aggiornati = process_league(driver, cfg)
                            if aggiornati == 0:
                                last_empty_check[target] = datetime.now()
                            else:
                                last_empty_check.pop(target, None)
                        except Exception as e:
                            print(f"\n⚠️ Errore scraping {target}: {e}")
                            last_empty_check[target] = datetime.now()
                            try: driver.quit()
                            except: pass
                            try:
                                driver = webdriver.Chrome(options=chrome_options)
                                _current_driver = driver
                                driver.set_page_load_timeout(30)
                            except Exception as e2:
                                print(f"❌ Impossibile ricreare Chrome: {e2}")
                                break
                except Exception as e:
                    print(f"\n❌ Errore Chrome driver: {e}")
                finally:
                    if driver:
                        try: driver.quit()
                        except: pass
                    _current_driver = None

            # Coppe: driver proprio (scrape_nowgoal_matches lo crea internamente)
            for target in coppe:
                cfg = TARGET_CONFIG[target]
                try:
                    scrape_nowgoal_matches(cfg)
                except Exception as e:
                    print(f"\n⚠️ Errore coppa {target}: {e}")

            # Leghe via NowGoal (es. MLS): stessa logica coppe ma salva in h2h_by_round
            for target in leghe_nowgoal:
                cfg = TARGET_CONFIG[target]
                try:
                    aggiornati = scrape_nowgoal_league(cfg)
                    if aggiornati == 0:
                        last_empty_check[target] = datetime.now()
                    else:
                        last_empty_check.pop(target, None)
                except Exception as e:
                    print(f"\n⚠️ Errore lega NowGoal {target}: {e}")

        elif agenda:
            # Tutte in cooldown
            print(f"\n⏳ {len(agenda)} leghe in agenda ma in cooldown (<{COOLDOWN_MIN}min)")

        # --- DASHBOARD VISIVA E ATTESA ---
        print("\n" + "-"*50)
        print(" ⌨️  Premi 'H' per NASCONDERE questa finestra")
        print("-"*50)

        for i in range(60):
            if msvcrt.kbhit():
                if msvcrt.getch().decode('utf-8').lower() == 'h':
                    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
                    print("\n👻 Finestra nascosta! Il bot continua a lavorare.")

            h = heartbeat[i % 2]
            orario_live = datetime.now().strftime("%H:%M:%S")
            min_rimanenti = 10 - (i*10 // 60)
            sys.stdout.write(f"\r ✅ [OPERATIVO] {h} Ultimo check: {orario_live} | Prossimo tra {min_rimanenti} min...  ")
            sys.stdout.flush()
            time.sleep(10)

if __name__ == "__main__":
    while True:
        try:
            run_director_loop()
        except Exception as e:
            print(f"\n❌ ERRORE FATALE: {e}")
            print("🔄 Il daemon riparte tra 60s...")
            time.sleep(60)