"""
Analizza il matching tra SoccerStats e il database teams
Output chiaro per capire quali alias aggiungere
"""
import os
import sys
import requests
from bs4 import BeautifulSoup

# --- FIX PERCORSI ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db

teams_collection = db['teams']

SOCCERSTATS_LEAGUES = [
    # ITALIA
    {"name": "Serie A", "url": "https://www.soccerstats.com/widetable.asp?league=italy"},
    {"name": "Serie B", "url": "https://www.soccerstats.com/widetable.asp?league=italy2"},
    {"name": "Serie C - Girone A", "url": "https://www.soccerstats.com/widetable.asp?league=italy3"},
    {"name": "Serie C - Girone B", "url": "https://www.soccerstats.com/widetable.asp?league=italy4"},
    {"name": "Serie C - Girone C", "url": "https://www.soccerstats.com/widetable.asp?league=italy5"},
    
    # EUROPA TOP
    {"name": "Premier League", "url": "https://www.soccerstats.com/widetable.asp?league=england"},
    {"name": "La Liga", "url": "https://www.soccerstats.com/widetable.asp?league=spain"},
    {"name": "Bundesliga", "url": "https://www.soccerstats.com/widetable.asp?league=germany"},
    {"name": "Ligue 1", "url": "https://www.soccerstats.com/widetable.asp?league=france"},
    {"name": "Eredivisie", "url": "https://www.soccerstats.com/widetable.asp?league=netherlands"},
    {"name": "Liga Portugal", "url": "https://www.soccerstats.com/widetable.asp?league=portugal"},
    
    # EUROPA SERIE B
    {"name": "Championship", "url": "https://www.soccerstats.com/widetable.asp?league=england2"},
    {"name": "LaLiga 2", "url": "https://www.soccerstats.com/widetable.asp?league=spain2"},
    {"name": "2. Bundesliga", "url": "https://www.soccerstats.com/widetable.asp?league=germany2"},
    {"name": "Ligue 2", "url": "https://www.soccerstats.com/widetable.asp?league=france2"},
    
    # EUROPA NORDICI + EXTRA
    {"name": "Scottish Premiership", "url": "https://www.soccerstats.com/widetable.asp?league=scotland"},
    {"name": "Allsvenskan", "url": "https://www.soccerstats.com/widetable.asp?league=sweden"},
    {"name": "Eliteserien", "url": "https://www.soccerstats.com/widetable.asp?league=norway"},
    {"name": "Superligaen", "url": "https://www.soccerstats.com/widetable.asp?league=denmark"},
    {"name": "Jupiler Pro League", "url": "https://www.soccerstats.com/widetable.asp?league=belgium"},
    {"name": "Süper Lig", "url": "https://www.soccerstats.com/widetable.asp?league=turkey"},
    {"name": "League of Ireland Premier Division", "url": "https://www.soccerstats.com/widetable.asp?league=ireland"},
    
    # AMERICHE
    {"name": "Brasileirão Serie A", "url": "https://www.soccerstats.com/widetable.asp?league=brazil"},
    {"name": "Primera División", "url": "https://www.soccerstats.com/widetable.asp?league=argentina"},
    {"name": "Major League Soccer", "url": "https://www.soccerstats.com/widetable.asp?league=usa"},
    
    # ASIA
    {"name": "J1 League", "url": "https://www.soccerstats.com/widetable.asp?league=japan"}
]

def analyze_matching():
    print("🔍 ANALISI MATCHING SOCCERSTATS <-> DATABASE\n")
    
    headers = {"User-Agent": "Mozilla/5.0"}
    
    total_matched = 0
    total_unmatched = 0
    unmatched_list = []
    
    for league in SOCCERSTATS_LEAGUES:
        print(f"\n{'='*80}")
        print(f"📊 {league['name']}")
        print(f"{'='*80}")
        
        try:
            resp = requests.get(league['url'], headers=headers, timeout=15)
            soup = BeautifulSoup(resp.content, "html.parser")
            rows = soup.find_all("tr")
            
            league_matched = 0
            league_unmatched = 0
            
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 29:
                    continue
                if not cells[0].get_text(strip=True).isdigit():
                    continue
                
                team_name_soccerstats = cells[1].get_text(strip=True)
                
                # Cerca nel DB
                filter_q = {
                    "league": league['name'],
                    "$or": [
                        {"name": team_name_soccerstats},
                        {"aliases.soccerstats": team_name_soccerstats},
                        {"aliases": team_name_soccerstats}
                    ]
                }
                
                db_team = teams_collection.find_one(filter_q)
                
                if db_team:
                    # MATCH TROVATO
                    print(f"   ✅ MATCH: '{db_team['name']}' (DB) = '{team_name_soccerstats}' (SoccerStats)")
                    league_matched += 1
                    total_matched += 1
                else:
                    # NO MATCH - Cerca squadra nel campionato giusto
                    possible_team = teams_collection.find_one({"league": league['name']})
                    
                    if possible_team:
                        # Trova tutte le squadre del campionato
                        all_teams = list(teams_collection.find({"league": league['name']}, {"name": 1}))
                        db_names = [t['name'] for t in all_teams]
                        
                        print(f"   ❌ NO MATCH: '{team_name_soccerstats}' (SoccerStats)")
                        print(f"      → Squadre disponibili in {league['name']}: {', '.join(db_names[:5])}...")
                    else:
                        print(f"   ❌ NO MATCH: '{team_name_soccerstats}' (SoccerStats) - Campionato non trovato nel DB")
                    
                    league_unmatched += 1
                    total_unmatched += 1
                    unmatched_list.append({
                        "league": league['name'],
                        "soccerstats_name": team_name_soccerstats
                    })
            
            print(f"\n   📈 Statistiche {league['name']}: {league_matched} matched, {league_unmatched} unmatched")
            
        except Exception as e:
            print(f"   ⚠️ Errore: {e}")
    
    # RIEPILOGO FINALE
    print(f"\n{'='*80}")
    print(f"📊 RIEPILOGO FINALE")
    print(f"{'='*80}")
    print(f"✅ Totale MATCHED: {total_matched}")
    print(f"❌ Totale UNMATCHED: {total_unmatched}")
    
    if unmatched_list:
        print(f"\n{'='*80}")
        print(f"📋 LISTA SQUADRE SENZA MATCH (da aggiungere agli alias)")
        print(f"{'='*80}")
        
        for item in unmatched_list:
            # Trova la squadra più probabile nel DB
            possible = teams_collection.find_one(
                {"league": item['league']},
                sort=[("name", 1)]
            )
            if possible:
                print(f"\nCampionato: {item['league']}")
                print(f"   SoccerStats: '{item['soccerstats_name']}'")
                print(f"   → Aggiungi a quale squadra del DB? (verifica manualmente)")
            else:
                print(f"\n⚠️ {item['league']}: '{item['soccerstats_name']}' - Campionato vuoto nel DB!")

if __name__ == "__main__":
    analyze_matching()