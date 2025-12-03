import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config import db  # ← CENTRALIZZATO!

# Niente più pymongo.MongoClient qui!
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
    "Guidonia": "Guidonia Montecelio 1937 FC", # CORRETTO

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

    # --- SERIE C - GIRONE A ---
    "Union Brescia": "Union Brescia",
    "Cittadella": "Cittadella",
    "Trento": "Trento",
    "Renate": "Renate",
    "Giana Erminio": "Giana Erminio",
    "Novara": "Novara",
    "AlbinoLeffe": "AlbinoLeffe",
    "Lumezzane": "Lumezzane",
    "Virtus Verona": "Virtus Verona",

    # --- SERIE C - GIRONE B ---
    "Arezzo": "Arezzo",
    "Ravenna": "Ravenna",
    "Ascoli": "Ascoli",
    "Ternana": "Ternana",
    "Athletic Carpi": "Athletic Carpi",
    "Pineto": "Pineto",
    "Campobasso": "Campobasso",
    "Vis Pesaro": "Vis Pesaro",
    "Forli": "Forlì FC",
    "Pianese": "Pianese",
    "Gubbio": "Gubbio",
    "Sambenedettese": "Sambenedettese",
    "Pontedera": "Pontedera",
    "Bra": "Bra",
    "Livorno": "Livorno",
    "Perugia": "Perugia",
    "Torres": "Torres",
    "Rimini": "Rimini",

    # --- PREMIER LEAGUE (CORRETTI) ---
    "Manchester City": "Manchester City",
    "Manchester Utd": "Manchester Utd.",
    "Nottm Forest": "Nottingham Forest", # CORRETTO
    "West Ham Utd": "West Ham United",   # CORRETTO
    "Aston Villa": "Aston Villa",
    "Crystal Palace": "Crystal Palace",
    "Arsenal": "Arsenal FC",             # CORRETTO
    "Chelsea": "Chelsea FC",             # CORRETTO
    "Brighton": "Brighton & Hove Albion",# CORRETTO
    "Sunderland": "Sunderland AFC",      # CORRETTO
    "Bournemouth": "AFC Bournemouth",    # Probabile
    "Tottenham": "Tottenham Hotspur",    # CORRETTO
    "Liverpool": "Liverpool FC",         # CORRETTO
    "Brentford": "Brentford FC",         # CORRETTO
    "Everton": "Everton FC",             # CORRETTO
    "Newcastle Utd": "Newcastle United", # CORRETTO
    "Fulham": "Fulham FC",               # CORRETTO
    "Leeds Utd": "Leeds United",         # CORRETTO
    "Burnley": "Burnley FC",             # CORRETTO
    "Wolverhampton": "Wolverhampton Wanderers", # CORRETTO

    # --- LA LIGA (CORRETTI) ---
    "Elche": "Elche CF",                 # CORRETTO
    "Villarreal": "Villarreal CF",       # CORRETTO
    "Valencia": "Valencia CF",           # CORRETTO
    "Atletico Madrid": "Atlético de Madrid", # CORRETTO (accento)
    "Levante": "Levante UD",             # CORRETTO
    "Alaves": "Deportivo Alavés",        # CORRETTO
    "Espanyol": "RCD Espanyol Barcelona",# CORRETTO
    "Real Betis": "Real Betis Balompié", # CORRETTO
    "Real Madrid": "Real Madrid CF",     # CORRETTO
    "Barcellona": "FC Barcelona",        # CORRETTO
    "Athletic Club": "Athletic Bilbao",  # Spesso è Bilbao su TM
    "Real Sociedad": "Real Sociedad",
    "Siviglia": "Sevilla FC",            # CORRETTO (Nome spagnolo)
    "Rayo Vallecano": "Rayo Vallecano",
    "Real Oviedo": "Real Oviedo",
    "Getafe": "Getafe CF",
    "Celta Vigo": "Celta de Vigo",
    "Mallorca": "RCD Mallorca",
    "Osasuna": "CA Osasuna",
    "Girona": "Girona FC",

    # --- BUNDESLIGA (NOMI ORIGINALI TEDESCHI) ---
    "Bayern": "FC Bayern München",
    "Dortmund": "Borussia Dortmund",
    "Leverkusen": "Bayer 04 Leverkusen",
    "Stoccarda": "VfB Stuttgart",        # CORRETTO
    "Eintracht": "Eintracht Frankfurt",  # CORRETTO
    "Lipsia": "RB Leipzig",              # CORRETTO
    "Werder Brema": "SV Werder Bremen",  # CORRETTO
    "Hoffenheim": "TSG 1899 Hoffenheim",
    "Magonza": "1.FSV Mainz 05",         # CORRETTO
    "Monchengladbach": "Borussia Mönchengladbach",
    "Union Berlino": "1.FC Union Berlin",# CORRETTO
    "Colonia": "1.FC Köln",              # CORRETTO
    "Heidenheim": "1.FC Heidenheim 1846",
    "Friburgo": "SC Freiburg",           # CORRETTO
    "Augusta": "FC Augsburg",            # CORRETTO
    "Amburgo": "Hamburger SV",           # CORRETTO
    "Sankt Pauli": "FC St. Pauli",       # CORRETTO
    "Wolfsburg": "VfL Wolfsburg",        # CORRETTO

    # --- LIGUE 1 (NOMI ORIGINALI FRANCESI) ---
    "PSG": "Paris Saint-Germain",        # CORRETTO
    "Marsiglia": "Olympique Marseille",  # CORRETTO
    "Nizza": "OGC Nice",                 # CORRETTO
    "Brest": "Stade Brestois 29",        # CORRETTO
    "Monaco": "AS Monaco",
    "Strasburgo": "RC Strasbourg Alsace",# CORRETTO
    "Lille": "LOSC Lille",               # CORRETTO
    "Paris FC": "Paris FC",
    "Lens": "RC Lens",                   # CORRETTO
    "Tolosa": "FC Toulouse",             # CORRETTO
    "Lorient": "FC Lorient",
    "Metz": "FC Metz",
    "Le Havre": "AC Le Havre",
    "Rennes": "Stade Rennais FC",        # CORRETTO
    "Lyon": "Olympique Lyon",            # CORRETTO
    "Angers": "Angers SCO",
    "Nantes": "FC Nantes",
    "Auxerre": "AJ Auxerre",

    # --- LIGA PORTUGAL ---
    "Guimaraes": "Vitória Guimarães SC", # CORRETTO
    "AVS": "Avs Futebol",                # CORRETTO
    "Tondela": "CD Tondela",
    "Estrela Amadora": "CF Estrela Amadora",
    "Estoril": "GD Estoril Praia",
    "Nacional": "CD Nacional",
    "Santa Clara": "CD Santa Clara",
    "FC Porto": "FC Porto",
    "Benfica": "SL Benfica",             # CORRETTO
    "Gil Vicente": "Gil Vicente FC",
    "Famalicao": "FC Famalicão",         # CORRETTO
    "Moreirense": "Moreirense FC",
    "Sporting Braga": "SC Braga",
    "Rio Ave": "Rio Ave FC",
    "Alverca": "FC Alverca",
    "Casa Pia": "Casa Pia AC",
    "Arouca": "FC Arouca",
    "Sporting CP": "Sporting CP",

    # --- EREDIVISIE ---
    "Sparta": "Sparta Rotterdam",
    "Go Ahead Eagles": "Go Ahead Eagles Deventer",
    "Excelsior": "Excelsior Rotterdam",
    "FC Twente": "Twente Enschede FC",   # CORRETTO
    "PSV Eindhoven": "PSV Eindhoven",
    "Feyenoord": "Feyenoord Rotterdam",
    "AZ Alkmaar": "AZ Alkmaar",
    "NEC Nijmegen": "NEC Nijmegen",
    "FC Utrecht": "FC Utrecht",
    "Ajax Amsterdam": "Ajax Amsterdam",
    "FC Groningen": "FC Groningen",
    "Heerenveen": "SC Heerenveen",
    "Fortuna Sittard": "Fortuna Sittard",
    "FC Volendam": "FC Volendam",
    "PEC Zwolle": "PEC Zwolle",
    "NAC Breda": "NAC Breda",
    "Heracles Almelo": "Heracles Almelo",
    "Telstar": "SC Telstar",
}


print("🔧 Inizio FIX Aliases Transfermarkt...")
count = 0

for db_name, tm_name in updates_transfermarkt.items():
    res = teams.update_one(
        {"name": db_name},
        {"$set": {"aliases_transfermarkt": tm_name}},
        upsert=False
    )

    if res.matched_count > 0:
        # print(f"✅ {db_name} -> aliases_transfermarkt = '{tm_name}'")
        count += 1
    else:
        print(f"⚠️ Squadra '{db_name}' non trovata nel DB.")

print(f"\nFinito. Aggiornati {count} alias Transfermarkt.")
