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
from datetime import datetime
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
    
    # Rimuovi trattini (Al-Hilal -> Al Hilal)
    name = name.replace("-", " ")

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
        al = team_doc['aliases']
        # Supporta sia dict (es. {soccerstats: "X", nowgoal: "Y"}) che list
        alias_values = al.values() if isinstance(al, dict) else al
        for alias in alias_values:
            if isinstance(alias, str) and alias.strip():
                aliases.add(alias.lower().strip())
                normalized_alias = normalize_name(alias)
                if normalized_alias:
                    aliases.add(normalized_alias)
    
    # Aggiungi singole parole del nome come alias, ma escludi parole troppo comuni
    COMMON_WORDS = {"town", "city", "united", "rovers", "athletic", "county", "wanderers",
                    "albion", "orient", "forest", "villa", "palace", "hotspur", "wednesday",
                    "stanley", "argyle", "dons", "vale", "rangers", "real", "club", "sport",
                    "sporting", "dynamo", "lokomotiv", "spartak", "torpedo"}
    words = team_name.lower().split()
    if len(words) > 1:
        for word in words:
            if len(word) >= 4 and word not in COMMON_WORDS:
                aliases.add(word)
    
    if normalized:
        words_norm = normalized.split()
        if len(words_norm) > 1:
            for word in words_norm:
                if len(word) >= 4 and word not in COMMON_WORDS:
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

            # Anno corretto: se la data con anno corrente è entro 14 giorni nel passato
            # oppure nel futuro → anno corrente. Altrimenti è un match dell'anno prossimo.
            # FIX: evita che partite di febbraio vengano assegnate al 2027 quando il pipeline
            # gira il 1° marzo (mese 2 < mese 3 → l'old logic usava current_year + 1, sbagliato).
            month_int = int(month)
            try:
                try_this_year = datetime(current_year, month_int, int(day))
                days_ago = (datetime.now() - try_this_year).days
                year = current_year if (try_this_year > datetime.now() or days_ago <= 14) else current_year + 1
            except ValueError:
                year = current_year
            
            date_str = f"{year}-{month}-{day}"
            time_str = f"{hour}:{minute}"
            return (date_str, time_str)
    except:
        pass
    return None

