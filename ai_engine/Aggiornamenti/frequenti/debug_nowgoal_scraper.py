import os
import sys
import time
import re
import ctypes  # // aggiunto per: nascondere la finestra
ctypes.windll.kernel32.SetConsoleTitleW("Aggiornamento Quote Calcio (debug_nowgoal_scraper.py)")
import msvcrt  # // aggiunto per: tasto H e battito cardiaco
import json
from datetime import datetime, timedelta, timezone
import atexit
import signal
import subprocess

# --- LOGGING: output su terminale + file log ---
class _TeeOutput:
    def __init__(self, log_path):
        self.terminal = sys.stdout
        self.log = open(log_path, 'w', encoding='utf-8')
    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
    def flush(self):
        self.terminal.flush()
        self.log.flush()

_log_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_log_root, 'log')):
    _p = os.path.dirname(_log_root)
    if _p == _log_root:
        break
    _log_root = _p
sys.stdout = _TeeOutput(os.path.join(_log_root, 'log', 'quote-live-1x2-nowgoal.txt'))
sys.stderr = sys.stdout
print(f"{'='*50}")
print(f"AVVIO DAEMON QUOTE 1X2 (NowGoal): {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
print(f"{'='*50}\n")

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

# --- ANTI-ZOMBIE: cleanup Chrome orfani all'avvio e all'uscita ---
_current_driver = None

def _cleanup_chrome():
    """Chiude il Chrome driver corrente all'uscita del processo."""
    global _current_driver
    if _current_driver is not None:
        try:
            _current_driver.quit()
            print(f"   [CLEANUP] Chrome chiuso via atexit handler")
        except:
            pass
        _current_driver = None

def _kill_orphan_chrome():
    """All'avvio, killa Chrome zombie (scoped_dir con parent morto)."""
    try:
        r = subprocess.run(
            ['powershell', '-Command',
             '$k=0; Get-CimInstance Win32_Process | Where-Object { $_.Name -eq "chrome.exe" -and $_.CommandLine -match "scoped_dir" } | ForEach-Object { $p=Get-Process -Id $_.ParentProcessId -EA SilentlyContinue; if(-not $p){Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue; $k++} }; if($k -gt 0){Write-Host "Killati $k Chrome zombie"}'],
            capture_output=True, text=True, timeout=30
        )
        if r.stdout.strip():
            print(f"   [CLEANUP] {r.stdout.strip()}")
    except:
        pass

atexit.register(_cleanup_chrome)
try:
    signal.signal(signal.SIGTERM, lambda s, f: (_cleanup_chrome(), sys.exit(0)))
except:
    pass

_kill_orphan_chrome()

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
    
    # 🆕 EUROPA SERIE B
    {"name": "Championship", "url": "https://football.nowgoal26.com/league/37"},
    {"name": "LaLiga 2", "url": "https://football.nowgoal26.com/subleague/33"},
    {"name": "2. Bundesliga", "url": "https://football.nowgoal26.com/league/9"},
    {"name": "Ligue 2", "url": "https://football.nowgoal26.com/league/12"},
    
    # 🆕 EUROPA NORDICI + EXTRA
    {"name": "Scottish Premiership", "url": "https://football.nowgoal26.com/subleague/29"},
    {"name": "Allsvenskan", "url": "https://football.nowgoal26.com/subleague/26"},
    {"name": "Eliteserien", "url": "https://football.nowgoal26.com/subleague/22"},
    {"name": "Superligaen", "url": "https://football.nowgoal26.com/subleague/7"},
    {"name": "Jupiler Pro League", "url": "https://football.nowgoal26.com/subleague/5"},
    {"name": "Süper Lig", "url": "https://football.nowgoal26.com/subleague/30"},
    {"name": "League of Ireland Premier Division", "url": "https://football.nowgoal26.com/subleague/1"},
    
    # 🆕 AMERICHE
    {"name": "Brasileirão Serie A", "url": "https://football.nowgoal26.com/league/4"},
    {"name": "Primera División", "url": "https://football.nowgoal26.com/subleague/2"},
    {"name": "Major League Soccer", "url": "https://football.nowgoal26.com/subleague/21"},
    
    # 🆕 ASIA
    {"name": "J1 League", "url": "https://football.nowgoal26.com/subleague/25"},

    # NUOVI CAMPIONATI (24/03/2026)
    {"name": "League One", "url": "https://football.nowgoal26.com/league/39"},
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
        if k in name:
            name = name.replace(k, v)

    return name.strip()

def get_team_aliases(team_name: str, team_doc: Optional[Dict] = None) -> List[str]:
    """
    Genera tutti i possibili alias per una squadra.
    Include: nome originale, nome normalizzato, alias dal DB, nomi parziali
    """
    aliases = set()
    
    # Nome originale (lowercase)
    aliases.add(team_name.lower().strip())
    
    # Nome normalizzato
    normalized = normalize_name(team_name)
    if normalized:
        aliases.add(normalized)
    
    # Alias dal database
    if team_doc and 'aliases' in team_doc:
        for alias in team_doc['aliases']:
            if alias and alias.strip():
                aliases.add(alias.lower().strip())
                # Aggiungi anche la versione normalizzata dell'alias
                normalized_alias = normalize_name(alias)
                if normalized_alias:
                    aliases.add(normalized_alias)
    
    # Aggiungi anche parti del nome (per nomi composti)
    # Es: "Estoril Praia" -> aggiungi anche "estoril" e "praia"
    # Min 5 chars per evitare alias ambigui ("city", "real", "club", ecc.)
    words = team_name.lower().split()
    if len(words) > 1:
        for word in words:
            if len(word) >= 5:
                aliases.add(word)

    # Stesso per il nome normalizzato
    if normalized:
        words_norm = normalized.split()
        if len(words_norm) > 1:
            for word in words_norm:
                if len(word) >= 5:
                    aliases.add(word)
    
    # Rimuovi stringhe vuote
    aliases.discard("")
    
    return list(aliases)

def extract_odds_from_row(row_text: str) -> Optional[Dict[str, float]]:
    """Estrae le quote 1X2 da una riga di testo"""
    try:
        # Cerca tutti i numeri in formato quota (es. 2.50, 3.25)
        floats = [float(x) for x in re.findall(r'\d+\.\d{2}', row_text)]
        
        # Filtra solo quote valide (tra 1.01 e 25.0)
        valid_odds = [f for f in floats if 1.01 <= f <= 25.0]
        
        # Servono almeno 3 quote (1, X, 2)
        if len(valid_odds) >= 3:
            return {
                "1": valid_odds[0],
                "X": valid_odds[1], 
                "2": valid_odds[2]
            }
    except:
        pass
    
    return None

def find_match_in_rows(home_aliases: List[str], away_aliases: List[str], rows_data: List) -> Optional[Tuple[Dict, str, bool]]:
    """
    Cerca una partita nelle righe del sito usando gli alias.
    Usa POSITION MATCHING (home aliases solo vs home_text, away vs away_text)
    e SCORING (alias più lungo/specifico vince).

    Ritorna (quote_dict, row_text, has_odds) se trovata, None altrimenti.
    """
    # Normalizza TUTTI gli alias (rimuovi accenti, lowercase, ecc.)
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

    best_match = None
    best_score = 0

    for row in rows_data:
        # Supporta sia dict (nuovo) che str (backward compat)
        if isinstance(row, dict):
            home_text = clean_nowgoal_text(row["home_text"])
            away_text = clean_nowgoal_text(row["away_text"])
            full_text = row["full_text"]
        else:
            # Fallback: cerca nel testo completo (vecchio comportamento)
            full = clean_nowgoal_text(row.lower())
            home_text = full
            away_text = full
            full_text = row

        # Position matching: home aliases SOLO contro home_text
        home_matches = [n for n in home_search if re.search(r'\b' + re.escape(n) + r'\b', home_text)]
        # Position matching: away aliases SOLO contro away_text
        away_matches = [n for n in away_search if re.search(r'\b' + re.escape(n) + r'\b', away_text)]

        if home_matches and away_matches:
            # Scoring: somma lunghezza alias più lungo per home + away
            score = max(len(m) for m in home_matches) + max(len(m) for m in away_matches)

            if score > best_score:
                odds = extract_odds_from_row(full_text)
                best_match = (odds, full_text, odds is not None)
                best_score = score

    return best_match

def click_round_and_wait(driver, round_num: int, stage=None) -> bool:
    try:
        element = None
        # Se c'è uno stage (Serie C), clicca la giornata dello stage corretto
        if stage:
            try:
                element = driver.find_element(By.CSS_SELECTOR, f"div.round span[round='{round_num}'][stage='{stage}']")
            except:
                pass
        # Altrimenti cerca la giornata visibile
        if not element:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, f"div.round span[round='{round_num}']")
                for el in elements:
                    if el.is_displayed():
                        element = el
                        break
            except:
                pass
        if not element:
            return False
        # Salva contenuto attuale per verificare il cambio
        try:
            old_html = driver.find_element(By.CSS_SELECTOR, "div.list").get_attribute("innerHTML")[:200]
        except:
            old_html = ""
        # Click nativo Selenium
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

