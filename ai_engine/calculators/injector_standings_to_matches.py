import os
import sys
import re
from datetime import datetime
import dateutil.parser

# --- FIX PERCORSI UNIVERSALE ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db

# --- CONFIGURAZIONE ---
standings_col = db['classifiche']
matches_col = db['h2h_by_round']

def get_round_number(doc):
    name = doc.get('_id', '') or doc.get('round_name', '')
    match = re.search(r'(\d+)', str(name))
    return int(match.group(1)) if match else 999

def find_target_rounds(league_docs):
    if not league_docs: return []
    sorted_docs = sorted(league_docs, key=get_round_number)
    now = datetime.now()
    closest_index = -1
    min_diff = float('inf')
    for i, doc in enumerate(sorted_docs):
        dates = []
        for m in doc.get('matches', []):
            d_raw = m.get('date_obj') or m.get('date')
            try:
                if d_raw:
                    d = d_raw if isinstance(d_raw, datetime) else dateutil.parser.parse(d_raw)
                    dates.append(d.replace(tzinfo=None))
            except: pass
        if dates:
            avg_date = sum([d.timestamp() for d in dates]) / len(dates)
            diff = abs(now.timestamp() - avg_date)
            if diff < min_diff: min_diff = diff; closest_index = i
    if closest_index == -1: return []
    start_idx = max(0, closest_index - 1)
    end_idx = min(len(sorted_docs), closest_index + 2)
    return sorted_docs[start_idx:end_idx]

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

    # 2. AGGIORNIAMO LE PARTITE (solo round mirati: prec/attuale/succ)
    print("🤖 Selezione round mirati (Prec/Attuale/Succ)...")
    light_docs = list(matches_col.find({}, {"_id": 1, "league": 1, "matches.date": 1, "matches.date_obj": 1}))
    by_league = {}
    for doc in light_docs:
        lg = doc.get("league")
        if lg:
            by_league.setdefault(lg, []).append(doc)
    target_ids = []
    for lg_name, lg_docs in by_league.items():
        target = find_target_rounds(lg_docs)
        target_ids.extend([d["_id"] for d in target])
    all_target_rounds = list(matches_col.find({"_id": {"$in": target_ids}}))
    print(f"   📋 {len(by_league)} campionati, {len(light_docs)} docs → {len(all_target_rounds)} giornate mirate")

    updated_rounds = 0
    total_matches_updated = 0

    for round_doc in all_target_rounds:
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