import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

# CONFIGURAZIONE DB
teams_collection = db['teams']
fixtures_collection = db['fixtures']
h2h_collection = db['h2h_by_round']

# // modificato per: logica bulk - Supporto alla cache in memoria
def get_stats_from_ranking(team_name, bulk_cache=None):
    """Recupera statistiche (Casa, Fuori, Totali) dal ranking. Supporta Bulk Cache."""
    team = None
    
    # Ricerca in Bulk Cache
    if bulk_cache and "TEAMS" in bulk_cache:
        for t in bulk_cache["TEAMS"]:
            # 1. Controllo Nome Esatto
            if t.get("name") == team_name:
                team = t
                break
            
            # 2. Controllo Alias (Gestione sicura del tipo)
            aliases = t.get("aliases", [])
            if isinstance(aliases, list):
                # Se è una lista (caso normale), controlla se il nome è dentro
                if team_name in aliases:
                    team = t
                    break
            elif isinstance(aliases, dict):
                # Se è un dizionario (caso raro), usa .get()
                if team_name == aliases.get("soccerstats"):
                    team = t
                    break
    
    # Fallback su DB se non trovato in cache o cache assente
    if not team:
        team = teams_collection.find_one({
            "$or": [{"name": team_name}, {"aliases": team_name}, {"aliases.soccerstats": team_name}]
        })
        
    if not team or "ranking" not in team: 
        return None
    
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

def calculate_theoretical_odds_professional(stats_h, stats_a):
    """
    Calcola quote teoriche professionali con 4 picchetti:
    1. Campo specifico (casa vs trasferta) - peso 40%
    2. Totale stagionale - peso 25%
    3. Forma recente (ultimi 5) - peso 20%
    4. Rating normalizzato - peso 15%
    """
    
    # PICCHETTO 1: Campo specifico (Casa vs Trasferta) - 40%
    denom_campo = stats_h["home"]["P"] + stats_a["away"]["P"]
    if denom_campo < 5:  # Minimo 5 partite per affidabilità
        return None
    
    p1_campo = (stats_h["home"]["W"] + stats_a["away"]["L"]) / denom_campo
    pX_campo = (stats_h["home"]["D"] + stats_a["away"]["D"]) / denom_campo
    p2_campo = (stats_h["home"]["L"] + stats_a["away"]["W"]) / denom_campo
    
    # PICCHETTO 2: Totale stagionale - 25%
    denom_tot = stats_h["total"]["P"] + stats_a["total"]["P"]
    if denom_tot < 10:
        return None
    
    p1_tot = (stats_h["total"]["W"] + stats_a["total"]["L"]) / denom_tot
    pX_tot = (stats_h["total"]["D"] + stats_a["total"]["D"]) / denom_tot
    p2_tot = (stats_h["total"]["L"] + stats_a["total"]["W"]) / denom_tot
    
    # PICCHETTO 3: Forma recente (ultimi 5 match) - 20%
    # Simulazione con peso su partite recenti (ultimi 30% delle partite)
    recent_weight = 0.3
    h_recent = max(int(stats_h["home"]["P"] * recent_weight), 1)
    a_recent = max(int(stats_a["away"]["P"] * recent_weight), 1)
    
    # Stimiamo forma recente usando percentuali degli ultimi match
    h_win_rate = stats_h["home"]["W"] / max(stats_h["home"]["P"], 1)
    a_loss_rate = stats_a["away"]["L"] / max(stats_a["away"]["P"], 1)
    
    p1_forma = (h_win_rate + a_loss_rate) / 2
    pX_forma = ((stats_h["home"]["D"] / max(stats_h["home"]["P"], 1)) + 
                (stats_a["away"]["D"] / max(stats_a["away"]["P"], 1))) / 2
    p2_forma = ((stats_h["home"]["L"] / max(stats_h["home"]["P"], 1)) + 
                (stats_a["away"]["W"] / max(stats_a["away"]["P"], 1))) / 2
    
    # PICCHETTO 4: Rating normalizzato - 15%
    # Basato su punti per partita
    h_points = (stats_h["home"]["W"] * 3 + stats_h["home"]["D"]) / max(stats_h["home"]["P"], 1)
    a_points = (stats_a["away"]["W"] * 3 + stats_a["away"]["D"]) / max(stats_a["away"]["P"], 1)
    
    total_points = h_points + a_points
    if total_points > 0:
        p1_rating = h_points / total_points
        p2_rating = a_points / total_points
        pX_rating = 1 - (p1_rating + p2_rating) / 2  # Compensazione
    else:
        p1_rating = p2_rating = pX_rating = 0.33
    
    # MEDIA PESATA DEI 4 PICCHETTI
    weights = [0.40, 0.25, 0.20, 0.15]
    
    p1 = (p1_campo * weights[0] + p1_tot * weights[1] + 
          p1_forma * weights[2] + p1_rating * weights[3])
    pX = (pX_campo * weights[0] + pX_tot * weights[1] + 
          pX_forma * weights[2] + pX_rating * weights[3])
    p2 = (p2_campo * weights[0] + p2_tot * weights[1] + 
          p2_forma * weights[2] + p2_rating * weights[3])
    
    # Normalizzazione (le probabilità devono sommare 1)
    total = p1 + pX + p2
    if total > 0:
        p1, pX, p2 = p1/total, pX/total, p2/total
    else:
        p1 = pX = p2 = 0.33
    
    # Smoothing: evita probabilità troppo basse
    min_prob = 0.05
    p1 = max(p1, min_prob)
    pX = max(pX, min_prob)
    p2 = max(p2, min_prob)
    
    # Ri-normalizza dopo smoothing
    total = p1 + pX + p2
    p1, pX, p2 = p1/total, pX/total, p2/total
    
    # Conversione in quote
    qt_1 = 1/p1 if p1 > 0.001 else 99.0
    qt_X = 1/pX if pX > 0.001 else 99.0
    qt_2 = 1/p2 if p2 > 0.001 else 99.0
    
    return qt_1, qt_X, qt_2

