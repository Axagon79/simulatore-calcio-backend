import os
import sys
from config import db

# --- CONFIGURAZIONE ---
standings_col = db['classifiche']
matches_col = db['h2h_by_round']
teams_col = db['teams']

def normalize(name):
    """Pulisce il nome per facilitare il matching"""
    if not name: return ""
    return name.lower().strip()

def inject_standings_final():
    print("💉 AVVIO INIEZIONE (Metodo: Nome -> ID -> Punti)")
    
    # 1. CREIAMO IL DIZIONARIO DI TRADUZIONE (Nome -> ID)
    # Carichiamo tutta la collezione 'teams' in memoria
    name_to_id_map = {}
    
    print("📚 Caricamento dizionario nomi...")
    teams_cursor = teams_col.find({})
    for team in teams_cursor:
        t_id = team.get('team_id') or team.get('id') or team.get('_id')
        if not t_id: continue
        
        # Mappiamo il nome ufficiale
        if team.get('name'):
            name_to_id_map[normalize(team['name'])] = str(t_id)
            
        # Mappiamo tutti gli alias
        aliases = team.get('aliases', [])
        # Aggiungiamo anche l'alias transfermarkt se esiste
        if team.get('aliases_transfermarkt'):
            aliases.append(team.get('aliases_transfermarkt'))
            
        for alias in aliases:
            if alias and isinstance(alias, str):
                name_to_id_map[normalize(alias)] = str(t_id)

    # 2. CREIAMO LA MAPPA DEI PUNTI (ID -> Punti)
    # Carichiamo le classifiche usando l'ID come chiave
    id_to_stats_map = {}
    
    standings_cursor = standings_col.find({})
    for doc in standings_cursor:
        for row in doc['table']:
            t_id = row.get('team_id')
            if t_id:
                id_to_stats_map[str(t_id)] = {
                    'rank': row['rank'],
                    'points': row['points']
                }
                
    print(f"📊 Mappa pronta: {len(name_to_id_map)} nomi conosciuti, {len(id_to_stats_map)} classifiche caricate.")

    # 3. AGGIORNIAMO LE PARTITE
    rounds_cursor = matches_col.find({})
    updated_rounds = 0
    matches_count = 0
    
    for round_doc in rounds_cursor:
        matches = round_doc.get('matches', [])
        modified = False
        
        for match in matches:
            current_h2h = match.get('h2h_data', {})
            if current_h2h is None: current_h2h = {}
            
            # --- CERCA CASA (Usando il nome per trovare l'ID) ---
            home_name = match.get('home')
            home_id = name_to_id_map.get(normalize(home_name)) 
            
            if home_id and home_id in id_to_stats_map:
                stats = id_to_stats_map[home_id]
                current_h2h['home_rank'] = stats['rank']
                current_h2h['home_points'] = stats['points']
                modified = True
                
            # --- CERCA OSPITE (Usando il nome per trovare l'ID) ---
            away_name = match.get('away')
            away_id = name_to_id_map.get(normalize(away_name)) 
            
            if away_id and away_id in id_to_stats_map:
                stats = id_to_stats_map[away_id]
                current_h2h['away_rank'] = stats['rank']
                current_h2h['away_points'] = stats['points']
                modified = True
                
            match['h2h_data'] = current_h2h
            if modified: matches_count += 1

        if modified:
            matches_col.update_one({'_id': round_doc['_id']}, {'$set': {'matches': matches}})
            updated_rounds += 1

    print(f"🏁 COMPLETATO.")
    print(f"   Giornate aggiornate: {updated_rounds}")
    print(f"   Partite aggiornate: {matches_count}")

if __name__ == "__main__":
    inject_standings_final()