def get_round_number_from_text(text):
    match = re.search(r'(\d+)', str(text))
    return int(match.group(1)) if match else 0

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

def get_all_match_rows(driver) -> List[Dict]:
    """Estrae tutte le righe di partite dalla pagina corrente.
    Ritorna lista di dict: {full_text, home_text, away_text}
    Home/away estratti dai link <a href='/team/summary/'>."""
    try:
        rows = driver.find_elements(By.CSS_SELECTOR, "tr[id]")
        result = []
        for row in rows:
            full_text = row.text.strip()
            if not full_text:
                continue

            # Estrai home/away dai link squadra
            home_text = ""
            away_text = ""
            try:
                team_links = row.find_elements(By.CSS_SELECTOR, "a[href*='/team/summary/']")
                if len(team_links) >= 2:
                    home_text = team_links[0].text.strip().lower()
                    away_text = team_links[1].text.strip().lower()
                elif len(team_links) == 1:
                    home_text = team_links[0].text.strip().lower()
            except:
                pass

            result.append({
                "full_text": full_text,
                "home_text": home_text,
                "away_text": away_text
            })
        return result
    except:
        return []

def analyze_missing_match(
    home: str,
    away: str,
    home_aliases: List[str],
    away_aliases: List[str],
    all_rows: List[Dict],
    round_num: int,
    league_name: str
) -> Dict:
    """Analizza perché una partita non è stata trovata"""

    analysis = {
        "partita": f"{home} vs {away}",
        "lega": league_name,
        "giornata": round_num,
        "timestamp": datetime.now().isoformat(),
        "motivi": [],
        "dettagli": {}
    }

    if not all_rows:
        analysis["motivi"].append("NESSUNA_RIGA_TROVATA_PER_GIORNATA")
        return analysis

    # Cerca le squadre singolarmente (usa position matching)
    home_found_in = []
    away_found_in = []

    home_search_diag = set()
    for a in home_aliases:
        for n in generate_search_names(a.lower()): home_search_diag.add(n)
    home_search_diag.discard("")
    away_search_diag = set()
    for a in away_aliases:
        for n in generate_search_names(a.lower()): away_search_diag.add(n)
    away_search_diag.discard("")

    for idx, row in enumerate(all_rows):
        row_ft = row["full_text"] if isinstance(row, dict) else row
        row_clean = clean_nowgoal_text(row_ft.lower())

        if any(re.search(r'\b' + re.escape(n) + r'\b', row_clean) for n in home_search_diag):
            home_found_in.append(idx)

        if any(re.search(r'\b' + re.escape(n) + r'\b', row_clean) for n in away_search_diag):
            away_found_in.append(idx)

    def _row_text(idx):
        r = all_rows[idx]
        return (r["full_text"] if isinstance(r, dict) else r)[:200]

    # Analizza i risultati
    if not home_found_in and not away_found_in:
        analysis["motivi"].append("NESSUNA_SQUADRA_TROVATA")
        analysis["dettagli"]["nota"] = "Nessuna delle due squadre trovata sul sito"

    elif home_found_in and not away_found_in:
        analysis["motivi"].append("SOLO_CASA_TROVATA")
        analysis["dettagli"]["righe_casa"] = home_found_in[:3]

        if home_found_in:
            analysis["dettagli"]["riga_esempio"] = _row_text(home_found_in[0])
            analysis["dettagli"]["suggerimento"] = f"Cerca '{away}' in questa riga per vedere come si chiama sul sito"

    elif away_found_in and not home_found_in:
        analysis["motivi"].append("SOLO_TRASFERTA_TROVATA")
        analysis["dettagli"]["righe_trasferta"] = away_found_in[:3]

        if away_found_in:
            analysis["dettagli"]["riga_esempio"] = _row_text(away_found_in[0])
            analysis["dettagli"]["suggerimento"] = f"Cerca '{home}' in questa riga per vedere come si chiama sul sito"

    elif home_found_in and away_found_in:
        # Entrambe trovate ma non nella stessa riga
        same_row = set(home_found_in) & set(away_found_in)
        if same_row:
            analysis["motivi"].append("PARTITA_TROVATA_MA_SENZA_QUOTE")
            example_idx = list(same_row)[0]
            analysis["dettagli"]["esempio_riga"] = _row_text(example_idx)
        else:
            analysis["motivi"].append("SQUADRE_IN_RIGHE_DIVERSE")

    analysis["dettagli"]["alias_casa"] = home_aliases
    analysis["dettagli"]["alias_trasferta"] = away_aliases
    
    return analysis

