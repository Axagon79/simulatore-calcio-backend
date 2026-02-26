import os
import sys
import time
import random
import re
import importlib
import atexit

# --- CONFIGURAZIONE PERCORSI ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db

# --- SELENIUM ---
import undetected_chromedriver as uc
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

# --- COLLEZIONI ---
rankings_collection = db['classifiche']
teams_collection = db['teams']

# --- CACHE TEAMS IN MEMORIA (evita ~520 query regex individuali) ---
_teams_cache = {}  # nome_lower → transfermarkt_id
_tmid_to_name = {}  # transfermarkt_id → nome ufficiale dal DB

def _build_teams_cache():
    """Carica tutte le teams e costruisce un dizionario nome/alias → tm_id."""
    all_teams = list(teams_collection.find({}, {"name": 1, "aliases": 1, "aliases_transfermarkt": 1, "transfermarkt_id": 1}))
    for t in all_teams:
        tm_id = t.get("transfermarkt_id")
        if not tm_id:
            continue
        # Nome principale
        name = t.get("name", "")
        if name:
            _teams_cache[name.strip().lower()] = tm_id
            _tmid_to_name[str(tm_id)] = name.strip()
        # Aliases standard
        for alias in (t.get("aliases") or []):
            if alias:
                _teams_cache[alias.strip().lower()] = tm_id
        # Aliases Transfermarkt
        for alias in (t.get("aliases_transfermarkt") or []):
            if alias:
                _teams_cache[alias.strip().lower()] = tm_id
    print(f"   ✅ Cache teams: {len(all_teams)} squadre → {len(_teams_cache)} nomi indicizzati")

_build_teams_cache()

