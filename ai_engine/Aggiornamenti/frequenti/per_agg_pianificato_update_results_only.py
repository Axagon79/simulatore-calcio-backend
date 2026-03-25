import os
import sys
import time
import importlib.util
import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup

# --- CONFIGURAZIONE PERCORSI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
aggiornamenti_dir = os.path.dirname(current_dir)
ai_engine_dir = os.path.dirname(aggiornamenti_dir)
project_root = os.path.dirname(ai_engine_dir)

if ai_engine_dir not in sys.path:
    sys.path.insert(0, ai_engine_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

print(f"📂 project_root: {project_root}\n")

try:
    spec = importlib.util.spec_from_file_location("config", os.path.join(project_root, "config.py"))
    config_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_module)
    db = config_module.db
    print(f"✅ DB Connesso: {db.name}\n")
except Exception as e:
    print(f"❌ Errore Import Config: {e}")
    sys.exit(1)

# --- CONFIGURAZIONE ---
COLLECTION_H2H = "h2h_by_round"
COLLECTION_TEAMS = "teams"
DEBUG_MODE = True

# --- CONFIGURAZIONE LEGHE ---
LEAGUES_CONFIG = [
    # ITALIA
    {"league_name": "Serie A", "id_prefix": "SerieA", "url": "https://www.betexplorer.com/it/football/italy/serie-a/results/"},
    {"league_name": "Serie B", "id_prefix": "SerieB", "url": "https://www.betexplorer.com/it/football/italy/serie-b/results/"},
    {"league_name": "Serie C - Girone A", "id_prefix": "SerieC-GironeA", "url": "https://www.betexplorer.com/it/football/italy/serie-c-group-a/results/"},
    {"league_name": "Serie C - Girone B", "id_prefix": "SerieC-GironeB", "url": "https://www.betexplorer.com/it/football/italy/serie-c-group-b/results/"},
    {"league_name": "Serie C - Girone C", "id_prefix": "SerieC-GironeC", "url": "https://www.betexplorer.com/it/football/italy/serie-c-group-c/results/"},
    
    # EUROPA TOP
    {"league_name": "Premier League", "id_prefix": "PremierLeague", "url": "https://www.betexplorer.com/it/football/england/premier-league/results/"},
    {"league_name": "La Liga", "id_prefix": "LaLiga", "url": "https://www.betexplorer.com/it/football/spain/laliga/results/"},
    {"league_name": "Bundesliga", "id_prefix": "Bundesliga", "url": "https://www.betexplorer.com/it/football/germany/bundesliga/results/"},
    {"league_name": "Ligue 1", "id_prefix": "Ligue1", "url": "https://www.betexplorer.com/it/football/france/ligue-1/results/"},
    {"league_name": "Eredivisie", "id_prefix": "Eredivisie", "url": "https://www.betexplorer.com/it/football/netherlands/eredivisie/results/"},
    {"league_name": "Liga Portugal", "id_prefix": "LigaPortugal", "url": "https://www.betexplorer.com/it/football/portugal/liga-portugal/results/"},
    
    # 🆕 EUROPA SERIE B
    {"league_name": "Championship", "id_prefix": "Championship", "url": "https://www.betexplorer.com/it/football/england/championship/results/"},
    {"league_name": "League One", "id_prefix": "LeagueOne", "url": "https://www.betexplorer.com/it/football/england/league-one/results/"},
    {"league_name": "LaLiga 2", "id_prefix": "LaLiga2", "url": "https://www.betexplorer.com/it/football/spain/laliga2/results/"},
    {"league_name": "2. Bundesliga", "id_prefix": "2.Bundesliga", "url": "https://www.betexplorer.com/it/football/germany/2-bundesliga/results/"},
    {"league_name": "Ligue 2", "id_prefix": "Ligue2", "url": "https://www.betexplorer.com/it/football/france/ligue-2/results/"},
    
    # 🆕 EUROPA NORDICI + EXTRA
    {"league_name": "Scottish Premiership", "id_prefix": "ScottishPremiership", "url": "https://www.betexplorer.com/it/football/scotland/premiership/results/"},
    {"league_name": "Allsvenskan", "id_prefix": "Allsvenskan", "url": "https://www.betexplorer.com/it/football/sweden/allsvenskan/results/"},
    {"league_name": "Eliteserien", "id_prefix": "Eliteserien", "url": "https://www.betexplorer.com/it/football/norway/eliteserien/results/"},
    {"league_name": "Superligaen", "id_prefix": "Superligaen", "url": "https://www.betexplorer.com/it/football/denmark/superliga/results/"},
    {"league_name": "Jupiler Pro League", "id_prefix": "JupilerProLeague", "url": "https://www.betexplorer.com/it/football/belgium/jupiler-pro-league/results/"},
    {"league_name": "Süper Lig", "id_prefix": "SüperLig", "url": "https://www.betexplorer.com/it/football/turkey/super-lig/results/"},
    {"league_name": "League of Ireland Premier Division", "id_prefix": "LeagueofIrelandPremierDivision", "url": "https://www.betexplorer.com/it/football/ireland/premier-division/results/"},
    
    # 🆕 AMERICHE
    {"league_name": "Brasileirão Serie A", "id_prefix": "Brasileirao", "url": "https://www.betexplorer.com/it/football/brazil/serie-a-betano/results/"},
    {"league_name": "Primera División", "id_prefix": "PrimeraDivisión", "url": "https://www.betexplorer.com/it/football/argentina/liga-profesional/results//"},
    {"league_name": "Major League Soccer", "id_prefix": "MLS", "url": "https://www.betexplorer.com/it/football/usa/mls/results/"},
    
    # 🆕 ASIA
    {"league_name": "J1 League", "id_prefix": "J1League", "url": "https://www.betexplorer.com/it/football/japan/j1-league/results/"},

    # NUOVI CAMPIONATI (24/03/2026)
    {"league_name": "League Two", "id_prefix": "LeagueTwo", "url": "https://www.betexplorer.com/it/football/england/league-two/results/"},
    {"league_name": "Veikkausliiga", "id_prefix": "Veikkausliiga", "url": "https://www.betexplorer.com/it/football/finland/veikkausliiga/results/"},
    {"league_name": "3. Liga", "id_prefix": "3.Liga", "url": "https://www.betexplorer.com/it/football/germany/3-liga/results/"},
    {"league_name": "Liga MX", "id_prefix": "LigaMX", "url": "https://www.betexplorer.com/it/football/mexico/liga-mx/results/"},
    {"league_name": "Eerste Divisie", "id_prefix": "EersteDivisie", "url": "https://www.betexplorer.com/it/football/netherlands/eerste-divisie/results/"},
    {"league_name": "Liga Portugal 2", "id_prefix": "LigaPortugal2", "url": "https://www.betexplorer.com/it/football/portugal/liga-portugal-2/results/"},
    {"league_name": "1. Lig", "id_prefix": "1.Lig", "url": "https://www.betexplorer.com/it/football/turkey/1-lig/results/"},
    {"league_name": "Saudi Pro League", "id_prefix": "SaudiProLeague", "url": "https://www.betexplorer.com/it/football/saudi-arabia/saudi-professional-league/results/"},
    {"league_name": "Scottish Championship", "id_prefix": "ScottishChampionship", "url": "https://www.betexplorer.com/it/football/scotland/championship/results/"},
]

