import sys
import os
from datetime import datetime

# --- CONFIGURAZIONE PATH ---
# Assicura che trovi config.py
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

try:
    from config import db
except ImportError:
    print("❌ Errore: config.py non trovato.")
    sys.exit(1)

print(f"🔌 Connesso al DB: {db.name}")

# Cache per simulare la velocità dello script di produzione
ALL_ROUNDS_CACHE = list(db.h2h_by_round.find({}).sort('last_updated', -1))

def debug_lucifero(team_name):
    print(f"\n🔍 ANALISI LUCIFERO PER: {team_name.upper()}")
    print("-" * 60)
    
    team_matches = []
    
    # 1. Trova le ultime 6 partite REALI (Stessa logica dello script automatico)
    for round_doc in ALL_ROUNDS_CACHE:
        for m in round_doc.get('matches', []):
            if m.get('status') == 'Finished' and ':' in m.get('real_score', ''):
                if m.get('home') == team_name or m.get('away') == team_name:
                    team_matches.append(m)
                    if len(team_matches) >= 6: break
        if len(team_matches) >= 6: break
    
    if not team_matches:
        print("❌ Nessuna partita trovata per questa squadra.")
        return

    # 2. Calcolo Punteggio con stampa dettagli
    weights = [6, 5, 4, 3, 2, 1] # Pesi decrescenti
    total_score = 0
    max_score = 0
    limit = min(len(team_matches), 6)
    
    print(f"{'DATA':<12} | {'AVVERSARIO':<15} | {'RIS':<5} | {'ESITO':<5} | {'PESO':<4} | {'PUNTI'}")
    print("-" * 60)

    for i in range(limit):
        m = team_matches[i]
        w = weights[i]
        max_score += (3 * w) # Max punti possibili (Vittoria * peso)
        
        try:
            score = m['real_score'].split(':')
            gh = int(score[0])
            ga = int(score[1])
            is_home = (m['home'] == team_name)
            opponent = m['away'] if is_home else m['home']
            
            punti = 0
            esito_str = "S"
            
            if gh == ga: 
                punti = 1
                esito_str = "P"
            elif (is_home and gh > ga) or (not is_home and ga > gh): 
                punti = 3
                esito_str = "V"
            
            punti_pesati = punti * w
            total_score += punti_pesati
            
            # Formattazione data (se presente o stringa)
            date_show = m.get('match_time', 'N/D')
            if 'date_obj' in m and isinstance(m['date_obj'], datetime):
                date_show = m['date_obj'].strftime('%d/%m')

            print(f"{date_show:<12} | {opponent:<15} | {m['real_score']:<5} | {esito_str:<5} | x{w:<3} | {punti_pesati} ({punti}*{w})")
            
        except Exception as e:
            print(f"Errore riga: {e}")
            continue

    print("-" * 60)
    
    if max_score == 0:
        print("Calcolo impossibile (Max Score 0)")
        return

    lucifero_value = (total_score / max_score) * 25.0
    final_score = round(lucifero_value, 2)
    
    print(f"📊 TOTALE PUNTI OTTENUTI: {total_score}")
    print(f"🏆 MASSIMO POSSIBILE:    {max_score}")
    print(f"🔥 PUNTEGGIO LUCIFERO:   {final_score} / 25.00")
    print("=" * 60)

if __name__ == "__main__":
    while True:
        nome = input("\nInserisci nome squadra (o 'q' per uscire): ").strip()
        if nome.lower() == 'q': break
        debug_lucifero(nome)