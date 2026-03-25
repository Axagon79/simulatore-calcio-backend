import os
import sys
import time
import re
import subprocess
import atexit

_active_driver = None
def _cleanup():
    global _active_driver
    if _active_driver:
        try: _active_driver.quit()
        except: pass
        _active_driver = None
atexit.register(_cleanup)
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
    # ITALIA
    {"name": "Serie A", "url": "https://football.nowgoal26.com/subleague/34"},
    {"name": "Serie B", "url": "https://football.nowgoal26.com/subleague/40"},
    {"name": "Serie C - Girone A", "url": "https://football.nowgoal26.com/subleague/142", "stage": "1525"},
    {"name": "Serie C - Girone B", "url": "https://football.nowgoal26.com/subleague/142", "stage": "1526"},
    {"name": "Serie C - Girone C", "url": "https://football.nowgoal26.com/subleague/142", "stage": "1527"},
    # EUROPA TOP
    {"name": "Premier League", "url": "https://football.nowgoal26.com/league/36"},
    {"name": "La Liga", "url": "https://football.nowgoal26.com/league/31"},
    {"name": "Bundesliga", "url": "https://football.nowgoal26.com/league/8"},
    {"name": "Ligue 1", "url": "https://football.nowgoal26.com/league/11"},
    {"name": "Eredivisie", "url": "https://football.nowgoal26.com/league/16"},
    {"name": "Liga Portugal", "url": "https://football.nowgoal26.com/league/23"},
    # EUROPA SERIE B
    {"name": "Championship", "url": "https://football.nowgoal26.com/league/37"},
    {"name": "League One", "url": "https://football.nowgoal26.com/league/39"},
    {"name": "LaLiga 2", "url": "https://football.nowgoal26.com/subleague/33"},
    {"name": "2. Bundesliga", "url": "https://football.nowgoal26.com/league/9"},
    {"name": "Ligue 2", "url": "https://football.nowgoal26.com/league/12"},
    # EUROPA NORDICI + EXTRA
    {"name": "Scottish Premiership", "url": "https://football.nowgoal26.com/subleague/29"},
    {"name": "Allsvenskan", "url": "https://football.nowgoal26.com/subleague/26"},
    {"name": "Eliteserien", "url": "https://football.nowgoal26.com/subleague/22"},
    {"name": "Superligaen", "url": "https://football.nowgoal26.com/subleague/7"},
    {"name": "Jupiler Pro League", "url": "https://football.nowgoal26.com/subleague/5"},
    {"name": "Süper Lig", "url": "https://football.nowgoal26.com/subleague/30"},
    {"name": "League of Ireland Premier Division", "url": "https://football.nowgoal26.com/subleague/1"},
    # AMERICHE
    {"name": "Brasileirão Serie A", "url": "https://football.nowgoal26.com/league/4"},
    {"name": "Primera División", "url": "https://football.nowgoal26.com/subleague/2"},
    {"name": "Major League Soccer", "url": "https://football.nowgoal26.com/subleague/21"},
    # ASIA
    {"name": "J1 League", "url": "https://football.nowgoal26.com/subleague/25"},

    # NUOVI CAMPIONATI (24/03/2026)
    {"name": "League Two", "url": "https://football.nowgoal26.com/league/35"},
    {"name": "Veikkausliiga", "url": "https://football.nowgoal26.com/subleague/13"},
    {"name": "3. Liga", "url": "https://football.nowgoal26.com/league/693"},
    {"name": "Liga MX", "url": "https://football.nowgoal26.com/subleague/140", "has_stages": True},
    {"name": "Eerste Divisie", "url": "https://football.nowgoal26.com/subleague/17"},
    {"name": "Liga Portugal 2", "url": "https://football.nowgoal26.com/subleague/157"},
    {"name": "1. Lig", "url": "https://football.nowgoal26.com/subleague/130"},
    {"name": "Saudi Pro League", "url": "https://football.nowgoal26.com/subleague/292"},
    {"name": "Scottish Championship", "url": "https://football.nowgoal26.com/subleague/150"},
]

def strip_accents(text):
    """Rimuove accenti per matching flessibile"""
    for k, v in {'á':'a','à':'a','ã':'a','â':'a','é':'e','è':'e','ê':'e',
                  'í':'i','ì':'i','ó':'o','ò':'o','ô':'o','õ':'o',
                  'ú':'u','ù':'u','ü':'u','ñ':'n','ç':'c','ø':'o','å':'a','ä':'a'}.items():
        text = text.replace(k, v)
    return text

