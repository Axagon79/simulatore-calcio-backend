import os
import sys
from datetime import datetime
from config import db 

# --- CONFIGURAZIONE COLLEZIONI ---
standings_col = db['classifiche']
matches_col = db['h2h_by_round']

def validate_data_sync_v3():
    print(f"🔍 AVVIO VALIDATOR V3 (Fix Percorso ID) - {datetime.now().strftime('%H:%M:%S')}")
    print("--------------------------------------------------")

    # 1. CARICAMENTO DELLA "VERITÀ" (Dalle classifiche)
    truth_map = {}
    standings_cursor = standings_col.find({})
    
    for doc in standings_cursor:
        table = doc.get('table', [])
        for row in table:
            tm_id = row.get('transfermarkt_id')
            if tm_id is None: continue
            
            truth_map[str(tm_id)] = {
                'points': row.get('points'),
                'rank': row.get('rank'),
                'team_name': row.get('team')
            }

    print(f"📊 Verità caricata: {len(truth_map)} squadre mappate.")
    print("--------------------------------------------------")

    # 2. SCANSIONE DEI MATCH (Dalla collezione h2h_by_round)
    rounds_cursor = matches_col.find({})
    total_errors = 0
    matches_checked = 0

    for round_doc in rounds_cursor:
        round_id = round_doc.get('_id')
        matches = round_doc.get('matches', [])
        
        for m in matches:
            matches_checked += 1
            h2h = m.get('h2h_data', {})
            if not h2h: continue

            # --- CORREZIONE PERCORSO ---
            # Gli ID sono fuori da h2h_data, Rank/Points sono dentro
            for role in ['home', 'away']:
                # Cerchiamo l'ID direttamente nell'oggetto match (m)
                team_id_in_match = str(m.get(f'{role}_tm_id'))
                team_name = m.get(role)
                
                if team_id_in_match in truth_map:
                    real = truth_map[team_id_in_match]
                    match_p = h2h.get(f'{role}_points')
                    match_r = h2h.get(f'{role}_rank')
                    
                    # Verifica discrepanze (convertiamo in stringa per sicurezza nel confronto)
                    if str(match_p) != str(real['points']) or str(match_r) != str(real['rank']):
                        total_errors += 1
                        print(f"❌ ERRORE [{round_id}] - {team_name} (ID: {team_id_in_match})")
                        print(f"   -> Nel Match: {match_p}pt, Pos. {match_r}°")
                        print(f"   -> Reale:     {real['points']}pt, Pos. {real['rank']}°")
                else:
                    # Debug per capire se l'ID manca o è formattato male
                    if team_id_in_match not in ["None", "null", ""]:
                        # Se vuoi vedere quali ID non hanno corrispondenza in classifica, scommenta sotto:
                        # print(f"⚠️ ID {team_id_in_match} ({team_name}) non trovato in classifiche.")
                        pass

    print("--------------------------------------------------")
    print(f"🏁 CONCLUSIONE: {matches_checked} partite analizzate.")
    if total_errors == 0:
        print("✅ Nessuna discrepanza trovata. I dati sono ora correttamente verificati.")
    else:
        print(f"🚨 TROVATI {total_errors} ERRORI DI SINCRONIZZAZIONE.")

if __name__ == "__main__":
    validate_data_sync_v3()