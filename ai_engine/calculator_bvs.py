import pymongo
import os
from dotenv import load_dotenv

# 1. CONFIGURAZIONE
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '..', '.env')
load_dotenv(env_path)

MONGO_URI = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI')
client = pymongo.MongoClient(MONGO_URI)
db = client.get_database()
fixtures_collection = db['fixtures']
matches_collection = db['matches_history']

def get_bvs_score(home_team, away_team):
    """
    Calcola la Potenza BVS (Max 12 punti) secondo il metodo di Roger Fazio.
    
    LOGICA:
    - Picchetto Tecnico -> Genera Quote Teoriche (B, V, S).
    - Quote Reali (OddsMath) -> Genera Quote Reali (B, V, S).
    
    REGOLE:
    1. BVS PURO: Base e Variante coincidono -> 12 Punti alla Favorita (Base).
    2. SEMI BVS: Solo Base coincide -> 6 Punti alla Favorita (Base).
    3. NON BVS: Base non coincide (o Base è X) -> 6 Punti alla Sfavorita (Sorpresa).
    """

    print(f"\n📊 --- ANALISI BVS: {home_team} vs {away_team} ---")

    # --- 1. CALCOLO PICCHETTO TECNICO (STATS) ---
    def get_stats(team, side):
        query = {"homeTeam": team} if side == "home" else {"awayTeam": team}
        matches = list(matches_collection.find(query))
        played = len(matches)
        if played == 0: return 0, 0, 0, 0
        
        wins = 0; draws = 0; losses = 0
        for m in matches:
            res = m['result']
            if res == 'H': res = '1'
            if res == 'A': res = '2'
            if res == 'D': res = 'X'
            
            if side == "home":
                if res == '1': wins += 1
                elif res == 'X': draws += 1
                else: losses += 1
            else: 
                if res == '2': wins += 1
                elif res == 'X': draws += 1
                else: losses += 1
        return played, wins, draws, losses

    h_played, h_wins, h_draws, h_losses = get_stats(home_team, "home")
    a_played, a_wins, a_draws, a_losses = get_stats(away_team, "away")
    
    denom = h_played + a_played
    if denom < 5:
        print(f"   ⚠️ Dati insufficienti ({denom} partite). BVS Neutro.")
        return 0, 0

    # Probabilità
    prob_1 = (h_wins + a_losses) / denom
    prob_X = (h_draws + a_draws) / denom
    prob_2 = (h_losses + a_wins) / denom
    
    # Quote Teoriche (Picchetto)
    qt_1 = 1/prob_1 if prob_1 > 0.001 else 99.0
    qt_X = 1/prob_X if prob_X > 0.001 else 99.0
    qt_2 = 1/prob_2 if prob_2 > 0.001 else 99.0

    # Definizione Ordine Teorico (B-V-S)
    # Ordina per quota crescente (La più bassa è la Base)
    ordine_teorico = sorted([(qt_1, '1'), (qt_X, 'X'), (qt_2, '2')], key=lambda x: x[0])
    base_teorica = ordine_teorico[0][1]
    variante_teorica = ordine_teorico[1][1]
    sorpresa_teorica = ordine_teorico[2][1] # La quota più alta

    print(f"   [PICCHETTO] 1:{qt_1:.2f} X:{qt_X:.2f} 2:{qt_2:.2f}")
    print(f"   Ord. Teorico: Base={base_teorica} > Var={variante_teorica} > Sorp={sorpresa_teorica}")

    # --- 2. RECUPERO QUOTE REALI (BOOKMAKER) ---
    query = {"homeTeam": home_team, "awayTeam": away_team, "status": {"$ne": "Finished"}}
    fixture = fixtures_collection.find_one(query)
    
    if not fixture or "odds" not in fixture:
        print(f"   ❌ Quote Reali ASSENTI nel DB. Impossibile calcolare BVS.")
        return 0, 0 # Nessun punteggio senza confronto

    odds = fixture["odds"]
    qr_1 = float(odds.get("1", 99.0))
    qr_X = float(odds.get("X", 99.0))
    qr_2 = float(odds.get("2", 99.0))

    # Definizione Ordine Reale (B-V-S)
    ordine_reale = sorted([(qr_1, '1'), (qr_X, 'X'), (qr_2, '2')], key=lambda x: x[0])
    base_reale = ordine_reale[0][1]
    variante_reale = ordine_reale[1][1]
    
    print(f"   [BOOKMAKER] 1:{qr_1:.2f} X:{qr_X:.2f} 2:{qr_2:.2f}")
    print(f"   Ord. Reale:   Base={base_reale} > Var={variante_reale} ...")

    # --- 3. LOGICA PUNTI ---
    punti_casa = 0
    punti_ospite = 0
    
    # Caso Speciale: Se la Base è X, è sempre NON-BVS (Regola prudenza)
    if base_teorica == 'X' or base_reale == 'X':
        print("   ⚠️ BASE = X (Pareggio Favorito). Declassato a NON-BVS.")
        is_bvs = False
        is_semi_bvs = False
        is_non_bvs = True
    else:
        # Check congruenza
        if base_teorica == base_reale:
            if variante_teorica == variante_reale:
                is_bvs = True
                is_semi_bvs = False
                is_non_bvs = False
            else:
                is_bvs = False
                is_semi_bvs = True
                is_non_bvs = False
        else:
            is_bvs = False
            is_semi_bvs = False
            is_non_bvs = True

    # Assegnazione Punti
    if is_bvs:
        print("   ✅ BVS PURO! (12 Punti alla Favorita)")
        if base_teorica == '1': punti_casa = 12
        elif base_teorica == '2': punti_ospite = 12
        
    elif is_semi_bvs:
        print("   ⚠️ SEMI-BVS (6 Punti alla Favorita)")
        if base_teorica == '1': punti_casa = 6
        elif base_teorica == '2': punti_ospite = 6
        
    elif is_non_bvs:
        print("   🚫 NON-BVS (6 Punti alla Sfavorita/Sorpresa)")
        # Diamo i punti alla squadra considerata SORPRESA dal Picchetto (la più scarsa sulla carta)
        # O meglio: alla squadra OPPOSTA alla Base Teorica (se base era 1, punti al 2)
        
        squadra_target = None
        if base_teorica == '1': squadra_target = '2'
        elif base_teorica == '2': squadra_target = '1'
        # Se base era X (raro qui), diamo punti a chi ha quota più alta
        elif base_teorica == 'X': squadra_target = sorpresa_teorica
        
        if squadra_target == '1': punti_casa = 6
        elif squadra_target == '2': punti_ospite = 6
        elif squadra_target == 'X': pass # Nessuno prende punti se la sorpresa è X

    print(f"   ⚡ RISULTATO PUNTI BVS: Casa {punti_casa} - Ospite {punti_ospite}")
    return punti_casa, punti_ospite

# TEST
if __name__ == "__main__":
    # Esempio di test (sostituisci con squadre che hanno quote nel DB)
    # Udinese vs Bologna l'abbiamo vista nel log
    get_bvs_score("Juventus", "Cagliari")
