import os
import sys
import time
from datetime import datetime, timedelta

# --- FIX PERCORSI ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path: raise FileNotFoundError("No config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# COLLEZIONE PARALLELA (Sandbox)
safe_col = db['matches_history_betexplorer']

LEAGUES = [
    # ITALIA
    {"name": "Serie A", "url": "https://www.betexplorer.com/football/italy/serie-a/results/"},
    {"name": "Serie B", "url": "https://www.betexplorer.com/football/italy/serie-b/results/"},
    {"name": "Serie C - Girone A", "url": "https://www.betexplorer.com/football/italy/serie-c-group-a/results/"},
    {"name": "Serie C - Girone B", "url": "https://www.betexplorer.com/football/italy/serie-c-group-b/results/"},
    {"name": "Serie C - Girone C", "url": "https://www.betexplorer.com/football/italy/serie-c-group-c/results/"},
    
    # EUROPA TOP
    {"name": "Premier League", "url": "https://www.betexplorer.com/football/england/premier-league/results/"},
    {"name": "La Liga", "url": "https://www.betexplorer.com/football/spain/laliga/results/"},
    {"name": "Bundesliga", "url": "https://www.betexplorer.com/football/germany/bundesliga/results/"},
    {"name": "Ligue 1", "url": "https://www.betexplorer.com/football/france/ligue-1/results/"},
    {"name": "Eredivisie", "url": "https://www.betexplorer.com/football/netherlands/eredivisie/results/"},
    {"name": "Liga Portugal", "url": "https://www.betexplorer.com/football/portugal/liga-portugal/results/"},
    
    # 🆕 EUROPA SERIE B
    {"name": "Championship", "url": "https://www.betexplorer.com/football/england/championship/results/"},
    {"name": "LaLiga 2", "url": "https://www.betexplorer.com/football/spain/laliga2/results/"},
    {"name": "2. Bundesliga", "url": "https://www.betexplorer.com/football/germany/2-bundesliga/results/"},
    {"name": "Ligue 2", "url": "https://www.betexplorer.com/football/france/ligue-2/results/"},
    
    # 🆕 EUROPA NORDICI + EXTRA
    {"name": "Scottish Premiership", "url": "https://www.betexplorer.com/football/scotland/premiership/results/"},
    {"name": "Allsvenskan", "url": "https://www.betexplorer.com/football/sweden/allsvenskan/results/"},
    {"name": "Eliteserien", "url": "https://www.betexplorer.com/football/norway/eliteserien/results/"},
    {"name": "Superligaen", "url": "https://www.betexplorer.com/football/denmark/superliga/results/"},
    {"name": "Jupiler Pro League", "url": "https://www.betexplorer.com/football/belgium/jupiler-pro-league/results/"},
    {"name": "Süper Lig", "url": "https://www.betexplorer.com/football/turkey/super-lig/results/"},
    {"name": "League of Ireland Premier Division", "url": "https://www.betexplorer.com/football/ireland/premier-division/results/"},
    
    # 🆕 AMERICHE
    {"name": "Brasileirão Serie A", "url": "https://www.betexplorer.com/it/football/brazil/serie-a-betano/results/"},
    {"name": "Primera División", "url": "https://www.betexplorer.com/it/football/argentina/liga-profesional/results/"},
    {"name": "Major League Soccer", "url": "https://www.betexplorer.com/football/usa/mls/results/"},
    
    # 🆕 ASIA
    {"name": "J1 League", "url": "https://www.betexplorer.com/football/japan/j1-league/results/"}
]

def clean_float(txt):
    try:
        if not txt or txt == '-': return None
        return float(txt)
    except:
        return None

