# Script per arricchire h2h_by_round con gli ID Transfermarkt dalle squadre
import os
import sys
from datetime import datetime
from pymongo import MongoClient

# --- CONFIGURAZIONE PERCORSI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_dir = os.path.dirname(os.path.dirname(current_dir))
project_root = os.path.dirname(ai_engine_dir)

if ai_engine_dir not in sys.path:
    sys.path.insert(0, ai_engine_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from config import db
    print(f"✅ DB Connesso: {db.name}")
except ImportError:
    print("❌ Errore Import Config")
    sys.exit(1)

# --- CONFIGURAZIONI ---
H2H_COLLECTION = "h2h_by_round"
TEAMS_COLLECTION = "teams"

def find_team_in_db(team_name, league=None):
    """
    Cerca squadra con filtro per lega
    """
    base_filter = {}
    if league:
        base_filter["league"] = league
    
    # Cerca nel nome
    query = {**base_filter, "name": team_name}
    team = db[TEAMS_COLLECTION].find_one(query)
    if team and "transfermarkt_id" in team:
        return team["transfermarkt_id"]
    
    # Cerca negli aliases
    query = {**base_filter, "aliases": team_name}
    team = db[TEAMS_COLLECTION].find_one(query)
    if team and "transfermarkt_id" in team:
        return team["transfermarkt_id"]
    
    # Cerca in aliases_transfermarkt
    query = {**base_filter, "aliases_transfermarkt": team_name}
    team = db[TEAMS_COLLECTION].find_one(query)
    if team and "transfermarkt_id" in team:
        return team["transfermarkt_id"]
    
    return None


def enrich_h2h_with_ids():
    """
    Arricchisce h2h_by_round con gli ID Transfermarkt per ogni squadra.
    Salva dopo ogni giornata processata.
    """
    
    h2h_col = db[H2H_COLLECTION]
    not_found_teams = set()  # Per il report finale
    total_matches_processed = 0
    total_matches_enriched = 0
    
    print("\n" + "="*70)
    print("🚀 INIZIO ARRICCHIMENTO H2H CON TRANSFERMARKT IDs")
    print("="*70)
    
    # Ottieni tutti i documenti (giornate)
    all_rounds = list(h2h_col.find())
    total_rounds = len(all_rounds)
    
    for round_idx, round_doc in enumerate(all_rounds, 1):
        round_id = round_doc.get("_id", "Unknown")
        league = round_doc.get("league", "Unknown")
        matches = round_doc.get("matches", [])
        
        print(f"\n📋 [{round_idx}/{total_rounds}] Elaborazione: {league} - {round_id}")
        
        modified = False
        enriched_count = 0
        
        # Processa ogni partita della giornata
        for match_idx, match in enumerate(matches):
            home_team = match.get("home", "")
            away_team = match.get("away", "")
            
            total_matches_processed += 1
            
            # Ricerca ID per squadra CASA
            home_id = find_team_in_db(home_team, league=league)
            if home_id:
                old_id = match.get("home_tm_id")
                if "home_tm_id" not in match or match["home_tm_id"] != home_id:
                    match["home_tm_id"] = home_id
                    modified = True
                    enriched_count += 1
                    if old_id and old_id != home_id:
                        print(f"   🔄 {home_team}: {old_id} → {home_id}")
                    else:
                        print(f"   ➕ {home_team}: aggiunto ID {home_id}")
            else:
                not_found_teams.add(home_team)

            # Ricerca ID per squadra TRASFERTA
            away_id = find_team_in_db(away_team, league=league)
            if away_id:
                old_id = match.get("away_tm_id")
                if "away_tm_id" not in match or match["away_tm_id"] != away_id:
                    match["away_tm_id"] = away_id
                    modified = True
                    enriched_count += 1
                    if old_id and old_id != away_id:
                        print(f"   🔄 {away_team}: {old_id} → {away_id}")
                    else:
                        print(f"   ➕ {away_team}: aggiunto ID {away_id}")
            else:
                not_found_teams.add(away_team)

        
        # Salva il documento se modificato
        if modified:
            h2h_col.update_one(
                {"_id": round_id},
                {
                    "$set": {
                        "matches": matches,
                        "last_updated": datetime.now()
                    }
                }
            )
            total_matches_enriched += enriched_count
            print(f"   ✅ Salvato: {enriched_count} partite arricchite in questa giornata")
        else:
            print(f"   ⚪ Nessuna modifica necessaria")
    
    # --- REPORT FINALE ---
    print("\n" + "="*70)
    print("✅ ELABORAZIONE COMPLETATA!")
    print("="*70)
    print(f"📊 Statistiche Finali:")
    print(f"   • Partite processate: {total_matches_processed}")
    print(f"   • Partite arricchite con ID: {total_matches_enriched}")
    print(f"   • Giornate elaborate: {total_rounds}")
    
    if not_found_teams:
        print(f"\n⚠️  SQUADRE NON TROVATE ({len(not_found_teams)}):")
        for team in sorted(not_found_teams):
            print(f"   • {team}")
    else:
        print(f"\n🎉 TUTTE LE SQUADRE TROVATE! Nessuna squadra mancante.")
    
    print("="*70)

if __name__ == "__main__":
    enrich_h2h_with_ids()