import os
import sys
import time
import re
from datetime import datetime

# --- SETUP PERCORSI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_dir = os.path.dirname(os.path.dirname(current_dir))
project_root = os.path.dirname(ai_engine_dir)

if ai_engine_dir not in sys.path: sys.path.insert(0, ai_engine_dir)
if project_root not in sys.path: sys.path.insert(0, project_root)

try:
    from config import db
    print(f"✅ DB Connesso: {db.name}")
except ImportError:
    # Fallback brutale se non trova il config
    sys.path.append(r"C:\Progetti\simulatore-calcio-backend\ai_engine")
    try: from config import db
    except: sys.exit(1)

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    print("❌ Errore: Selenium non installato.")
    sys.exit(1)

# --- CONFIGURAZIONE LEGHE DA CONTROLLARE ---
LEAGUES_CONFIG = [
    {"name": "Serie A", "url": "https://football.nowgoal26.com/subleague/34"},
    {"name": "Serie B", "url": "https://football.nowgoal26.com/subleague/40"},
    {"name": "Serie C - Girone A", "url": "https://football.nowgoal26.com/subleague/142"},
    {"name": "Serie C - Girone B", "url": "https://football.nowgoal26.com/subleague/2025-2026/142/1526"},
    {"name": "Serie C - Girone C", "url": "https://football.nowgoal26.com/subleague/144"},
    {"name": "Premier League", "url": "https://football.nowgoal26.com/league/36"},
    {"name": "La Liga", "url": "https://football.nowgoal26.com/league/31"},
    {"name": "Bundesliga", "url": "https://football.nowgoal26.com/league/8"},
    {"name": "Ligue 1", "url": "https://football.nowgoal26.com/league/11"},
    {"name": "Eredivisie", "url": "https://football.nowgoal26.com/league/16"},
    {"name": "Liga Portugal", "url": "https://football.nowgoal26.com/league/23"},
]

def normalize_name_base(name):
    """Normalizzazione base senza le correzioni speciali, per vedere il problema 'puro'"""
    if not name: return ""
    return name.lower().strip()

def get_round_number_from_text(text):
    match = re.search(r'(\d+)', str(text))
    return int(match.group(1)) if match else 0

def click_specific_round(driver, target_round):
    try:
        str_round = str(target_round)
        xpath_list = [
            f"//div[contains(@class,'subLeague_round')]//a[text()='{str_round}']",
            f"//td[text()='{str_round}']",
            f"//li[text()='{str_round}']"
        ]
        element = None
        for xpath in xpath_list:
            try:
                element = driver.find_element(By.XPATH, xpath)
                if element: break
            except: pass
        if not element: return False
        driver.execute_script("arguments[0].click();", element) 
        time.sleep(2)
        return True
    except: return False

def run_diagnostic():
    print(f"\n🕵️  AVVIO DIAGNOSTICA NOMI SQUADRE")
    print(f"    (Questo script non modifica il DB, cerca solo errori di matching)")
    
    chrome_options = Options()
    # chrome_options.add_argument("--headless") # Commentato per vedere cosa succede
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--log-level=3")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    missing_report = []

    try:
        for league in LEAGUES_CONFIG:
            lname = league['name']
            url = league['url']
            print(f"\n🏆 CONTROLLO: {lname}")
            
            # Prende l'ultima giornata Scheduled o Timed dal DB
            rounds_cursor = db.h2h_by_round.find({"league": lname})
            rounds_list = list(rounds_cursor)
            if not rounds_list: continue
            
            rounds_list.sort(key=lambda x: get_round_number_from_text(x.get('round_name', '0')))
            
            # Cerca la giornata attiva
            active_round = None
            for r in rounds_list:
                if any(m.get('status') in ['Scheduled', 'Timed', 'Finished'] for m in r.get('matches', [])):
                     # Prendiamo l'ultima giocata o quella attuale per avere più dati possibile
                     active_round = r
            
            if not active_round: 
                print("   Nessuna giornata rilevante trovata.")
                continue

            r_num = get_round_number_from_text(active_round['round_name'])
            print(f"   📅 Analisi Giornata {r_num}...")

            driver.get(url)
            time.sleep(3)
            click_specific_round(driver, r_num)
            
            # Legge tutto il testo della pagina (righe della tabella)
            try: 
                rows = driver.find_elements(By.CSS_SELECTOR, "tr[id]")
                site_texts = [r.text.lower() for r in rows]
            except: 
                print("   ❌ Impossibile leggere la tabella.")
                continue

            # Confronta DB vs SITO
            for m in active_round['matches']:
                h_db = normalize_name_base(m['home'])
                a_db = normalize_name_base(m['away'])
                
                found = False
                for txt in site_texts:
                    if h_db in txt and a_db in txt:
                        found = True
                        break
                
                if not found:
                    # Tenta di trovare un suggerimento parziale
                    suggestion = "Nessun suggerimento evidente"
                    for txt in site_texts:
                        # Cerca se almeno una parola della squadra è presente
                        h_parts = [p for p in h_db.split() if len(p)>3]
                        if any(p in txt for p in h_parts):
                             suggestion = f"Forse è questa riga? -> '{txt[:40]}...'"
                             break

                    report_line = f"[{lname}] DB: '{m['home']}' vs '{m['away']}' | {suggestion}"
                    print(f"   ⚠️  MANCANTE: {m['home']} - {m['away']}")
                    missing_report.append(report_line)

    except Exception as e:
        print(f"❌ Errore imprevisto: {e}")
    finally:
        driver.quit()

    # Salvataggio Report
    if missing_report:
        with open("MISSING_TEAMS.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(missing_report))
        print(f"\n📝 FILE GENERATO: MISSING_TEAMS.txt ({len(missing_report)} partite non trovate)")
        print("   Apri questo file per vedere quali nomi aggiungere al dizionario 'replacements'.")
    else:
        print("\n✅ OTTIMO! Nessuna squadra mancante trovata. I nomi coincidono tutti.")

if __name__ == "__main__":
    run_diagnostic()
