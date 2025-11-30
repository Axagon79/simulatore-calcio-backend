import pymongo

# CONFIGURAZIONE DB
MONGO_URI = "mongodb+srv://Database_User:LPmYAZkzEVxjSaAd@pup-pals-cluster.y1h2r.mongodb.net/pup_pals_db?retryWrites=true&w=majority"

client = pymongo.MongoClient(MONGO_URI)
db = client["pup_pals_db"]
teams = db["teams"]

# Mappa: Nome nel TUO DB -> Nome usato da TRANSFERMARKT
updates_transfermarkt = {
    # --- ITALIA SERIE A ---
    "Inter": "Inter",
    "Juventus": "Juventus FC",
    "Napoli": "SSC Napoli",
    "AC Milan": "AC Milan",
    "Atalanta": "Atalanta",
    "AS Roma": "AS Roma",
    "Fiorentina": "ACF Fiorentina",
    "Como": "Como 1907",
    "Bologna": "Bologna FC",
    "Lazio": "SS Lazio",
    "Parma": "Parma Calcio",
    "Torino": "Torino FC",
    "Udinese": "Udinese Calcio",
    "Sassuolo": "US Sassuolo",
    "Genoa": "Genoa CFC",
    "Cagliari": "Cagliari Calcio",
    "Pisa": "Pisa Sporting Club",
    "Cremonese": "US Cremonese",
    "Lecce": "US Lecce",
    "Hellas Verona": "Hellas Verona",

    # --- ITALIA SERIE B ---
    "Monza": "AC Monza",
    "Venezia": "Venezia FC",
    "Spezia": "Spezia Calcio",
    "Palermo": "Palermo FC",
    "Empoli": "Empoli FC",
    "Sampdoria": "UC Sampdoria",
    "Cesena": "Cesena FC",
    "Catanzaro": "US Catanzaro",
    "Modena": "Modena FC",
    "Juve Stabia": "SS Juve Stabia",
    "Bari": "SSC Bari",
    "Frosinone": "Frosinone Calcio",
    "Pescara": "Delfino Pescara 1936",
    "Mantova": "Mantova 1911",
    "Carrarese": "Carrarese Calcio 1908",
    "Reggiana": "AC Reggiana",
    "Avellino": "US Avellino 1912",
    "Sudtirol": "FC Südtirol",
    "Padova": "Calcio Padova",
    "Entella": "Virtus Entella",
    "D. Bellunesi": "Dolomiti Bellunesi",

    # --- SERIE C A/B/C (principali) ---
    "Triestina": "US Triestina Calcio 1918",
    "Pro Vercelli": "FC Pro Vercelli 1892",
    "Pergolettese": "US Pergolettese 1932",
    "Pro Patria": "Aurora Pro Patria 1919",
    "Vicenza": "LR Vicenza",
    "Lecco": "Calcio Lecco",
    "Alcione": "Alcione Milano",
    "Arzignano": "Arzignano Valchiampo",
    "Ospitaletto": "Ospitaletto Franciacorta",

    "Juventus U23": "Juventus Next Gen",
    "Inter U23": "Inter U23",
    "Guidonia": "Guidonia Montecelio",

    "Atalanta B": "Atalanta U23",
    "Foggia": "Calcio Foggia 1920",
    "Latina": "Latina Calcio 1932",
    "Picerno": "AZ Picerno",
    "A. Cerignola": "Audace Cerignola",
    "Giugliano": "Giugliano Calcio 1928",
    "Casertana": "Casertana FC",
    "Crotone": "FC Crotone",
    "Salernitana": "US Salernitana",
    "Casarano": "Casarano Calcio",
    "Trapani": "FC Trapani 1905",
    "Catania": "Catania FC",
    "Benevento": "Benevento Calcio",
    "Cosenza": "Cosenza Calcio",
    "Monopoli": "SS Monopoli 1966",
    "Sorrento": "Sorrento 1945",
    "Cavese": "Cavese 1919",
    "Siracusa": "Siracusa Calcio",
    "Altamura": "Team Altamura",
    "Potenza": "Potenza Calcio",

    # --- SERIE C - GIRONE A: mancanti alias TM ---
    "Union Brescia": "Union Brescia",
    "Cittadella": "Cittadella",
    "Trento": "Trento",
    "Renate": "Renate",
    "Giana Erminio": "Giana Erminio",
    "Novara": "Novara",
    "AlbinoLeffe": "AlbinoLeffe",
    "Lumezzane": "Lumezzane",
    "Virtus Verona": "Virtus Verona",

    # --- SERIE C - GIRONE B: mancanti alias TM ---
    "Arezzo": "Arezzo",
    "Ravenna": "Ravenna",
    "Ascoli": "Ascoli",
    "Ternana": "Ternana",
    "Athletic Carpi": "Athletic Carpi",
    "Pineto": "Pineto",
    "Campobasso": "Campobasso",
    "Vis Pesaro": "Vis Pesaro",
    "Forli": "Forli",
    "Pianese": "Pianese",
    "Gubbio": "Gubbio",
    "Sambenedettese": "Sambenedettese",
    "Pontedera": "Pontedera",
    "Bra": "Bra",
    "Livorno": "Livorno",
    "Perugia": "Perugia",
    "Torres": "Torres",
    "Rimini": "Rimini",

    # --- PREMIER LEAGUE ---
    "Manchester City": "Manchester City",
    "Manchester Utd": "Manchester Utd.",
    "Nottm Forest": "Nottm Forest",
    "West Ham Utd": "West Ham Utd.",

    # Mancanti da check_data_health
    "Aston Villa": "Aston Villa",
    "Crystal Palace": "Crystal Palace",
    "Arsenal": "Arsenal",
    "Chelsea": "Chelsea",
    "Brighton": "Brighton",
    "Sunderland": "Sunderland",
    "Bournemouth": "Bournemouth",
    "Tottenham": "Tottenham",
    "Liverpool": "Liverpool",
    "Brentford": "Brentford",
    "Everton": "Everton",
    "Newcastle Utd": "Newcastle Utd",
    "Fulham": "Fulham",
    "Leeds Utd": "Leeds Utd",
    "Burnley": "Burnley",
    "Wolverhampton": "Wolverhampton",

    # --- LA LIGA (SPAGNA) ---
    "Elche": "Elche",
    "Villarreal": "Villarreal",
    "Valencia": "Valencia",
    "Atletico Madrid": "Atletico Madrid",
    "Levante": "Levante",
    "Alaves": "Alaves",
    "Espanyol": "Espanyol",
    "Real Betis": "Real Betis",

    # Mancanti da check_data_health
    "Real Madrid": "Real Madrid",
    "Barcellona": "Barcellona",
    "Athletic Club": "Athletic Club",
    "Real Sociedad": "Real Sociedad",
    "Siviglia": "Siviglia",
    "Rayo Vallecano": "Rayo Vallecano",
    "Real Oviedo": "Real Oviedo",
    "Getafe": "Getafe",
    "Celta Vigo": "Celta Vigo",
    "Mallorca": "Mallorca",
    "Osasuna": "Osasuna",
    "Girona": "Girona",

    # --- BUNDESLIGA (GERMANIA) ---
    "Bayern": "FC Bayern Monaco",
    "Dortmund": "Borussia Dortmund",
    "Leverkusen": "Bayer 04 Leverkusen",
    "Stoccarda": "VfB Stoccarda",
    "Eintracht": "Eintracht Francoforte",
    "Lipsia": "RB Lipsia",
    "Werder Brema": "SV Werder Brema",
    "Hoffenheim": "TSG 1899 Hoffenheim",
    "Magonza": "1.FSV Magonza 05",
    "Monchengladbach": "Borussia Mönchengladbach",
    "Union Berlino": "1.FC Union Berlino",
    "Colonia": "1.FC Colonia",
    "Heidenheim": "1.FC Heidenheim 1846",

    # Mancanti da check_data_health
    "Friburgo": "Friburgo",
    "Augusta": "Augusta",
    "Amburgo": "Amburgo",
    "Sankt Pauli": "Sankt Pauli",
    "Wolfsburg": "Wolfsburg",

    # --- LIGUE 1 (FRANCIA) ---
    "PSG": "FC Paris Saint-Germain",
    "Marsiglia": "Olympique Marsiglia",
    "Nizza": "OGC Nizza",
    "Brest": "Stade Brest 29",

    # Mancanti da check_data_health
    "Monaco": "Monaco",
    "Strasburgo": "Strasburgo",
    "Lille": "Lille",
    "Paris FC": "Paris FC",
    "Lens": "Lens",
    "Tolosa": "Tolosa",
    "Lorient": "Lorient",
    "Metz": "Metz",
    "Le Havre": "Le Havre",
    "Rennes": "Rennes",
    "Lyon": "Lyon",
    "Angers": "Angers",
    "Nantes": "Nantes",
    "Auxerre": "Auxerre",

    # --- LIGA PORTUGAL ---
    "Guimaraes": "Vit. Guimarães",
    "AVS": "Avs FS",
    "Tondela": "CD Tondela",
    "Estrela Amadora": "CF Estrela Amadora",
    "Estoril": "GD Estoril Praia",
    "Nacional": "CD Nacional",
    "Santa Clara": "CD Santa Clara",

    # Mancanti da check_data_health
    "FC Porto": "FC Porto",
    "Benfica": "Benfica",
    "Gil Vicente": "Gil Vicente",
    "Famalicao": "Famalicao",
    "Moreirense": "Moreirense",
    "Sporting Braga": "Sporting Braga",
    "Rio Ave": "Rio Ave",
    "Alverca": "Alverca",
    "Casa Pia": "Casa Pia",
    "Arouca": "Arouca",
    "Sporting CP": "Sporting CP",

    # --- EREDIVISIE (OLANDA) ---
    "Sparta": "Sparta Rotterdam",
    "Go Ahead Eagles": "Go Ahead Eagles Deventer",
    "Excelsior": "Excelsior Rotterdam",
    "FC Twente": "FC Twente Enschede",

    # Mancanti da check_data_health
    "PSV Eindhoven": "PSV Eindhoven",
    "Feyenoord": "Feyenoord",
    "AZ Alkmaar": "AZ Alkmaar",
    "NEC Nijmegen": "NEC Nijmegen",
    "FC Utrecht": "FC Utrecht",
    "Ajax Amsterdam": "Ajax Amsterdam",
    "FC Groningen": "FC Groningen",
    "Heerenveen": "Heerenveen",
    "Fortuna Sittard": "Fortuna Sittard",
    "FC Volendam": "FC Volendam",
    "PEC Zwolle": "PEC Zwolle",
    "NAC Breda": "NAC Breda",
    "Heracles Almelo": "Heracles Almelo",
    "Telstar": "Telstar",
}

print("🔧 Inizio FIX Aliases Transfermarkt...")
count = 0

for db_name, tm_name in updates_transfermarkt.items():
    res = teams.update_one(
        {"name": db_name},
        {"$set": {"aliases_transfermarkt": tm_name}},
        upsert=False  # non crea nuove squadre, aggiorna solo quelle esistenti
    )

    if res.matched_count > 0:
        print(f"✅ {db_name} -> aliases_transfermarkt = '{tm_name}'")
        count += 1
    else:
        print(f"⚠️ Squadra '{db_name}' non trovata nel DB (controlla il name).")

print(f"\nFinito. Aggiornati {count} alias Transfermarkt.")
