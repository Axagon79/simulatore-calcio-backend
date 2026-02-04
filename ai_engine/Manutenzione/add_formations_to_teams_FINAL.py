"""
AGGIUNGI MODULI ALLE SQUADRE - VERSIONE FINALE
Con tutti i nomi esatti dal database
"""

import os
import sys

# FIX PERCORSI - Trova la root del progetto
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.insert(0, current_path)

from config import db

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

    # CHAMPIONSHIP (Inghilterra Serie B)
    "Charlton": "4-2-3-1",
    "QPR": "4-3-3",
    "Derby": "4-2-3-1",
    "Ipswich": "4-2-3-1",
    "Norwich": "4-3-3",
    "Blackburn": "4-2-3-1",
    "Southampton": "4-3-3",
    "Watford": "4-2-3-1",
    "Birmingham": "4-3-3",
    "Leicester City": "4-2-3-1",
    "Coventry City": "4-3-3",
    "Oxford United": "4-4-2",
    "Hull City": "4-2-3-1",
    "Bristol City": "3-5-2",
    "Preston NE": "4-2-3-1",
    "FC Portsmouth": "4-3-3",
    "West Brom": "4-2-3-1",
    "Stoke City": "4-3-3",
    "Wrexham": "4-4-2",
    "Millwall": "4-2-3-1",
    "Swansea City": "4-3-3",
    "Sheff Wed": "4-4-2",
    "Sheff Utd": "3-5-2",
    "Middlesbrough": "4-2-3-1",
    "Cardiff City": "4-3-3",
    "Burnley": "4-4-2",
    "Sunderland": "4-3-3",
    "Leeds Utd": "4-3-3",

    # LALIGA 2 (Spagna Serie B)
    "Almería": "4-2-3-1",
    "Castellón": "4-4-2",
    "Córdoba": "4-2-3-1",
    "Granada": "4-3-3",
    "Las Palmas": "4-3-3",
    "Logroñés": "4-4-2",
    "Mirandés": "4-4-2",
    "Oviedo": "4-2-3-1",
    "Racing Santander": "4-3-3",
    "Sporting Gijón": "4-2-3-1",
    "Tenerife": "4-4-2",
    "Real Valladolid": "4-3-3",
    "Real Zaragoza": "4-2-3-1",
    "Cartagena": "4-4-2",
    "Eldense": "4-3-3",
    "Eibar": "4-2-3-1",
    "Burgos": "4-4-2",
    "Racing Ferrol": "4-3-3",
    "Albacete": "4-4-2",
    "Huesca": "4-3-3",
    "Real Sociedad B": "4-3-3",
    "Deportivo": "4-3-3",

    # 2. BUNDESLIGA (Germania Serie B)
    "Greuther Fürth": "4-2-3-1",
    "Magdeburgo": "4-4-2",
    "Pr. Münster": "4-3-3",
    "VfL Bochum": "4-3-3",
    "Elversberg": "4-4-2",
    "Hertha BSC": "4-2-3-1",
    "Paderborn": "4-2-3-1",
    "Norimberga": "4-2-3-1",
    "Schalke 04": "4-2-3-1",
    "Dynamo Dresda": "4-4-2",
    "Darmstadt": "4-3-3",
    "1.FC K'lautern": "4-2-3-1",
    "Karlsruher SC": "4-3-3",
    "Düsseldorf": "4-3-3",
    "Hannover 96": "4-2-3-1",
    "Holstein Kiel": "4-3-3",
    "Arm. Bielefeld": "4-3-3",
    "E. Braunschweig": "4-4-2",

    # LIGUE 2 (Francia Serie B)
    "US Boulogne": "4-3-3",
    "Rodez": "4-4-2",
    "Annecy": "4-3-3",
    "Grenoble": "4-2-3-1",
    "USL Dunkerque": "4-4-2",
    "Guingamp": "4-3-3",
    "Red Star FC": "4-3-3",
    "Pau": "4-2-3-1",
    "Stade Reims": "4-2-3-1",
    "SC Bastia": "4-3-3",
    "Le Mans FC": "4-4-2",
    "Stade Lavallois": "4-3-3",
    "AS Nancy": "4-2-3-1",
    "Troyes": "4-3-3",
    "Saint-Étienne": "4-2-3-1",
    "Montpellier": "4-2-3-1",
    "Amiens": "4-3-3",
    "Clermont Foot": "4-3-3",

    # SCOTTISH PREMIERSHIP (Scozia)
    "Celtic": "4-3-3",
    "Rangers": "4-3-3",
    "Aberdeen": "4-2-3-1",
    "Hearts": "4-3-3",
    "Hibernian": "4-2-3-1",
    "Motherwell": "4-4-2",
    "Dundee United": "4-3-3",
    "Dundee": "4-4-2",
    "Kilmarnock": "4-4-2",
    "St Mirren": "4-3-3",
    "Ross County": "4-4-2",
    "St Johnstone": "4-4-2",

    # ALLSVENSKAN (Svezia)
    "Hammarby": "4-3-3",
    "Mjällby AIF": "4-4-2",
    "Degerfors": "4-4-2",
    "Sirius": "4-3-3",
    "AIK": "4-2-3-1",
    "Halmstads BK": "4-4-2",
    "Kalmar FF": "4-3-3",
    "Västerås SK": "4-4-2",
    "Örgryte": "4-3-3",
    "Malmö FF": "4-3-3",
    "Häcken": "4-2-3-1",
    "Brommapojkarna": "4-4-2",
    "Elfsborg": "4-3-3",
    "IFK Göteborg": "4-3-3",
    "GAIS": "4-4-2",
    "Djurgården": "4-2-3-1",

    # ELITESERIEN (Norvegia)
    "HamKam": "4-4-2",
    "Viking": "4-3-3",
    "Molde": "4-3-3",
    "Rosenborg": "4-2-3-1",
    "Kristiansund": "4-4-2",
    "Brann": "4-3-3",
    "KFUM": "4-4-2",
    "Start": "4-3-3",
    "Sarpsborg 08": "4-4-2",
    "Bodø/Glimt": "4-3-3",
    "Vålerenga": "4-2-3-1",
    "Sandefjord": "4-4-2",
    "Aalesund": "4-3-3",
    "Lillestrøm": "4-3-3",
    "Tromsø": "4-4-2",
    "Fredrikstad": "4-3-3",

    # SUPERLIGAEN (Danimarca)
    "Randers FC": "4-3-3",
    "Vejle BK": "4-4-2",
    "Copenhagen": "4-3-3",
    "Nordsjaelland": "4-3-3",
    "FC Fredericia": "4-4-2",
    "Aarhus GF": "4-3-3",
    "Odense BK": "4-3-3",
    "FC Midtjylland": "4-2-3-1",
    "Viborg FF": "4-4-2",
    "Bröndby IF": "4-3-3",
    "Sönderjyske": "4-4-2",
    "Silkeborg IF": "4-3-3",

    # JUPILER PRO LEAGUE (Belgio)
    "KVC Westerlo": "4-3-3",
    "VV Sint-Truiden": "4-4-2",
    "Zulte Waregem": "4-3-3",
    "FCV Dender EH": "4-4-2",
    "R Charleroi SC": "4-2-3-1",
    "Cercle Bruges": "4-3-3",
    "KAA Gent": "4-3-3",
    "OH Leuven": "4-2-3-1",
    "KRC Genk": "4-3-3",
    "RSC Anderlecht": "4-3-3",
    "Union SG": "3-5-2",
    "La Louvière": "4-4-2",
    "Club Bruges": "4-3-3",
    "Standard Liegi": "4-2-3-1",
    "KV Mechelen": "4-3-3",
    "Anversa": "4-3-3",

    # SÜPER LIG (Turchia)
    "Karagümrük": "4-2-3-1",
    "Antalyaspor": "4-4-2",
    "Samsunspor": "4-3-3",
    "Trabzonspor": "4-2-3-1",
    "Eyüpspor": "4-4-2",
    "Basaksehir": "4-2-3-1",
    "Konyaspor": "4-4-2",
    "Göztepe": "4-3-3",
    "C. Rizespor": "4-4-2",
    "Galatasaray": "4-2-3-1",
    "Besiktas": "4-3-3",
    "Alanyaspor": "4-4-2",
    "Kayserispor": "4-4-2",
    "Kocaelispor": "4-3-3",
    "Gaziantep FK": "4-4-2",
    "Kasimpasa": "4-3-3",
    "Fenerbahce": "4-2-3-1",
    "Genclerbirligi": "4-4-2",

    # LEAGUE OF IRELAND PREMIER DIVISION
    "Drogheda United": "4-4-2",
    "Waterford FC": "4-3-3",
    "St. Pat's": "4-3-3",
    "Galway United": "4-4-2",
    "Derry City": "4-3-3",
    "Dundalk FC": "4-2-3-1",
    "Shelbourne": "4-3-3",
    "Shamrock Rovers": "4-3-3",
    "Sligo Rovers": "4-4-2",
    "Bohemians": "4-3-3",

    # BRASILEIRÃO SERIE A
    "Athletico-PR": "4-2-3-1",
    "Corinthians": "4-2-3-1",
    "Internacional": "4-3-3",
    "Santos": "4-3-3",
    "Flamengo": "4-4-2",
    "Palmeiras": "4-3-3",
    "São Paulo": "4-2-3-1",
    "Botafogo": "4-3-3",
    "Fluminense": "4-2-3-1",
    "Cruzeiro": "4-3-3",
    "Atlético Mineiro": "4-3-3",
    "Grêmio": "4-2-3-1",
    "Vasco da Gama": "4-3-3",
    "Fortaleza": "4-3-3",
    "Bahia": "4-2-3-1",
    "Bragantino": "4-3-3",
    "Cuiabá": "4-4-2",
    "Juventude": "4-4-2",
    "Vitória": "4-3-3",
    "Ceará": "4-4-2",

    # PRIMERA DIVISIÓN (Argentina)
    "River Plate": "4-3-3",
    "Boca Juniors": "4-2-3-1",
    "Racing Club": "4-3-3",
    "Independiente": "4-2-3-1",
    "San Lorenzo": "4-4-2",
    "Vélez Sarsfield": "4-3-3",
    "Estudiantes": "4-4-2",
    "Lanús": "4-2-3-1",
    "Argentinos Juniors": "4-4-2",
    "Talleres": "4-3-3",
    "Belgrano": "4-4-2",
    "Instituto": "4-4-2",
    "Newells Old Boys": "4-3-3",
    "Rosario Central": "4-3-3",
    "Huracán": "4-4-2",
    "Tigre": "4-3-3",
    "Platense": "4-4-2",
    "Defensa y Justicia": "4-3-3",
    "Unión Santa Fe": "4-4-2",
    "Colón": "4-4-2",
    "Banfield": "4-3-3",
    "Gimnasia LP": "4-4-2",
    "Central Córdoba": "4-4-2",
    "Sarmiento": "4-4-2",
    "Barracas Central": "4-4-2",
    "Godoy Cruz": "4-3-3",
    "Atlético Tucumán": "4-4-2",
    "Riestra": "4-4-2",

    # MAJOR LEAGUE SOCCER (USA)
    "New York": "4-2-3-1",
    "New England": "4-4-2",
    "Chicago": "4-3-3",
    "Montréal": "4-2-3-1",
    "Minnesota": "4-3-3",
    "Cincinnati": "4-3-3",
    "Colorado": "4-4-2",
    "Portland": "4-2-3-1",
    "Orlando": "4-2-3-1",
    "Miami": "4-3-3",
    "SJ Earthquakes": "4-4-2",
    "Atlanta": "4-3-3",
    "Salt Lake": "4-3-3",
    "Seattle": "4-2-3-1",
    "Dallas": "4-3-3",
    "Nashville": "4-2-3-1",
    "Houston": "4-3-3",
    "LAFC": "4-3-3",
    "Kansas City": "4-3-3",
    "Columbus": "4-2-3-1",
    "San Diego": "4-3-3",
    "St. Louis CITY": "4-3-3",
    "Vancouver": "4-3-3",
    "Toronto": "4-2-3-1",
    "LA Galaxy": "4-3-3",
    "Charlotte": "4-3-3",
    "Philadelphia": "4-3-3",
    "New York City": "4-3-3",
    "D.C. United": "4-2-3-1",
    "Austin": "4-3-3",

    # J1 LEAGUE (Giappone)
    "Vissel Kobe": "4-3-3",
    "Yokohama F. Marinos": "4-3-3",
    "Urawa Red Diamonds": "4-2-3-1",
    "Kawasaki Frontale": "4-3-3",
    "Kashima Antlers": "4-2-3-1",
    "FC Tokyo": "4-3-3",
    "Nagoya Grampus": "4-2-3-1",
    "Cerezo Osaka": "4-3-3",
    "Gamba Osaka": "4-2-3-1",
    "Sanfrecce Hiroshima": "3-4-2-1",
    "Kashiwa Reysol": "4-3-3",
    "Sagan Tosu": "4-4-2",
    "Shonan Bellmare": "3-4-2-1",
    "Albirex Niigata": "4-3-3",
    "Consadole Sapporo": "4-4-2",
    "Avispa Fukuoka": "4-2-3-1",
    "Kyoto Sanga": "4-3-3",
    "Tokyo Verdy": "4-4-2",
    "Machida Zelvia": "4-4-2",
    "Jubilo Iwata": "4-3-3",
}