def clean_nowgoal_text(text):
    """Pulisce testo riga NowGoal: rimuove [N], separa numeri incollati a lettere"""
    text = re.sub(r'\[\d+\]', '', text)             # [20], [3] etc.
    text = re.sub(r'(\d)([a-z])', r'\1 \2', text)   # 3real → 3 real
    text = re.sub(r'([a-z])(\d)', r'\1 \2', text)   # madrid2 → madrid 2
    return strip_accents(text)

def generate_search_names(name):
    """Da un alias genera varianti senza prefissi/suffissi comuni (input già lowercase)"""
    name = strip_accents(name)
    names = [name]
    for p in ['fc ', 'cf ', 'ca ', 'rcd ', 'cd ', 'ud ', 'rc ', 'sd ']:
        if name.startswith(p):
            short = name[len(p):].strip()
            if len(short) >= 3: names.append(short)
    for s in [' fc', ' cf']:
        if name.endswith(s):
            short = name[:-len(s)].strip()
            if len(short) >= 3: names.append(short)
    if ' de ' in name:
        names.append(name.replace(' de ', ' '))
    return list(set(names))

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
        "ü": "u", "ö": "o", "é": "e", "è": "e", "ì": "i", "ñ": "n", "ã": "a", "ç": "c",
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

def click_specific_round(driver, target_round, stage=None):
    try:
        element = None
        # Se c'è uno stage (Serie C), clicca la giornata dello stage corretto
        if stage:
            try:
                element = driver.find_element(By.CSS_SELECTOR, f"div.round span[round='{target_round}'][stage='{stage}']")
            except:
                pass
        # Altrimenti cerca la giornata visibile
        if not element:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, f"div.round span[round='{target_round}']")
                for el in elements:
                    if el.is_displayed():
                        element = el
                        break
            except: pass
        if not element:
            return False
        # Salva contenuto attuale per verificare il cambio
        try:
            old_html = driver.find_element(By.CSS_SELECTOR, "div.list").get_attribute("innerHTML")[:200]
        except:
            old_html = ""
        # Click nativo Selenium (l'elemento è visibile e il sito usa onclick bubbling)
        element.click()
        # Attendi che il contenuto cambi (max 10 secondi)
        for _ in range(20):
            time.sleep(0.5)
            try:
                new_html = driver.find_element(By.CSS_SELECTOR, "div.list").get_attribute("innerHTML")[:200]
                if new_html != old_html:
                    break
            except:
                pass
        time.sleep(2)
        return True
    except:
        return False

def get_target_rounds_from_page(driver, league_name, has_stages=False):
    """Legge il round corrente dalla pagina NowGoal e restituisce i 3 round dal DB (corrente, -1, +1)."""
    current_round = None
    try:
        if has_stages:
            elements = driver.find_elements(By.CSS_SELECTOR, "div.round span.current")
            if elements:
                current_round = int(elements[-1].get_attribute("round"))
        else:
            el = driver.find_element(By.CSS_SELECTOR, "div.round span.current")
            current_round = int(el.get_attribute("round"))
    except:
        pass

    # Salva la giornata corrente nel DB per index.js
    if current_round is not None:
        from datetime import datetime, timezone
        db.league_current_rounds.update_one(
            {"league": league_name},
            {"$set": {"current_round": current_round, "updated_at": datetime.now(timezone.utc)}},
            upsert=True
        )

    rounds_cursor = db.h2h_by_round.find({"league": league_name})
    rounds_list = list(rounds_cursor)
    if not rounds_list: return []
    rounds_list.sort(key=lambda x: get_round_number_from_text(x.get('round_name', '0')))

    if current_round is None:
        # Fallback: ultima giornata
        anchor_index = len(rounds_list) - 1
    else:
        anchor_index = -1
        for i, r in enumerate(rounds_list):
            if get_round_number_from_text(r.get('round_name', '0')) == current_round:
                anchor_index = i
                break
        if anchor_index == -1:
            anchor_index = len(rounds_list) - 1

    indices = [anchor_index, anchor_index - 1, anchor_index + 1]
    return [rounds_list[i] for i in indices if 0 <= i < len(rounds_list)]