def parse_date_cell(date_text):
    """
    Estrae la data dall'ultima cella della riga (es. 'Oggi', 'Ieri', '03.12.', '15.09.').
    """
    today = datetime.now()
    txt = date_text.strip()
    
    if not txt: return "Unknown"

    # Gestione Parole Chiave
    if "Oggi" in txt or "Today" in txt:
        return today.strftime("%Y-%m-%d")
    if "Ieri" in txt or "Yesterday" in txt:
        yesterday = today - timedelta(days=1)
        return yesterday.strftime("%Y-%m-%d")
    
    # Gestione Formato numerico "DD.MM."
    try:
        # Rimuovi punto finale se presente (es "03.12.")
        clean_txt = txt.rstrip(".")
        parts = clean_txt.split(".")
        
        if len(parts) >= 2:
            day = int(parts[0])
            month = int(parts[1])
            
            # Logica Anno Intelligente
            # Se siamo a Dicembre e leggiamo "05.01", è probabile che sia Gennaio prossimo (o passato?)
            # BetExplorer mostra risultati PASSATI. Quindi:
            # Se oggi è 2025, e leggiamo 05.01, è Gennaio 2025.
            # Se oggi è Gennaio 2026 e leggiamo 15.12, è Dicembre 2025.
            
            year = today.year
            dt = datetime(year, month, day)
            
            # Se la data costruita è nel futuro (più di 2 giorni), allora è dell'anno scorso
            if dt > (today + timedelta(days=2)):
                year -= 1
            
            # Ricostruiamo con l'anno corretto
            final_dt = datetime(year, month, day)
            return final_dt.strftime("%Y-%m-%d")
            
    except:
        pass # Fallback a Unknown

    return "Unknown"

def run_scraper():
    print("🚀 AVVIO SCRAPER V3 (DATA FIX)...")
    
    ALL_MATCHES_BUFFER = []
    chrome_options = Options()
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--log-level=3")
    # Blocca immagini
    prefs = {"profile.managed_default_content_settings.images": 2}
    chrome_options.add_experimental_option("prefs", prefs)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    for league in LEAGUES:
        print(f"\n🌍 Scarico {league['name']}...")
        try:
            driver.get(league['url'])
            time.sleep(3) 

            rows = driver.find_elements(By.CSS_SELECTOR, ".table-main tr")
            league_count = 0

            for row in rows:
                try:
                    # Ignora righe header data (es. "Round 15")
                    if "h-text-left" in row.get_attribute("class") and not row.find_elements(By.TAG_NAME, "a"):
                        continue
                    
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) < 5: continue

                    # 1. SQUADRE
                    match_text = cells[0].text
                    if "-" not in match_text: continue
                    parts = match_text.split("-")
                    home = parts[0].strip()
                    away = parts[1].strip()

                    # 2. RISULTATO
                    score_text = cells[1].text
                    if ":" not in score_text: continue
                    score_parts = score_text.split(":")
                    gh = int(score_parts[0])
                    ga = int(score_parts[1])

                    # 3. QUOTE
                    o1 = clean_float(cells[2].text)
                    ox = clean_float(cells[3].text)
                    o2 = clean_float(cells[4].text)
                    
                    # 4. DATA (Ultima cella)
                    date_text = cells[-1].text
                    formatted_date = parse_date_cell(date_text)

                    # Logica risultato 1X2
                    if gh > ga: res = '1'
                    elif ga > gh: res = '2'
                    else: res = 'X'

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
            print(f"   📦 Trovate: {league_count} partite.")

        except Exception as e:
            print(f"   ❌ Errore: {e}")

    driver.quit()

    # SALVATAGGIO FINALE
    if len(ALL_MATCHES_BUFFER) > 50:
        print(f"\n🧹 PULIZIA E SALVATAGGIO IN {safe_col.name}...")
        safe_col.delete_many({}) 
        safe_col.insert_many(ALL_MATCHES_BUFFER)
        print(f"   ✅ Salvate {len(ALL_MATCHES_BUFFER)} partite correttamente.")
    else:
        print("\n⚠️ Errore: Scaricate poche partite. DB non toccato.")

if __name__ == "__main__":
    run_scraper()
