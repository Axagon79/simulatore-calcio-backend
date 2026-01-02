import os
import sys
import time
from datetime import datetime

# --- FIX PERCORSI ---
current_path = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_path))
sys.path.append(project_root)

from config import db
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

history_col = db['matches_history']

LEAGUES = [
    {"name": "Serie A", "url": "https://www.betexplorer.com/football/italy/serie-a/results/"},
    {"name": "Serie B", "url": "https://www.betexplorer.com/football/italy/serie-b/results/"},
    {"name": "Serie C - Girone A", "url": "https://www.betexplorer.com/football/italy/serie-c-group-a/results/"},
    {"name": "Serie C - Girone B", "url": "https://www.betexplorer.com/football/italy/serie-c-group-b/results/"},
    {"name": "Serie C - Girone C", "url": "https://www.betexplorer.com/football/italy/serie-c-group-c/results/"},
    {"name": "Premier League", "url": "https://www.betexplorer.com/football/england/premier-league/results/"},
    {"name": "La Liga", "url": "https://www.betexplorer.com/football/spain/laliga/results/"},
    {"name": "Bundesliga", "url": "https://www.betexplorer.com/football/germany/bundesliga/results/"},
    {"name": "Ligue 1", "url": "https://www.betexplorer.com/football/france/ligue-1/results/"},
    {"name": "Eredivisie", "url": "https://www.betexplorer.com/football/netherlands/eredivisie/results/"},
    {"name": "Liga Portugal", "url": "https://www.betexplorer.com/football/portugal/liga-portugal/results/"}
]

def clean_float(txt):
    try:
        if not txt or txt == '-': return None
        return float(txt)
    except:
        return None

def parse_betexplorer_date(date_str):
    try:
        dt = datetime.strptime(date_str, "%d.%m.%Y")
        return dt.strftime("%Y-%m-%d")
    except:
        return date_str

def run_scraper():
    print("🚀 AVVIO SCRAPER (MODALITÀ TABULA RASA: Sostituzione Totale)...")

    # Lista temporanea in memoria per accumulare TUTTI i dati prima di cancellare
    ALL_MATCHES_BUFFER = []

    chrome_options = Options()
    # chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--log-level=3")
    prefs = {"profile.managed_default_content_settings.images": 2}
    chrome_options.add_experimental_option("prefs", prefs)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    for league in LEAGUES:
        print(f"\n🌍 Scarico {league['name']}...")
        try:
            driver.get(league['url'])
            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "table-main")))
            except:
                print("⚠️ Timeout tabella.")
                continue

            rows = driver.find_elements(By.CSS_SELECTOR, ".table-main tr")
            current_date = "Unknown"
            league_count = 0

            for row in rows:
                try:
                    if "h-text-left" in row.get_attribute("class"):
                        current_date = row.text.strip()
                        continue
                    
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) < 5: continue

                    match_text = cells[0].text
                    if "-" not in match_text: continue
                    parts = match_text.split("-")
                    home = parts[0].strip()
                    away = parts[1].strip()

                    score_text = cells[1].text
                    if ":" not in score_text: continue
                    score_parts = score_text.split(":")
                    gh = int(score_parts[0])
                    ga = int(score_parts[1])

                    o1 = clean_float(cells[2].text)
                    ox = clean_float(cells[3].text)
                    o2 = clean_float(cells[4].text)
                    formatted_date = parse_betexplorer_date(current_date)

                    if gh > ga: res = '1'
                    elif ga > gh: res = '2'
                    else: res = 'X'

                    # Aggiungi al buffer in memoria
                    doc = {
                        "league": league['name'],
                        "date": formatted_date,
                        "homeTeam": home,
                        "awayTeam": away,
                        "homeGoals": gh,
                        "awayGoals": ga,
                        "result": res,
                        "odds_1": o1, "odds_x": ox, "odds_2": o2,
                        "source": "betexplorer",
                        "unique_id": f"{formatted_date}_{home}_{away}"
                    }
                    ALL_MATCHES_BUFFER.append(doc)
                    league_count += 1

                except:
                    continue
            print(f"   📦 In buffer: {league_count} partite.")

        except Exception as e:
            print(f"   ❌ Errore {league['name']}: {e}")

    driver.quit()

    # --- FASE CRITICA: SOSTITUZIONE DB ---
    if len(ALL_MATCHES_BUFFER) > 50: # Controllo sicurezza (non cancellare se lo scraper ha fallito)
        print(f"\n🧹 SVUOTO DB VECCHIO...")
        history_col.delete_many({}) # CANCELLA TUTTO
        print("   ✅ DB Svuotato.")
        
        print(f"💾 SALVO {len(ALL_MATCHES_BUFFER)} NUOVE PARTITE...")
        history_col.insert_many(ALL_MATCHES_BUFFER)
        print("   ✅ Salvataggio completato! Il DB ora è pulito e aggiornato.")
    else:
        print("\n⚠️ ATTENZIONE: Scaricate poche partite (<50). Non tocco il DB per sicurezza.")

if __name__ == "__main__":
    run_scraper()
