import os
import sys
import time
import re
from datetime import datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait



# --- CONFIGURAZIONE PERCORSI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_dir = os.path.dirname(os.path.dirname(current_dir))
project_root = os.path.dirname(ai_engine_dir)



if ai_engine_dir not in sys.path:
    sys.path.insert(0, ai_engine_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)



try:
    from config import db
    print(f"✅ DB Connesso: {db.name}")
except ImportError:
    print("❌ Errore Import Config")
    sys.exit(1)



# --- CONFIGURAZIONE ---
COLLECTION_NAME = "h2h_by_round"
TARGET_SEASON = "2025"



LEAGUES_TM = [
    {"name": "Serie A", "url": f"https://www.transfermarkt.it/serie-a/gesamtspielplan/wettbewerb/IT1/saison_id/{TARGET_SEASON}"},
    {"name": "Serie B", "url": f"https://www.transfermarkt.it/serie-b/gesamtspielplan/wettbewerb/IT2/saison_id/{TARGET_SEASON}"},
    {"name": "Serie C - Girone A", "url": f"https://www.transfermarkt.it/serie-c-girone-a/gesamtspielplan/wettbewerb/IT3A/saison_id/{TARGET_SEASON}"},
    {"name": "Serie C - Girone B", "url": f"https://www.transfermarkt.it/serie-c-girone-b/gesamtspielplan/wettbewerb/IT3B/saison_id/{TARGET_SEASON}"},
    {"name": "Serie C - Girone C", "url": f"https://www.transfermarkt.it/serie-c-girone-c/gesamtspielplan/wettbewerb/IT3C/saison_id/{TARGET_SEASON}"},
    {"name": "Premier League", "url": f"https://www.transfermarkt.it/premier-league/gesamtspielplan/wettbewerb/GB1/saison_id/{TARGET_SEASON}"},
    {"name": "La Liga", "url": f"https://www.transfermarkt.it/laliga/gesamtspielplan/wettbewerb/ES1/saison_id/{TARGET_SEASON}"},
    {"name": "Bundesliga", "url": f"https://www.transfermarkt.it/bundesliga/gesamtspielplan/wettbewerb/L1/saison_id/{TARGET_SEASON}"},
    {"name": "Ligue 1", "url": f"https://www.transfermarkt.it/ligue-1/gesamtspielplan/wettbewerb/FR1/saison_id/{TARGET_SEASON}"},
    {"name": "Eredivisie", "url": f"https://www.transfermarkt.it/eredivisie/gesamtspielplan/wettbewerb/NL1/saison_id/{TARGET_SEASON}"},
    {"name": "Liga Portugal", "url": f"https://www.transfermarkt.it/liga-nos/gesamtspielplan/wettbewerb/PO1/saison_id/{TARGET_SEASON}"}
]



# --- UTILS ---
def extract_tm_id(url):
    """Estrae l'ID numerico dal link (es. /verein/1234)."""
    if not url: return None
    match = re.search(r'/verein/(\d+)', url)
    return match.group(1) if match else None



def extract_round_number(text):
    """Estrae solo il numero dalla giornata (es. '19. Giornata' -> '19')."""
    if not text: return None
    match = re.search(r'(\d+)', text)
    return match.group(1) if match else None



def setup_driver():
    """Configura il browser Chrome in modalità headless (senza finestra)."""
    chrome_options = Options()
    #chrome_options.add_argument("--headless")  # Esegue senza aprire la finestra
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver



def process_league(col, league, driver):
    print(f"\n🌍 Elaborazione: {league['name']}...")
    updated_count = 0
    
    try:
        # SELENIUM: Apriamo la pagina con il browser vero
        print(f"   → Carico pagina: {league['url']}")
        driver.get(league['url'])
        
        # ⬇️⬇️⬇️ MODIFICA QUI: TRIPLO REFRESH ⬇️⬇️⬇️
        print(f"   ⏳ Aspetto caricamento iniziale...")
        time.sleep(4)  # Aspettiamo che la pagina si carichi completamente
        
        # Facciamo 3 refresh consecutivi per forzare i dati freschi
        for i in range(1, 4):
            print(f"   🔄 Refresh #{i}/3...")
            driver.refresh()
            time.sleep(4)  # Aspettiamo dopo ogni refresh
        # ⬆️⬆️⬆️ FINE MODIFICA ⬆️⬆️⬆️
        
        # Prendiamo l'HTML aggiornato
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, "html.parser")
        
        headers = soup.find_all("div", class_="content-box-headline")


        for header in headers:
            round_name_tm = header.get_text(strip=True)
            round_num = extract_round_number(round_name_tm)
            if not round_num: continue


            safe_league = league['name'].replace(" ", "")
            doc_id = f"{safe_league}_{round_num}Giornata"


            db_doc = col.find_one({"_id": doc_id})
            if not db_doc: continue


            db_matches = db_doc.get("matches", [])
            modified_doc = False


            table = header.find_next("table")
            if not table: continue
            rows = table.find_all("tr")


            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 5: continue


                team_links = [
                    a for a in row.find_all("a")
                    if a.get("title") and "spielbericht" not in a.get("href", "") and "verein" in a.get("href", "")
                ]
                if len(team_links) < 2: continue


                home_id_tm = extract_tm_id(team_links[0]['href'])
                away_id_tm = extract_tm_id(team_links[-1]['href'])
                if not home_id_tm or not away_id_tm: continue


                final_score = None
                full_text = row.get_text(" ", strip=True)
                candidates = re.findall(r'(\d+:\d+)', full_text)
                
                if not candidates:
                    continue


                candidate_score = candidates[-1]


                if len(candidate_score) <= 4:
                    final_score = candidate_score
                else:
                    continue


                for m in db_matches:
                    db_h_id = str(m.get('home_tm_id', ''))
                    db_a_id = str(m.get('away_tm_id', ''))


                    if db_h_id == home_id_tm and db_a_id == away_id_tm:
                        if m.get('real_score') != final_score:
                            m['real_score'] = final_score
                            m['status'] = "Finished"
                            modified_doc = True
                            updated_count += 1
                            print(f"   ✅ {m['home']} - {m['away']} -> {final_score}")
                        break


            if modified_doc:
                col.update_one(
                    {"_id": doc_id},
                    {"$set": {"matches": db_matches, "last_updated": datetime.now()}}
                )


    except Exception as e:
        print(f"   ❌ Errore in {league['name']}: {e}")


    return updated_count



def run_auto_update():
    print("\n🚀 AGGIORNAMENTO AUTOMATICO (SELENIUM + TRIPLO REFRESH)")
    col = db[COLLECTION_NAME]
    
    # Avviamo il browser UNA VOLTA SOLA
    driver = setup_driver()
    
    try:
        total = 0
        for league in LEAGUES_TM:
            total += process_league(col, league, driver)
        
        print(f"\n🏁 FINE. Partite aggiornate: {total}")
    
    finally:
        # Chiudiamo il browser alla fine
        driver.quit()



if __name__ == "__main__":
    run_auto_update()