def save_report(report_data: Dict, output_dir: str = "scraper_reports"):
    """Salva il report in formato JSON e TXT"""
    
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_file = os.path.join(output_dir, f"report_{timestamp}.json")
    txt_file = os.path.join(output_dir, f"report_{timestamp}.txt")
    
    # File JSON
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    
    # File TXT
    with open(txt_file, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("REPORT SCRAPER QUOTE CALCIO\n")
        f.write("="*80 + "\n\n")
        
        f.write(f"Data: {report_data['timestamp']}\n")
        f.write(f"Partite totali: {report_data['summary']['total_matches']}\n")
        f.write(f"Partite aggiornate: {report_data['summary']['updated']}\n")
        f.write(f"Successo: {report_data['summary']['success_rate']:.1f}%\n\n")
        
        if report_data['issues']:
            # Separa partite senza quote da partite non trovate
            senza_quote = [i for i in report_data['issues'] if 'PARTITA_TROVATA_SENZA_QUOTE' in i.get('motivi', [])]
            non_trovate = [i for i in report_data['issues'] if 'PARTITA_TROVATA_SENZA_QUOTE' not in i.get('motivi', [])]
            
            # ANALISI SQUADRE PROBLEMATICHE (solo per partite non trovate)
            if non_trovate:
                f.write("="*80 + "\n")
                f.write("🚨 SQUADRE CON PROBLEMI DI MATCHING\n")
                f.write("="*80 + "\n\n")
                
                # Conta occorrenze di ogni squadra
                team_problems = {}
                for issue in non_trovate:
                    partita = issue['partita']
                    # Estrai home e away da "Home vs Away"
                    teams = partita.split(' vs ')
                    if len(teams) == 2:
                        home, away = teams[0].strip(), teams[1].strip()
                        team_problems[home] = team_problems.get(home, 0) + 1
                        team_problems[away] = team_problems.get(away, 0) + 1
                
                # Ordina per numero di occorrenze
                sorted_teams = sorted(team_problems.items(), key=lambda x: x[1], reverse=True)
                
                f.write(f"Totale squadre uniche con problemi: {len(sorted_teams)}\n\n")
                
                for team, count in sorted_teams:
                    f.write(f"❌ {team} ({count} partite mancanti)\n")
                    
                    # Mostra gli alias usati per questa squadra
                    for issue in non_trovate:
                        if team in issue['partita']:
                            dettagli = issue.get('dettagli', {})
                            # Determina se è casa o trasferta
                            if issue['partita'].startswith(team):
                                aliases = dettagli.get('alias_casa', [])
                            else:
                                aliases = dettagli.get('alias_trasferta', [])
                            
                            if aliases:
                                f.write(f"   Alias usati: {', '.join(aliases[:5])}\n")
                                break
                    
                    f.write("\n")
                
                f.write("\n💡 SUGGERIMENTI:\n")
                f.write("1. Vai sul sito NowGoal e cerca queste squadre\n")
                f.write("2. Annota il nome ESATTO usato sul sito\n")
                f.write("3. Aggiungi il nome del sito come alias nel database\n")
                f.write("4. Se il nome è molto diverso, aggiorna normalize_name()\n\n")
            
            # DETTAGLIO PARTITE NON TROVATE
            if non_trovate:
                f.write("="*80 + "\n")
                f.write("DETTAGLIO PARTITE NON TROVATE\n")
                f.write("="*80 + "\n\n")
                
                # Raggruppa per motivo
                issues_by_reason = {}
                for issue in non_trovate:
                    for motivo in issue.get('motivi', []):
                        if motivo not in issues_by_reason:
                            issues_by_reason[motivo] = []
                        issues_by_reason[motivo].append(issue)
                
                for motivo, issues in issues_by_reason.items():
                    f.write(f"\n{motivo} ({len(issues)} partite)\n")
                    f.write("-"*80 + "\n")
                    
                    for issue in issues[:10]:  # Max 10 esempi per motivo
                        f.write(f"  • {issue['partita']}\n")
                        f.write(f"    Lega: {issue['lega']} - Giornata: {issue['giornata']}\n")
                        
                        dettagli = issue.get('dettagli', {})
                        if 'nota' in dettagli:
                            f.write(f"    Nota: {dettagli['nota']}\n")
                        
                        # 🔍 MOSTRA LA RIGA ESEMPIO CON SUGGERIMENTO
                        if 'riga_esempio' in dettagli:
                            f.write(f"\n    📄 RIGA SUL SITO:\n")
                            f.write(f"    {dettagli['riga_esempio']}\n")
                            if 'suggerimento' in dettagli:
                                f.write(f"    💡 {dettagli['suggerimento']}\n")
                        
                        if 'righe_casa' in dettagli:
                            f.write(f"    ⚠️ Casa trovata in altre righe\n")
                        if 'righe_trasferta' in dettagli:
                            f.write(f"    ⚠️ Trasferta trovata in altre righe\n")
                        
                        f.write("\n")
                    
                    if len(issues) > 10:
                        f.write(f"  ... e altre {len(issues)-10} partite\n")
            
            # PARTITE SENZA QUOTE (sezione separata, meno importante)
            if senza_quote:
                f.write("\n\n" + "="*80 + "\n")
                f.write("ℹ️ PARTITE TROVATE MA SENZA QUOTE (NORMALE)\n")
                f.write("="*80 + "\n\n")
                f.write(f"Totale: {len(senza_quote)} partite\n")
                f.write("Queste partite sono sul sito ma le quote non sono ancora pubblicate.\n")
                f.write("Riprova più tardi, specialmente vicino alla data della partita.\n\n")
                
                # Raggruppa per lega
                by_league = {}
                for issue in senza_quote:
                    lega = issue['lega']
                    if lega not in by_league:
                        by_league[lega] = []
                    by_league[lega].append(issue)
                
                for lega, issues in by_league.items():
                    f.write(f"\n{lega}: {len(issues)} partite\n")
    
    return json_file, txt_file

def run_scraper():
    """Funzione principale dello scraper"""
    
    print("\n🚀 AVVIO SCRAPER QUOTE CALCIO")
    print("="*80)
    
    report_data = {
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'summary': {
            'total_matches': 0,
            'updated': 0,
            'not_updated': 0,
            'success_rate': 0
        },
        'leagues': [],
        'issues': []
    }
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    
    driver = None
    global _current_driver

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        _current_driver = driver
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
            
            # Naviga alla pagina della lega
            driver.get(league_url)
            time.sleep(3)

            # Determina giornata corrente e recupera i 3 round dal DB (identico alla produzione)
            has_stages = league.get("has_stages", False)
            rounds_to_process = get_target_rounds_from_page(driver, league_name, has_stages=has_stages)
            if not rounds_to_process:
                print(f"   ⚠️ Impossibile determinare giornata corrente, skip")
                continue

            # La prima giornata restituita è quella corrente (anchor)
            current_round_num = get_round_number_from_text(rounds_to_process[0].get('round_name', '0'))
            print(f"   📅 Giornata corrente sul sito: {current_round_num}")

            for round_doc in rounds_to_process:
                round_num = get_round_number_from_text(round_doc.get('round_name', '0'))

                print(f"\n   ⚙️ Giornata {round_num}")

                # Naviga alla giornata E ATTENDI sempre
                stage = league.get("stage")
                if round_num != current_round_num:
                    # Giornata diversa: fai click
                    if not click_round_and_wait(driver, round_num, stage=stage):
                        print(f"      ⚠️ Navigazione fallita, skip")
                        continue
                else:
                    # Giornata corrente: assicurati che sia caricata
                    print(f"      ℹ️ Già sulla giornata corrente, attendo caricamento...")
                    try:
                        WebDriverWait(driver, 15).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "tr[id]"))
                        )
                        time.sleep(1)
                    except Exception as e:
                        print(f"      ⚠️ Timeout caricamento tabella, skip")
                        continue

                matches = round_doc.get('matches', [])
                
                print(f"      📊 {len(matches)} partite da processare")
                
                # Estrai tutte le righe dal sito
                all_rows = get_all_match_rows(driver)
                
                print(f"      🔍 Righe trovate sul sito: {len(all_rows)}")
                
                if not all_rows:
                    print(f"      ⚠️ Nessuna riga trovata sul sito")
                    continue
                
                # DEBUG: mostra prima riga come esempio
                if all_rows:
                    print(f"      📄 Esempio prima riga: {all_rows[0]['full_text'][:80]}...")
                
                # Processa ogni partita
                updated_count = 0
                found_without_odds_count = 0
                
                for match in matches:
                    league_stats['processed'] += 1
                    report_data['summary']['total_matches'] += 1
                    
                    # Recupera alias per le squadre con ricerca multipla
                    # 1. Cerca per nome esatto
                    home_team_doc = db.teams.find_one({"name": match['home']})
                    if not home_team_doc:
                        # 2. Cerca negli alias
                        home_team_doc = db.teams.find_one({"aliases": match['home']})
                    if not home_team_doc:
                        # 3. Cerca case-insensitive
                        home_team_doc = db.teams.find_one({
                            "name": {"$regex": f"^{re.escape(match['home'])}$", "$options": "i"}
                        })
                    
                    away_team_doc = db.teams.find_one({"name": match['away']})
                    if not away_team_doc:
                        away_team_doc = db.teams.find_one({"aliases": match['away']})
                    if not away_team_doc:
                        away_team_doc = db.teams.find_one({
                            "name": {"$regex": f"^{re.escape(match['away'])}$", "$options": "i"}
                        })
                    
                    home_aliases = get_team_aliases(match['home'], home_team_doc)
                    away_aliases = get_team_aliases(match['away'], away_team_doc)
                    
                    # Cerca la partita nelle righe del sito
                    result = find_match_in_rows(home_aliases, away_aliases, all_rows)
                    
                    if result:
                        odds_dict, row_text, has_odds = result
                        
                        if has_odds:
                            # CASO 1: Partita trovata CON quote ✓
                            if 'odds' not in match:
                                match['odds'] = {}
                            match['odds']['1'] = odds_dict['1']
                            match['odds']['X'] = odds_dict['X']
                            match['odds']['2'] = odds_dict['2']
                            match['odds']['src'] = "NowGoal"
                            match['odds']['ts'] = datetime.now()
                            
                            updated_count += 1
                            league_stats['updated'] += 1
                            report_data['summary']['updated'] += 1
                            
                            print("✓", end="", flush=True)
                        else:
                            # CASO 2: Partita trovata SENZA quote ⏳
                            found_without_odds_count += 1
                            
                            analysis = {
                                "partita": f"{match['home']} vs {match['away']}",
                                "lega": league_name,
                                "giornata": round_num,
                                "timestamp": datetime.now().isoformat(),
                                "motivi": ["PARTITA_TROVATA_SENZA_QUOTE"],
                                "dettagli": {
                                    "nota": "La partita è presente sul sito ma le quote non sono ancora disponibili",
                                    "riga_trovata": row_text[:150]
                                }
                            }
                            report_data['issues'].append(analysis)
                            
                            print("⏳", end="", flush=True)
                    else:
                        # CASO 3: Partita NON trovata ✗
                        analysis = analyze_missing_match(
                            match['home'], match['away'],
                            home_aliases, away_aliases,
                            all_rows, round_num, league_name
                        )
                        report_data['issues'].append(analysis)
                        
                        print("✗", end="", flush=True)
                
                # Salva le modifiche nel DB
                if updated_count > 0:
                    db.h2h_by_round.update_one(
                        {"_id": round_doc["_id"]},
                        {"$set": {"matches": matches}}
                    )
                
                print(f" ({updated_count}/{len(matches)})")
                
                # Statistiche dettagliate
                if found_without_odds_count > 0:
                    print(f"      ⏳ {found_without_odds_count} partite trovate ma senza quote (normali per partite future)")
                
                # Se TUTTE le partite falliscono (né quote né trovate), dump completo per debug
                if updated_count == 0 and found_without_odds_count == 0 and len(matches) > 0:
                    print(f"\n      ⚠️ ATTENZIONE: 0 partite trovate su {len(matches)}!")
                    print(f"      📄 DUMP RIGHE SITO (prime 3):")
                    for i, row in enumerate(all_rows[:3]):
                        print(f"         [{i+1}] {row['full_text'][:120]}")
                    print(f"      🏠 PARTITE DB (prime 3):")
                    for i, m in enumerate(matches[:3]):
                        print(f"         [{i+1}] {m['home']} vs {m['away']}")
            
            report_data['leagues'].append(league_stats)
            print(f"   📈 Totale lega: {league_stats['updated']}/{league_stats['processed']}")
        
    except Exception as e:
        print(f"\n❌ Errore critico: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        if driver:
            driver.quit()
        _current_driver = None

        # Calcola statistiche finali
        total = report_data['summary']['total_matches']
        updated = report_data['summary']['updated']
        report_data['summary']['not_updated'] = total - updated
        
        if total > 0:
            report_data['summary']['success_rate'] = (updated / total) * 100
        
        # Salva report
        json_file, txt_file = save_report(report_data)
        
        # Stampa riepilogo
        print("\n" + "="*80)
        print("📊 RIEPILOGO FINALE")
        print("="*80)
        print(f"🎯 Partite totali: {total}")
        print(f"✅ Partite aggiornate: {updated}")
        print(f"❌ Partite non aggiornate: {total - updated}")
        print(f"📈 Successo: {report_data['summary']['success_rate']:.1f}%")
        
        # Analizza i motivi delle partite non aggiornate
        if report_data['issues']:
            motivi_count = {}
            for issue in report_data['issues']:
                for motivo in issue.get('motivi', []):
                    motivi_count[motivo] = motivi_count.get(motivo, 0) + 1
            
            print(f"\n📋 DETTAGLIO PARTITE NON AGGIORNATE:")
            
            # Partite senza quote (normali)
            senza_quote = motivi_count.get('PARTITA_TROVATA_SENZA_QUOTE', 0)
            if senza_quote > 0:
                print(f"   ⏳ {senza_quote} partite trovate ma senza quote disponibili")
                print(f"      → Normale per partite future, riprova più tardi")
            
            # Partite non trovate (problemi)
            problemi = total - updated - senza_quote
            if problemi > 0:
                print(f"   ⚠️ {problemi} partite NON TROVATE sul sito (problemi di matching)")
                print(f"      → Controlla il report per dettagli sui nomi delle squadre")
                
                # Identifica squadre uniche con problemi
                non_trovate = [i for i in report_data['issues'] if 'PARTITA_TROVATA_SENZA_QUOTE' not in i.get('motivi', [])]
                team_problems = {}
                
                for issue in non_trovate:
                    partita = issue['partita']
                    teams = partita.split(' vs ')
                    if len(teams) == 2:
                        home, away = teams[0].strip(), teams[1].strip()
                        team_problems[home] = team_problems.get(home, 0) + 1
                        team_problems[away] = team_problems.get(away, 0) + 1
                
                print(f"\n   🎯 SQUADRE PROBLEMATICHE ({len(team_problems)} uniche):")
                sorted_teams = sorted(team_problems.items(), key=lambda x: x[1], reverse=True)
                
                for i, (team, count) in enumerate(sorted_teams[:10], 1):  # Top 10
                    print(f"      {i}. {team} ({count} partite)")
                
                if len(sorted_teams) > 10:
                    print(f"      ... e altre {len(sorted_teams)-10} squadre")
                
                print(f"\n   💡 PROSSIMI PASSI:")
                print(f"      1. Apri il report TXT per vedere gli alias usati")
                print(f"      2. Controlla i nomi sul sito NowGoal")
                print(f"      3. Aggiungi gli alias mancanti al database")
        
        print(f"\n📄 Report salvato in:")
        print(f"   • {json_file}")
        print(f"   • {txt_file}")
        
# --- CONFIGURAZIONE ORARI FISSI ---
ORARI_RUN = [0, 2, 10, 12, 14, 16, 18, 20, 22]

# --- PAUSA PIPELINE NOTTURNA (con lock file) ---
PIPELINE_PAUSE_START_H = 3   # Ora inizio pausa
PIPELINE_PAUSE_START_M = 55  # Minuto inizio pausa (03:55)
PIPELINE_CHECK_LOCK_H = 5    # Dalle 05:30 inizia a controllare il lock
PIPELINE_CHECK_LOCK_M = 30
PIPELINE_FALLBACK_H = 10     # Alle 10:00 riprende comunque (fallback crash)
LOCK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'log', 'pipeline_running.lock')

