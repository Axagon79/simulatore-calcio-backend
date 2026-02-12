import os
import sys
import time
import random
import requests
import importlib
from bs4 import BeautifulSoup

# --- CONFIGURAZIONE PERCORSI ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db

# --- COLLEZIONI ---
rankings_collection = db['classifiche']
teams_collection = db['teams']  # <--- FONDAMENTALE: Ci serve per cercare gli ID

# --- CACHE TEAMS IN MEMORIA (evita ~520 query regex individuali) ---
_teams_cache = {}  # nome_lower → transfermarkt_id

def _build_teams_cache():
    """Carica tutte le teams e costruisce un dizionario nome/alias → tm_id."""
    all_teams = list(teams_collection.find({}, {"name": 1, "aliases": 1, "aliases_transfermarkt": 1, "transfermarkt_id": 1}))
    for t in all_teams:
        tm_id = t.get("transfermarkt_id")
        if not tm_id:
            continue
        # Nome principale
        name = t.get("name", "")
        if name:
            _teams_cache[name.strip().lower()] = tm_id
        # Aliases standard
        for alias in (t.get("aliases") or []):
            if alias:
                _teams_cache[alias.strip().lower()] = tm_id
        # Aliases Transfermarkt
        for alias in (t.get("aliases_transfermarkt") or []):
            if alias:
                _teams_cache[alias.strip().lower()] = tm_id
    print(f"   ✅ Cache teams: {len(all_teams)} squadre → {len(_teams_cache)} nomi indicizzati")

_build_teams_cache()

# --- CONFIGURAZIONE COMPETIZIONI (ANNO 2025) ---
COMPETITIONS = [
    # ITALIA (Transfermarkt.it -> Nomi Italiani)
    {
        "name": "Serie A",
        "country": "Italy",
        "table_url": "https://www.transfermarkt.it/serie-a/tabelle/wettbewerb/IT1", 
        "dual_tables": False,
    },
    {
        "name": "Serie B",
        "country": "Italy",
        "table_url": "https://www.transfermarkt.it/serie-b/tabelle/wettbewerb/IT2",
        "dual_tables": False,
    },
    {
        "name": "Serie C - Girone A",
        "country": "Italy",
        "table_url": "https://www.transfermarkt.it/serie-c-girone-a/tabelle/wettbewerb/IT3A",
        "dual_tables": False,
    },
    {
        "name": "Serie C - Girone B",
        "country": "Italy",
        "table_url": "https://www.transfermarkt.it/serie-c-girone-b/tabelle/wettbewerb/IT3B",
        "dual_tables": False,
    },
    {
        "name": "Serie C - Girone C",
        "country": "Italy",
        "table_url": "https://www.transfermarkt.it/serie-c-girone-c/tabelle/wettbewerb/IT3C",
        "dual_tables": False,
    },
    
    # EUROPA TOP (Transfermarkt.com -> Nomi Internazionali/Inglesi)
    {
        "name": "Premier League",
        "country": "England",
        "table_url": "https://www.transfermarkt.com/premier-league/tabelle/wettbewerb/GB1",
        "dual_tables": False,
    },
    {
        "name": "La Liga",
        "country": "Spain",
        "table_url": "https://www.transfermarkt.com/la-liga/tabelle/wettbewerb/ES1",    
        "dual_tables": False,
    },
    {
        "name": "Bundesliga",
        "country": "Germany",
        "table_url": "https://www.transfermarkt.com/bundesliga/tabelle/wettbewerb/L1",
        "dual_tables": False,
    },
    {
        "name": "Ligue 1",
        "country": "France",
        "table_url": "https://www.transfermarkt.com/ligue-1/tabelle/wettbewerb/FR1",
        "dual_tables": False,
    },
    {
        "name": "Eredivisie",
        "country": "Netherlands",
        "table_url": "https://www.transfermarkt.com/eredivisie/tabelle/wettbewerb/NL1",
        "dual_tables": False,
    },
    {
        "name": "Liga Portugal",
        "country": "Portugal",
        "table_url": "https://www.transfermarkt.com/liga-nos/tabelle/wettbewerb/PO1",
        "dual_tables": False,
    },
    
    # 🆕 EUROPA SERIE B
    {
        "name": "Championship",
        "country": "England",
        "table_url": "https://www.transfermarkt.com/championship/tabelle/wettbewerb/GB2",
        "dual_tables": False,
    },
    {
        "name": "LaLiga 2",
        "country": "Spain",
        "table_url": "https://www.transfermarkt.com/laliga2/tabelle/wettbewerb/ES2",
        "dual_tables": False,
    },
    {
        "name": "2. Bundesliga",
        "country": "Germany",
        "table_url": "https://www.transfermarkt.com/2-bundesliga/tabelle/wettbewerb/L2",
        "dual_tables": False,
    },
    {
        "name": "Ligue 2",
        "country": "France",
        "table_url": "https://www.transfermarkt.com/ligue-2/tabelle/wettbewerb/FR2",
        "dual_tables": False,
    },
    
    # 🆕 EUROPA NORDICI + EXTRA
    {
        "name": "Scottish Premiership",
        "country": "Scotland",
        "table_url": "https://www.transfermarkt.com/premiership/tabelle/wettbewerb/SC1",
        "dual_tables": False,
    },
    {
        "name": "Allsvenskan",
        "country": "Sweden",
        "table_url": "https://www.transfermarkt.com/allsvenskan/tabelle/wettbewerb/SE1",
        "dual_tables": False,
    },
    {
        "name": "Eliteserien",
        "country": "Norway",
        "table_url": "https://www.transfermarkt.com/eliteserien/tabelle/wettbewerb/NO1",
        "dual_tables": False,
    },
    {
        "name": "Superligaen",
        "country": "Denmark",
        "table_url": "https://www.transfermarkt.com/superligaen/tabelle/wettbewerb/DK1",
        "dual_tables": False,
    },
    {
        "name": "Jupiler Pro League",
        "country": "Belgium",
        "table_url": "https://www.transfermarkt.com/jupiler-pro-league/tabelle/wettbewerb/BE1",
        "dual_tables": False,
    },
    {
        "name": "Süper Lig",
        "country": "Turkey",
        "table_url": "https://www.transfermarkt.com/super-lig/tabelle/wettbewerb/TR1",
        "dual_tables": False,
    },
    {
        "name": "League of Ireland Premier Division",
        "country": "Ireland",
        "table_url": "https://www.transfermarkt.com/premier-league/tabelle/wettbewerb/IR1",
        "dual_tables": False,
    },
    
    # 🆕 AMERICHE
    {
        "name": "Brasileirão Serie A",
        "country": "Brazil",
        "table_url": "https://www.transfermarkt.com/campeonato-brasileiro-serie-a/tabelle/wettbewerb/BRA1",
        "dual_tables": False,
    },
    {
        "name": "Primera División",
        "country": "Argentina",
        "table_url": "https://www.transfermarkt.com/torneo-inicial/tabelle/wettbewerb/ARG1",
        "dual_tables": True,
    },
    {
        "name": "Major League Soccer",
        "country": "USA",
        "table_url": "https://www.transfermarkt.com/major-league-soccer/tabelle/wettbewerb/MLS1",
        "dual_tables": False,
    },
    
    # 🆕 ASIA
    {
        "name": "J1 League",
        "country": "Japan",
        "table_url": "https://www.transfermarkt.com/j1-league/tabelle/wettbewerb/JAP1",
        "dual_tables": False,
    },
]