def add_formations():
    """Aggiunge il campo formation a tutte le squadre (solo se mancante o diverso)."""

    print("\n" + "="*60)
    print("⚽ AGGIUNGI MODULI ALLE SQUADRE - VERSIONE FINALE")
    print("="*60)

    total_teams = teams_col.count_documents({})
    print(f"\n📊 Squadre totali nel database: {total_teams}")

    updated = 0
    skipped = 0
    not_found = []

    # Itera su tutte le squadre
    for team in teams_col.find({}):
        team_name = team.get("name", "")
        current_formation = team.get("formation")

        new_formation = FORMATIONS.get(team_name)

        if new_formation:
            # Controlla se il modulo è già uguale
            if current_formation == new_formation:
                skipped += 1
                print(f"⏭️  {team_name}: già {new_formation}")
            else:
                teams_col.update_one(
                    {"_id": team["_id"]},
                    {"$set": {"formation": new_formation}}
                )
                updated += 1
                if current_formation:
                    print(f"✅ {team_name}: {current_formation} → {new_formation}")
                else:
                    print(f"✅ {team_name}: (vuoto) → {new_formation}")
        else:
            not_found.append(team_name)
            print(f"❌ {team_name}: MANCA nel dizionario")

    print("\n" + "="*60)
    print(f"✅ COMPLETATO!")
    print(f"   Aggiornate: {updated}")
    print(f"   Già corrette: {skipped}")
    print(f"   Mancanti nel dizionario: {len(not_found)}")
    print("="*60)

    if not_found:
        print(f"\n⚠️  Squadre ancora senza modulo:")
        for name in not_found:
            print(f"   - {name}")


if __name__ == "__main__":
    add_formations()
