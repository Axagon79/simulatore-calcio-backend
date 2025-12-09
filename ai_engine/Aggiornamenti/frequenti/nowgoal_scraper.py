import os
import sys
import time
import re
from datetime import datetime, timedelta

# FIX PERCORSI
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_dir = os.path.dirname(os.path.dirname(current_dir))
project_root = os.path.dirname(ai_engine_dir)

if ai_engine_dir not in sys.path: sys.path.insert(0, ai_engine_dir)
if project_root not in sys.path: sys.path.insert(0, project_root)

try:
    from config import db
    print(f"✅ DB Connesso: {db.name}")
except ImportError:
    sys.path.append(r"C:\Progetti\simulatore-calcio-backend\ai_engine")
    try: from config import db
    except: sys.exit(1)

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    print("❌ Errore Selenium.")
    sys.exit(1)

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
    {"name": "Liga Portugal", "url": "https://football.nowgoal26.com/league/23"} 
]

def normalize_name(name):
    if not name: return ""
    name = name.lower().strip()
    
    # --- DIZIONARIO DI CORREZIONI MASSIVO ---
    replacements = {
        # --- GENERALE & PREFISSI/SUFFISSI ---
        "fc ": "", "cf ": "", "ac ": "", "as ": "", "sc ": "", "us ": "", "ss ": "", 
        "calcio": "", "team ": "", "sport": "", "1918": "", "1913": "", "1928": "",
        "united": "utd", "city": "ci", # Normalizzazione generica
        
        # --- CARATTERI SPECIALI ---
        "ü": "u", "ö": "o", "é": "e", "è": "e", "ñ": "n", "ã": "a", "ç": "c",
        "südtirol": "sudtirol", "köln": "koln",
        
        # --- SERIE A/B/C (ITALIA) ---
        "inter milan": "inter", "inter u23": "inter", 
        "juve next gen": "juventus", "juventus u23": "juventus", "juve stabia": "juve",
        "atalanta u23": "atalanta", "milan futuro": "milan",
        "giana erminio": "giana", 
        "virtus verona": "virtus", "virtus entella": "entella",
        "audace cerignola": "cerignola", "team altamura": "altamura",
        "albinoLeffe": "albinoleffe", "arzignano": "arzignano",
        "sorrento": "sorrento", "picerno": "picerno", "latina": "latina",
        "benevento": "benevento", "avellino": "avellino",
        "catania": "catania", "foggia": "foggia", "crotone": "crotone",
        
        # --- PREMIER LEAGUE (INGHILTERRA) ---
        "manchester utd.": "manchester united", "man utd": "manchester united",
        "man city": "manchester city",
        "nott'm forest": "nottingham forest", "nottingham": "nottingham forest",
        "west ham utd.": "west ham", "west ham united": "west ham",
        "brighton": "brighton hove albion", "wolves": "wolverhampton",
        "newcastle": "newcastle united", "leeds": "leeds united",
        
        # --- LA LIGA (SPAGNA) ---
        "atlético": "atletico madrid", "atletico": "atletico madrid",
        "barcellona": "barcelona", "siviglia": "sevilla",
        "celta de vigo": "celta vigo", "celta": "celta vigo",
        "rayo vallecano": "rayo", "alavés": "alaves",
        "athletic club": "athletic bilbao", 
        
        # --- BUNDESLIGA (GERMANIA) ---
        "bayern": "bayern munchen", "bayern monaco": "bayern munchen",
        "leverkusen": "bayer leverkusen", "bayer": "bayer leverkusen",
        "dortmund": "borussia dortmund", 
        "magonza": "mainz", "mainz 05": "mainz",
        "colonia": "koln", "fc koln": "koln",
        "friburgo": "freiburg", 
        "eintracht": "eintracht frankfurt",
        "stoccarda": "stuttgart",
        "lipsia": "rb leipzig", "leipzig": "rb leipzig",
        "bor. m'gladbach": "borussia monchengladbach", "gladbach": "monchengladbach",
        
        # --- LIGUE 1 (FRANCIA) ---
        "marsiglia": "marseille", "olympique marseille": "marseille",
        "nizza": "nice", "ogc nice": "nice",
        "lione": "lyon", "olymp. lione": "lyon",
        "stade rennes": "rennes",
        "psg": "paris saint germain",
        
        # --- EREDIVISIE & PORTOGALLO ---
        "psv": "psv eindhoven", "az alkmaar": "az",
        "sporting cp": "sporting", "sporting lisbona": "sporting",
        "vit. guimarães": "vitoria guimaraes",
    }
    
    for k, v in replacements.items():
        if k in name: # Sostituzione più aggressiva
            name = name.replace(k, v)
            
    return name.strip()



def get_round_number_from_text(text):
    match = re.search(r'(\d+)', str(text))
    return int(match.group(1)) if match else 0

def click_specific_round(driver, target_round):
    try:
        str_round = str(target_round)
        xpath_list = [
            f"//div[contains(@class,'subLeague_round')]//a[text()='{str_round}']",
            f"//td[text()='{str_round}']",
            f"//li[text()='{str_round}']",
            f"//a[normalize-space()='{str_round}']"
        ]
        element = None
        for xpath in xpath_list:
            try:
                element = driver.find_element(By.XPATH, xpath)
                if element: break
            except: pass
        if not element: return False
        driver.execute_script("arguments[0].click();", element) 
        time.sleep(3)
        return True
    except: return False

