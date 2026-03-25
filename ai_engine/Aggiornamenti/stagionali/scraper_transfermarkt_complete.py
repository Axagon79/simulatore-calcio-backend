import requests
from bs4 import BeautifulSoup
import time
import random
import re
import sys
import unicodedata
from fake_useragent import UserAgent

# CONFIGURAZIONE DB
sys.path.insert(0, r"C:\Progetti\simulatore-calcio-backend")
from config import db
teams_collection = db["teams"]

# TUTTI I CAMPIONATI PRINCIPALI
LEAGUES_CONFIG = [
    #ITALIA
    {
        "name": "Serie A",
        "url_value": "https://www.transfermarkt.it/serie-a/startseite/wettbewerb/IT1",
        "url_age": "https://www.transfermarkt.it/serie-a/altersschnitt/wettbewerb/IT1/plus/1",
    },
    {
        "name": "Serie B",
        "url_value": "https://www.transfermarkt.it/serie-b/startseite/wettbewerb/IT2",
        "url_age": "https://www.transfermarkt.it/serie-b/altersschnitt/wettbewerb/IT2/plus/1",
    },
    {
        "name": "Serie C - Girone A",
        "url_value": "https://www.transfermarkt.it/serie-c-girone-a/startseite/wettbewerb/IT3A",
        "url_age": "https://www.transfermarkt.it/serie-c-girone-a/altersschnitt/wettbewerb/IT3A/plus/1",
    },
    {
        "name": "Serie C - Girone B",
        "url_value": "https://www.transfermarkt.it/serie-c-girone-b/startseite/wettbewerb/IT3B",
        "url_age": "https://www.transfermarkt.it/serie-c-girone-b/altersschnitt/wettbewerb/IT3B/plus/1",
    },
    {
        "name": "Serie C - Girone C",
        "url_value": "https://www.transfermarkt.it/serie-c-girone-c/startseite/wettbewerb/IT3C",
        "url_age": "https://www.transfermarkt.it/serie-c-girone-c/altersschnitt/wettbewerb/IT3C/plus/1",
    },

    # PREMIER LEAGUE
    {
        "name": "Premier League",
        "url_value": "https://www.transfermarkt.it/premier-league/startseite/wettbewerb/GB1",
        "url_age": "https://www.transfermarkt.it/premier-league/altersschnitt/wettbewerb/GB1/plus/1",
    },

    # LA LIGA
    {
        "name": "La Liga",
        "url_value": "https://www.transfermarkt.it/laliga/startseite/wettbewerb/ES1",
        "url_age": "https://www.transfermarkt.it/laliga/altersschnitt/wettbewerb/ES1/plus/1",
    },

    # BUNDESLIGA
    {
        "name": "Bundesliga",
        "url_value": "https://www.transfermarkt.it/bundesliga/startseite/wettbewerb/L1",
        "url_age": "https://www.transfermarkt.it/bundesliga/altersschnitt/wettbewerb/L1/plus/1",
    },

    # LIGUE 1
    {
        "name": "Ligue 1",
        "url_value": "https://www.transfermarkt.it/ligue-1/startseite/wettbewerb/FR1",
        "url_age": "https://www.transfermarkt.it/ligue-1/altersschnitt/wettbewerb/FR1/plus/1",
    },

    # EREDIVISIE
    {
        "name": "Eredivisie",
        "url_value": "https://www.transfermarkt.it/eredivisie/startseite/wettbewerb/NL1",
        "url_age": "https://www.transfermarkt.it/eredivisie/altersschnitt/wettbewerb/NL1/plus/1",
    },

    # LIGA PORTUGAL
    {
        "name": "Liga Portugal",
        "url_value": "https://www.transfermarkt.it/liga-portugal/startseite/wettbewerb/PO1",
        "url_age": "https://www.transfermarkt.it/liga-portugal/altersschnitt/wettbewerb/PO1/plus/1",
    },

    # SUPER LIG
    {
        "name": "Super Lig (Turchia)",
        "url_value": "https://www.transfermarkt.it/super-lig/startseite/wettbewerb/TR1",
        "url_age": "https://www.transfermarkt.it/super-lig/altersschnitt/wettbewerb/TR1/plus/1"
    },

    # EUROPA SERIE B
    {
        "name": "Championship",
        "url_value": "https://www.transfermarkt.it/championship/startseite/wettbewerb/GB2",
        "url_age": "https://www.transfermarkt.it/championship/altersschnitt/wettbewerb/GB2/plus/1"
    },
    {
        "name": "League One",
        "url_value": "https://www.transfermarkt.it/league-one/startseite/wettbewerb/GB3",
        "url_age": "https://www.transfermarkt.it/league-one/altersschnitt/wettbewerb/GB3/plus/1"
    },
    {
        "name": "LaLiga 2",
        "url_value": "https://www.transfermarkt.it/laliga2/startseite/wettbewerb/ES2",
        "url_age": "https://www.transfermarkt.it/laliga2/altersschnitt/wettbewerb/ES2/plus/1"
    },
    {
        "name": "2. Bundesliga",
        "url_value": "https://www.transfermarkt.it/2-bundesliga/startseite/wettbewerb/L2",
        "url_age": "https://www.transfermarkt.it/2-bundesliga/altersschnitt/wettbewerb/L2/plus/1"
    },
    {
        "name": "Ligue 2",
        "url_value": "https://www.transfermarkt.it/ligue-2/startseite/wettbewerb/FR2",
        "url_age": "https://www.transfermarkt.it/ligue-2/altersschnitt/wettbewerb/FR2/plus/1"
    },

    # EUROPA NORDICI
    {
        "name": "Scottish Premiership",
        "url_value": "https://www.transfermarkt.it/premiership/startseite/wettbewerb/SC1",
        "url_age": "https://www.transfermarkt.it/premiership/altersschnitt/wettbewerb/SC1/plus/1"
    },
    {
        "name": "Allsvenskan",
        "url_value": "https://www.transfermarkt.it/allsvenskan/startseite/wettbewerb/SE1",
        "url_age": "https://www.transfermarkt.it/allsvenskan/altersschnitt/wettbewerb/SE1/plus/1"
    },
    {
        "name": "Eliteserien",
        "url_value": "https://www.transfermarkt.it/eliteserien/startseite/wettbewerb/NO1",
        "url_age": "https://www.transfermarkt.it/eliteserien/altersschnitt/wettbewerb/NO1/plus/1"
    },
    {
        "name": "Superligaen",
        "url_value": "https://www.transfermarkt.it/superligaen/startseite/wettbewerb/DK1",
        "url_age": "https://www.transfermarkt.it/superligaen/altersschnitt/wettbewerb/DK1/plus/1"
    },
    {
        "name": "Jupiler Pro League",
        "url_value": "https://www.transfermarkt.it/jupiler-pro-league/startseite/wettbewerb/BE1",
        "url_age": "https://www.transfermarkt.it/jupiler-pro-league/altersschnitt/wettbewerb/BE1/plus/1"
    },
    {
        "name": "League of Ireland Premier Division",
        "url_value": "https://www.transfermarkt.it/premier-league/startseite/wettbewerb/IR1",
        "url_age": "https://www.transfermarkt.it/league-of-ireland-premier-division/altersschnitt/wettbewerb/IR1/plus/1"
    },

    # AMERICHE
    {
        "name": "Brasileirão Serie A",
        "url_value": "https://www.transfermarkt.it/campeonato-brasileiro-serie-a/startseite/wettbewerb/BRA1",
        "url_age": "https://www.transfermarkt.it/campeonato-brasileiro-serie-a/altersschnitt/wettbewerb/BRA1/plus/1"
    },
    {
        "name": "Primera División",
        "url_value": "https://www.transfermarkt.it/primera-division/startseite/wettbewerb/AR1N",
        "url_age": "https://www.transfermarkt.it/primera-division/altersschnitt/wettbewerb/AR1N/plus/1"
    },
    {
        "name": "Major League Soccer",
        "url_value": "https://www.transfermarkt.it/major-league-soccer/startseite/wettbewerb/MLS1",
        "url_age": "https://www.transfermarkt.it/major-league-soccer/altersschnitt/wettbewerb/MLS1/plus/1"
    },

    # NUOVI CAMPIONATI (24/03/2026)
    {
        "name": "League Two",
        "url_value": "https://www.transfermarkt.it/league-two/startseite/wettbewerb/GB4",
        "url_age": "https://www.transfermarkt.it/league-two/altersschnitt/wettbewerb/GB4/plus/1"
    },
    {
        "name": "Veikkausliiga",
        "url_value": "https://www.transfermarkt.it/veikkausliiga/startseite/wettbewerb/FI1",
        "url_age": "https://www.transfermarkt.it/veikkausliiga/altersschnitt/wettbewerb/FI1/plus/1"
    },
    {
        "name": "3. Liga",
        "url_value": "https://www.transfermarkt.it/3-liga/startseite/wettbewerb/L3",
        "url_age": "https://www.transfermarkt.it/3-liga/altersschnitt/wettbewerb/L3/plus/1"
    },
    {
        "name": "Liga MX",
        "url_value": "https://www.transfermarkt.it/liga-mx-clausura/startseite/wettbewerb/MEX1",
        "url_age": "https://www.transfermarkt.it/liga-mx-clausura/altersschnitt/wettbewerb/MEX1/plus/1"
    },
    {
        "name": "Eerste Divisie",
        "url_value": "https://www.transfermarkt.it/eerste-divisie/startseite/wettbewerb/NL2",
        "url_age": "https://www.transfermarkt.it/eerste-divisie/altersschnitt/wettbewerb/NL2/plus/1"
    },
    {
        "name": "Liga Portugal 2",
        "url_value": "https://www.transfermarkt.it/liga-portugal-2/startseite/wettbewerb/PO2",
        "url_age": "https://www.transfermarkt.it/liga-portugal-2/altersschnitt/wettbewerb/PO2/plus/1"
    },
    {
        "name": "1. Lig",
        "url_value": "https://www.transfermarkt.it/1-lig/startseite/wettbewerb/TR2",
        "url_age": "https://www.transfermarkt.it/1-lig/altersschnitt/wettbewerb/TR2/plus/1"
    },
    {
        "name": "Saudi Pro League",
        "url_value": "https://www.transfermarkt.it/saudi-professional-league/startseite/wettbewerb/SA1",
        "url_age": "https://www.transfermarkt.it/saudi-professional-league/altersschnitt/wettbewerb/SA1/plus/1"
    },
    {
        "name": "Scottish Championship",
        "url_value": "https://www.transfermarkt.it/scottish-championship/startseite/wettbewerb/SC2",
        "url_age": "https://www.transfermarkt.it/scottish-championship/altersschnitt/wettbewerb/SC2/plus/1"
    },

    # ASIA
    {
        "name": "J1 League",
        "url_value": "https://www.transfermarkt.it/j1-100-year-vision-league/teilnehmer/pokalwettbewerb/J1YV",
        "url_age": "https://www.transfermarkt.it/j1-100-year-vision-league/teilnehmer/pokalwettbewerb/J1YV"
    },

    # NUOVI CAMPIONATI (24/03/2026)
    {
        "name": "League Two",
        "url_value": "https://www.transfermarkt.it/league-two/startseite/wettbewerb/GB4",
        "url_age": "https://www.transfermarkt.it/league-two/altersschnitt/wettbewerb/GB4/plus/1"
    },
    {
        "name": "Veikkausliiga",
        "url_value": "https://www.transfermarkt.it/veikkausliiga/startseite/wettbewerb/FI1",
        "url_age": "https://www.transfermarkt.it/veikkausliiga/altersschnitt/wettbewerb/FI1/plus/1"
    },
    {
        "name": "3. Liga",
        "url_value": "https://www.transfermarkt.it/3-liga/startseite/wettbewerb/L3",
        "url_age": "https://www.transfermarkt.it/3-liga/altersschnitt/wettbewerb/L3/plus/1"
    },
    {
        "name": "Liga MX",
        "url_value": "https://www.transfermarkt.it/liga-mx/startseite/wettbewerb/MEX1",
        "url_age": "https://www.transfermarkt.it/liga-mx/altersschnitt/wettbewerb/MEX1/plus/1"
    },
    {
        "name": "Eerste Divisie",
        "url_value": "https://www.transfermarkt.it/eerste-divisie/startseite/wettbewerb/NL2",
        "url_age": "https://www.transfermarkt.it/eerste-divisie/altersschnitt/wettbewerb/NL2/plus/1"
    },
    {
        "name": "Liga Portugal 2",
        "url_value": "https://www.transfermarkt.it/liga-portugal-2/startseite/wettbewerb/PO2",
        "url_age": "https://www.transfermarkt.it/liga-portugal-2/altersschnitt/wettbewerb/PO2/plus/1"
    },
    {
        "name": "1. Lig",
        "url_value": "https://www.transfermarkt.it/1-lig/startseite/wettbewerb/TR2",
        "url_age": "https://www.transfermarkt.it/1-lig/altersschnitt/wettbewerb/TR2/plus/1"
    },
    {
        "name": "Saudi Pro League",
        "url_value": "https://www.transfermarkt.it/saudi-pro-league/startseite/wettbewerb/SA1",
        "url_age": "https://www.transfermarkt.it/saudi-pro-league/altersschnitt/wettbewerb/SA1/plus/1"
    },
    {
        "name": "Scottish Championship",
        "url_value": "https://www.transfermarkt.it/scottish-championship/startseite/wettbewerb/SC2",
        "url_age": "https://www.transfermarkt.it/scottish-championship/altersschnitt/wettbewerb/SC2/plus/1"
    },
]