def find_match_with_datetime(home_aliases: List[str], away_aliases: List[str], rows: List[Tuple[str, Optional[str], Optional[str]]]) -> Optional[Tuple[str, str, str, Optional[str]]]:
    """
    Cerca una partita nelle righe e ritorna (data, orario, row_text, match_status) se trovata.
    rows e' una lista di (row_text, data_t, match_status) dove data_t e' es. '2026-03-04 01:00'.
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

    for row_text, data_t, match_status in rows:
        row_clean = clean_nowgoal_text(row_text.lower())

        home_found = any(re.search(r'\b' + re.escape(n) + r'\b', row_clean) for n in home_search)
        away_found = any(re.search(r'\b' + re.escape(n) + r'\b', row_clean) for n in away_search)

        if home_found and away_found:
            # PRIORITÀ: testo visibile = orario CET italiano (quello che l'utente vede)
            # data-t è in timezone server NowGoal (UTC+8 Pechino) → NON usarlo come prima scelta
            datetime_result = extract_datetime_from_row(row_text)
            if datetime_result:
                date_str, time_str = datetime_result
                if 'independiente' in row_clean or 'talleres' in row_clean:
                    print(f"\n      [DBG] row_text='{row_text[:80]}' → date={date_str} time={time_str} data_t={data_t}")
                return (date_str, time_str, row_text, match_status)
            # Fallback: data-t (NB: timezone server, potrebbe essere diverso da CET)
            if data_t:
                try:
                    dt = datetime.strptime(data_t[:16], "%Y-%m-%d %H:%M")
                    return (dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M"), row_text, match_status)
                except:
                    pass
            return None

    return None

def click_round_and_wait(driver, round_num: int, timeout: int = 15, has_stages: bool = False) -> bool:
    """Clicca su una giornata e attende il caricamento"""
    try:
        # Nuova struttura: <span round="N"> dentro div.round
        element = None
        try:
            if has_stages:
                # Liga MX: round duplicati (Clausura + Apertura), prendi l'ultimo (fase corrente)
                elements = driver.find_elements(By.CSS_SELECTOR, f"div.round span[round='{round_num}']")
                if elements:
                    element = elements[-1]
            else:
                element = driver.find_element(By.CSS_SELECTOR, f"div.round span[round='{round_num}']")
        except:
            pass
        # Fallback vecchia struttura
        if not element:
            for xpath in [
                f"//div[contains(@class,'subLeague_round')]//a[text()='{round_num}']",
                f"//a[normalize-space()='{round_num}']"
            ]:
                try:
                    element = driver.find_element(By.XPATH, xpath)
                    if element: break
                except:
                    pass

        if not element:
            return False

        driver.execute_script("arguments[0].click();", element)
        # Attendi che lo span cliccato diventi "current on"
        try:
            WebDriverWait(driver, timeout).until(
                lambda d: d.find_element(By.CSS_SELECTOR, f"div.round span[round='{round_num}'].on") or
                          d.find_element(By.CSS_SELECTOR, f"div.round span[round='{round_num}'].current")
            )
        except:
            pass
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.schedulis"))
        )
        time.sleep(2)
        return True
    except Exception as e:
        print(f" ⚠️ Errore navigazione giornata {round_num}: {e}")
        return False

def get_current_round_from_page(driver, has_stages: bool = False) -> Optional[int]:
    """Determina quale giornata è visualizzata"""
    try:
        # Nuova struttura: <span round="30" class="current on">
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.schedulis"))
        )
        try:
            if has_stages:
                # Liga MX: round duplicati, prendi l'ultimo span.current (fase corrente)
                elements = driver.find_elements(By.CSS_SELECTOR, "div.round span.current")
                if elements:
                    round_attr = elements[-1].get_attribute("round")
                    if round_attr:
                        return int(round_attr)
            else:
                current = driver.find_element(By.CSS_SELECTOR, "div.round span.current")
                round_attr = current.get_attribute("round")
                if round_attr:
                    return int(round_attr)
        except:
            pass
        # Fallback: cerca span con classe "on"
        try:
            if has_stages:
                elements = driver.find_elements(By.CSS_SELECTOR, "div.round span.on")
                if elements:
                    round_attr = elements[-1].get_attribute("round")
                    if round_attr:
                        return int(round_attr)
            else:
                current = driver.find_element(By.CSS_SELECTOR, "div.round span.on")
                round_attr = current.get_attribute("round")
                if round_attr:
                    return int(round_attr)
        except:
            pass
    except Exception as e:
        print(f" ⚠️ Impossibile leggere giornata: {e}")
    return None

def get_all_match_rows(driver) -> List[Tuple[str, Optional[str], Optional[str]]]:
    """Estrae tutte le righe di partite come (testo, data_t, match_status).
    data_t e' l'attributo data-t dello span[name='timeData'], es. '2026-03-04 01:00' (anno incluso).
    match_status e' il testo dello stato (es. 'Postp.', 'Susp.') se non e' un risultato normale.
    """
    try:
        divs = driver.find_elements(By.CSS_SELECTOR, "div.schedulis")
        result = []
        for div in divs:
            text = div.text.strip()
            if not text:
                continue
            data_t = None
            try:
                span = div.find_element(By.CSS_SELECTOR, "span[name='timeData']")
                data_t = span.get_attribute("data-t")
            except:
                pass
            # Leggi stato partita (Postp., Susp., Canc., ecc.)
            match_status = None
            try:
                score_span = div.find_element(By.CSS_SELECTOR, "span.score")
                score_text = score_span.text.strip()
                # Se non è un risultato (X - X) e non è una lineetta/vuoto → è uno stato speciale
                if score_text and score_text != '-' and not re.match(r'^\d+\s*-\s*\d+$', score_text):
                    match_status = score_text
            except:
                pass
            result.append((text, data_t, match_status))
        return result
    except:
        return []

def convert_to_utc(date_str: str, time_str: str) -> datetime:
    """
    Crea oggetto datetime da data e orario CET (ora italiana, da NowGoal).
    Salvato come naive datetime — la data corrisponde al giorno italiano.
    NB: il nome 'convert_to_utc' è legacy, in realtà NON converte a UTC.
    """
    try:
        return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except Exception as e:
        print(f" ⚠️ Errore conversione datetime: {e}")
        return datetime.now()


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


def _crea_driver():
    """Crea e configura un nuovo Chrome driver headless"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)")

    chrome_ver = None
    try:
        r = subprocess.run(['reg', 'query', r'HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon', '/v', 'version'],
                           capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            if line.strip().startswith('version'):
                chrome_ver = line.split()[-1]
    except:
        pass

    service = Service(ChromeDriverManager(driver_version=chrome_ver).install() if chrome_ver else ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def _driver_vivo(driver) -> bool:
    """Controlla se la sessione Chrome è ancora attiva"""
    try:
        _ = driver.title
        return True
    except Exception:
        return False


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

    driver = None
    league_count = 0

    try:
        driver = _crea_driver()
        global _active_driver
        _active_driver = driver

        for league in LEAGUES_CONFIG:
            league_name = league['name']
            league_url = league['url']
            league_count += 1

            print(f"\n📋 {league_name}")
            print("-"*40)

            league_stats = {
                'name': league_name,
                'processed': 0,
                'updated': 0
            }

            # Pulizia memoria ogni 5 campionati
            if league_count % 5 == 0:
                try:
                    driver.execute_cdp_cmd("Network.clearBrowserCache", {})
                    driver.execute_cdp_cmd("Network.clearBrowserCookies", {})
                    print("   🧹 Memoria Chrome svuotata.")
                except Exception:
                    pass

            # Naviga alla pagina con recovery se la sessione è morta
            try:
                if not _driver_vivo(driver):
                    raise Exception("sessione morta")
                driver.get(league_url)
            except Exception as nav_err:
                print(f"   ⚠️ Chrome crash ({nav_err.__class__.__name__}), ricreo il browser...")
                try:
                    driver.quit()
                except Exception:
                    pass
                try:
                    driver = _crea_driver()
                    _active_driver = driver
                    driver.get(league_url)
                    print("   ✅ Browser ricreato, continuo.")
                except Exception as e2:
                    print(f"   ❌ Impossibile ricreare Chrome: {e2}. Salto {league_name}.")
                    report_data['leagues'].append(league_stats)
                    continue

            time.sleep(3)

            has_stages = league.get('has_stages', False)

            # Determina giornata corrente
            current_round = get_current_round_from_page(driver, has_stages=has_stages)
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
                    if not click_round_and_wait(driver, round_num, has_stages=has_stages):
                        print(f" ⚠️ Navigazione fallita, skip")
                        continue
                else:
                    try:
                        WebDriverWait(driver, 15).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "div.schedulis"))
                        )
                        time.sleep(1)
                    except:
                        print(f" ⚠️ Timeout caricamento")
                        continue
                
                # Recupera partite dal DB
                round_docs = list(db.h2h_by_round.find({
                    "league": league_name,
                    "round_name": {"$regex": f"^{round_num}\\.Giornata$"}
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
                    
                    # Recupera alias squadre (supporta aliases come dict o array)
                    def _find_team(name):
                        doc = db.teams.find_one({"name": name})
                        if not doc:
                            doc = db.teams.find_one({"aliases.soccerstats": name})
                        if not doc:
                            doc = db.teams.find_one({"aliases.nowgoal": name})
                        if not doc:
                            doc = db.teams.find_one({"aliases": name})
                        return doc
                    home_team_doc = _find_team(match['home'])
                    away_team_doc = _find_team(match['away'])
                    
                    home_aliases = get_team_aliases(match['home'], home_team_doc)
                    away_aliases = get_team_aliases(match['away'], away_team_doc)
                    
                    # Cerca partita con data e orario
                    result = find_match_with_datetime(home_aliases, away_aliases, all_rows)
                    
                    if result:
                        date_str, time_str, _, m_status = result

                        # Converti in oggetto datetime UTC (MongoDB lo salverà come ISODate)
                        date_obj_utc = convert_to_utc(date_str, time_str)        # datetime object
                        match_time_formatted = format_match_time(time_str)        # "20:45"

                        # Aggiorna nel match
                        match['date_obj'] = date_obj_utc          # MongoDB: ISODate("2026-02-04T20:45:00.000Z")
                        match['match_time'] = match_time_formatted # String: "20:45"

                        # Stato speciale (Postp., Susp., Canc., ecc.)
                        if m_status:
                            match['match_status_detail'] = m_status
                            print(f"⚠{m_status}", end="", flush=True)
                        else:
                            # Rimuovi stato speciale se la partita torna normale
                            match.pop('match_status_detail', None)
                            print("✓", end="", flush=True)

                        updated_count += 1
                        league_stats['updated'] += 1
                        report_data['summary']['updated'] += 1


                    else:
                        league_stats['processed'] += 0  # no-op, match non trovato
                
                # Salva modifiche nel DB
                if updated_count > 0:
                    db.h2h_by_round.update_one(
                        {"_id": round_doc["_id"]},
                        {"$set": {"matches": matches}}
                    )

                    # Propaga date, match_time, match_status_detail in unified e prediction_versions
                    for match in matches:
                        date_obj = match.get('date_obj')
                        match_time = match.get('match_time', '')
                        if date_obj:
                            new_date = date_obj.strftime('%Y-%m-%d') if hasattr(date_obj, 'strftime') else str(date_obj)[:10]
                            # Aggiorna date e match_time in unified e prediction_versions
                            for coll_name in ['daily_predictions_unified', 'prediction_versions']:
                                coll = db[coll_name]
                                # Aggiorna tutti i documenti di questa partita (qualsiasi data vecchia)
                                coll.update_many(
                                    {"home": match['home'], "away": match['away'], "league": league_name},
                                    {"$set": {"date": new_date, "match_time": match_time}}
                                )

                        m_status_detail = match.get('match_status_detail')
                        if m_status_detail:
                            db.daily_predictions_unified.update_many(
                                {"home": match['home'], "away": match['away'], "league": league_name},
                                {"$set": {"match_status_detail": m_status_detail}}
                            )
                        else:
                            # Rimuovi se la partita torna normale
                            db.daily_predictions_unified.update_many(
                                {"home": match['home'], "away": match['away'], "league": league_name, "match_status_detail": {"$exists": True}},
                                {"$unset": {"match_status_detail": ""}}
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
