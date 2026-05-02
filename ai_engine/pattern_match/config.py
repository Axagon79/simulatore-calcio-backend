"""
Configurazione Pattern Match Engine.

Costanti e parametri centralizzati. Niente logica.
"""
from __future__ import annotations

from pathlib import Path

# ====================================================================
# Percorsi
# ====================================================================

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
PATTERN_MATCH_ROOT = Path(__file__).resolve().parent
CACHE_ROOT = PATTERN_MATCH_ROOT / "_cache_pattern_match"
CACHE_FOOTBALLDATA = CACHE_ROOT / "footballdata"
CACHE_CLUBELO = CACHE_ROOT / "clubelo"

# MongoDB: stesso cluster e database di AI Simulator, collezioni con prefisso historical__
# (Vedi History_System_Engine.md sezione 7).
MONGO_COLLECTION_MATCHES = "historical__matches_pattern"
MONGO_COLLECTION_PREDICTIONS = "historical__pattern_predictions"
MONGO_COLLECTION_VALIDATION = "historical__pattern_validation"

# La connessione MongoDB usa la config esistente del progetto (config.db).
# Importata dove serve, non qui (questo file e' costanti).


# ====================================================================
# Leghe (10) — codice Football-Data + codice/nome ClubElo
# ====================================================================

LEAGUES = [
    {"fd_code": "E0",  "name": "Premier League",        "country": "ENG"},
    {"fd_code": "SP1", "name": "La Liga",               "country": "ESP"},
    {"fd_code": "I1",  "name": "Serie A",               "country": "ITA"},
    {"fd_code": "D1",  "name": "Bundesliga",            "country": "GER"},
    {"fd_code": "F1",  "name": "Ligue 1",               "country": "FRA"},
    {"fd_code": "N1",  "name": "Eredivisie",            "country": "NED"},
    {"fd_code": "P1",  "name": "Primeira Liga",         "country": "POR"},
    {"fd_code": "SC0", "name": "Scottish Premiership",  "country": "SCO"},
    {"fd_code": "B1",  "name": "Pro League Belgio",     "country": "BEL"},
    {"fd_code": "T1",  "name": "Super Lig",             "country": "TUR"},
]


# ====================================================================
# Stagioni (10): 2015/16 -> 2024/25
# Formato Football-Data: "1516", "1617", ..., "2425"
# ====================================================================

SEASONS = [
    "1516", "1617", "1718", "1819", "1920",
    "2021", "2122", "2223", "2324", "2425",
]


# ====================================================================
# Football-Data
# ====================================================================

FOOTBALLDATA_URL_TEMPLATE = "https://www.football-data.co.uk/mmz4281/{stagione}/{lega}.csv"

# Colonne minime richieste per costruire il vettore feature
FD_REQUIRED_COLS = [
    "Date", "HomeTeam", "AwayTeam",
    "FTHG", "FTAG", "FTR",
    "B365H", "B365D", "B365A",
]


# ====================================================================
# ClubElo
# ====================================================================

CLUBELO_TEAM_URL_TEMPLATE = "http://api.clubelo.com/{team}"