# Normalizzazione nomi Transfermarkt (varie forme -> nome TM "canonico")
TM_NAME_NORMALIZE = {
    # --- SERIE C ITALIA ---
    "Dolomiti": "Dolomiti Bellunesi",
    "Dolomiti Bellunesi": "Dolomiti Bellunesi",

    # Guidonia: DB -> aliases_transfermarkt = "Guidonia Montecelio"
    "Guidonia": "Guidonia Montecelio",
    "Guidonia Montecelio": "Guidonia Montecelio",
    "Guidonia Montecelio 1937 FC": "Guidonia Montecelio",

    # --- PREMIER LEAGUE ---
    "Man City": "Manchester City",
    "Manchester City": "Manchester City",

    "Man Utd": "Manchester Utd.",
    "Manchester Utd.": "Manchester Utd.",

    "Nottm Forest": "Nottm Forest",
    "Nott'm Forest": "Nottm Forest",

    "West Ham Utd.": "West Ham Utd.",
    "West Ham United": "West Ham Utd.",

    # --- LA LIGA ---
    "Elche": "Elche",
    "Elche CF": "Elche",

    "Villarreal": "Villarreal",
    "Villarreal CF": "Villarreal",

    "Valencia": "Valencia",
    "Valencia CF": "Valencia",

    "Levante": "Levante",
    "Levante UD": "Levante",

    "Espanyol": "Espanyol",
    "RCD Espanyol Barcellona": "Espanyol",

    "Alaves": "Alaves",
    "Deportivo Alavés": "Alaves",

    "Real Betis": "Real Betis",
    "Real Betis Balompié": "Real Betis",

    "Atletico Madrid": "Atletico Madrid",
    "Atlético de Madrid": "Atletico Madrid",

    # --- LIGA PORTUGAL ---
    "Guimaraes": "Vit. Guimarães",
    "Vitória Guimarães SC": "Vit. Guimarães",
    "Vit. Guimarães": "Vit. Guimarães",

    "AVS": "Avs FS",
    "Avs FS": "Avs FS",
    "Avs Futebol": "Avs FS",

    "Tondela": "CD Tondela",
    "CD Tondela": "CD Tondela",

    "Estrela Amadora": "CF Estrela Amadora",
    "CF Estrela Amadora": "CF Estrela Amadora",

    "Estoril": "GD Estoril Praia",
    "GD Estoril Praia": "GD Estoril Praia",

    "Nacional": "CD Nacional",
    "CD Nacional": "CD Nacional",

    "Santa Clara": "CD Santa Clara",
    "CD Santa Clara": "CD Santa Clara",

    # --- EREDIVISIE ---
    "Sparta": "Sparta Rotterdam",
    "Sparta R.": "Sparta Rotterdam",
    "Sparta Rotterdam": "Sparta Rotterdam",

    "Go Ahead Eagles": "Go Ahead Eagles Deventer",
    "Go Ahead Eagles Deventer": "Go Ahead Eagles Deventer",

    "Excelsior": "Excelsior Rotterdam",
    "Excelsior Rotterdam": "Excelsior Rotterdam",

    "FC Twente": "FC Twente Enschede",
    "FC Twente Enschede": "FC Twente Enschede",
}

