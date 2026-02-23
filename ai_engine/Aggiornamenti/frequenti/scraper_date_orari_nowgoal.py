import os
import sys
import time
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

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
    try:
        from config import db
    except:
        sys.exit(1)

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    print("❌ Errore Selenium.")
    sys.exit(1)

# CONFIGURAZIONE CAMPIONATI (identica allo script delle quote)
LEAGUES_CONFIG = [
    # ITALIA
    {"name": "Serie A", "url": "https://football.nowgoal26.com/subleague/34"},
    {"name": "Serie B", "url": "https://football.nowgoal26.com/subleague/40"},
    {"name": "Serie C - Girone A", "url": "https://football.nowgoal26.com/subleague/142"},
    {"name": "Serie C - Girone B", "url": "https://football.nowgoal26.com/subleague/2025-2026/142/1526"},
    {"name": "Serie C - Girone C", "url": "https://football.nowgoal26.com/subleague/2025-2026/142/1527"},
    # EUROPA TOP
    {"name": "Premier League", "url": "https://football.nowgoal26.com/league/36"},
    {"name": "La Liga", "url": "https://football.nowgoal26.com/league/31"},
    {"name": "Bundesliga", "url": "https://football.nowgoal26.com/league/8"},
    {"name": "Ligue 1", "url": "https://football.nowgoal26.com/league/11"},
    {"name": "Eredivisie", "url": "https://football.nowgoal26.com/league/16"},
    {"name": "Liga Portugal", "url": "https://football.nowgoal26.com/league/23"},
    # EUROPA SERIE B
    {"name": "Championship", "url": "https://football.nowgoal26.com/league/37"},
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
]

def strip_accents(text):
    for k, v in {'á':'a','à':'a','ã':'a','â':'a','é':'e','è':'e','ê':'e',
                  'í':'i','ì':'i','ó':'o','ò':'o','ô':'o','õ':'o',
                  'ú':'u','ù':'u','ü':'u','ñ':'n','ç':'c','ø':'o','å':'a','ä':'a'}.items():
        text = text.replace(k, v)
    return text

def clean_nowgoal_text(text):
    text = re.sub(r'\[\d+\]', '', text)
    text = re.sub(r'(\d)([a-z])', r'\1 \2', text)
    text = re.sub(r'([a-z])(\d)', r'\1 \2', text)
    return strip_accents(text)

def generate_search_names(name):
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