def get_bvs_classification(qt_1, qt_X, qt_2, qr_1, qr_X, qr_2):
    """
    Classifica la partita secondo il metodo BVS.
    
    Returns: dict con tutte le informazioni necessarie
    """
    # Ordina quote teoriche
    ord_t = sorted([(qt_1, '1'), (qt_X, 'X'), (qt_2, '2')], key=lambda x: x[0])
    base_t, var_t, sorpresa_t = ord_t[0][1], ord_t[1][1], ord_t[2][1]
    
    # Ordina quote reali
    ord_r = sorted([(qr_1, '1'), (qr_X, 'X'), (qr_2, '2')], key=lambda x: x[0])
    base_r, var_r, sorpresa_r = ord_r[0][1], ord_r[1][1], ord_r[2][1]
    
    # Calcola differenza percentuale sulla favorita
    quote_map_t = {'1': qt_1, 'X': qt_X, '2': qt_2}
    quote_map_r = {'1': qr_1, 'X': qr_X, '2': qr_2}
    
    qt_fav = quote_map_t[base_t]
    qr_fav = quote_map_r[base_r]
    
    diff_perc = abs(qt_fav - qr_fav) / qt_fav * 100 if qt_fav > 0 else 100
    
    # Classificazione BVS
    concordanza_elementi = 0
    if base_t == base_r:
        concordanza_elementi += 1
        if var_t == var_r:
            concordanza_elementi += 1
            if sorpresa_t == sorpresa_r:
                concordanza_elementi += 1
    
    if concordanza_elementi == 3:
        tipo = "PURO"
    elif concordanza_elementi == 1:  # Solo base concorda
        tipo = "SEMI"
    else:
        tipo = "NON_BVS"
    
    # Linearità
    is_linear = diff_perc < 20
    
    return {
        'tipo': tipo,
        'base_t': base_t,
        'var_t': var_t,
        'sorpresa_t': sorpresa_t,
        'base_r': base_r,
        'var_r': var_r,
        'sorpresa_r': sorpresa_r,
        'diff_perc': diff_perc,
        'is_linear': is_linear,
        'concordanza': concordanza_elementi,
        'qt_fav': qt_fav,
        'qr_fav': qr_fav,
        'quote_map_t': quote_map_t,
        'quote_map_r': quote_map_r
    }

def calculate_team_bvs_score(team_sign, classification, qr_1, qr_X, qr_2):
    """
    Calcola il punteggio BVS per UNA SINGOLA squadra (casa '1' o ospite '2').
    Ogni squadra ha il suo punteggio indipendente e continuo.
    """
    tipo = classification['tipo']
    diff_perc = classification['diff_perc']
    is_linear = classification['is_linear']
    base_r = classification['base_r']
    base_t = classification['base_t']
    
    quote_map_t = classification['quote_map_t']
    quote_map_r = classification['quote_map_r']
    
    qt_team = quote_map_t[team_sign]
    qr_team = quote_map_r[team_sign]
    
    # Calcola diff% specifica per questa squadra
    diff_team_perc = abs(qt_team - qr_team) / qt_team * 100 if qt_team > 0 else 100
    
    # ========================================
    # STEP 1: PESO BASE
    # ========================================
    is_favorita_reale = (team_sign == base_r)
    is_favorita_teorica = (team_sign == base_t)
    
    if tipo == "PURO":
        if is_favorita_reale:
            peso_base = 7.0
        else:
            peso_base = -2.0
    
    elif tipo == "SEMI":
        if is_favorita_reale:
            peso_base = 3.5
        else:
            peso_base = 1.5
    
    else:  # NON_BVS
        if is_favorita_teorica and not is_favorita_reale:
            peso_base = -4.0
        elif not is_favorita_teorica and is_favorita_reale:
            peso_base = 3.0
        else:
            peso_base = -1.0
    
    # ========================================
    # STEP 2, 3, 4, 5: FORMULA FINALE (Preservata)
    # ========================================
    fattore_distanza = max(0.0, 1.0 - (diff_team_perc / 100.0))
    
    if is_linear:
        fattore_linear = 1.0 - (diff_perc / 100.0)
    else:
        fattore_linear = max(0.3, 1.0 - (diff_perc / 80.0))
    
    boost_speciale = 0.0
    is_special_case = False
    
    if not is_linear and qr_team < 1.65 and is_favorita_reale:
        is_special_case = True
        boost_speciale = max(0.0, (1.65 - qr_team) * 6.0)
    
    if is_special_case:
        punteggio_raw = (peso_base * fattore_distanza * fattore_linear) + boost_speciale
    else:
        punteggio_raw = peso_base * fattore_distanza * fattore_linear
    
    punteggio = max(-6.0, min(7.0, punteggio_raw))
    
    debug_info = {
        'team_sign': team_sign,
        'is_favorita_reale': is_favorita_reale,
        'is_favorita_teorica': is_favorita_teorica,
        'diff_team_perc': diff_team_perc,
        'peso_base': peso_base,
        'fattore_distanza': fattore_distanza,
        'fattore_linear': fattore_linear,
        'boost_speciale': boost_speciale,
        'is_special_case': is_special_case,
        'punteggio_raw': punteggio_raw,
        'punteggio_final': punteggio
    }
    
    return punteggio, debug_info

