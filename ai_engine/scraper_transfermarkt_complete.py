import requests
from bs4 import BeautifulSoup
import pymongo
import time
import random
import re
import unicodedata
from fake_useragent import UserAgent

# CONFIGURAZIONE DB
MONGO_URI = "mongodb+srv://Database_User:LPmYAZkzEVxjSaAd@pup-pals-cluster.y1h2r.mongodb.net/pup_pals_db?retryWrites=true&w=majority"
client = pymongo.MongoClient(MONGO_URI)
db = client["pup_pals_db"]
teams_collection = db["teams"]

# TUTTI I CAMPIONATI PRINCIPALI (senza Turchia)
LEAGUES_CONFIG = [
    # ITALIA
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

def update_team_data(tm_name: str, data_dict: dict):
    """
    Aggiorna SOLO stats.marketValue / stats.avgAge della squadra trovata.
    Non tocca name, aliases o altri campi.
    """
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
            rows = soup.select("table.items tbody tr")
            for row in rows:
                name_tag = row.find("td", class_="hauptlink")
                if not name_tag:
                    continue

                tm_raw = name_tag.text.strip().replace("\n", "")
                tm_name = TM_NAME_NORMALIZE.get(tm_raw, tm_raw)

                val_cells = row.find_all("td", class_="rechts")
                if not val_cells:
                    continue

                raw_text = val_cells[-1].text.strip()
                if "€" not in raw_text:
                    continue

                market_val = clean_money_value(raw_text)
                if market_val < 1_000:
                    continue

                if tm_name not in league_stats:
                    league_stats[tm_name] = {}
                league_stats[tm_name]["marketValue"] = market_val
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
        else:
            print(f"   ⚠️ HTTP {r.status_code} su Età")
    except Exception as e:
        print(f"   ❌ Err Età: {e}")

    # -------- 3. SALVATAGGIO + STAMPA --------
    print("   💾 Aggiornamento DB...")
    for tm_name, stats in league_stats.items():
        val = stats.get("marketValue", 0.0)
        age = stats.get("avgAge", 0.0)

        found, db_team = update_team_data(tm_name, stats)

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