# ----------------- HELPER -----------------

def normalize_text(text: str) -> str:
    """Rimuove gli accenti per confronti più robusti."""
    nfd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")

def clean_tm_name(name: str) -> str:
    """Pulisce il nome Transfermarkt (fallback generico)."""
    name = name.strip()
    name = normalize_text(name)
    name = re.sub(r"^(AC|FC|US|SS|SSC|UC|AS|VfL|1\.|SC|RC|AJ)\s+", "", name)
    name = re.sub(
        r"\s+(FC|AC|Calcio|1905|1912|1919|1920|1936|1966|1945|1928|2000|1908|1911|1899|1846|05|04|SV|SCO|1892|1932|1918|1915|1937|1910|1913|1898)$",
        "",
        name,
    )
    return name.strip()

def clean_money_value(value_str: str) -> float:
    """Converte testi tipo '27,75 mln €' in numero float (€ assoluti)."""
    if not value_str:
        return 0.0
    val = value_str.replace("€", "").strip()
    multiplier = 1.0
    if "mld" in val or "bn" in val:
        multiplier = 1_000_000_000
        val = val.replace("mld", "").replace("bn", "")
    elif "mln" in val or "m" in val:
        multiplier = 1_000_000
        val = val.replace("mln", "").replace("m", "")
    elif "mila" in val or "k" in val:
        multiplier = 1_000
        val = val.replace("mila", "").replace("k", "")
    try:
        val = val.replace(",", ".")
        return float(val) * multiplier
    except Exception:
        return 0.0