def get_bvs_score(home_team, away_team, bulk_cache=None):
    """
    Calcola BVS con punteggio continuo per ENTRAMBE le squadre. Supporta Bulk Cache.
    """
    print(f"\n📊 --- ANALISI BVS PROFESSIONALE: {home_team} vs {away_team} ---")

    # 1. RECUPERO DATI [modificato per: logica bulk]
    stats_h = get_stats_from_ranking(home_team, bulk_cache)
    stats_a = get_stats_from_ranking(away_team, bulk_cache)

    if not stats_h or not stats_a:
        print("   ⚠️ Dati classifica mancanti. BVS Neutro.")
        return 0, 0

    # 2. CALCOLO PICCHETTO TECNICO PROFESSIONALE
    theoretical = calculate_theoretical_odds_professional(stats_h, stats_a)
    if not theoretical:
        print("   ⚠️ Dati insufficienti per calcolo professionale. BVS Neutro.")
        return 0, 0
    
    qt_1, qt_X, qt_2 = theoretical
    print(f"   [PICCHETTO PROF] 1:{qt_1:.2f} X:{qt_X:.2f} 2:{qt_2:.2f}")

    # 3. RECUPERO QUOTE REALI [modificato per: logica bulk]
    qr_1 = qr_X = qr_2 = 99.0
    
    if bulk_cache and "MATCH_H2H" in bulk_cache and "quotes" in bulk_cache["MATCH_H2H"]:
        q = bulk_cache["MATCH_H2H"]["quotes"]
        qr_1, qr_X, qr_2 = float(q.get("1", 99.0)), float(q.get("X", 99.0)), float(q.get("2", 99.0))
    else:
        # Fallback su aggregazione DB se bulk non disponibile
        pipeline = [
            {"$unwind": "$matches"},
            {"$match": {
                "$or": [
                    {"matches.home": home_team, "matches.away": away_team, "matches.odds": {"$exists": True}},
                    {"matches.home": {"$regex": f"^{home_team}$", "$options": "i"}, 
                     "matches.away": {"$regex": f"^{away_team}$", "$options": "i"}, 
                     "matches.odds": {"$exists": True}}
                ]
            }},
            {"$sort": {"last_updated": -1}}, {"$limit": 1}, {"$project": {"match": "$matches"}}
        ]
        result = list(h2h_collection.aggregate(pipeline))
        if result:
            odds = result[0]["match"]["odds"]
            qr_1, qr_X, qr_2 = float(odds.get("1", 99.0)), float(odds.get("X", 99.0)), float(odds.get("2", 99.0))
    
    if qr_1 == 99.0:
        print(f"   ❌ Quote NON trovate. BVS Neutro.")
        return 0, 0
        
    print(f"   [BOOKMAKER]     1:{qr_1:.2f} X:{qr_X:.2f} 2:{qr_2:.2f}")

    # 4. CLASSIFICAZIONE E PUNTEGGIO (Preservata)
    classification = get_bvs_classification(qt_1, qt_X, qt_2, qr_1, qr_X, qr_2)
    punti_h, debug_h = calculate_team_bvs_score('1', classification, qr_1, qr_X, qr_2)
    punti_a, debug_a = calculate_team_bvs_score('2', classification, qr_1, qr_X, qr_2)
    
    print(f"\n   ⚡ PUNTEGGIO BVS FINALE:")
    print(f"   • Casa: {punti_h:+.2f} | Ospite: {punti_a:+.2f}")
    print(f"   {'='*70}")
    
    return round(punti_h, 2), round(punti_a, 2)

if __name__ == "__main__":
    get_bvs_score("Cagliari", "Pisa")