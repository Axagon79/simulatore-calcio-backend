import os
import sys
import time
import random
import requests
import re
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

# --- CONFIGURAZIONE COMPETIZIONI (ANNO 2025) ---
COMPETITIONS = [
    # ITALIA (Transfermarkt.it -> Nomi Italiani)
    {
        "name": "Serie A",
        "country": "Italy",
        "table_url": "https://www.transfermarkt.it/serie-a/tabelle/wettbewerb/IT1/saison_id/2025", 
    },
    {
        "name": "Serie B",
        "country": "Italy",
        "table_url": "https://www.transfermarkt.it/serie-b/tabelle/wettbewerb/IT2/saison_id/2025",
    },
    {
        "name": "Serie C - Girone A",
        "country": "Italy",
        "table_url": "https://www.transfermarkt.it/serie-c-girone-a/tabelle/wettbewerb/IT3A/saison_id/2025",
    },
    {
        "name": "Serie C - Girone B",
        "country": "Italy",
        "table_url": "https://www.transfermarkt.it/serie-c-girone-b/tabelle/wettbewerb/IT3B/saison_id/2025",
    },
    {
        "name": "Serie C - Girone C",
        "country": "Italy",
        "table_url": "https://www.transfermarkt.it/serie-c-girone-c/tabelle/wettbewerb/IT3C/saison_id/2025",
    },
    # ESTERO (Transfermarkt.com -> Nomi Internazionali/Inglesi)
    {
        "name": "Premier League",
        "country": "England",
        "table_url": "https://www.transfermarkt.com/premier-league/tabelle/wettbewerb/GB1/saison_id/2025",
    },
    {
        "name": "La Liga",
        "country": "Spain",
        "table_url": "https://www.transfermarkt.com/la-liga/tabelle/wettbewerb/ES1/saison_id/2025",
    },
    {
        "name": "Eredivisie",
        "country": "Netherlands",
        "table_url": "https://www.transfermarkt.com/eredivisie/tabelle/wettbewerb/NL1/saison_id/2025",
    },
    {
        "name": "Bundesliga",
        "country": "Germany",
        "table_url": "https://www.transfermarkt.com/bundesliga/tabelle/wettbewerb/L1/saison_id/2025",
    },
    {
        "name": "Ligue 1",
        "country": "France",
        "table_url": "https://www.transfermarkt.com/ligue-1/tabelle/wettbewerb/FR1/saison_id/2025",
    },
    {
        "name": "Liga Portugal",
        "country": "Portugal",
        "table_url": "https://www.transfermarkt.com/liga-nos/tabelle/wettbewerb/PO1/saison_id/2025",
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
    Cerca il nome scaricato nella collezione 'teams' (Nome o Alias).
    Se trova la squadra, restituisce il suo 'transfermarkt_id' (dal DB) e il 'team_id'.
    """
    if not scraped_name: return None, None
    
    # Cerca per Nome ESATTO, per ALIAS o per ALIAS TRANSFERMARKT
    query = {
        "$or": [
            {"name": {"$regex": f"^{re.escape(scraped_name)}$", "$options": "i"}},
            {"aliases": {"$regex": f"^{re.escape(scraped_name)}$", "$options": "i"}},
            {"aliases_transfermarkt": {"$regex": f"^{re.escape(scraped_name)}$", "$options": "i"}}
        ]
    }
    
    team = teams_collection.find_one(query)
    
    if team:
        # Restituisce il numeretto (transfermarkt_id) presente nel TUO DB e l'ID interno
        return team.get('transfermarkt_id'), (team.get('team_id') or team.get('id') or team.get('_id'))
    
    return None, None

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
            
            # Cerca il contenitore tabella principale
            table_div = soup.find("div", {"class": "responsive-table"})
            if not table_div:
                print("   ❌ Tabella non trovata (Verificare URL o Blocco IP).")
                continue
                
            rows = table_div.find("tbody").find_all("tr")
            standing_table = []
            found_ids_count = 0
            
            for row in rows:
                try:
                    # 1. POSIZIONE (Rank)
                    rank_cell = row.find("td", {"class": "rechts hauptlink"}) 
                    if not rank_cell: rank_cell = row.find_all("td")[0] # Fallback
                    
                    rank_text = rank_cell.get_text(strip=True).replace('.', '')
                    if not rank_text.isdigit(): continue
                    rank = int(rank_text)

                    # 2. NOME SQUADRA
                    name_cell = row.find("td", {"class": "no-border-links hauptlink"})
                    if not name_cell: name_cell = row.find("td", {"class": "hauptlink"})
                    if not name_cell: continue
                    
                    team_link = name_cell.find("a")
                    team_name = team_link.get_text(strip=True) # es. "Inter Milan"
                    
                    # 3. PUNTI
                    points_cells = row.find_all("td", {"class": "zentriert"})
                    if points_cells:
                        points = to_int(points_cells[-1].get_text(strip=True).split(':')[0])
                        played = to_int(points_cells[0].get_text(strip=True))
                    else:
                        points = 0; played = 0

                    # --- 4. RICERCA NEL TUO DB (Nome -> ID) ---
                    # Cerchiamo il nome scaricato dentro 'teams' per ottenere i TUOI dati
                    tm_id_from_db, _ = find_db_data(team_name) # Usiamo _ perché internal_id non ci serve più
                    
                    if tm_id_from_db:
                        found_ids_count += 1

                    team_data = {
                        "rank": rank,
                        "team": team_name,                 # Nome scaricato
                        "transfermarkt_id": tm_id_from_db, # Il numeretto preso dal TUO DB teams           # Il tuo ID interno
                        "points": points,
                        "played": played
                    }
                    standing_table.append(team_data)
                    
                except Exception:
                    continue

            # --- SALVATAGGIO ---
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
                print(f"   ✅ Salvate {len(standing_table)} squadre (ID trovati: {found_ids_count}).")
            else:
                print("   ⚠️ Nessuna squadra estratta.")

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