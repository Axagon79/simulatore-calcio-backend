import os
import sys
import statistics

# Setup path per importare config
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

teams = db["teams"]
avail = db["players_availability_tm"]

# MAPPING NOMI COMPLETO
TEAM_ALIASES = {
    # Girone A
    "Vicenza": "LR Vicenza",
    "Lecco": "Calcio Lecco",
    "Alcione": "Alcione Milano",
    "Cittadella": "AS Cittadella",
    "Pro Vercelli": "FC Pro Vercelli 1892",
    "Trento": "AC Trento",
    "Renate": "AC Renate",
    "Giana Erminio": "AS Giana Erminio",
    "AlbinoLeffe": "UC AlbinoLeffe",
    "Lumezzane": "FC Lumezzane",
    "Triestina": "US Triestina Calcio 1918",
    "Ospitaletto": "Ospitaletto Franciacorta",
    "Arzignano": "Arzignano Valchiampo",
    "D. Bellunesi": "Dolomiti Bellunesi",
    "Pergolettese": "US Pergolettese 1932",
    "Pro Patria": "Aurora Pro Patria 1919",
    "Novara": "Novara FC",
    # Girone B
    "Arezzo": "SS Arezzo",
    "Ascoli": "Ascoli Calcio",
    "Athletic Carpi": "AC Carpi",
    "Bra": "AC Bra",
    "Campobasso": "Campobasso FC",
    "Forli": "Forlì FC",
    "Gubbio": "AS Gubbio 1910",
    "Guidonia": "Guidonia Montecelio 1937 FC",
    "Juventus U23": "Juventus Next Gen",
    "Livorno": "US Livorno 1915",
    "Perugia": "AC Perugia Calcio",
    "Pianese": "US Pianese",
    "Pineto": "Pineto Calcio",
    "Pontedera": "US Città di Pontedera",
    "Ravenna": "Ravenna FC 1913",
    "Rimini": "Rimini FC",
    "Sambenedettese": "US Sambenedettese",
    "Ternana": "Ternana Calcio",
    "Vis Pesaro": "Vis Pesaro 1898",
    # Girone C
    "A. Cerignola": "Audace Cerignola",
    "Altamura": "Team Altamura",
    "Atalanta B": "Atalanta U23",
    "Benevento": "Benevento Calcio",
    "Casarano": "Casarano Calcio",
    "Casertana": "Casertana FC",
    "Catania": "Catania FC",
    "Cavese": "Cavese 1919",
    "Cosenza": "Cosenza Calcio",
    "Crotone": "FC Crotone",
    "Foggia": "Calcio Foggia 1920",
    "Giugliano": "Giugliano Calcio 1928",
    "Latina": "Latina Calcio 1932",
    "Monopoli": "SS Monopoli 1966",
    "Picerno": "AZ Picerno",
    "Potenza": "Potenza Calcio",
    "Salernitana": "US Salernitana",
    "Siracusa": "Siracusa Calcio",
    "Sorrento": "Sorrento 1945",
    "Trapani": "FC Trapani 1905",
}

def calcola_affidabilita_giocatore(events):
    """
    Calcola affidabilità SEVERA (0-10):
    - STARTING: 1.0 pti
    - SUB_IN:   0.7 pti
    - BENCH:    0.2 pti
    - Altro:    0.0 pti
    """
    if not events or len(events) == 0:
        return 5.0  # default neutro se non ci sono dati
    
    # Ultimi 10 eventi (o meno se non ce ne sono 10)
    ultimi_eventi = events[-10:]
    
    punti_totali = 0.0
    
    for evento in ultimi_eventi:
        status = evento.get("status", "")
        
        if status == "STARTING":
            punti_totali += 1.0
        elif status == "SUB_IN":
            punti_totali += 0.7
        elif status == "BENCH":
            punti_totali += 0.2
        # SQUAD, ABSENT, INJURY valgono 0
        
    # Normalizza su 10
    # Se ha giocato sempre titolare (10pt su 10 match) -> 10.0
    # Se ha fatto sempre panca (2pt su 10 match) -> 2.0
    affidabilita = (punti_totali / len(ultimi_eventi)) * 10.0
    
    return round(min(10.0, max(0.0, affidabilita)), 2)