def smart_find_team(tm_name: str):
    """
    Trova la squadra nel DB usando:
    1) aliases_transfermarkt (nome esatto Transfermarkt),
    2) name (pulito),
    3) aliases array come fallback.
    """
    # 1) Alias Transfermarkt esatto
    t = teams_collection.find_one({"aliases_transfermarkt": tm_name})
    if t:
        return t

    # 2) Match su name (pulito)
    clean_name = clean_tm_name(tm_name)
    t = teams_collection.find_one({"name": clean_name})
    if t:
        return t

    # 3) Regex su name
    t = teams_collection.find_one(
        {"name": {"$regex": re.escape(clean_name), "$options": "i"}}
    )
    if t:
        return t

    # 4) Dentro aliases array
    t = teams_collection.find_one({"aliases": {"$in": [clean_name, tm_name]}})
    if t:
        return t

    return None

def update_team_data(tm_name: str, data_dict: dict, tm_id: int = None):
    """
    Aggiorna SOLO stats.marketValue / stats.avgAge della squadra trovata.
    Cerca prima per ID (univoco), poi per nome.
    """
    # ✅ PRIMA: Cerca per ID (100% affidabile)
    if tm_id:
        db_team = teams_collection.find_one({"transfermarkt_id": tm_id})
        if db_team:
            update_fields = {}
            for k, v in data_dict.items():
                update_fields[f"stats.{k}"] = v
            
            teams_collection.update_one(
                {"_id": db_team["_id"]},
                {"$set": update_fields},
            )
            return True, db_team
    
    # ❌ FALLBACK: Cerca per nome (vecchio metodo)
    db_team = smart_find_team(tm_name)
    if not db_team:
        return False, None

    update_fields = {}
    for k, v in data_dict.items():
        update_fields[f"stats.{k}"] = v

    teams_collection.update_one(
        {"_id": db_team["_id"]},
        {"$set": update_fields},
    )
    return True, db_team

