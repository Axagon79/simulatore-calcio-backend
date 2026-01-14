import requests
import re
import sys
import json
import time
import datetime
import os
sys.path.insert(0, r"C:\Progetti\simulatore-calcio-backend")
from config import db
from bs4 import BeautifulSoup

# --- CONFIGURAZIONE ---
# Nuova collezione MongoDB
COLLECTION_NAME = "league_stats"

# --- CONFIGURAZIONE CAMPIONATI ESPANSA (26 campionati totali) ---
LEAGUES_CONFIG = {
    # === ITALIA ===
    "Serie A": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=italy",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=italy"
    },
    "Serie B": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=italy2",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=italy2"
    },
    "Serie C - Girone A": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=italy3",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=italy3"
    },
    "Serie C - Girone B": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=italy4",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=italy4"
    },
    "Serie C - Girone C": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=italy5",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=italy5"
    },

    # === TOP 5 EUROPA ===
    "Premier League": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=england",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=england"
    },
    "Championship": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=england2",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=england2"
    },
    "La Liga": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=spain",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=spain"
    },
    "LaLiga 2": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=spain2",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=spain2"
    },
    "Bundesliga": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=germany",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=germany"
    },
    "2. Bundesliga": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=germany2",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=germany2"
    },
    "Ligue 1": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=france",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=france"
    },
    "Ligue 2": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=france2",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=france2"
    },

    # === EUROPA SECONDARIA ===
    "Eredivisie": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=netherlands",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=netherlands"
    },
    "Liga Portugal": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=portugal",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=portugal"
    },
    "Scottish Premiership": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=scotland",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=scotland"
    },
    "Jupiler Pro League": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=belgium",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=belgium"
    },
    "Süper Lig": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=turkey",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=turkey"
    },

    # === NORDICI ===
    "Allsvenskan": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=sweden",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=sweden"
    },
    "Eliteserien": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=norway",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=norway"
    },
    "Superligaen": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=denmark",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=denmark"
    },
    "League of Ireland": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=ireland",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=ireland"
    },

    # === AMERICHE ===
    "Brasileirão": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=brazil",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=brazil"
    },
    "Primera División": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=argentina",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=argentina"
    },
    "MLS": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=usa",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=usa"
    },

    # === ASIA ===
    "J1 League": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=japan",
        "url_stats": "https://www.soccerstats.com/latest.asp?league=japan"
    }
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def get_dates_from_current(url):
    """Scarica SOLO le date dalla stagione in corso."""
    print(f"📅 Cerco date su {url}...", end=" ")
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            print(f"❌ Err {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        match_date = re.search(r"([1-2]?\d (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))", text)
        if match_date:
            date_str = match_date.group(1)
            print(f"✅ Inizio: {date_str}")
            return date_str
        else:
            print("⚠️ Data non trovata")
            return None
    except Exception as e:
        print(f"❌ Errore: {e}")
        return None

def get_stats_from_past(url):
    """Scarica SOLO la media gol dalla stagione passata."""
    print(f"📊 Cerco statistiche su {url}...", end=" ")
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            print(f"❌ Err {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        rows = soup.find_all("tr")

        for row in rows:
            text = row.get_text(" ", strip=True)
            if "Goals per match" in text:
                match = re.search(r"Goals per match.+?(\d+\.\d+)", text)
                if match:
                    val = float(match.group(1))
                    print(f"✅ Media Gol: {val}")
                    return val

        print("⚠️ Media Gol non trovata")
        return None
    except Exception as e:
        print(f"❌ Errore: {e}")
        return None

def parse_next_update(date_str):
    """Calcola la data di prossimo aggiornamento (Data Inizio - 15 gg)."""
    if not date_str:
        return "Manuale"

    try:
        months = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6, 
                  "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}

        day, month_str = date_str.split()
        month = months.get(month_str)

        current_year = datetime.datetime.now().year
        dt_start = datetime.datetime(current_year, month, int(day))

        if dt_start < (datetime.datetime.now() - datetime.timedelta(days=30)):
            dt_start = dt_start.replace(year=current_year + 1)

        dt_check = dt_start - datetime.timedelta(days=15)
        return dt_check.strftime("%Y-%m-%d")
    except:
        return "Manuale"

def main():
    print("=" * 70)
    print("⚽ AGGIORNAMENTO MEDIE GOL - METODO DOPPIO BINARIO v2.0")
    print("=" * 70)
    print("📊 26 Campionati | 💾 Salvataggio MongoDB")
    print("=" * 70)
    print("1️⃣ Link Current → Per le date")
    print("2️⃣ Link 2025 → Per la media gol consolidata")
    print("=" * 70)

    final_stats = {}

    for league_name, config in LEAGUES_CONFIG.items():
        print(f"\n🏆 Elaboro: {league_name}")

        # 1. Prendi la data dal campionato IN CORSO
        start_date = get_dates_from_current(config["url_current"])

        # 2. Prendi la media gol dal campionato PASSATO
        avg_goals = get_stats_from_past(config["url_stats"])

        # Fallback se la media gol non si trova
        if avg_goals is None:
            print(f"⚠️ Fallimento link storico. Provo link corrente per media gol...")
            avg_goals = get_stats_from_past(config["url_current"])

            if avg_goals is None:
                avg_goals = 2.50  # Default estremo

        next_update = parse_next_update(start_date)

        final_stats[league_name] = {
            "avg_goals": avg_goals,
            "season_start": start_date,
            "next_update_check": next_update,
            "last_updated": datetime.datetime.now().strftime("%Y-%m-%d")
        }

        print(f"✅ Salvato: Media {avg_goals} | Next Check: {next_update}")
        time.sleep(1)  # Pausa per non sovraccaricare il server

    # === SALVATAGGIO MONGODB ===
    print("\n" + "=" * 70)
    print("💾 SALVATAGGIO IN MONGODB...")
    print("=" * 70)

    try:
        from config import db

        for league_name, stats in final_stats.items():
            db[COLLECTION_NAME].update_one(
                {"_id": league_name},
                {"$set": {
                    "avg_goals": stats["avg_goals"],
                    "season_start": stats["season_start"],
                    "next_update_check": stats["next_update_check"],
                    "last_updated": stats["last_updated"]
                }},
                upsert=True
            )
            print(f"✅ {league_name}: {stats['avg_goals']} gol/partita → MongoDB")

        print("=" * 70)
        print(f"🎉 AGGIORNAMENTO COMPLETATO! {len(final_stats)} campionati salvati.")
        print("=" * 70)

    except ImportError:
        print("⚠️ MongoDB non disponibile. Salvo in file JSON locale...")

        # Fallback: salva in file locale
        output_file = os.path.join(os.path.dirname(__file__), "league_stats.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(final_stats, f, indent=4)
        print(f"📁 File salvato in: {output_file}")

if __name__ == "__main__":
    main()