def get_target_rounds(league_name):
    rounds_cursor = db.h2h_by_round.find({"league": league_name})
    rounds_list = list(rounds_cursor)
    if not rounds_list: return []
    rounds_list.sort(key=lambda x: get_round_number_from_text(x.get('round_name', '0')))
    
    anchor_index = -1
    for i, r in enumerate(rounds_list):
        matches = r.get('matches', [])
        if any(m.get('status') in ['Scheduled', 'Timed'] for m in matches):
            anchor_index = i
            break
    if anchor_index == -1: anchor_index = len(rounds_list) - 1
    
    indices = [anchor_index - 1, anchor_index, anchor_index + 1]
    return [rounds_list[i] for i in indices if 0 <= i < len(rounds_list)]

def run_scraper():
    print(f"\n🚀 AVVIO SCRAPER (LOGICA STRICT: Aggiorna se diverse o scadute)")
    
    chrome_options = Options()
    # chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--log-level=3")
    
    driver = None
    total_updated = 0

    try:
        for league in LEAGUES_CONFIG:
            lname = league['name']
            url = league['url']
            
            rounds_to_process = get_target_rounds(lname)
            if not rounds_to_process: continue

            if driver is None:
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)

            driver.get(url)
            time.sleep(3)

            for round_doc in rounds_to_process:
                round_num = get_round_number_from_text(round_doc['round_name'])
                print(f"   🔄 {lname} G.{round_num}...", end="")
                
                click_specific_round(driver, round_num)
                
                try: rows = driver.find_elements(By.CSS_SELECTOR, "tr[id]")
                except: rows = []
                
                scraped_data = []
                for row in rows:
                    try:
                        row_text = row.text.lower()
                        floats = [float(x) for x in re.findall(r'\d+\.\d{2}', row_text)]
                        valid_odds = [f for f in floats if 1.01 <= f <= 25.0]
                        if len(valid_odds) >= 3:
                            scraped_data.append({
                                "text": row_text,
                                "1": valid_odds[0], "X": valid_odds[1], "2": valid_odds[2]
                            })
                    except: continue
                
                matches = round_doc['matches']
                mod = False
                match_count = 0
                
                for m in matches:
                    # 1. Carichiamo la squadra dal DB per leggere i suoi alias
                    team_h_doc = db.teams.find_one({"name": m['home']})
                    team_a_doc = db.teams.find_one({"name": m['away']})

                    # 2. Creiamo la lista di TUTTI i nomi possibili (Nome vero + Alias)
                    # Per la casa
                    possible_names_h = [m['home'].lower().strip()]
                    if team_h_doc and 'aliases' in team_h_doc:
                        possible_names_h.extend([x.lower().strip() for x in team_h_doc['aliases'] if x])
                    
                    # Per la trasferta
                    possible_names_a = [m['away'].lower().strip()]
                    if team_a_doc and 'aliases' in team_a_doc:
                        possible_names_a.extend([x.lower().strip() for x in team_a_doc['aliases'] if x])

                    found_item = None
                    
                    # 3. CONTROLLO POTENZIATO
                    # Controlliamo ogni riga del sito usando le liste estese
                    for item in scraped_data:
                        row_txt = item['text'] # È già minuscolo
                        
                        # C'è almeno un nome di Casa nella riga?
                        h_match = any(alias in row_txt for alias in possible_names_h)
                        # C'è almeno un nome di Trasferta nella riga?
                        a_match = any(alias in row_txt for alias in possible_names_a)

                        if h_match and a_match:
                            found_item = item
                            break
                            if h in item['text'] and a in item['text']:
                                found_item = item
                                break
                    
                    # Se non trovo la quota nel sito, passo alla prossima (Pace)
                    if not found_item:
                        continue

                    # Nuove quote trovate
                    new_odds_val = {
                        "1": found_item["1"], "X": found_item["X"], "2": found_item["2"],
                        "src": "NowGoal", "ts": datetime.now()
                    }

                    # DECISIONE: AGGIORNARE O NO?
                    should_update = False
                    
                    if 'odds' not in m:
                        # Caso 1: Non c'era quota -> Aggiorna sicuro
                        should_update = True
                    else:
                        # Caso 2: C'era quota. Controlliamo tempo e valore.
                        # Tempo
                        is_fresh = (datetime.now() - m['odds'].get('ts', datetime.min)).total_seconds() < 21600
                        
                        # Valore
                        old_1 = m['odds'].get('1')
                        old_X = m['odds'].get('X')
                        old_2 = m['odds'].get('2')
                        is_different = (old_1 != new_odds_val['1'] or old_X != new_odds_val['X'] or old_2 != new_odds_val['2'])
                        
                        if not is_fresh:
                            # Se è vecchia -> Aggiorna (per rinfrescare il timestamp anche se uguale)
                            should_update = True
                        elif is_different:
                            # Se è fresca MA diversa -> Aggiorna (Variazione Live)
                            should_update = True
                        # Se è fresca E uguale -> Salta (should_update resta False)
                    
                    if should_update:
                        m['odds'] = new_odds_val
                        mod = True
                        match_count += 1
                
                if mod:
                    db.h2h_by_round.update_one({"_id": round_doc["_id"]}, {"$set": {"matches": matches}})
                    print(f" ✅ Aggiornate {match_count} quote.")
                    total_updated += match_count
                else:
                    print(f" (Nessuna variazione)")

    except Exception as e:
        print(f"❌ Errore: {e}")
    finally:
        if driver: driver.quit()
        print(f"\n🏁 FINE. Totale Aggiornati: {total_updated}")

if __name__ == "__main__":
    run_scraper()