# --- HEADERS ANTI-BLOCCO ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
}

def to_int(val):
    try:
        return int(val)
    except:
        return 0

def normalize_name(name):
    """Pulisce il nome per migliorare la ricerca nel DB"""
    if not name: return ""
    return name.strip()

def find_db_data(scraped_name):
    """
    Cerca il nome scaricato nella cache in-memory (Nome o Alias).
    Restituisce (transfermarkt_id, None) — il team_id non è più necessario.
    """
    if not scraped_name: return None, None

    tm_id = _teams_cache.get(scraped_name.strip().lower())
    if tm_id:
        return tm_id, None

    return None, None

def scrape_single_table(soup, table_index=0, split_mode=None, force_grid_view=False):
    """
    Scarica una singola tabella dalla pagina.
    table_index: 0 = prima tabella, 1 = seconda tabella
    split_mode: None = tabella intera, 'first_half' = prime 15, 'second_half' = ultime 15
    force_grid_view: True = usa grid-view (Argentina), False = usa responsive-table
    """
    standings_table = []
    
    # Trova TUTTE le tabelle nella pagina
    if force_grid_view:
        # Argentina: usa grid-view
        all_tables = soup.find_all("div", class_="grid-view")
    else:
        # Campionati normali: usa responsive-table
        all_tables = soup.find_all("div", class_="responsive-table")
        
        # Fallback: se non trova responsive-table, prova grid-view
        if not all_tables:
            all_tables = soup.find_all("div", class_="grid-view")


    if table_index >= len(all_tables):
        print(f"⚠️  Tabella {table_index} non trovata")
        return []

    tablediv = all_tables[table_index]

    # Per grid-view (Argentina), la tabella è dentro il div
    if "grid-view" in tablediv.get("class", []):
        table = tablediv.find("table", class_="items")
        if not table:
            print(f"⚠️  Tabella items non trovata dentro grid-view")
            return []
        rows = table.find("tbody").find_all("tr")
    else:
        rows = tablediv.find("tbody").find_all("tr")

    
    foundidscount = 0
    for row in rows:
        try:
            # 1. POSIZIONE
            rankcell = row.find("td", class_="rechts hauptlink")
            if not rankcell:
                rankcell = row.find_all("td")[0]
            ranktext = rankcell.get_text(strip=True).replace(".", "")
            if not ranktext.isdigit():
                continue
            rank = int(ranktext)
            
            # 2. NOME SQUADRA
            namecell = row.find("td", class_="no-border-links hauptlink")
            if not namecell:
                namecell = row.find("td", class_="hauptlink")
            if not namecell:
                continue
            teamlink = namecell.find("a")
            teamname = teamlink.get_text(strip=True)
            
            # 3. PUNTI
            pointscells = row.find_all("td", class_="zentriert")
            if pointscells:
                points = to_int(pointscells[-1].get_text(strip=True).split()[0])
                played = to_int(pointscells[0].get_text(strip=True))
            else:
                points = 0
                played = 0
            
            # Cerca nel DB
            tmidfromdb, _ = find_db_data(teamname)
            if tmidfromdb:
                foundidscount += 1
            
            teamdata = {
                "rank": rank,
                "team": teamname,
                "transfermarkt_id": tmidfromdb,
                "points": points,
                "played": played
            }
            standings_table.append(teamdata)
            
        except Exception:
            continue
    
        # Se split_mode attivo, dividi la tabella
    if split_mode == 'first_half':
        standings_table = standings_table[:15]  # Prime 15 squadre
        # Ricalcola rank da 1 a 15
        for i, team in enumerate(standings_table, 1):
            team['rank'] = i
        # Ricalcola foundidscount
        foundidscount = sum(1 for team in standings_table if team.get('transfermarkt_id'))
    elif split_mode == 'second_half':
        standings_table = standings_table[15:30]  # Ultime 15 squadre
        # Ricalcola rank da 1 a 15
        for i, team in enumerate(standings_table, 1):
            team['rank'] = i
        # Ricalcola foundidscount
        foundidscount = sum(1 for team in standings_table if team.get('transfermarkt_id'))
    
    print(f"   ✅ Estratte {len(standings_table)} squadre (ID trovati: {foundidscount})")
    return standings_table