def normalize_name(name: str) -> str:
    """Normalizza il nome di una squadra (identica allo script delle quote)"""
    if not name:
        return ""
    name = name.lower().strip()
    
    # Rimuovi caratteri speciali comuni
    replacements = {
        "ü": "u", "ö": "o", "é": "e", "è": "e", "à": "a", "ì": "i",
        "ñ": "n", "ã": "a", "ç": "c", "á": "a", "í": "i",
        "ó": "o", "ú": "u", "ê": "e", "ô": "o", "â": "a",
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    
    # Rimuovi prefissi comuni
    prefixes = ["fc ", "cf ", "ac ", "as ", "sc ", "us ", "ss ", "asd ", "asc "]
    for prefix in prefixes:
        if name.startswith(prefix):
            name = name[len(prefix):]
    
    # Rimuovi suffissi comuni
    suffixes = [" fc", " cf", " ac", " calcio", " 1913", " 1928", " 1918", " united", " city"]
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    
    # Normalizzazioni specifiche
    specific_mappings = {
        "inter milan": "inter", "inter milano": "inter",
        "juve next gen": "juventus u23", "juventus ng": "juventus u23",
        "hellas verona": "verona", "giana erminio": "giana",
        "manchester utd": "manchester united", "man utd": "manchester united",
        "man city": "manchester city", "nott'm forest": "nottingham forest",
        "west ham utd": "west ham", "brighton": "brighton hove albion",
        "wolves": "wolverhampton", "atletico": "atletico madrid",
        "barcellona": "barcelona", "siviglia": "sevilla",
        "celta de vigo": "celta vigo", "celta": "celta vigo",
        "athletic club": "athletic bilbao", "bayern": "bayern munchen",
        "bayern monaco": "bayern munchen", "leverkusen": "bayer leverkusen",
        "dortmund": "borussia dortmund", "leipzig": "rb leipzig",
        "lipsia": "rb leipzig", "gladbach": "monchengladbach",
        "marsiglia": "marseille", "nizza": "nice", "lione": "lyon",
        "psg": "paris saint germain", "sporting cp": "sporting",
        "sporting lisbona": "sporting",
    }
    for old, new in specific_mappings.items():
        if old in name:
            name = name.replace(old, new)
    
    return name.strip()

def get_team_aliases(team_name: str, team_doc: Optional[Dict] = None) -> List[str]:
    """Genera tutti i possibili alias per una squadra"""
    aliases = set()
    aliases.add(team_name.lower().strip())
    normalized = normalize_name(team_name)
    if normalized:
        aliases.add(normalized)
    
    if team_doc and 'aliases' in team_doc:
        for alias in team_doc['aliases']:
            if alias and alias.strip():
                aliases.add(alias.lower().strip())
                normalized_alias = normalize_name(alias)
                if normalized_alias:
                    aliases.add(normalized_alias)
    
    words = team_name.lower().split()
    if len(words) > 1:
        for word in words:
            if len(word) >= 4:
                aliases.add(word)
    
    if normalized:
        words_norm = normalized.split()
        if len(words_norm) > 1:
            for word in words_norm:
                if len(word) >= 4:
                    aliases.add(word)
    
    aliases.discard("")
    return list(aliases)

def extract_datetime_from_row(row_text: str) -> Optional[Tuple[str, str]]:
    """
    Estrae data e orario da una riga di testo di Nowgoal.
    Formato tipico: "25 03-02 21:00 Team A vs Team B ..."
    Ritorna (data, orario) o None
    """
    try:
        # Pattern per data e ora: "DD-MM HH:MM"
        # Es: "03-02 21:00" oppure "14-12 12:30"
        match = re.search(r'(\d{2})-(\d{2})\s+(\d{2}):(\d{2})', row_text)
        if match:
            day, month, hour, minute = match.groups()
            # Anno corrente (o prossimo se il mese è passato)
            current_year = datetime.now().year
            current_month = datetime.now().month
            
            # Se il mese nella riga è minore del mese corrente, potrebbe essere anno prossimo
            month_int = int(month)
            year = current_year if month_int >= current_month else current_year + 1
            
            date_str = f"{year}-{month}-{day}"
            time_str = f"{hour}:{minute}"
            return (date_str, time_str)
    except:
        pass
    return None

def find_match_with_datetime(home_aliases: List[str], away_aliases: List[str], rows_text: List[str]) -> Optional[Tuple[str, str, str]]:
    """
    Cerca una partita nelle righe e ritorna (data, orario, row_text) se trovata.
    """
    home_search = set()
    for alias in home_aliases:
        for n in generate_search_names(alias.lower()):
            home_search.add(n)
        home_search.add(normalize_name(alias))
    home_search.discard("")

    away_search = set()
    for alias in away_aliases:
        for n in generate_search_names(alias.lower()):
            away_search.add(n)
        away_search.add(normalize_name(alias))
    away_search.discard("")

    for row_text in rows_text:
        row_clean = clean_nowgoal_text(row_text.lower())

        home_found = any(re.search(r'\b' + re.escape(n) + r'\b', row_clean) for n in home_search)
        away_found = any(re.search(r'\b' + re.escape(n) + r'\b', row_clean) for n in away_search)
        
        if home_found and away_found:
            datetime_result = extract_datetime_from_row(row_text)
            if datetime_result:
                date_str, time_str = datetime_result
                return (date_str, time_str, row_text)
            else:
                # Partita trovata ma senza data/ora parsabile
                return None
    
    return None

def click_round_and_wait(driver, round_num: int, timeout: int = 15) -> bool:
    """Clicca su una giornata e attende il caricamento"""
    try:
        str_round = str(round_num)
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
                if element:
                    break
            except:
                pass
        
        if not element:
            return False
        
        driver.execute_script("arguments[0].click();", element)
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "tr[id]"))
        )
        time.sleep(1)
        return True
    except Exception as e:
        print(f" ⚠️ Errore navigazione giornata {round_num}: {e}")
        return False

