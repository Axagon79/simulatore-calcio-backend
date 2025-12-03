import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time

# CONFIGURAZIONE DB
history_col = db['matches_history']

LEAGUES = [
    {"name": "Serie A", "url": "https://www.betexplorer.com/it/football/italy/serie-a/results/"},
    {"name": "Serie B", "url": "https://www.betexplorer.com/it/football/italy/serie-b/results/"},
    {"name": "Serie C - Girone A", "url": "https://www.betexplorer.com/it/football/italy/serie-c-group-a/results/"},
    {"name": "Serie C - Girone B", "url": "https://www.betexplorer.com/it/football/italy/serie-c-group-b/results/"},
    {"name": "Serie C - Girone C", "url": "https://www.betexplorer.com/it/football/italy/serie-c-group-c/results/"},
    {"name": "Premier League", "url": "https://www.betexplorer.com/it/football/england/premier-league/results/"},
    {"name": "La Liga", "url": "https://www.betexplorer.com/it/football/spain/laliga/results/"},
    {"name": "Bundesliga", "url": "https://www.betexplorer.com/it/football/germany/bundesliga/results/"},
    {"name": "Ligue 1", "url": "https://www.betexplorer.com/it/football/france/ligue-1/results/"},
    {"name": "Eredivisie", "url": "https://www.betexplorer.com/it/football/netherlands/eredivisie/results/"},
    {"name": "Liga Portugal", "url": "https://www.betexplorer.com/it/football/portugal/liga-portugal/results/"},
    {"name": "Super Lig", "url": "https://www.betexplorer.com/it/football/turkey/super-lig/results/"}
]

def clean_float(txt):
    try:
        if not txt or txt == '-': return None
        return float(txt)
    except:
        return None

def run_scraper():
    print("🚀 AVVIO SCRAPER SELENIUM...")

    chrome_options = Options()
    # chrome_options.add_argument("--headless") # Scommenta per nascondere il browser
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--log-level=3")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    for league in LEAGUES:
        print(f"\n🌍 Analisi {league['name']}...")
        try:
            driver.get(league['url'])

            # Attesa tabella
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "table"))
                )
                time.sleep(3) 
            except:
                print("⚠️ Timeout attesa tabella.")
                continue

            rows = driver.find_elements(By.TAG_NAME, "tr")
            saved_count = 0

            for row in rows:
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) < 6: continue

                    # 1. Partita
                    match_text = cells[0].text.replace("\n", " ")
                    if "-" not in match_text: continue

                    parts = match_text.split("-")
                    home = parts[0].strip()
                    away = parts[1].strip()

                    # 2. Risultato
                    score_text = cells[1].text
                    if ":" not in score_text: continue

                    score_parts = score_text.split(":")
                    gh = int(score_parts[0])
                    ga = int(score_parts[1])

                    # 3. Quote
                    o1 = clean_float(cells[2].text)
                    ox = clean_float(cells[3].text)
                    o2 = clean_float(cells[4].text)

                    if o1 is None: continue 

                    # 4. Data
                    date_str = cells[5].text

                    # Salvataggio
                    doc = {
                        "league": league['name'],
                        "home_team": home, "away_team": away,
                        "home_goals": gh, "away_goals": ga,
                        "odds_1": o1, "odds_x": ox, "odds_2": o2,
                        "date_str": date_str,
                        "timestamp": time.time()
                    }

                    history_col.update_one(
                        {"league": league['name'], "home_team": home, "away_team": away},
                        {"$set": doc},
                        upsert=True
                    )
                    saved_count += 1

                except Exception:
                    continue

            print(f"   ✅ Salvate {saved_count} partite con quote.")

        except Exception as e:
            print(f"   ❌ Errore campionato: {e}")

    driver.quit()
    print("\n🏁 Finito.")

if __name__ == "__main__":
    run_scraper()