# Mapping manuale nomi Football-Data -> ClubElo (popolato iterativamente)
# Quando un team Football-Data non ha match diretto in ClubElo, lo aggiungiamo qui.
TEAM_NAME_MAPPING_FD_TO_ELO = {
    # Premier League
    "Man United": "ManUnited",
    "Man City": "ManCity",
    "Newcastle": "Newcastle",
    "Nott'm Forest": "Forest",
    "Tottenham": "Tottenham",
    "West Brom": "WestBrom",
    "West Ham": "WestHam",
    "Wolves": "Wolves",
    "Sheffield United": "SheffieldUnited",
    "Crystal Palace": "CrystalPalace",
    "Bournemouth": "Bournemouth",
    "Brighton": "Brighton",
    "Leicester": "Leicester",
    "Leeds": "Leeds",
    "Aston Villa": "AstonVilla",
    "Norwich": "Norwich",
    "Stoke": "Stoke",
    "Swansea": "Swansea",
    "Hull": "Hull",
    "Watford": "Watford",
    "Cardiff": "Cardiff",
    "Huddersfield": "Huddersfield",
    "Burnley": "Burnley",
    "Brentford": "Brentford",
    "Sunderland": "Sunderland",
    "Middlesbrough": "Middlesbrough",
    "Luton": "Luton",
    "Ipswich": "Ipswich",
    # Serie A
    "AC Milan": "Milan",
    "Inter": "Inter",
    "Juventus": "Juventus",
    "Napoli": "Napoli",
    "Roma": "Roma",
    "Lazio": "Lazio",
    "Atalanta": "Atalanta",
    "Fiorentina": "Fiorentina",
    "Bologna": "Bologna",
    "Torino": "Torino",
    "Sampdoria": "Sampdoria",
    "Genoa": "Genoa",
    "Udinese": "Udinese",
    "Sassuolo": "Sassuolo",
    "Hellas Verona": "Verona",
    "Verona": "Verona",
    "Cagliari": "Cagliari",
    "Lecce": "Lecce",
    "Empoli": "Empoli",
    "Monza": "Monza",
    "Salernitana": "Salernitana",
    "Spezia": "Spezia",
    "Cremonese": "Cremonese",
    "Como": "Como",
    "Parma": "Parma",
    "Frosinone": "Frosinone",
    "Venezia": "Venezia",
    "Carpi": "Carpi",
    "Palermo": "Palermo",
    "Pescara": "Pescara",
    "Crotone": "Crotone",
    "Benevento": "Benevento",
    "Spal": "Spal",
    "Chievo": "Chievo",
    "Brescia": "Brescia",
    # La Liga (principali)
    "Real Madrid": "RealMadrid",
    "Barcelona": "Barcelona",
    "Ath Madrid": "AtleticoMadrid",
    "Atletico Madrid": "AtleticoMadrid",
    "Sevilla": "Sevilla",
    "Valencia": "Valencia",
    "Villarreal": "Villarreal",
    "Real Sociedad": "Sociedad",
    "Sociedad": "Sociedad",
    "Ath Bilbao": "Bilbao",
    "Athletic Bilbao": "Bilbao",
    "Bilbao": "Bilbao",
    "Real Betis": "Betis",
    "Betis": "Betis",
    "Celta": "Celta",
    "Espanol": "Espanyol",
    "Espanyol": "Espanyol",
    "Getafe": "Getafe",
    "Levante": "Levante",
    "Las Palmas": "LasPalmas",
    "Mallorca": "Mallorca",
    "Osasuna": "Osasuna",
    "Granada": "Granada",
    "Eibar": "Eibar",
    "Alaves": "Alaves",
    "Leganes": "Leganes",
    "Girona": "Girona",
    "Cadiz": "Cadiz",
    "Vallecano": "Vallecano",
    "Rayo Vallecano": "Vallecano",
    "Elche": "Elche",
    "Almeria": "Almeria",
    "Valladolid": "Valladolid",
    "Huesca": "Huesca",
    "Sp Gijon": "Gijon",
    # Bundesliga
    "Bayern Munich": "Bayern",
    "Dortmund": "Dortmund",
    "RB Leipzig": "RBLeipzig",
    "Leverkusen": "Leverkusen",
    "Bayer Leverkusen": "Leverkusen",
    "M'gladbach": "Gladbach",
    "Frankfurt": "Frankfurt",
    "Wolfsburg": "Wolfsburg",
    "Schalke 04": "Schalke",
    "Schalke": "Schalke",
    "Hoffenheim": "Hoffenheim",
    "Stuttgart": "Stuttgart",
    "Werder Bremen": "Bremen",
    "Hertha": "Hertha",
    "Hertha BSC": "Hertha",
    "Hamburg": "Hamburg",
    "Mainz": "Mainz",
    "FC Koln": "Koeln",
    "Augsburg": "Augsburg",
    "Freiburg": "Freiburg",
    "Union Berlin": "UnionBerlin",
    "Bochum": "Bochum",
    "Heidenheim": "Heidenheim",
    "Darmstadt": "Darmstadt",
    "Paderborn": "Paderborn",
    "Fortuna Dusseldorf": "Duesseldorf",
    "Dusseldorf": "Duesseldorf",
    "Nurnberg": "Nuernberg",
    "Hannover": "Hannover",
    "Ingolstadt": "Ingolstadt",
    "Holstein Kiel": "Kiel",
    "St Pauli": "Pauli",
    "Greuther Furth": "Fuerth",
    # Ligue 1
    "Paris SG": "Paris",
    "Marseille": "Marseille",
    "Lyon": "Lyon",
    "Monaco": "Monaco",
    "Lille": "Lille",
    "Rennes": "Rennes",
    "Nice": "Nice",
    "Nantes": "Nantes",
    "Bordeaux": "Bordeaux",
    "St Etienne": "Saint-Etienne",
    "Saint-Etienne": "Saint-Etienne",
    "Strasbourg": "Strasbourg",
    "Montpellier": "Montpellier",
    "Toulouse": "Toulouse",
    "Reims": "Reims",
    "Lens": "Lens",
    "Brest": "Brest",
    "Troyes": "Troyes",
    "Lorient": "Lorient",
    "Angers": "Angers",
    "Clermont": "Clermont",
    "Auxerre": "Auxerre",
    "Le Havre": "LeHavre",
    "Metz": "Metz",
    "Caen": "Caen",
    "Dijon": "Dijon",
    "Amiens": "Amiens",
    "Nimes": "Nimes",
    "Guingamp": "Guingamp",
    "Bastia": "Bastia",
    "Ajaccio": "Ajaccio",
    "Ajaccio GFCO": "Ajaccio",
    "GFC Ajaccio": "Ajaccio",
    "Evian Thonon Gaillard": "EvianTG",
    # Eredivisie
    "Ajax": "Ajax",
    "PSV Eindhoven": "PSV",
    "PSV": "PSV",
    "Feyenoord": "Feyenoord",
    "AZ Alkmaar": "AZ",
    "AZ": "AZ",
    "Utrecht": "Utrecht",
    "Twente": "Twente",
    "Vitesse": "Vitesse",
    "Heerenveen": "Heerenveen",
    "Groningen": "Groningen",
    "Heracles": "Heracles",
    "Sparta Rotterdam": "Sparta",
    "PEC Zwolle": "Zwolle",
    "Zwolle": "Zwolle",
    "Excelsior": "Excelsior",
    "Willem II": "WillemII",
    "Go Ahead Eagles": "GAEagles",
    "Fortuna Sittard": "Sittard",
    "NEC Nijmegen": "NEC",
    "NEC": "NEC",
    "RKC Waalwijk": "Waalwijk",
    "Almere City": "Almere",
    "FC Volendam": "Volendam",
    "Volendam": "Volendam",
    "Cambuur": "Cambuur",
    "ADO Den Haag": "DenHaag",
    "Den Haag": "DenHaag",
    "Roda JC": "Roda",
    # Primeira Liga
    "Benfica": "Benfica",
    "Porto": "Porto",
    "Sporting": "Sporting",
    "Sp Lisbon": "Sporting",
    "Sporting CP": "Sporting",
    "Braga": "Braga",
    "Sp Braga": "Braga",
    "Vitoria SC": "GuimaraesVit",
    "Vitoria Guimaraes": "GuimaraesVit",
    "Boavista": "Boavista",
    "Maritimo": "Maritimo",
    "Pacos Ferreira": "Pacos",
    "Pacos": "Pacos",
    "Belenenses": "Belenenses",
    "Setubal": "Setubal",
    "Vit Setubal": "Setubal",
    "Tondela": "Tondela",
    "Aves": "Aves",
    "Portimonense": "Portimonense",
    "Moreirense": "Moreirense",
    "Estoril": "Estoril",
    "Famalicao": "Famalicao",
    "Gil Vicente": "GilVicente",
    "Santa Clara": "SantaClara",
    "Casa Pia": "CasaPia",
    "Estrela": "Estrela",
    "Chaves": "Chaves",
    "Arouca": "Arouca",
    "Rio Ave": "RioAve",
    "Pacos": "Pacos",
    "Nacional": "Nacional",
    "Feirense": "Feirense",
    "AVS": "AVS",
    "Farense": "Farense",
    "Estrela Amadora": "Estrela",
    # Scottish Premiership
    "Celtic": "Celtic",
    "Rangers": "Rangers",
    "Hearts": "Hearts",
    "Aberdeen": "Aberdeen",
    "Hibernian": "Hibernian",
    "Motherwell": "Motherwell",
    "Kilmarnock": "Kilmarnock",
    "St Johnstone": "Johnstone",
    "St Mirren": "StMirren",
    "Dundee": "Dundee",
    "Dundee Utd": "DundeeUnited",
    "Dundee United": "DundeeUnited",
    "Livingston": "Livingston",
    "Ross County": "RossCounty",
    "Hamilton": "Hamilton",
    "Inverness": "Inverness",
    "Partick": "Partick",
    "Falkirk": "Falkirk",
    "Dunfermline": "Dunfermline",
    "Dundee Utd": "DundeeUnited",
    "Livi": "Livingston",
    # Belgio
    "Club Brugge": "ClubBrugge",
    "Anderlecht": "Anderlecht",
    "Genk": "Genk",
    "Gent": "Gent",
    "Standard": "Standard",
    "St Truiden": "Truiden",
    "Sint-Truiden": "Truiden",
    "Sint Truiden": "Truiden",
    "Antwerp": "Antwerp",
    "Charleroi": "Charleroi",
    "Mechelen": "Mechelen",
    "Cercle Brugge": "Cercle",
    "Cercle Brug": "Cercle",
    "Oostende": "Oostende",
    "Kortrijk": "Kortrijk",
    "Eupen": "Eupen",
    "Mouscron": "Mouscron",
    "Waasland-Beveren": "WaaslandBeveren",
    "Beerschot VA": "Beerschot",
    "Beerschot Wilrijk": "Beerschot",
    "Beerschot": "Beerschot",
    "Westerlo": "Westerlo",
    "OH Leuven": "Leuven",
    "Leuven": "Leuven",
    "Seraing": "Seraing",
    "RWDM": "RWDM",
    "Dender": "Dender",
    "Lommel": "Lommel",
    "Roeselare": "Roeselare",
    "Lokeren": "Lokeren",
    # Turchia
    "Galatasaray": "Galatasaray",
    "Fenerbahce": "Fenerbahce",
    "Besiktas": "Besiktas",
    "Trabzonspor": "Trabzonspor",
    "Basaksehir": "Basaksehir",
    "Istanbul Basaksehir": "Basaksehir",
    "Goztepe": "Goztepe",
    "Antalyaspor": "Antalyaspor",
    "Konyaspor": "Konyaspor",
    "Sivasspor": "Sivasspor",
    "Alanyaspor": "Alanyaspor",
    "Kayserispor": "Kayserispor",
    "Gaziantep": "Gaziantep",
    "Gaziantep FK": "Gaziantep",
    "Hatayspor": "Hatayspor",
    "Adana Demirspor": "AdanaDemirspor",
    "Demirspor": "AdanaDemirspor",
    "Rizespor": "Rizespor",
    "Caykur Rizespor": "Rizespor",
    "Samsunspor": "Samsunspor",
    "Pendikspor": "Pendikspor",
    "Karagumruk": "Karagumruk",
    "Fatih Karagumruk": "Karagumruk",
    "Umraniyespor": "Umraniyespor",
    "Bodrum": "Bodrum",
    "Bodrum FK": "Bodrum",
    "Eyupspor": "Eyupspor",
    "Adanaspor": "Adanaspor",
    "Akhisar Belediye": "AkhisarBld",
    "Akhisar": "AkhisarBld",
    "Genclerbirligi": "Genclerbirligi",
    "Bursaspor": "Bursaspor",
    "Osmanlispor": "Osmanlispor",
    "Erzurumspor": "BBErzurum",
    "Yeni Malatyasp": "YeniMalatya",
    "Yeni Malatya": "YeniMalatya",
    "Ankaragucu": "Ankaragucu",
    "Pendik": "Pendikspor",
    "Istanbulspor": "Istanbulspor",
    "Karabukspor": "Karabukspor",
    "Mersin": "Mersin",
    "Goztepe": "Goztepe",
}


