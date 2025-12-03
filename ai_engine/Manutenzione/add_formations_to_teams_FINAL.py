"""
AGGIUNGI MODULI ALLE SQUADRE - VERSIONE FINALE
Con tutti i nomi esatti dal database
"""

import pymongo

MONGO_URI = "mongodb+srv://Database_User:LPmYAZkzEVxjSaAd@pup-pals-cluster.y1h2r.mongodb.net/"
DB_NAME = "pup_pals_db"

client = pymongo.MongoClient(MONGO_URI)
db = client[DB_NAME]
teams_col = db["teams"]


# DIZIONARIO COMPLETO CON NOMI ESATTI DAL DATABASE
FORMATIONS = {
    # SERIE A
    "AC Milan": "3-5-2",
    "Fiorentina": "4-2-3-1",
    "Genoa": "4-2-3-1",
    "Pisa": "4-3-3",
    "Lecce": "4-3-3",  # Non nel PDF, uso 4-3-3 default
    "Parma": "4-2-3-1",  # Non nel PDF, uso 4-2-3-1 default
    "Torino": "3-4-2-1",
    "Inter": "3-5-2",
    "Atalanta": "3-4-2-1",
    "AS Roma": "4-3-3",
    "Hellas Verona": "3-4-2-1",  # Non nel PDF, uso 3-4-2-1 default
    "Napoli": "4-3-3",
    "Bologna": "4-2-3-1",
    "Juventus": "3-5-2",
    "Lazio": "4-3-3",
    "Cagliari": "4-2-3-1",
    "Cremonese": "3-5-2",
    "Udinese": "3-5-2",
    "Sassuolo": "4-3-3",
    "Como": "4-3-3",
    
    # SERIE B
    "Venezia": "4-3-3",
    "Monza": "3-5-2",
    "Modena": "4-2-3-1",
    "Frosinone": "3-4-2-1",
    "Sampdoria": "4-3-3",
    "Spezia": "3-5-2",
    "Pescara": "4-3-3",
    "Bari": "4-2-3-1",
    "Mantova": "4-3-3",
    "Cesena": "4-3-3",
    "Palermo": "4-3-3",
    "Reggiana": "4-4-2",
    "Juve Stabia": "4-3-3",  # Non nel PDF, default 4-3-3
    "Empoli": "4-3-3",
    "Catanzaro": "3-4-3",
    "Sudtirol": "4-3-3",  # Non nel PDF, default 4-3-3
    "Padova": "3-4-3",
    "Entella": "4-4-2",  # Virtus Entella
    "Avellino": "4-3-3",
    "Carrarese": "4-4-2",
    
    # SERIE C GIRONE A
    "Lumezzane": "4-4-2",
    "Pro Patria": "3-5-2",
    "Virtus Verona": "3-5-2",
    "Pergolettese": "4-3-3",  # Non nel PDF, default
    "D. Bellunesi": "4-3-3",  # Dolomiti Bellunesi
    "Arzignano": "4-2-3-1",  # Arzignano Valchiampo
    "Ospitaletto": "4-3-3",
    "Triestina": "4-3-3",
    "AlbinoLeffe": "3-5-2",
    "Novara": "4-2-3-1",
    "Renate": "4-3-3",
    "Vicenza": "3-4-2-1",
    "Lecco": "4-3-3",  # Non nel PDF, default
    "Union Brescia": "4-2-3-1",
    "Inter U23": "3-5-2",
    "Alcione": "4-3-3",  # Alcione Milano
    "Cittadella": "4-3-1-2",
    "Pro Vercelli": "3-5-2",  # Non nel PDF, default
    "Trento": "4-4-2",
    "Giana Erminio": "3-4-3",
    
    # SERIE C GIRONE B
    "Pineto": "3-4-2-1",
    "Arezzo": "4-3-3",
    "Ravenna": "4-2-3-1",
    "Ascoli": "3-5-2",
    "Ternana": "3-4-3",
    "Guidonia": "4-3-3",  # Guidonia Montecelio
    "Athletic Carpi": "4-2-3-1",  # Carpi
    "Campobasso": "3-4-3",
    "Bra": "4-4-2",
    "Vis Pesaro": "3-5-2",
    "Rimini": "3-5-2",
    "Torres": "4-3-3",
    "Perugia": "4-3-3",
    "Livorno": "4-2-3-1",
    "Pontedera": "4-3-3",
    "Sambenedettese": "4-3-3",
    "Juventus U23": "4-3-3",  # Juventus Next Gen
    "Gubbio": "3-5-2",
    "Pianese": "4-4-2",
    "Forli": "4-3-3",
    
    # SERIE C GIRONE C
    "A. Cerignola": "4-3-3",  # Audace Cerignola
    "Atalanta B": "3-4-3",  # Atalanta U23
    "Cavese": "3-5-2",
    "Altamura": "3-5-2",  # Team Altamura
    "Cosenza": "4-3-3",
    "Giugliano": "4-2-3-1",
    "Siracusa": "4-4-2",
    "Picerno": "3-5-2",  # AZ Picerno
    "Foggia": "4-3-3",
    "Latina": "3-5-2",
    "Potenza": "3-4-2-1",
    "Crotone": "3-4-3",
    "Monopoli": "4-3-3",
    "Casertana": "3-4-2-1",
    "Casarano": "4-2-3-1",
    "Trapani": "4-3-3",
    "Benevento": "4-3-3",
    "Salernitana": "4-3-3",
    "Catania": "4-3-3",
    "Sorrento": "4-3-3",
    
    # BUNDESLIGA
    "Wolfsburg": "4-2-3-1",  # Non nel PDF, default
    "Amburgo": "4-2-3-1",  # Non nel PDF, default
    "Union Berlino": "3-5-2",  # Union Berlin
    "Augusta": "3-4-2-1",  # Augsburg
    "Magonza": "3-4-3",  # Mainz 05
    "Friburgo": "3-4-3",  # Freiburg
    "Hoffenheim": "4-2-3-1",
    "Werder Brema": "3-4-2-1",
    "Stoccarda": "4-2-3-1",  # Stuttgart
    "Lipsia": "4-2-2-2",  # RB Lipsia
    "Eintracht": "3-4-2-1",  # Eintracht Frankfurt
    "Leverkusen": "4-2-3-1",  # Bayer Leverkusen
    "Dortmund": "4-2-3-1",  # Borussia Dortmund
    "Bayern": "4-2-3-1",  # Bayern Monaco
    "Colonia": "4-2-3-1",
    "Heidenheim": "3-4-2-1",
    "Monchengladbach": "4-2-3-1",  # Borussia Mönchengladbach
    "Sankt Pauli": "3-4-3",  # St. Pauli
    
    # EREDIVISIE
    "FC Groningen": "4-3-3",  # Non nel PDF, default
    "Ajax Amsterdam": "4-3-3",
    "PSV Eindhoven": "4-3-3",
    "Feyenoord": "4-3-3",
    "AZ Alkmaar": "4-2-3-1",
    "NEC Nijmegen": "4-3-3",
    "FC Utrecht": "4-3-3",
    "Excelsior": "4-3-3",  # Non nel PDF, default
    "FC Twente": "4-2-3-1",
    "Heerenveen": "4-3-3",
    "Fortuna Sittard": "4-3-3",
    "Sparta": "3-4-3",  # Sparta Rotterdam
    "Go Ahead Eagles": "4-4-2",
    "FC Volendam": "4-3-3",  # Non nel PDF, default
    "NAC Breda": "4-2-3-1",
    "PEC Zwolle": "4-3-3",
    "Heracles Almelo": "3-4-3",
    "Telstar": "4-3-3",  # Non nel PDF, default
    
    # LA LIGA
    "Elche": "4-4-2",
    "Real Oviedo": "4-2-3-1",
    "Real Madrid": "3-4-3",
    "Barcellona": "4-3-3",
    "Athletic Club": "4-2-3-1",  # Athletic Bilbao
    "Villarreal": "4-4-2",
    "Real Sociedad": "4-3-3",
    "Real Betis": "4-2-3-1",
    "Valencia": "4-4-2",
    "Siviglia": "4-3-3",
    "Espanyol": "4-2-3-1",
    "Rayo Vallecano": "4-2-3-1",
    "Levante": "4-3-3",
    "Girona": "4-2-3-1",
    "Osasuna": "4-3-3",
    "Mallorca": "4-4-2",
    "Alaves": "4-2-3-1",
    "Celta Vigo": "4-3-3",
    "Getafe": "4-4-2",
    "Atletico Madrid": "3-5-2",
    
    # LIGA PORTUGAL
    "Moreirense": "4-3-3",
    "Santa Clara": "3-5-2",
    "Estrela Amadora": "3-4-3",
    "Rio Ave": "4-2-3-1",
    "Nacional": "4-4-2",
    "Sporting Braga": "4-3-3",  # Braga
    "Estoril": "4-3-3",
    "Guimaraes": "4-3-3",  # Vitória Guimarães
    "Famalicao": "4-3-3",
    "Sporting CP": "3-4-3",
    "FC Porto": "4-3-3",  # Porto
    "Benfica": "4-3-3",
    "Gil Vicente": "4-3-3",
    "Casa Pia": "4-4-2",
    "Arouca": "4-3-3",
    "Tondela": "4-3-3",  # Non nel PDF, default
    "AVS": "4-2-3-1",
    "Alverca": "4-3-3",  # Non nel PDF, default
    
    # LIGUE 1
    "Monaco": "4-4-2",
    "PSG": "4-3-3",  # Paris Saint-Germain
    "Marsiglia": "4-2-3-1",
    "Strasburgo": "4-2-3-1",  # Non nel PDF, default
    "Lille": "4-2-3-1",
    "Nizza": "4-3-3",
    "Paris FC": "3-4-3",
    "Lens": "3-4-3",
    "Tolosa": "4-3-3",
    "Rennes": "4-3-3",
    "Lyon": "4-3-3",  # Lione
    "Nantes": "4-3-3",
    "Auxerre": "4-2-3-1",
    "Brest": "4-3-3",
    "Lorient": "4-3-3",
    "Metz": "4-2-3-1",  # Non nel PDF, default
    "Le Havre": "4-3-3",  # Non nel PDF, default
    "Angers": "4-3-3",
    
    # PREMIER LEAGUE
    "Everton": "4-2-3-1",
    "Fulham": "4-2-3-1",
    "Brentford": "4-3-3",
    "Liverpool": "4-3-3",
    "Manchester Utd": "4-2-3-1",  # Manchester United
    "Tottenham": "4-3-3",  # Tottenham Hotspur
    "Bournemouth": "4-2-3-1",
    "Sunderland": "4-3-3",
    "Brighton": "4-2-3-1",
    "Chelsea": "4-2-3-1",
    "Arsenal": "4-3-3",
    "Newcastle Utd": "4-3-3",  # Newcastle United
    "Nottm Forest": "4-2-3-1",  # Nottingham Forest
    "West Ham Utd": "4-2-3-1",  # West Ham United
    "Leeds Utd": "4-3-3",  # Leeds United
    "Burnley": "4-4-2",
    "Wolverhampton": "4-2-3-1",
    "Manchester City": "4-3-3",
    "Aston Villa": "4-2-3-1",
    "Crystal Palace": "4-2-3-1",
}


def add_formations():
    """Aggiunge il campo formation a tutte le squadre."""
    
    print("\n" + "="*60)
    print("⚽ AGGIUNGI MODULI ALLE SQUADRE - VERSIONE FINALE")
    print("="*60)
    
    total_teams = teams_col.count_documents({})
    print(f"\n📊 Squadre totali nel database: {total_teams}")
    
    updated = 0
    not_found = []
    
    # Itera su tutte le squadre
    for team in teams_col.find({}):
        team_name = team.get("name", "")
        
        formation = FORMATIONS.get(team_name)
        
        if formation:
            teams_col.update_one(
                {"_id": team["_id"]},
                {"$set": {"formation": formation}}
            )
            updated += 1
            print(f"✅ {team_name}: {formation}")
        else:
            not_found.append(team_name)
            print(f"❌ {team_name}: MANCA")
    
    print("\n" + "="*60)
    print(f"✅ COMPLETATO!")
    print(f"   Aggiornate: {updated}/{total_teams}")
    print(f"   Mancanti: {len(not_found)}")
    print("="*60)
    
    if not_found:
        print(f"\n⚠️  Squadre ancora senza modulo:")
        for name in not_found:
            print(f"   - {name}")


if __name__ == "__main__":
    add_formations()