def get_current_round_from_page(driver) -> Optional[int]:
    """Determina quale giornata è visualizzata"""
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "tr[id]"))
        )
        first_row = driver.find_element(By.CSS_SELECTOR, "tr[id]")
        first_row_text = first_row.text.strip()
        match = re.match(r'^(\d+)', first_row_text)
        if match:
            return int(match.group(1))
    except Exception as e:
        print(f" ⚠️ Impossibile leggere giornata: {e}")
    return None

def get_all_match_rows(driver) -> List[str]:
    """Estrae tutte le righe di partite"""
    try:
        rows = driver.find_elements(By.CSS_SELECTOR, "tr[id]")
        return [row.text for row in rows if row.text.strip()]
    except:
        return []

def convert_to_utc(date_str: str, time_str: str) -> datetime:
    """
    Converte data e ora in oggetto datetime UTC per MongoDB.
    MongoDB salverà automaticamente come ISODate nel formato corretto.
    """
    try:
        # Parse date e time
        dt_naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        # Converti in UTC con tzinfo
        dt_utc = dt_naive.replace(tzinfo=timezone.utc)
        return dt_utc  # Ritorna oggetto datetime, non stringa!
    except Exception as e:
        print(f" ⚠️ Errore conversione datetime: {e}")
        # Fallback
        return datetime.now(timezone.utc)


def format_match_time(time_str: str) -> str:
    """
    Formatta l'orario come stringa HH:MM.
    Output: "20:45"
    """
    try:
        # Parse e ri-formatta per essere sicuri del formato
        time_obj = datetime.strptime(time_str, "%H:%M")
        return time_obj.strftime("%H:%M")
    except:
        # Se già nel formato corretto, ritorna così com'è
        return time_str


