import os
import sys
import time

import ctypes  # // aggiunto per: nascondere la finestra
import msvcrt  # // aggiunto per: leggere i tasti senza bloccare il ciclo
import importlib.util
import re
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

try:
    spec = importlib.util.spec_from_file_location("config", os.path.join(project_root, "config.py"))
    config_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_module)
    db = config_module.db
except Exception as e:
    print(f"❌ Errore Config: {e}")
    sys.exit()

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
    "Major League Soccer": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/usa/mls/results/", "id_prefix": "MLS", "league_name": "Major League Soccer"},
    "J1 League": {"tipo": "lega", "url": "https://www.betexplorer.com/it/football/japan/j1-league/results/", "id_prefix": "J1League", "league_name": "J1 League"},
    "UCL": {"tipo": "coppa", "matches_collection": "matches_champions_league", "nowgoal_url": "https://football.nowgoal26.com/cupmatch/103", "name": "Champions League", "season": "2025-2026"},
    "UEL": {"tipo": "coppa", "matches_collection": "matches_europa_league", "nowgoal_url": "https://football.nowgoal26.com/cupmatch/113", "name": "Europa League", "season": "2025-2026"}
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
                        modified = True
                        totale_aggiornati += 1
                    break
        
        if modified:
            h2h_col.update_one(
                {"_id": doc_id}, 
                {"$set": {"matches": db_matches, "last_updated": datetime.now()}}
            )

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

# --- LOGICA DIRETTORE AGGIORNATA ---

def run_director_loop():
    print(f"\n{'='*50}")
    print(f" 🚀 DIRETTORE RISULTATI - SISTEMA ATTIVO ")
    print(f"{'='*50}")
    print(" ⌨️  Premi 'H' per NASCONDERE questa finestra")

    heartbeat = ["❤️", "   "]
    last_empty_check = {}  # {league_name: datetime} — cooldown per leghe senza risultati
    COOLDOWN_MIN = 30  # Minuti di attesa dopo check vuoto

    while True:
        ora_attuale = datetime.now()

        # Gestione Pausa Notturna + Pipeline (03:30-09:00 per evitare conflitti Chrome)
        if 2 <= ora_attuale.hour < 9:
            sys.stdout.write(f"\r 💤 [PAUSA] Il Direttore riposa. Sveglia alle 09:00...          ")
            sys.stdout.flush()
            time.sleep(1800)
            continue

        agenda = set()

        # --- DEFINIZIONE FINESTRA TEMPORALE ---
        # Cerca partite iniziate tra 2h e 5h fa (2h partita + 3h margine per BetExplorer)
        # Dopo 5h dal fischio d'inizio senza risultato → probabilmente posticipata
        soglia_fine = ora_attuale - timedelta(hours=2)   # Iniziata da almeno 2 ore
        soglia_inizio = ora_attuale - timedelta(hours=5)  # Non più vecchia di 5 ore

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

            print(f"\n🎯 Aggiornamento: {list(agenda_filtrata)}")

            # Leghe: un solo Chrome driver per tutte
            if leghe:
                driver = None
                try:
                    chrome_options = Options()
                    chrome_options.add_argument("--headless")
                    driver = webdriver.Chrome(options=chrome_options)

                    for target in leghe:
                        cfg = TARGET_CONFIG[target]
                        aggiornati = process_league(driver, cfg)
                        if aggiornati == 0:
                            last_empty_check[target] = datetime.now()
                        else:
                            # Risultati trovati: rimuovi dal cooldown (potrebbe finirne un'altra)
                            last_empty_check.pop(target, None)
                finally:
                    if driver:
                        driver.quit()

            # Coppe: driver proprio (scrape_nowgoal_matches lo crea internamente)
            for target in coppe:
                cfg = TARGET_CONFIG[target]
                scrape_nowgoal_matches(cfg)

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
    run_director_loop()