def is_pipeline_window():
    """Pausa durante la pipeline notturna. Inizia alle 03:55, finisce quando il lock file sparisce (dopo le 05:30)."""
    now = datetime.now()
    h, m = now.hour, now.minute

    # Prima delle 03:55 → nessuna pausa
    if h < PIPELINE_PAUSE_START_H or (h == PIPELINE_PAUSE_START_H and m < PIPELINE_PAUSE_START_M):
        return False

    # Dopo le 10:00 → fallback, riprendi comunque
    if h >= PIPELINE_FALLBACK_H:
        return False

    # Tra 03:55 e 05:30 → pausa fissa (inutile controllare, pipeline non è ancora finita)
    if h < PIPELINE_CHECK_LOCK_H or (h == PIPELINE_CHECK_LOCK_H and m < PIPELINE_CHECK_LOCK_M):
        return True

    # Dopo le 05:30 → controlla lock file
    return os.path.exists(LOCK_FILE)


def prossimo_orario():
    """Calcola il prossimo orario di esecuzione."""
    now = datetime.now()
    ora_corrente = now.hour * 60 + now.minute  # minuti dalla mezzanotte

    for h in ORARI_RUN:
        target = h * 60  # minuti dalla mezzanotte
        if target > ora_corrente:
            return now.replace(hour=h, minute=0, second=0, microsecond=0)

    # Se tutti gli orari di oggi sono passati, prendi il primo di domani
    domani = now + timedelta(days=1)
    return domani.replace(hour=ORARI_RUN[0], minute=0, second=0, microsecond=0)