def scrape_transfermarkt():
    print("🦁 AVVIO SCRAPER TRANSFERMARKT 2025 (Con Smart Matching ID)")
    
    for comp in COMPETITIONS:
        league_name = comp['name']
        country = comp['country']
        url = comp['table_url']
        
        print(f"\n🌍 Scarico: {league_name} ({country})...")
        
        try:
            # Pausa tattica anti-ban
            time.sleep(random.uniform(2.0, 4.0))
            
            resp = requests.get(url, headers=HEADERS, timeout=20)
            if resp.status_code != 200:
                print(f"   ❌ Errore HTTP {resp.status_code}")
                continue
                
            soup = BeautifulSoup(resp.content, "html.parser")
            
            # Verifica se il campionato ha 2 gironi
            if comp.get("dual_tables"):
                print("   📊 Campionato con 2 gironi - unisco in classifica unica...")
                
                # Zona A
                table_a = scrape_single_table(soup, table_index=0, force_grid_view=True)
                
                # Zona B
                table_b = scrape_single_table(soup, table_index=1, force_grid_view=True)
                
                # Unisci entrambe le zone in una classifica unica
                if table_a and table_b:
                    combined_table = table_a + table_b  # 30 squadre totali
                    
                    filter_query = {"country": country, "league": league_name}
                    update_doc = {
                        "$set": {
                            "country": country,
                            "league": league_name,
                            "last_updated": time.time(),
                            "source": "transfermarkt",
                            "table": combined_table
                        }
                    }
                    rankings_collection.update_one(filter_query, update_doc, upsert=True)
                    print(f"   ✅ Salvate {len(combined_table)} squadre in classifica unica")
                else:
                    print("   ⚠️ Errore: impossibile unire le zone")

            
            else:
                # Classifica unica (funzionamento normale)
                standing_table = scrape_single_table(soup, table_index=0)
                
                if len(standing_table) > 0:
                    filter_query = {"country": country, "league": league_name}
                    update_doc = {
                        "$set": {
                            "country": country,
                            "league": league_name,
                            "last_updated": time.time(),
                            "source": "transfermarkt",
                            "table": standing_table
                        }
                    }
                    rankings_collection.update_one(filter_query, update_doc, upsert=True)
                    print(f"   ✅ Salvate {len(standing_table)} squadre")
                else:
                    print("  ⚠️ Nessuna squadra estratta.")


        except Exception as e:
            print(f"   ❌ Errore: {e}")

if __name__ == "__main__":
    # 1. Esegue lo scaricamento e salvataggio
    scrape_transfermarkt()
    
    print("\n🔗 Preparazione aggiornamento partite...")
    
    try:
        # --- CALCOLO PERCORSO DINAMICO ---
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Saliamo di 2 livelli: .../ai_engine
        ai_engine_path = os.path.dirname(os.path.dirname(current_dir))
        calculators_path = os.path.join(ai_engine_path, 'calculators')
        
        # Aggiungiamo al sistema temporaneamente
        if calculators_path not in sys.path:
            sys.path.append(calculators_path)

        # --- IMPORTAZIONE DINAMICA (Zittisce l'errore di Pylance) ---
        # Carichiamo il file come un modulo
        injector_module = importlib.import_module("injector_standings_to_matches")
        
        # 2. Esegue la funzione dentro il modulo
        injector_module.inject_standings_final()
        
    except ImportError as e:
        print(f"❌ Errore: Impossibile trovare il file injector.\nPercorso cercato: {calculators_path}\nDettaglio: {e}")
    except Exception as e:
        print(f"❌ Errore generico durante l'iniezione: {e}")