def run_scraper():
    print(f"\n🚀 AVVIO SCRAPER (LOGICA STRICT: Aggiorna se diverse o scadute)")
    
    chrome_options = Options()
    # chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--log-level=3")
    
    driver = None
    total_updated = 0
    league_stats = []  # Report per campionato
    scraper_start = time.time()

    # Cache tutti i teams per evitare query ripetute (1 query invece di ~1800)
    _teams_cache = {}
    for t in db.teams.find({}, {"name": 1, "aliases": 1}):
        _teams_cache[t['name']] = t

    try:
        for league in LEAGUES_CONFIG:
            lname = league['name']
            url = league['url']
            league_start = time.time()
            league_found = 0
            league_updated = 0
            league_skipped = 0
            
            if driver is None:
                chrome_ver = None
                try:
                    r = subprocess.run(['reg', 'query', r'HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon', '/v', 'version'], capture_output=True, text=True, timeout=5)
                    for line in r.stdout.splitlines():
                        if line.strip().startswith('version'):
                            chrome_ver = line.split()[-1]
                except: pass
                service = Service(ChromeDriverManager(driver_version=chrome_ver).install() if chrome_ver else ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
                _active_driver = driver

            driver.get(url)
            time.sleep(1.5)

            # Verifica caricamento, retry con refresh se fallisce
            stage = league.get('stage')
            for attempt in range(3):
                try:
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div.schedulis"))
                    )
                    # Click sul girone se necessario (Serie C: Group A/B/C)
                    if stage:
                        try:
                            stage_btn = driver.find_element(By.CSS_SELECTOR, f"div.stage span[stage='{stage}']")
                            stage_btn.click()
                            time.sleep(1.5)
                        except:
                            pass
                    # Seleziona quote 1X2 (default e AH)
                    try:
                        odds_1x2 = driver.find_element(By.CSS_SELECTOR, "li[type='O']")
                        driver.execute_script("arguments[0].click()", odds_1x2)
                        time.sleep(1.5)
                    except:
                        pass
                    break
                except:
                    print(f"   ⚠️ Pagina non caricata, refresh ({attempt+1}/3)...")
                    driver.refresh()
                    time.sleep(5)

            has_stages = league.get('has_stages', False)
            rounds_to_process = get_target_rounds_from_page(driver, lname, has_stages=has_stages)
            if not rounds_to_process: continue

            for idx, round_doc in enumerate(rounds_to_process):
                round_num = get_round_number_from_text(round_doc['round_name'])
                print(f"   🔄 {lname} G.{round_num}...", end="")

                # La prima giornata (corrente) è già caricata, le altre servono doppio click
                if idx > 0:
                    click_specific_round(driver, round_num, stage=stage)
                    time.sleep(0.5)
                    click_specific_round(driver, round_num, stage=stage)
                    # Dopo click giornata, riseleziona solo 1X2 (il girone resta)
                    try:
                        odds_1x2 = driver.find_element(By.CSS_SELECTOR, "li[type='O']")
                        driver.execute_script("arguments[0].click()", odds_1x2)
                        time.sleep(1.5)
                    except:
                        pass

                # Nuova struttura: div.schedulis con span.odds
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(driver.page_source, "html.parser")
                match_divs = soup.find_all("div", class_="schedulis")

                scraped_data = []
                league_found += len(match_divs)
                for m_div in match_divs:
                    try:
                        # Nomi squadre
                        home_span = m_div.find("span", class_="home")
                        away_span = m_div.find("span", class_="away")
                        home_name = home_span.find("span", onclick=re.compile(r"toTeam")).get_text(strip=True).lower() if home_span and home_span.find("span", onclick=re.compile(r"toTeam")) else ""
                        away_name = away_span.find("span", onclick=re.compile(r"toTeam")).get_text(strip=True).lower() if away_span and away_span.find("span", onclick=re.compile(r"toTeam")) else ""
                        row_text = f"{home_name} {away_name}"

                        # Quote da span.odds
                        odds_span = m_div.find("span", class_="odds")
                        if odds_span:
                            odds_values = odds_span.find_all("span")
                            if len(odds_values) >= 3:
                                try:
                                    o1 = float(odds_values[0].get_text(strip=True))
                                    oX = float(odds_values[1].get_text(strip=True))
                                    o2 = float(odds_values[2].get_text(strip=True))
                                    if 1.01 <= o1 <= 25.0 and 1.01 <= oX <= 25.0 and 1.01 <= o2 <= 25.0:
                                        scraped_data.append({"text": row_text, "1": o1, "X": oX, "2": o2})
                                except:
                                    pass
                    except: continue
                

                matches = round_doc['matches']
                mod = False
                match_count = 0

                for m in matches:
                    # 1. Carichiamo la squadra dalla cache per leggere i suoi alias
                    team_h_doc = _teams_cache.get(m['home'])
                    team_a_doc = _teams_cache.get(m['away'])

                    # 2. Creiamo la lista di TUTTI i nomi possibili + varianti senza prefissi/suffissi
                    possible_names_h = [m['home'].lower().strip()]
                    if team_h_doc and 'aliases' in team_h_doc:
                        possible_names_h.extend([x.lower().strip() for x in team_h_doc['aliases'] if x])
                    search_h = []
                    for alias in possible_names_h:
                        search_h.extend(generate_search_names(alias))
                        search_h.extend(generate_search_names(clean_nowgoal_text(alias)))
                    search_h = list(set(search_h))

                    possible_names_a = [m['away'].lower().strip()]
                    if team_a_doc and 'aliases' in team_a_doc:
                        possible_names_a.extend([x.lower().strip() for x in team_a_doc['aliases'] if x])
                    search_a = []
                    for alias in possible_names_a:
                        search_a.extend(generate_search_names(alias))
                        search_a.extend(generate_search_names(clean_nowgoal_text(alias)))
                    search_a = list(set(search_a))

                    found_item = None

                    # 3. Word boundary su testo pulito (no [N], no numeri incollati, no accenti)
                    for item in scraped_data:
                        row_txt = clean_nowgoal_text(item['text'])

                        h_match = any(re.search(r'\b' + re.escape(n) + r'\b', row_txt) for n in search_h)
                        a_match = any(re.search(r'\b' + re.escape(n) + r'\b', row_txt) for n in search_a)

                        if h_match and a_match:
                            found_item = item
                            break

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
                        if 'odds' not in m:
                            m['odds'] = {}
                        m['odds']['1'] = new_odds_val['1']
                        m['odds']['X'] = new_odds_val['X']
                        m['odds']['2'] = new_odds_val['2']
                        m['odds']['src'] = new_odds_val['src']
                        m['odds']['ts'] = new_odds_val['ts']
                        mod = True
                        match_count += 1
                
                if mod:
                    db.h2h_by_round.update_one({"_id": round_doc["_id"]}, {"$set": {"matches": matches}})
                    print(f" ✅ Aggiornate {match_count} quote.")
                    total_updated += match_count
                    league_updated += match_count
                    league_skipped += len(matches) - match_count
                else:
                    print(f" (Nessuna variazione)")
                    league_skipped += len(matches)

            league_elapsed = time.time() - league_start
            league_stats.append({"name": lname, "found": league_found, "updated": league_updated, "skipped": league_skipped, "time": league_elapsed})

    except Exception as e:
        print(f"❌ Errore: {e}")
    finally:
        if driver: driver.quit()
        total_elapsed = time.time() - scraper_start
        print(f"\n{'='*80}")
        print(f"📊 RIEPILOGO SCRAPER NOWGOAL (Quote 1X2)")
        print(f"{'='*80}")
        print(f"{'Campionato':<35} | {'Trovate':>8} | {'Aggiorn':>8} | {'Saltate':>8} | {'Tempo':>8}")
        print(f"{'-'*80}")
        for s in league_stats:
            print(f"{s['name']:<35} | {s['found']:>8} | {s['updated']:>8} | {s['skipped']:>8} | {s['time']:>6.1f}s")
        print(f"{'-'*80}")
        tot_found = sum(s['found'] for s in league_stats)
        tot_skip = sum(s['skipped'] for s in league_stats)
        print(f"{'TOTALE':<35} | {tot_found:>8} | {total_updated:>8} | {tot_skip:>8} | {total_elapsed:>6.1f}s")
        print(f"{'='*80}")
        print(f"⏱️ Tempo totale: {total_elapsed/60:.1f} minuti")

if __name__ == "__main__":
    run_scraper()