def run_scraper():
    """Funzione principale dello scraper"""
    print("\n🕐 AVVIO SCRAPER DATE E ORARI NOWGOAL")
    print("="*80)
    
    report_data = {
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'summary': {
            'total_matches': 0,
            'updated': 0,
            'not_updated': 0,
            'success_rate': 0
        },
        'leagues': []
    }
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    
    driver = None
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        for league in LEAGUES_CONFIG:
            league_name = league['name']
            league_url = league['url']
            
            print(f"\n📋 {league_name}")
            print("-"*40)
            
            league_stats = {
                'name': league_name,
                'processed': 0,
                'updated': 0
            }
            
            # Naviga alla pagina
            driver.get(league_url)
            time.sleep(3)
            
            # Determina giornata corrente
            current_round = get_current_round_from_page(driver)
            if not current_round:
                print(f" ⚠️ Impossibile determinare giornata corrente, skip")
                continue
            
            print(f" 📅 Giornata corrente: {current_round}")
            
            # Processa 3 giornate
            rounds_to_process = [current_round, current_round - 1, current_round + 1]
            
            for round_num in rounds_to_process:
                if round_num < 1:
                    continue
                
                print(f"\n ⚙️ Giornata {round_num}")
                
                # Naviga alla giornata
                if round_num != current_round:
                    if not click_round_and_wait(driver, round_num):
                        print(f" ⚠️ Navigazione fallita, skip")
                        continue
                    
                    actual_round = get_current_round_from_page(driver)
                    if actual_round and actual_round != round_num:
                        print(f" ⚠️ Sulla giornata {actual_round} invece di {round_num}")
                        continue
                else:
                    try:
                        WebDriverWait(driver, 15).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "tr[id]"))
                        )
                        time.sleep(1)
                    except:
                        print(f" ⚠️ Timeout caricamento")
                        continue
                
                # Recupera partite dal DB
                round_docs = list(db.h2h_by_round.find({
                    "league": league_name,
                    "round_name": {"$regex": f".*{round_num}.*"}
                }))
                
                if not round_docs:
                    print(f" ℹ️ Nessuna partita nel DB")
                    continue
                
                round_doc = round_docs[0]
                matches = round_doc.get('matches', [])
                print(f" 📊 {len(matches)} partite da processare")
                
                # Estrai righe dal sito
                all_rows = get_all_match_rows(driver)
                print(f" 🔍 Righe trovate: {len(all_rows)}")
                
                if not all_rows:
                    print(f" ⚠️ Nessuna riga sul sito")
                    continue
                
                # Processa ogni partita
                updated_count = 0
                
                for match in matches:
                    league_stats['processed'] += 1
                    report_data['summary']['total_matches'] += 1
                    
                    # Recupera alias squadre
                    home_team_doc = db.teams.find_one({"name": match['home']})
                    if not home_team_doc:
                        home_team_doc = db.teams.find_one({"aliases": match['home']})
                    
                    away_team_doc = db.teams.find_one({"name": match['away']})
                    if not away_team_doc:
                        away_team_doc = db.teams.find_one({"aliases": match['away']})
                    
                    home_aliases = get_team_aliases(match['home'], home_team_doc)
                    away_aliases = get_team_aliases(match['away'], away_team_doc)
                    
                    # Cerca partita con data e orario
                    result = find_match_with_datetime(home_aliases, away_aliases, all_rows)
                    
                    if result:
                        date_str, time_str, row_text = result
                        
                        # Converti in oggetto datetime UTC (MongoDB lo salverà come ISODate)
                        date_obj_utc = convert_to_utc(date_str, time_str)        # datetime object
                        match_time_formatted = format_match_time(time_str)        # "20:45"
                        
                        # Aggiorna nel match
                        match['date_obj'] = date_obj_utc          # MongoDB: ISODate("2026-02-04T20:45:00.000Z")
                        match['match_time'] = match_time_formatted # String: "20:45"
                        
                        updated_count += 1
                        league_stats['updated'] += 1
                        report_data['summary']['updated'] += 1
                        print("✓", end="", flush=True)


                    else:
                        print("✗", end="", flush=True)
                
                # Salva modifiche nel DB
                if updated_count > 0:
                    db.h2h_by_round.update_one(
                        {"_id": round_doc["_id"]},
                        {"$set": {"matches": matches}}
                    )
                
                print(f" ({updated_count}/{len(matches)})")
            
            report_data['leagues'].append(league_stats)
            print(f" 📈 Totale lega: {league_stats['updated']}/{league_stats['processed']}")
    
    except Exception as e:
        print(f"\n❌ Errore critico: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if driver:
            driver.quit()
    
    # Statistiche finali
    total = report_data['summary']['total_matches']
    updated = report_data['summary']['updated']
    report_data['summary']['not_updated'] = total - updated
    if total > 0:
        report_data['summary']['success_rate'] = (updated / total) * 100
    
    print("\n" + "="*80)
    print("📊 RIEPILOGO FINALE")
    print("="*80)
    print(f"🎯 Partite totali: {total}")
    print(f"✅ Date/Orari aggiornati: {updated}")
    print(f"❌ Non aggiornati: {total - updated}")
    print(f"📈 Successo: {report_data['summary']['success_rate']:.1f}%")
    print("\n✅ Scraper completato!")

if __name__ == "__main__":
    run_scraper()