# Override per le squadre originariamente non trovate, risolto via fuzzy search
# nel CSV globale ClubElo (vedi find_elo_names.py).
TEAM_NAME_MAPPING_FD_TO_ELO.update({
    "AVS": "AVS Futebol",
    "AZ Alkmaar": "Alkmaar",
    "Ath Madrid": "Atletico",
    "Atletico Madrid": "Atletico",
    "Beerschot VA": "Beerschot AC",
    "Bodrumspor": "Bodrum",
    "Cercle Brugge": "Cercle Brugge",
    "Club Brugge": "Brugge",
    "Ein Frankfurt": "Frankfurt",
    "Estrela": "Estrela Amadora",
    "For Sittard": "Sittard",
    "Fortuna Sittard": "Sittard",
    "Gaziantep": "Gaziantep FK",
    "Holstein Kiel": "Holstein",
    "Kayserispor": "Kayseri",
    "NAC Breda": "Breda",
    "Oud-Heverlee Leuven": "Leuven",
    "Vallecano": "Rayo Vallecano",
    "Werder Bremen": "Werder",
})


def fd_to_elo_team(fd_name: str) -> str:
    """
    Mapping nome Football-Data -> ClubElo.

    L'API ClubElo /api.clubelo.com/{team} richiede il nome SENZA SPAZI
    (es. CercleBrugge, non Cercle Brugge). Il CSV globale invece ha gli spazi.
    Quindi: applichiamo prima il mapping esplicito, poi togliamo sempre gli spazi.
    """
    name = TEAM_NAME_MAPPING_FD_TO_ELO.get(fd_name, fd_name)
    return name.replace(" ", "")