def calculate_serie_c_rating():
    """
    Rating Serie C V2 (Severo):
    - Affidabilità giocatori (70%)
    - Valore rosa (30%)
    """
    
    gironi = {
        "ITA3A": "Serie C - Girone A",
        "ITA3B": "Serie C - Girone B", 
        "ITA3C": "Serie C - Girone C"
    }
    
    for league_code, league_name in gironi.items():
        print(f"\n🏆 {league_name}")
        print("=" * 80)
        
        # Squadre del girone
        league_teams = list(teams.find({"league": league_name}))
        
        if len(league_teams) < 10:
            print("❌ Pochi dati, salto")
            continue
        
        # RANGE valore rosa per normalizzazione
        values = [t.get("stats", {}).get("marketValue", 0) for t in league_teams]
        # Filtra valori zero per evitare min=0
        valid_values = [v for v in values if v > 0]
        if not valid_values:
            val_min = 0
            val_max = 1000000 # Default fittizio
        else:
            val_min = min(valid_values)
            val_max = max(valid_values)
        
        print(f"📊 Valore rosa: {val_min:,}€ - {val_max:,}€\n")
        
        # CALCOLO PER SQUADRA
        for team in league_teams:
            team_name = team.get("name", "???")
            team_name_search = TEAM_ALIASES.get(team_name, team_name)
            
            # Giocatori
            giocatori = list(avail.find({
                "team_name": team_name_search,
                "league_code": league_code
            }))
            
            if not giocatori or len(giocatori) == 0:
                print(f"⚠️  {team_name[:20]:<20} | Nessun giocatore")
                # Se mancano giocatori, resetta o metti default basso
                teams.update_one({"_id": team["_id"]}, {"$set": {"stats.serieC_rating": 4.0}})
                continue
            
            # 1. AFFIDABILITÀ GIOCATORI (70%)
            affidabilita_list = []
            for giocatore in giocatori:
                events = giocatore.get("events", [])
                aff = calcola_affidabilita_giocatore(events)
                affidabilita_list.append(aff)
            
            # Ordina e prendi i "Top 16" (una rosa 'tipo' che ruota)
            affidabilita_list.sort(reverse=True)
            # Prendiamo i migliori 16 per simulare chi gioca davvero
            top_players_aff = affidabilita_list[:16]
            
            if len(top_players_aff) < 11:
                print(f"⚠️  {team_name[:20]:<20} | Solo {len(top_players_aff)} giocatori")
                # Default basso ma non nullo
                teams.update_one({"_id": team["_id"]}, {"$set": {"stats.serieC_rating": 4.5}})
                continue
            
            # Media affidabilità della "rosa titolare allargata"
            affidabilita_score = statistics.mean(top_players_aff)
            
            # 2. VALORE ROSA (30%)
            val = team.get("stats", {}).get("marketValue", val_min)
            
            if val_max > val_min:
                val_norm = (val - val_min) / (val_max - val_min)
            else:
                val_norm = 0.5
                
            # Valore rosa da 0 a 10
            valore_score = val_norm * 10.0
            
            # RATING FINALE
            rating = (affidabilita_score * 0.70) + (valore_score * 0.30)
            
            # MINIMO 3.0 (per non uccidere le squadre povere ma titolari)
            final_rating = max(3.0, round(rating, 2))
            
            # SALVA
            teams.update_one(
                {"_id": team["_id"]},
                {"$set": {"stats.serieC_rating": final_rating}}
            )
            
            print(f"✅ {team_name[:20]:<20} | "
                  f"Aff:{affidabilita_score:.1f} Val:{valore_score:.1f} "
                  f"→ {final_rating}/10")
        
        print()

if __name__ == "__main__":
    calculate_serie_c_rating()