# --- FUNZIONI UTILS ---
# Cache teams in memoria (1 query invece di ~20000)
_tm_id_cache = {}
def _build_tm_cache():
    if _tm_id_cache: return
    for t in db[COLLECTION_TEAMS].find({}, {"name": 1, "aliases": 1, "aliases_transfermarkt": 1, "transfermarkt_id": 1}):
        tm_id = t.get("transfermarkt_id")
        if not tm_id: continue
        tm_str = str(tm_id)
        _tm_id_cache[t["name"]] = tm_str
        for a in t.get("aliases", []):
            if isinstance(a, str):
                _tm_id_cache[a] = tm_str
        atm = t.get("aliases_transfermarkt")
        if atm and isinstance(atm, str):
            _tm_id_cache[atm] = tm_str

def find_team_tm_id(team_name):
    """Cerca team nella cache in memoria. Ritorna transfermarkt_id o None."""
    _build_tm_cache()
    return _tm_id_cache.get(team_name)

def extract_round_number(text):
    """Estrae numero round da testo"""
    if not text:
        return None
    match = re.search(r'(\d+)', text)
    return match.group(1) if match else None

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'}

def parse_betexplorer_html(html_content):
    """Parsa HTML BetExplorer"""
    soup = BeautifulSoup(html_content, 'html.parser')
    results_by_round = {}
    current_round = None
    
    rows = soup.find_all('tr')
    
    for row in rows:
        # Round header
        th = row.find('th', class_='h-text-left')
        if th:
            header_text = th.get_text(strip=True)
            round_num = extract_round_number(header_text)
            if round_num:
                current_round = round_num
                if current_round not in results_by_round:
                    results_by_round[current_round] = []
            continue
        
        if current_round is None:
            continue
        
        # Match rows
        cells = row.find_all('td')
        if len(cells) < 2:
            continue
        
        first_cell = cells[0]
        if not first_cell.has_attr('class') or 'h-text-left' not in first_cell['class']:
            continue
        
        match_link = first_cell.find('a')
        if not match_link:
            continue
        
        spans = match_link.find_all('span')
        if len(spans) < 2:
            continue
        
        home_team = spans[0].get_text(strip=True)
        away_team = spans[-1].get_text(strip=True)
        
        score_cell = cells[1]
        if not score_cell.has_attr('class') or 'h-text-center' not in score_cell['class']:
            continue
        
        score_link = score_cell.find('a')
        if not score_link:
            continue
        
        score_text = score_link.get_text(strip=True)
        
        if not re.match(r'^\d+:\d+$', score_text):
            continue
        
        results_by_round[current_round].append({
            "home": home_team,
            "away": away_team,
            "score": score_text
        })
    
    return results_by_round