# --- CONFIGURAZIONE COMPETIZIONI (NowGoal — URL diretti standings) ---
COMPETITIONS = [
    # ITALIA
    {"name": "Serie A", "country": "Italy", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/34/2948", "dual_tables": False},
    {"name": "Serie B", "country": "Italy", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/40/261", "dual_tables": False},
    {"name": "Serie C - Girone A", "country": "Italy", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/142/1525", "dual_tables": False},
    {"name": "Serie C - Girone B", "country": "Italy", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/142/1526", "dual_tables": False},
    {"name": "Serie C - Girone C", "country": "Italy", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/142/1527", "dual_tables": False},

    # EUROPA TOP
    {"name": "Premier League", "country": "England", "standings_url": "https://football.nowgoal26.com/leastanding/36", "dual_tables": False},
    {"name": "La Liga", "country": "Spain", "standings_url": "https://football.nowgoal26.com/leastanding/31", "dual_tables": False},
    {"name": "Bundesliga", "country": "Germany", "standings_url": "https://football.nowgoal26.com/leastanding/8", "dual_tables": False},
    {"name": "Ligue 1", "country": "France", "standings_url": "https://football.nowgoal26.com/leastanding/11", "dual_tables": False},
    {"name": "Eredivisie", "country": "Netherlands", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/16/98", "dual_tables": False},
    {"name": "Liga Portugal", "country": "Portugal", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/23/1123", "dual_tables": False},

    # EUROPA SERIE B
    {"name": "Championship", "country": "England", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/37/87", "dual_tables": False},
    {"name": "LaLiga 2", "country": "Spain", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/33/546", "dual_tables": False},
    {"name": "2. Bundesliga", "country": "Germany", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/9/132", "dual_tables": False},
    {"name": "Ligue 2", "country": "France", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/12/1778", "dual_tables": False},

    # EUROPA NORDICI + EXTRA
    {"name": "Scottish Premiership", "country": "Scotland", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/29/2498", "dual_tables": False},
    {"name": "Allsvenskan", "country": "Sweden", "standings_url": "https://football.nowgoal26.com/subleastanding/2026/26/431", "dual_tables": False},
    {"name": "Eliteserien", "country": "Norway", "standings_url": "https://football.nowgoal26.com/subleastanding/2026/22/3219", "dual_tables": False},
    {"name": "Superligaen", "country": "Denmark", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/7/1722", "dual_tables": False},
    {"name": "Jupiler Pro League", "country": "Belgium", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/5/114", "dual_tables": False},
    {"name": "Süper Lig", "country": "Turkey", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/30/690", "dual_tables": False},
    {"name": "League of Ireland Premier Division", "country": "Ireland", "standings_url": "https://football.nowgoal26.com/subleastanding/2026/1/418", "dual_tables": False},

    # AMERICHE
    {"name": "Brasileirão Serie A", "country": "Brazil", "standings_url": "https://football.nowgoal26.com/leastanding/4", "dual_tables": False},
    {"name": "Primera División", "country": "Argentina", "standings_url": "https://football.nowgoal26.com/subleastanding/2026/2/1232", "dual_tables": True},
    {"name": "Major League Soccer", "country": "USA", "standings_url": "https://football.nowgoal26.com/subleastanding/2026/21/165", "dual_tables": True},

    # ASIA
    {"name": "J1 League", "country": "Japan", "standings_url": "https://football.nowgoal26.com/subleastanding/2026/25/3540", "dual_tables": False},
]


def to_int(val):
    try:
        return int(val.replace('+', '').replace('-', '') if isinstance(val, str) and val.lstrip('-+').isdigit() else val)
    except:
        return 0

def to_int_signed(val):
    """Converte stringa con segno in int (es. '+31' → 31, '-5' → -5)."""
    try:
        return int(val)
    except:
        return 0

def find_db_data(scraped_name):
    """Cerca il nome nella cache in-memory. Restituisce (transfermarkt_id, None)."""
    if not scraped_name:
        return None, None
    tm_id = _teams_cache.get(scraped_name.strip().lower())
    if tm_id:
        return tm_id, None
    return None, None


# --- DRIVER SELENIUM ---
_driver = None

def _get_driver():
    global _driver
    if _driver:
        return _driver
    print("   🌐 Avvio Chrome (undetected_chromedriver)...")
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    _driver = uc.Chrome(options=options, headless=True, user_multi_procs=True)
    _driver.set_page_load_timeout(30)
    return _driver

def _quit_driver():
    global _driver
    if _driver:
        try:
            _driver.quit()
        except:
            pass
        _driver = None

atexit.register(_quit_driver)


def _parse_standings_table(driver):
    """
    Parsa la tabella standings attualmente visibile nella pagina.
    Restituisce lista di dict con campi: rank, team, transfermarkt_id, points, played,
    wins, draws, losses, goals_for, goals_against, goal_diff
    """
    standings = []
    foundids = 0

    try:
        # Attendi che la tabella si carichi
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table tr"))
        )
        time.sleep(1)  # Stabilizzazione

        # Trova tutte le righe della tabella
        rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        if not rows:
            # Prova senza tbody
            rows = driver.find_elements(By.CSS_SELECTOR, "table tr")

        for row in rows:
            try:
                cells = row.find_elements(By.TAG_NAME, "td")
                if not cells:
                    cells = row.find_elements(By.TAG_NAME, "th")
                if len(cells) < 10:
                    continue

                # Colonne NowGoal: R | Team | GP | W | D | L | GF | GA | GD | Pts | ...
                rank_text = cells[0].text.strip()
                if not rank_text.isdigit():
                    continue

                rank = int(rank_text)
                team_name_raw = cells[1].text.strip()
                # NowGoal aggiunge un numero in coda (badge forma recente, es. "AC Milan 2")
                # Rimuovi trailing " N" dove N è 1-2 cifre, ma NON se il numero fa parte del nome
                # (es. "2. Bundesliga" ha il numero all'inizio, non alla fine)
                team_name = re.sub(r'\s+\d{1,2}$', '', team_name_raw)
                played = to_int(cells[2].text.strip())
                wins = to_int(cells[3].text.strip())
                draws = to_int(cells[4].text.strip())
                losses = to_int(cells[5].text.strip())
                goals_for = to_int(cells[6].text.strip())
                goals_against = to_int(cells[7].text.strip())
                goal_diff = to_int_signed(cells[8].text.strip())
                points = to_int(cells[9].text.strip())

                # Cerca transfermarkt_id nel DB
                tm_id, _ = find_db_data(team_name)
                if not tm_id:
                    # Fallback: prova col nome raw (per squadre con numero nel nome)
                    tm_id, _ = find_db_data(team_name_raw)
                if tm_id:
                    foundids += 1
                    # Usa il nome ufficiale dal DB (es. "Inter" invece di "Inter Milan")
                    db_name = _tmid_to_name.get(str(tm_id))
                    if db_name:
                        team_name = db_name

                teamdata = {
                    "rank": rank,
                    "team": team_name,
                    "transfermarkt_id": tm_id,
                    "points": points,
                    "played": played,
                    "wins": wins,
                    "draws": draws,
                    "losses": losses,
                    "goals_for": goals_for,
                    "goals_against": goals_against,
                    "goal_diff": goal_diff,
                }
                standings.append(teamdata)

            except Exception:
                continue

    except Exception as e:
        print(f"      ⚠️ Errore parsing tabella: {e}")

    print(f"      Estratte {len(standings)} squadre (ID trovati: {foundids})")
    return standings


def _click_tab(driver, tab_name):
    """Clicca su un tab della tabella standings (Total/Home/Away).
    I tab NowGoal sono <li class='nav_selected/nav_unselected'>."""
    try:
        # Cerca tra i <li> con class nav_selected o nav_unselected (match esatto sul testo)
        nav_items = driver.find_elements(By.CSS_SELECTOR, "li.nav_selected, li.nav_unselected")
        for el in nav_items:
            if el.text.strip() == tab_name and el.is_displayed():
                el.click()
                time.sleep(2)  # Attendi ricaricamento tabella
                return True
        return False
    except Exception:
        return False


def scrape_nowgoal():
    """Scarica classifiche da NowGoal per tutte le competizioni."""
    print("🏆 AVVIO SCRAPER CLASSIFICHE NOWGOAL (Selenium)")
    driver = _get_driver()

    for comp in COMPETITIONS:
        league_name = comp['name']
        country = comp['country']
        standings_url = comp['standings_url']

        print(f"\n🌍 Scarico: {league_name} ({country})...")

        try:
            # Pausa anti-ban
            time.sleep(random.uniform(2.0, 4.0))

            # Naviga direttamente alla pagina standings
            print(f"   📊 URL: {standings_url}")
            driver.get(standings_url)
            time.sleep(random.uniform(2.5, 4.0))

            # Verifica che la pagina abbia caricato una tabella standings
            tables = driver.find_elements(By.CSS_SELECTOR, "table")
            if not tables:
                print(f"   ❌ Pagina senza tabella — URL probabilmente errato: {standings_url}")
                continue

            # Verifica che non sia una pagina di errore/redirect
            current_url = driver.current_url
            if 'leastanding' not in current_url and 'standing' not in current_url.lower():
                print(f"   ❌ Redirect a pagina diversa: {current_url}")
                continue

            # 3. Parsa tab "Total" (default)
            print(f"   📋 Tab Total...")
            table_total = _parse_standings_table(driver)

            # 4. Parsa tab "Home"
            print(f"   🏠 Tab Home...")
            table_home = []
            if _click_tab(driver, "Home"):
                table_home = _parse_standings_table(driver)
            else:
                print(f"      ⚠️ Tab Home non trovato")

            # 5. Parsa tab "Away"
            print(f"   ✈️ Tab Away...")
            table_away = []
            if _click_tab(driver, "Away"):
                table_away = _parse_standings_table(driver)
            else:
                print(f"      ⚠️ Tab Away non trovato")

            # 6. Torna su Total per reset
            _click_tab(driver, "Total")

            if not table_total:
                print(f"   ⚠️ Nessuna squadra estratta per {league_name}")
                continue

            # 7. dual_tables: unisci se ci sono 2 conference
            if comp.get("dual_tables") and len(table_total) > 0:
                print(f"   📊 Campionato dual ({len(table_total)} squadre totali)")

            # 8. Salva nel DB
            filter_query = {"country": country, "league": league_name}
            update_doc = {
                "$set": {
                    "country": country,
                    "league": league_name,
                    "last_updated": time.time(),
                    "source": "nowgoal",
                    "table": table_total,
                    "table_home": table_home,
                    "table_away": table_away,
                }
            }
            rankings_collection.update_one(filter_query, update_doc, upsert=True)
            print(f"   ✅ Salvate {len(table_total)} squadre (Total: {len(table_total)}, Home: {len(table_home)}, Away: {len(table_away)})")

        except Exception as e:
            print(f"   ❌ Errore: {e}")

    print(f"\n✅ Scraping classifiche completato!")


if __name__ == "__main__":
    # 1. Esegue lo scaricamento e salvataggio
    scrape_nowgoal()

    # Chiudi driver
    _quit_driver()

    print("\n🔗 Preparazione aggiornamento partite...")

    try:
        # --- CALCOLO PERCORSO DINAMICO ---
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Saliamo di 2 livelli: .../ai_engine
        ai_engine_path = os.path.dirname(os.path.dirname(current_dir))
        calculators_path = os.path.join(ai_engine_path, 'calculators')

        # Aggiungiamo al sistema temporaneamente
        if calculators_path not in sys.path:
            sys.path.append(calculators_path)

        # --- IMPORTAZIONE DINAMICA (Zittisce l'errore di Pylance) ---
        # Carichiamo il file come un modulo
        injector_module = importlib.import_module("injector_standings_to_matches")

        # 2. Esegue la funzione dentro il modulo
        injector_module.inject_standings_final()

    except ImportError as e:
        print(f"❌ Errore: Impossibile trovare il file injector.\nPercorso cercato: {calculators_path}\nDettaglio: {e}")
    except Exception as e:
        print(f"❌ Errore generico durante l'iniezione: {e}")
