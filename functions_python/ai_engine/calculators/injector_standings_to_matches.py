import os
import sys
from config import db

# --- CONFIGURAZIONE ---
standings_col = db['classifiche']
matches_col = db['h2h_by_round']

def inject_standings_final():
    print("💉 AVVIO INIEZIONE DIRETTA (Metodo: Transfermarkt ID -> Punti/Rank)")
    
    # 1. CREIAMO LA MAPPA DEI PUNTI (Dalle classifiche)
    tm_id_to_stats = {}
    
    print("📚 Caricamento dati dalle classifiche...")
    standings_cursor = standings_col.find({})
    for doc in standings_cursor:
        table = doc.get('table', [])
        for row in table:
            tm_id = row.get('transfermarkt_id')
            if tm_id is not None:
                tm_id_to_stats[str(tm_id)] = {
                    'rank': row.get('rank'),
                    'points': row.get('points')
                }
                
    print(f"📊 Mappa Verità pronta: {len(tm_id_to_stats)} squadre caricate.")

    # 2. AGGIORNIAMO LE PARTITE (In h2h_by_round)
    rounds_cursor = matches_col.find({})
    updated_rounds = 0
    total_matches_updated = 0
    
    for round_doc in rounds_cursor:
        round_id = round_doc.get('_id')
        matches = round_doc.get('matches', [])
        round_modified = False
        
        for match in matches:
            h2h = match.get('h2h_data', {})
            if h2h is None: h2h = {}
            
            match_modified = False
            
            # --- AGGIORNAMENTO CASA ---
            home_tm_id = str(match.get('home_tm_id'))
            if home_tm_id in tm_id_to_stats:
                stats = tm_id_to_stats[home_tm_id]
                h2h['home_rank'] = stats['rank']
                h2h['home_points'] = stats['points']
                match_modified = True
                
            # --- AGGIORNAMENTO OSPITE ---
            away_tm_id = str(match.get('away_tm_id'))
            if away_tm_id in tm_id_to_stats:
                stats = tm_id_to_stats[away_tm_id] # <--- CORRETTO QUI
                h2h['away_rank'] = stats['rank']
                h2h['away_points'] = stats['points']
                match_modified = True
                
            if match_modified:
                match['h2h_data'] = h2h
                round_modified = True
                total_matches_updated += 1

        if round_modified:
            matches_col.update_one(
                {'_id': round_id}, 
                {'$set': {'matches': matches}}
            )
            updated_rounds += 1
            print(f" ✅ Aggiornato Round: {round_id}")

    print("--------------------------------------------------")
    print(f"🏁 COMPLETATO.")
    print(f" 📂 Giornate salvate su DB: {updated_rounds}")
    print(f" ⚽ Partite sincronizzate: {total_matches_updated}")

if __name__ == "__main__":
    inject_standings_final()