def process_league(h2h_col, league_config):
    """
    Processa una lega: scraping + matching + update DB.
    FLOW CORRETTO:
    1. BetExplorer → nome squadra
    2. Cerca in teams → TM_ID
    3. Con coppia TM_ID cerca in h2h_by_round
    4. Aggiorna
    """
    print(f"\n🌍 Elaborazione: {league_config['league_name']}...")
    updated_count = 0
    
    stats = {
        "rounds_found": 0,
        "matches_extracted": 0,
        "matches_updated": 0,
        "already_updated": 0,
        "team_not_found": 0,
        "match_not_found_db": 0
    }
    
    errors = {
        "teams_not_found": [],
        "matches_not_found": []
    }
    
    try:
        # Scarica pagina con requests (no Selenium)
        if DEBUG_MODE:
            print(f"   🔄 Caricamento pagina...")

        r = requests.get(league_config['url'], headers=HEADERS, timeout=20)
        if r.status_code != 200:
            print(f"   ❌ HTTP {r.status_code}")
            return {"updated": 0, "stats": stats, "errors": errors}

        html_content = r.text
        results = parse_betexplorer_html(html_content)
        
        if not results:
            print(f"   ⚠️ Nessun risultato trovato")
            return {"updated": 0, "stats": stats, "errors": errors}
        
        stats["rounds_found"] = len(results)
        stats["matches_extracted"] = sum(len(m) for m in results.values())
        
        if DEBUG_MODE:
            print(f"   📊 Round: {stats['rounds_found']}, Partite: {stats['matches_extracted']}")
        
        # Processa ogni round
        for round_num, matches in results.items():
            doc_id = f"{league_config['id_prefix']}_{round_num}Giornata"
            db_doc = h2h_col.find_one({"_id": doc_id})
            
            if not db_doc:
                if DEBUG_MODE:
                    print(f"   ⚠️ Doc non trovato: {doc_id}")
                continue
            
            db_matches = db_doc.get("matches", [])
            modified_doc = False
            
            # Processa ogni partita
            for be_match in matches:
                # STEP 1: BetExplorer → Teams → TM_ID casa
                home_tm_id = find_team_tm_id(be_match["home"])
                if not home_tm_id:
                    if DEBUG_MODE:
                        print(f"   ❌ Team non trovato: '{be_match['home']}'")
                    stats["team_not_found"] += 1
                    errors["teams_not_found"].append(be_match["home"])
                    continue
                
                # STEP 2: BetExplorer → Teams → TM_ID trasferta
                away_tm_id = find_team_tm_id(be_match["away"])
                if not away_tm_id:
                    if DEBUG_MODE:
                        print(f"   ❌ Team non trovato: '{be_match['away']}'")
                    stats["team_not_found"] += 1
                    errors["teams_not_found"].append(be_match["away"])
                    continue
                
                # STEP 3: Con coppia TM_ID cerca in h2h_by_round
                match_found = False
                for db_match in db_matches:
                    db_h_id = str(db_match.get('home_tm_id', ''))
                    db_a_id = str(db_match.get('away_tm_id', ''))
                    
                    if db_h_id == home_tm_id and db_a_id == away_tm_id:
                        match_found = True
                        
                        current_score = db_match.get('real_score')
                        new_score = be_match["score"]
                        
                        # STEP 4: Aggiorna
                        if current_score != new_score:
                            db_match['real_score'] = new_score
                            db_match['status'] = "Finished"
                            modified_doc = True
                            updated_count += 1
                            stats["matches_updated"] += 1
                            print(f"   ✅ {db_match['home']} - {db_match['away']} -> {new_score}")
                        else:
                            stats["already_updated"] += 1
                            if DEBUG_MODE:
                                print(f"   ℹ️ {db_match['home']} - {db_match['away']} già aggiornato")
                        break
                
                if not match_found:
                    stats["match_not_found_db"] += 1
                    errors["matches_not_found"].append({
                        "home": be_match["home"],
                        "away": be_match["away"],
                        "home_tm_id": home_tm_id,
                        "away_tm_id": away_tm_id,
                        "doc_id": doc_id
                    })
                    if DEBUG_MODE:
                        print(f"   ⚠️ Match non trovato DB: {be_match['home']} ({home_tm_id}) - {be_match['away']} ({away_tm_id})")
            
            # Salva modifiche
            if modified_doc:
                h2h_col.update_one(
                    {"_id": doc_id},
                    {"$set": {"matches": db_matches, "last_updated": datetime.now()}}
                )
                if DEBUG_MODE:
                    print(f"   💾 Salvato: {doc_id}")
        
    except Exception as e:
        print(f"   ❌ Errore: {e}")
        if DEBUG_MODE:
            import traceback
            traceback.print_exc()
    
    # Statistiche
    if DEBUG_MODE:
        print(f"\n   📊 STATISTICHE:")
        print(f"      - Round trovati: {stats['rounds_found']}")
        print(f"      - Partite estratte: {stats['matches_extracted']}")
        print(f"      - Aggiornamenti: {stats['matches_updated']}")
        print(f"      - Già aggiornati: {stats['already_updated']}")
        print(f"      - Team non trovati: {stats['team_not_found']}")
        print(f"      - Match non trovati DB: {stats['match_not_found_db']}")
    
    return {"updated": updated_count, "stats": stats, "errors": errors}

