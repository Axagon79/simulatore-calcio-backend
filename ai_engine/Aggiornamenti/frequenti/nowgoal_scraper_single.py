import os
import sys
import time
import re
import json
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
    """Normalizza il nome di una squadra rimuovendo prefissi comuni e caratteri speciali"""
    if not name: 
        return ""
    
    name = name.lower().strip()
    
    # Rimuovi caratteri speciali comuni
    replacements = {
        "ü": "u", "ö": "o", "é": "e", "è": "e", "à": "a",
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
    
    # Normalizzazioni specifiche per squadre comuni
    specific_mappings = {
        # Italia
        "inter milan": "inter",
        "inter milano": "inter",
        "juve next gen": "juventus u23",
        "juventus ng": "juventus u23",
        "hellas verona": "verona",
        "giana erminio": "giana",
        
        # Inghilterra
        "manchester utd": "manchester united",
        "man utd": "manchester united",
        "man city": "manchester city",
        "nott'm forest": "nottingham forest",
        "nottingham": "nottingham forest",
        "west ham utd": "west ham",
        "brighton": "brighton hove albion",
        "wolves": "wolverhampton",
        
        # Spagna
        "atletico": "atletico madrid",
        "barcellona": "barcelona",
        "siviglia": "sevilla",
        "celta de vigo": "celta vigo",
        "celta": "celta vigo",
        "athletic club": "athletic bilbao",
        
        # Germania
        "bayern": "bayern munchen",
        "bayern monaco": "bayern munchen",
        "leverkusen": "bayer leverkusen",
        "dortmund": "borussia dortmund",
        "leipzig": "rb leipzig",
        "lipsia": "rb leipzig",
        "gladbach": "monchengladbach",
        "m'gladbach": "monchengladbach",
        
        # Francia
        "marsiglia": "marseille",
        "nizza": "nice",
        "lione": "lyon",
        "psg": "paris saint germain",
        
        # Altri
        "sporting cp": "sporting",
        "sporting lisbona": "sporting",
    }
    
    for old, new in specific_mappings.items():
        if old in name:
            name = name.replace(old, new)
    
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
    words = team_name.lower().split()
    if len(words) > 1:
        for word in words:
            if len(word) >= 4:  # Solo parole di almeno 4 caratteri
                aliases.add(word)
    
    # Stesso per il nome normalizzato
    if normalized:
        words_norm = normalized.split()
        if len(words_norm) > 1:
            for word in words_norm:
                if len(word) >= 4:
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

def find_match_in_rows(home_aliases: List[str], away_aliases: List[str], rows_text: List[str]) -> Optional[Tuple[Dict, str, bool]]:
    """
    Cerca una partita nelle righe del sito usando gli alias.
    Ritorna (quote_dict, row_text, has_odds) se trovata:
    - quote_dict: dizionario con le quote (può essere None)
    - row_text: testo della riga
    - has_odds: True se la riga ha quote, False altrimenti
    
    Ritorna None se la partita non è stata trovata per niente.
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

    for row_text in rows_text:
        row_clean = clean_nowgoal_text(row_text.lower())

        home_found = any(re.search(r'\b' + re.escape(n) + r'\b', row_clean) for n in home_search)
        away_found = any(re.search(r'\b' + re.escape(n) + r'\b', row_clean) for n in away_search)

        if home_found and away_found:
            odds = extract_odds_from_row(row_text)
            
            if odds:
                # Partita trovata CON quote
                return (odds, row_text, True)
            else:
                # Partita trovata SENZA quote
                return (None, row_text, False)
    
    # Partita non trovata
    return None

def click_round_and_wait(driver, round_num: int, timeout: int = 15) -> bool:
    """
    Clicca su una giornata e attende il caricamento della tabella.
    Ritorna True se ha successo, False altrimenti.
    """
    try:
        # Trova l'elemento della giornata
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
        
        # Clicca usando JavaScript per evitare problemi di interception
        driver.execute_script("arguments[0].click();", element)
        
        # Attendi che la tabella si carichi
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "tr[id]"))
        )
        
        # Breve pausa per stabilizzazione
        time.sleep(1)
        
        return True
        
    except Exception as e:
        print(f"   ⚠️ Errore navigazione giornata {round_num}: {e}")
        return False

def get_current_round_from_page(driver) -> Optional[int]:
    """
    Determina quale giornata è attualmente visualizzata nella pagina.
    Legge il numero dalla prima riga della tabella.
    """
    try:
        # Attendi che la tabella sia presente
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "tr[id]"))
        )
        
        # Prendi la prima riga
        first_row = driver.find_element(By.CSS_SELECTOR, "tr[id]")
        first_row_text = first_row.text.strip()
        
        # Il numero di giornata è tipicamente all'inizio (es. "15 14-12 12:30 ...")
        match = re.match(r'^(\d+)', first_row_text)
        if match:
            return int(match.group(1))
        
    except Exception as e:
        print(f"   ⚠️ Impossibile leggere giornata dalla pagina: {e}")
    
    return None

def get_all_match_rows(driver) -> List[str]:
    """Estrae tutte le righe di partite dalla pagina corrente"""
    try:
        rows = driver.find_elements(By.CSS_SELECTOR, "tr[id]")
        return [row.text for row in rows if row.text.strip()]
    except:
        return []

def analyze_missing_match(
    home: str, 
    away: str, 
    home_aliases: List[str], 
    away_aliases: List[str], 
    all_rows: List[str],
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
    
    # Cerca le squadre singolarmente
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
        row_clean = clean_nowgoal_text(row.lower())

        if any(re.search(r'\b' + re.escape(n) + r'\b', row_clean) for n in home_search_diag):
            home_found_in.append(idx)

        if any(re.search(r'\b' + re.escape(n) + r'\b', row_clean) for n in away_search_diag):
            away_found_in.append(idx)
    
    # Analizza i risultati
    if not home_found_in and not away_found_in:
        analysis["motivi"].append("NESSUNA_SQUADRA_TROVATA")
        analysis["dettagli"]["nota"] = "Nessuna delle due squadre trovata sul sito"
        
    elif home_found_in and not away_found_in:
        analysis["motivi"].append("SOLO_CASA_TROVATA")
        analysis["dettagli"]["righe_casa"] = home_found_in[:3]
        
        # 🔍 NUOVO: Trova quale squadra c'è nella riga con casa
        if home_found_in:
            riga_con_casa = all_rows[home_found_in[0]]
            # Estrai i nomi delle squadre dalla riga
            analysis["dettagli"]["riga_esempio"] = riga_con_casa[:200]
            analysis["dettagli"]["suggerimento"] = f"Cerca '{away}' in questa riga per vedere come si chiama sul sito"
        
    elif away_found_in and not home_found_in:
        analysis["motivi"].append("SOLO_TRASFERTA_TROVATA")
        analysis["dettagli"]["righe_trasferta"] = away_found_in[:3]
        
        # 🔍 NUOVO: Trova quale squadra c'è nella riga con trasferta
        if away_found_in:
            riga_con_trasferta = all_rows[away_found_in[0]]
            analysis["dettagli"]["riga_esempio"] = riga_con_trasferta[:200]
            analysis["dettagli"]["suggerimento"] = f"Cerca '{home}' in questa riga per vedere come si chiama sul sito"
        
    elif home_found_in and away_found_in:
        # Entrambe trovate ma non nella stessa riga
        same_row = set(home_found_in) & set(away_found_in)
        if same_row:
            analysis["motivi"].append("PARTITA_TROVATA_MA_SENZA_QUOTE")
            example_idx = list(same_row)[0]
            analysis["dettagli"]["esempio_riga"] = all_rows[example_idx][:200]
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
            
            # Naviga alla pagina della lega
            driver.get(league_url)
            time.sleep(3)
            
            # Determina giornata corrente
            current_round = get_current_round_from_page(driver)
            if not current_round:
                print(f"   ⚠️ Impossibile determinare giornata corrente, skip")
                continue
            
            print(f"   📅 Giornata corrente sul sito: {current_round}")
            
            # Processa 3 giornate: PRIMA LA CORRENTE, poi le altre
            # Questo evita problemi se il sito "perde" la giornata corrente dopo i click
            rounds_to_process = [current_round, current_round - 1, current_round + 1]
            
            for round_num in rounds_to_process:
                if round_num < 1:
                    continue
                
                print(f"\n   ⚙️ Giornata {round_num}")
                
                # Naviga alla giornata E ATTENDI sempre
                if round_num != current_round:
                    # Giornata diversa: fai click
                    if not click_round_and_wait(driver, round_num):
                        print(f"      ⚠️ Navigazione fallita, skip")
                        continue
                    
                    # VERIFICA di essere sulla giornata corretta
                    actual_round = get_current_round_from_page(driver)
                    if actual_round and actual_round != round_num:
                        print(f"      ⚠️ Click non riuscito: sulla giornata {actual_round} invece di {round_num}")
                        continue
                    elif actual_round:
                        print(f"      ✓ Confermata giornata {actual_round}")
                else:
                    # Giornata corrente: assicurati che sia caricata
                    print(f"      ℹ️ Già sulla giornata corrente, attendo caricamento...")
                    try:
                        WebDriverWait(driver, 15).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "tr[id]"))
                        )
                        time.sleep(1)  # Pausa per stabilizzazione
                    except Exception as e:
                        print(f"      ⚠️ Timeout caricamento tabella, skip")
                        continue
                
                # Recupera partite dal DB
                round_docs = list(db.h2h_by_round.find({
                    "league": league_name,
                    "round_name": {"$regex": f".*{round_num}.*"}
                }))
                
                if not round_docs:
                    print(f"      ℹ️ Nessuna partita nel DB")
                    continue
                
                round_doc = round_docs[0]
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
                    print(f"      📄 Esempio prima riga: {all_rows[0][:80]}...")
                
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
                        print(f"         [{i+1}] {row[:120]}")
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
        
if __name__ == "__main__":
    run_scraper()