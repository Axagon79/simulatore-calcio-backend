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
    {"name": "Premier League", "country": "England", "standings_url": "https://football.nowgoal26.com/leastanding/36", "dual_tables": False},
    {"name": "La Liga", "country": "Spain", "standings_url": "https://football.nowgoal26.com/leastanding/31", "dual_tables": False},
    {"name": "Bundesliga", "country": "Germany", "standings_url": "https://football.nowgoal26.com/leastanding/8", "dual_tables": False},
    {"name": "Ligue 1", "country": "France", "standings_url": "https://football.nowgoal26.com/leastanding/11", "dual_tables": False},
    {"name": "Eredivisie", "country": "Netherlands", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/16/98", "dual_tables": False},
    {"name": "Liga Portugal", "country": "Portugal", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/23/1123", "dual_tables": False},
    {"name": "Championship", "country": "England", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/37/87", "dual_tables": False},
    {"name": "League One", "country": "England", "standings_url": "https://football.nowgoal26.com/leastanding/39", "dual_tables": False},
    {"name": "LaLiga 2", "country": "Spain", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/33/546", "dual_tables": False},
    {"name": "2. Bundesliga", "country": "Germany", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/9/132", "dual_tables": False},
    {"name": "Ligue 2", "country": "France", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/12/1778", "dual_tables": False},
    {"name": "Scottish Premiership", "country": "Scotland", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/29/2498", "dual_tables": False},
    {"name": "Allsvenskan", "country": "Sweden", "standings_url": "https://football.nowgoal26.com/subleastanding/2026/26/431", "dual_tables": False},
    {"name": "Eliteserien", "country": "Norway", "standings_url": "https://football.nowgoal26.com/subleastanding/2026/22/3219", "dual_tables": False},
    {"name": "Superligaen", "country": "Denmark", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/7/1722", "dual_tables": False},
    {"name": "Jupiler Pro League", "country": "Belgium", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/5/114", "dual_tables": False},
    {"name": "Süper Lig", "country": "Turkey", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/30/690", "dual_tables": False},
    {"name": "League of Ireland Premier Division", "country": "Ireland", "standings_url": "https://football.nowgoal26.com/subleastanding/2026/1/418", "dual_tables": False},
    {"name": "Brasileirão Serie A", "country": "Brazil", "standings_url": "https://football.nowgoal26.com/leastanding/4", "dual_tables": False},
    {"name": "Primera División", "country": "Argentina", "standings_url": "https://football.nowgoal26.com/subleastanding/2026/2/1232", "dual_tables": True},
    {"name": "Major League Soccer", "country": "USA", "standings_url": "https://football.nowgoal26.com/subleastanding/2026/21/165", "dual_tables": True},
    {"name": "J1 League", "country": "Japan", "standings_url": "https://football.nowgoal26.com/subleastanding/2026/25/3540", "dual_tables": False},

    # NUOVI CAMPIONATI (24/03/2026)
    {"name": "League Two", "country": "England", "standings_url": "https://football.nowgoal26.com/leastanding/35", "dual_tables": False},
    {"name": "Veikkausliiga", "country": "Finland", "standings_url": "https://football.nowgoal26.com/subleastanding/2026/13/0", "dual_tables": False},
    {"name": "3. Liga", "country": "Germany", "standings_url": "https://football.nowgoal26.com/leastanding/693", "dual_tables": False},
    {"name": "Liga MX", "country": "Mexico", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/140/0", "dual_tables": False},
    {"name": "Eerste Divisie", "country": "Netherlands", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/17/0", "dual_tables": False},
    {"name": "Liga Portugal 2", "country": "Portugal", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/157/0", "dual_tables": False},
    {"name": "1. Lig", "country": "Turkey", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/130/0", "dual_tables": False},
    {"name": "Saudi Pro League", "country": "Saudi Arabia", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/292/0", "dual_tables": False},
    {"name": "Scottish Championship", "country": "Scotland", "standings_url": "https://football.nowgoal26.com/subleastanding/2025-2026/150/0", "dual_tables": False},
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

def _crea_chrome():
    """Crea un nuovo Chrome driver."""
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.page_load_strategy = 'eager'
    d = uc.Chrome(options=options, headless=True, user_multi_procs=True)
    d.set_page_load_timeout(30)
    return d

def _driver_vivo():
    """Controlla se la sessione Chrome è ancora attiva."""
    global _driver
    if not _driver:
        return False
    try:
        _ = _driver.title
        return True
    except Exception:
        return False

def _get_driver():
    global _driver
    if _driver_vivo():
        return _driver
    if _driver:
        try:
            _driver.quit()
        except Exception:
            pass
        _driver = None
    print("   🌐 Avvio Chrome (undetected_chromedriver)...")
    _driver = _crea_chrome()
    return _driver

def _ricrea_driver():
    """Chiude Chrome e lo ricrea da zero."""
    global _driver
    print("   🔄 Sessione morta — ricreo Chrome...")
    try:
        _driver.quit()
    except Exception:
        pass
    _driver = None
    try:
        _driver = _crea_chrome()
        print("   ✅ Chrome ricreato con successo!")
        return _driver
    except Exception as e:
        print(f"   ❌ Impossibile ricreare Chrome: {e}")
        return None

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
    Parsa la tabella standings attualmente visibile nella pagina (nuovo layout NowGoal).
    Restituisce lista di dict con campi: rank, team, transfermarkt_id, points, played,
    wins, draws, losses, goal_diff
    Nota: goals_for e goals_against non sono piu disponibili su NowGoal (solo GD).
    Lo step 5 (scraper_soccerstats) li scrive separatamente nella collection classifiche.
    """
    standings = []
    foundids = 0

    try:
        # Attendi che la lista si carichi (nuovo layout: li.standlis)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "li.standlis"))
        )
        time.sleep(1)

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(driver.page_source, "html.parser")
        rows = soup.find_all("li", class_="standlis")

        for row in rows:
            try:
                spans = row.find_all("span", recursive=False)
                if len(spans) < 8:
                    continue

                # Colonne: R | Team | P | W | D | L | GD | PTS
                rank_em = spans[0].find("em")
                rank_text = rank_em.get_text(strip=True) if rank_em else ""
                if not rank_text.isdigit():
                    continue
                rank = int(rank_text)

                team_span = spans[1].find("span", class_="name")
                team_name_raw = team_span.get_text(strip=True) if team_span else ""
                team_name = re.sub(r'\s+\d{1,2}$', '', team_name_raw)

                # P, W, D, L sono spans con span interno
                played = to_int(spans[2].get_text(strip=True))
                wins = to_int(spans[3].get_text(strip=True))
                draws = to_int(spans[4].get_text(strip=True))
                losses = to_int(spans[5].get_text(strip=True))
                goal_diff = to_int_signed(spans[6].get_text(strip=True))
                points = to_int(spans[7].get_text(strip=True))

                # Cerca transfermarkt_id nel DB
                tm_id, _ = find_db_data(team_name)
                if not tm_id:
                    tm_id, _ = find_db_data(team_name_raw)
                if tm_id:
                    foundids += 1
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
    Nuovo layout: span dentro #standingType con data-st-type."""
    try:
        tabs = driver.find_elements(By.CSS_SELECTOR, "#standingType span[data-st-type]")
        for el in tabs:
            if el.text.strip() == tab_name and el.is_displayed():
                driver.execute_script("arguments[0].click()", el)
                time.sleep(2)
                return True
        return False
    except Exception:
        return False


def scrape_nowgoal():
    """Scarica classifiche da NowGoal per tutte le competizioni."""
    print("🏆 AVVIO SCRAPER CLASSIFICHE NOWGOAL (Selenium)")
    driver = _get_driver()
    league_count = 0

    for comp in COMPETITIONS:
        league_name = comp['name']
        country = comp['country']
        standings_url = comp['standings_url']
        league_count += 1

        print(f"\n🌍 Scarico: {league_name} ({country})...")

        try:
            # Pulizia memoria ogni 5 campionati
            if league_count % 5 == 0:
                try:
                    driver.execute_cdp_cmd("Network.clearBrowserCache", {})
                    driver.execute_cdp_cmd("Network.clearBrowserCookies", {})
                    print("   🧹 Memoria Chrome svuotata.")
                except Exception:
                    pass

            # Pausa anti-ban
            time.sleep(random.uniform(2.0, 4.0))

            # Controlla sessione e ricrea se morta
            if not _driver_vivo():
                new_driver = _ricrea_driver()
                if not new_driver:
                    print(f"   ❌ Impossibile ricreare Chrome. Salto {league_name}.")
                    continue
                driver = new_driver

            # Naviga direttamente alla pagina standings
            print(f"   📊 URL: {standings_url}")
            driver.get(standings_url)
            time.sleep(random.uniform(2.5, 4.0))

            # Attendi caricamento classifica (nuovo layout: li.standlis)
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "li.standlis"))
                )
            except:
                print(f"   ❌ Pagina senza classifica — URL probabilmente errato: {standings_url}")
                continue

            # Verifica che non sia una pagina di errore/redirect
            current_url = driver.current_url
            if 'nowgoal' not in current_url:
                print(f"   ❌ Redirect a pagina esterna: {current_url}")
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

            # Preserva goals_for/goals_against dallo step 5 (scraper_soccerstats)
            existing = rankings_collection.find_one(filter_query)
            if existing:
                for tbl_key, tbl_data in [("table", table_total), ("table_home", table_home), ("table_away", table_away)]:
                    old_tbl = {t.get("team", ""): t for t in existing.get(tbl_key, [])}
                    for team_entry in tbl_data:
                        old = old_tbl.get(team_entry.get("team", ""), {})
                        if "goals_for" in old and "goals_for" not in team_entry:
                            team_entry["goals_for"] = old["goals_for"]
                        if "goals_against" in old and "goals_against" not in team_entry:
                            team_entry["goals_against"] = old["goals_against"]

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
            # Se la sessione è morta, ricrea il driver per il prossimo campionato
            if not _driver_vivo():
                new_driver = _ricrea_driver()
                if new_driver:
                    driver = new_driver

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
