import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

# CONFIGURAZIONE DB
teams_collection = db['teams']
fixtures_collection = db['fixtures']

def get_stats_from_ranking(team_name):
    """Recupera statistiche (Casa, Fuori, Totali) dal ranking."""
    team = teams_collection.find_one({
        "$or": [{"name": team_name}, {"aliases": team_name}, {"aliases.soccerstats": team_name}]
    })
    if not team or "ranking" not in team: return None
    r = team["ranking"]
    h = r.get("homeStats", {})
    a = r.get("awayStats", {})
    
    t_played = h.get("played", 0) + a.get("played", 0)
    t_wins = h.get("wins", 0) + a.get("wins", 0)
    t_draws = h.get("draws", 0) + a.get("draws", 0)
    t_losses = h.get("losses", 0) + a.get("losses", 0)

    return {
        "home": {"P": h.get("played", 0), "W": h.get("wins", 0), "D": h.get("draws", 0), "L": h.get("losses", 0)},
        "away": {"P": a.get("played", 0), "W": a.get("wins", 0), "D": a.get("draws", 0), "L": a.get("losses", 0)},
        "total": {"P": t_played, "W": t_wins, "D": t_draws, "L": t_losses}
    }

def get_bvs_score(home_team, away_team):
    """
    Calcola BVS con logica "MEDIA" (Compromesso tra Base e Severo):
    - PURO:     Favorita +7
    - SEMI:     Favorita 0, Sfavorita +2
    - NON-BVS:  Favorita -6, Sfavorita +6
    """
    print(f"\n📊 --- ANALISI BVS (Media): {home_team} vs {away_team} ---")

    # 1. RECUPERO DATI
    stats_h = get_stats_from_ranking(home_team)
    stats_a = get_stats_from_ranking(away_team)

    if not stats_h or not stats_a:
        print("   ⚠️ Dati classifica mancanti. BVS Neutro.")
        return 0, 0

    # 2. CALCOLO MISTO (Campo + Totale)
    denom_campo = stats_h["home"]["P"] + stats_a["away"]["P"]
    denom_tot = stats_h["total"]["P"] + stats_a["total"]["P"]
    
    if denom_campo < 1 or denom_tot < 1: return 0, 0

    p1_c = (stats_h["home"]["W"] + stats_a["away"]["L"]) / denom_campo
    pX_c = (stats_h["home"]["D"] + stats_a["away"]["D"]) / denom_campo
    p2_c = (stats_h["home"]["L"] + stats_a["away"]["W"]) / denom_campo

    p1_t = (stats_h["total"]["W"] + stats_a["total"]["L"]) / denom_tot
    pX_t = (stats_h["total"]["D"] + stats_a["total"]["D"]) / denom_tot
    p2_t = (stats_h["total"]["L"] + stats_a["total"]["W"]) / denom_tot

    p1 = (p1_c + p1_t) / 2
    pX = (pX_c + pX_t) / 2
    p2 = (p2_c + p2_t) / 2

    qt_1 = 1/p1 if p1 > 0.001 else 99.0
    qt_X = 1/pX if pX > 0.001 else 99.0
    qt_2 = 1/p2 if p2 > 0.001 else 99.0

    ord_t = sorted([(qt_1, '1'), (qt_X, 'X'), (qt_2, '2')], key=lambda x: x[0])
    base_t = ord_t[0][1]
    var_t = ord_t[1][1]

    print(f"   [PICCHETTO] 1:{qt_1:.2f} X:{qt_X:.2f} 2:{qt_2:.2f} (Base: {base_t})")

    # 3. QUOTE REALI
    query = {"homeTeam": home_team, "awayTeam": away_team, "status": {"$ne": "Finished"}}
    fixture = fixtures_collection.find_one(query)
    
    if not fixture or "odds" not in fixture:
        print(f"   ❌ Quote Reali ASSENTI. Skip.")
        return 0, 0

    odds = fixture["odds"]
    qr_1 = float(odds.get("1", 99.0))
    qr_X = float(odds.get("X", 99.0))
    qr_2 = float(odds.get("2", 99.0))

    ord_r = sorted([(qr_1, '1'), (qr_X, 'X'), (qr_2, '2')], key=lambda x: x[0])
    base_r = ord_r[0][1]
    var_r = ord_r[1][1]
    
    print(f"   [BOOKMAKER] 1:{qr_1:.2f} X:{qr_X:.2f} 2:{qr_2:.2f} (Base: {base_r})")

    # 4. DETERMINAZIONE STATO BVS
    state = "NON_BVS"
    if base_t != 'X' and base_r != 'X':
        if base_t == base_r:
            if var_t == var_r:
                state = "PURO"
            else:
                state = "SEMI"
    
    # 5. ASSEGNAZIONE PUNTI (LOGICA MEDIA)
    punti_h = 0
    punti_a = 0
    favorita_sign = base_t 
    
    if state == "PURO":
        print("   ✅ BVS PURO (Favorita +7)")
        if favorita_sign == '1': punti_h += 7
        elif favorita_sign == '2': punti_a += 7
        
    elif state == "SEMI":
        print("   ⚠️ SEMI-BVS (Favorita 0, Sfavorita +2)")
        # La sfavorita prende +2
        if favorita_sign == '1': punti_a += 2
        elif favorita_sign == '2': punti_h += 2
            
    else: # NON_BVS
        print("   🚫 NON-BVS (Favorita -6, Sfavorita +6)")
        if favorita_sign == 'X':
            if qt_1 < qt_2: favorita_sign = '1'
            else: favorita_sign = '2'
            
        if favorita_sign == '1':
            punti_h -= 6
            punti_a += 6
        elif favorita_sign == '2':
            punti_a -= 6
            punti_h += 6

    print(f"   ⚡ BONUS/MALUS BVS: Casa {punti_h} | Ospite {punti_a}")
    return punti_h, punti_a

if __name__ == "__main__":
    get_bvs_score("Trento", "Cittadella")