# ----------------- SCRAPER PER LEGA -----------------

def scrape_league_data(league_conf: dict):
    print(f"\n🌍 {league_conf['name']}...")
    ua = UserAgent()
    headers = {"User-Agent": ua.random}

    # Chiave = nome Transfermarkt normalizzato
    league_stats = {}

    # -------- 1. VALORE DI MERCATO --------
    print("   💰 Scarico Valori...")
    try:
        r = requests.get(league_conf["url_value"], headers=headers, timeout=20)
        if r.status_code == 200:
            soup = BeautifulSoup(r.content, "html.parser")
            
            # ✅ TROVA L'INDICE DELLA COLONNA "Valore rosa"
            headers_row = soup.select("table.items thead tr th")
            value_col_index = None
            
            for idx, th in enumerate(headers_row):
                header_text = th.get_text(strip=True).lower()
                # Cerca "valore rosa" o "valore di mercato" (totale, non medio)
                if "valore rosa" in header_text or \
                "vdm-rosa" in header_text or \
                "vdm rosa" in header_text or \
                ("valore" in header_text and "mercato" in header_text and "ø" not in header_text and "medio" not in header_text):
                    value_col_index = idx
                    break
            
            if value_col_index is None:
                print("   ⚠️ Colonna 'Valore rosa' non trovata")
            else:
                rows = soup.select("table.items tbody tr")
                for row in rows:
                    name_tag = row.find("td", class_="hauptlink")
                    if not name_tag:
                        continue

                    tm_raw = name_tag.text.strip().replace("\n", "")
                    tm_name = TM_NAME_NORMALIZE.get(tm_raw, tm_raw)
                    
                    # ✅ ESTRAI TRANSFERMARKT_ID
                    link_tag = name_tag.find("a")
                    tm_id = None
                    if link_tag and link_tag.get("href"):
                        href = link_tag["href"]
                        if "verein" in href:
                            parts = href.split("/")
                            if len(parts) >= 5:
                                try:
                                    tm_id = int(parts[4])
                                except:
                                    pass

                    # ✅ PRENDI LA CELLA NELLA COLONNA CORRETTA
                    all_cells = row.find_all("td")
                    if len(all_cells) <= value_col_index:
                        continue
                    
                    raw_text = all_cells[value_col_index].text.strip()
                    
                    if "€" not in raw_text:
                        continue

                    market_val = clean_money_value(raw_text)
                    if market_val < 1_000:
                        continue

                    if tm_name not in league_stats:
                        league_stats[tm_name] = {}
                    league_stats[tm_name]["marketValue"] = market_val
                    league_stats[tm_name]["tm_id"] = tm_id
        else:
            print(f"   ⚠️ HTTP {r.status_code} su Valori")
    except Exception as e:
        print(f"   ❌ Err Val: {e}")

    time.sleep(random.uniform(3, 5))

    # -------- 2. ETÀ MEDIA PER PARTITA --------
    print("   🎂 Scarico Età (Per Partita)...")
    try:
        r = requests.get(league_conf["url_age"], headers=headers, timeout=25)
        if r.status_code == 200:
            soup = BeautifulSoup(r.content, "html.parser")
            rows = soup.select("table.items tbody tr")
            for row in rows:
                name_tag = row.find("td", class_="hauptlink")
                if not name_tag:
                    continue

                tm_raw = name_tag.text.strip().replace("\n", "")
                tm_name = TM_NAME_NORMALIZE.get(tm_raw, tm_raw)
                
                # ✅ ESTRAI TRANSFERMARKT_ID (stesso codice di prima)
                link_tag = name_tag.find("a")
                tm_id = None
                if link_tag and link_tag.get("href"):
                    href = link_tag["href"]
                    if "verein" in href:
                        parts = href.split("/")
                        if len(parts) >= 5:
                            try:
                                tm_id = int(parts[4])
                            except:
                                pass

                cells = row.find_all("td", class_="zentriert")
                avg_age = 0.0
                if cells:
                    for cell in reversed(cells):
                        txt = cell.text.strip()
                        if "," in txt and len(txt) < 6:
                            try:
                                val = float(txt.replace(",", "."))
                                if 15.0 < val < 42.0:
                                    avg_age = val
                                    break
                            except Exception:
                                pass

                if avg_age > 0:
                    if tm_name not in league_stats:
                        league_stats[tm_name] = {}
                    league_stats[tm_name]["avgAge"] = avg_age
                    if tm_id and "tm_id" not in league_stats[tm_name]:  # ✅ SALVA ID se non c'è già
                        league_stats[tm_name]["tm_id"] = tm_id
        else:
            print(f"   ⚠️ HTTP {r.status_code} su Età")
    except Exception as e:
        print(f"   ❌ Err Età: {e}")

    # -------- 3. SALVATAGGIO + STAMPA --------
    print("   💾 Aggiornamento DB...")
    for tm_name, stats in league_stats.items():
        val = stats.get("marketValue", 0.0)
        age = stats.get("avgAge", 0.0)
        tm_id = stats.get("tm_id")  # ✅ PRENDI ID

        # ✅ PASSA ID alla funzione
        found, db_team = update_team_data(tm_name, stats, tm_id=tm_id)

        val_str = f"{val:,.0f}€" if val > 0 else "???"
        age_str = f"{age:.1f}" if age > 0 else "??"

        if found and db_team:
            print(f"      ✅ {db_team['name'][:20]:<20} | Val: {val_str:<15} | Età: {age_str}")
        else:
            print(f"      ⚠️ {tm_name[:20]:<20} | Val: {val_str:<15} | Età: {age_str}")

# ----------------- MAIN -----------------

if __name__ == "__main__":
    print("🚀 START SCRAPER (Valore + Età per Partita, tutti i campionati)")
    for league in LEAGUES_CONFIG:
        scrape_league_data(league)
        time.sleep(random.uniform(5, 8))
    print("\n✅ Completato.")