def run_auto_update():
    """Main execution"""
    print("\n🚀 AGGIORNAMENTO BETEXPLORER (Requests - NO Selenium)\n")

    h2h_col = db[COLLECTION_H2H]

    total_updated = 0
    start_time = time.time()

    global_stats = {
        "leagues_processed": 0,
        "total_matches_updated": 0,
        "total_already_updated": 0,
        "teams_not_found": set(),
        "matches_not_found": []
    }

    for idx, league_config in enumerate(LEAGUES_CONFIG, 1):
        print(f"\n{'='*60}")
        print(f"[{idx}/{len(LEAGUES_CONFIG)}] {league_config['league_name']}")
        print(f"{'='*60}")

        result = process_league(h2h_col, league_config)

        global_stats["leagues_processed"] += 1
        global_stats["total_matches_updated"] += result["stats"]["matches_updated"]
        global_stats["total_already_updated"] += result["stats"]["already_updated"]

        for team in result["errors"]["teams_not_found"]:
            global_stats["teams_not_found"].add(team)

        for match in result["errors"]["matches_not_found"]:
            match["league"] = league_config["league_name"]
            global_stats["matches_not_found"].append(match)

        total_updated += result["updated"]

        time.sleep(0.5)
    
    total_time = time.time() - start_time
    
    # REPORT FINALE
    print(f"\n\n{'='*80}")
    print(f"{'📊 REPORT FINALE':^80}")
    print(f"{'='*80}\n")
    print(f"⏱️  Tempo totale: {total_time:.1f}s")
    print(f"🌍 Leghe processate: {global_stats['leagues_processed']}")
    print(f"🔄 Partite aggiornate: {global_stats['total_matches_updated']}")
    print(f"✓  Partite già aggiornate: {global_stats['total_already_updated']}\n")
    
    if global_stats["teams_not_found"]:
        print(f"❌ TEAM NON TROVATI ({len(global_stats['teams_not_found'])}):")
        for team in sorted(global_stats["teams_not_found"]):
            print(f"   - {team}")
        print()
    
    if global_stats["matches_not_found"]:
        print(f"⚠️  MATCH NON TROVATI DB ({len(global_stats['matches_not_found'])}):")
        for match in global_stats["matches_not_found"][:10]:  # primi 10
            print(f"   [{match['league']}] {match['home']} - {match['away']}")
            print(f"   → TM_ID: {match['home_tm_id']} vs {match['away_tm_id']}")
        if len(global_stats["matches_not_found"]) > 10:
            print(f"   ... e altri {len(global_stats['matches_not_found']) - 10}")
        print()
    
    print(f"{'='*80}\n")
    
    if total_updated > 0:
        print(f"✅ Successo! {total_updated} partite aggiornate")
    elif global_stats["total_already_updated"] > 0:
        print(f"ℹ️  Database già aggiornato")
    else:
        print(f"⚠️  Nessun aggiornamento")

if __name__ == "__main__":
    run_auto_update()