def run_odds_loop():
    orari_str = ", ".join(f"{h:02d}:00" for h in ORARI_RUN)
    print(f"\n{'='*55}")
    print(f" 📊 DIRETTORE QUOTE (NOWGOAL) - SISTEMA ATTIVO")
    print(f" 📊 Orari fissi: {orari_str}")
    print(f"{'='*55}")
    print(" ⌨️  Premi 'H' per NASCONDERE questa finestra")
    print(" ⌨️  Premi 'CTRL+C' per terminare il processo\n")

    heartbeat = ["❤️", "   "]

    while True:
        # --- PAUSA PIPELINE NOTTURNA (03:30-09:00) ---
        if is_pipeline_window():
            lock_status = "🔒 lock attivo" if os.path.exists(LOCK_FILE) else "⏳ attesa lock"
            sys.stdout.write(f"\r 💤 [PAUSA PIPELINE] {datetime.now().strftime('%H:%M:%S')} | {lock_status}          ")
            sys.stdout.flush()
            time.sleep(60)
            continue

        # Calcola prossimo orario
        target = prossimo_orario()
        secondi_attesa = (target - datetime.now()).total_seconds()

        if secondi_attesa > 0:
            print(f"\n ⏰ Prossimo run: {target.strftime('%H:%M')} (tra {int(secondi_attesa // 60)} min)")

            # Attesa con heartbeat (cicli da 10 sec)
            cicli = int(secondi_attesa / 10) + 1
            for i in range(cicli):
                # Check pausa pipeline durante l'attesa
                if is_pipeline_window():
                    break

                # Controllo pressione tasto H
                if msvcrt.kbhit():
                    tasto = msvcrt.getch().decode('utf-8').lower()
                    if tasto == 'h':
                        ctypes.windll.user32.ShowWindow(
                            ctypes.windll.kernel32.GetConsoleWindow(), 0
                        )
                        print("\n👻 Finestra nascosta! Il monitoraggio quote continua in background.")

                # Controlla se è ora di partire
                if datetime.now() >= target:
                    break

                h = heartbeat[i % 2]
                orario_live = datetime.now().strftime("%H:%M:%S")
                min_mancanti = max(0, int((target - datetime.now()).total_seconds() // 60))
                sys.stdout.write(f"\r 📊 [NOWGOAL] {h} {orario_live} | Prossimo run alle {target.strftime('%H:%M')} (tra {min_mancanti} min)  ")
                sys.stdout.flush()
                time.sleep(10)

            # Se siamo entrati nella pausa durante l'attesa, torna al while
            if is_pipeline_window():
                continue

        # --- ESECUZIONE SCRAPER ---
        print(f"\n\n 🚀 Avvio scraper NowGoal — {datetime.now().strftime('%H:%M:%S')}")
        try:
            run_scraper()
        except Exception as e:
            print(f"\n❌ Errore durante lo scarico: {e}")

        print(f" ✅ Scraper completato — {datetime.now().strftime('%H:%M:%S')}")

if __name__ == "__main__":
    run_odds_loop()