import requests
import re
import json
import time
import datetime
import os
from bs4 import BeautifulSoup

# --- CONFIGURAZIONE FILE OUTPUT ---
OUTPUT_FILE = "ai_engine/engine/league_stats.json"

# --- CONFIGURAZIONE URL DOPPIO BINARIO ---
# 1. URL_CURRENT: Stagione in corso (recupera DATE inizio/fine)
# 2. URL_STATS: Stagione passata 2024/2025 (recupera MEDIA GOL consolidata)

# Nota: Se _2025 dà 404 per alcuni campionati minori, significa che SoccerStats 
# usa logiche diverse, ma per ora impostiamo lo standard 2024/25 = _2025.

LEAGUES_CONFIG = {
    "Serie A": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=italy",
        "url_stats":   "https://www.soccerstats.com/latest.asp?league=italy_2025"
    },
    "Serie B": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=italy2",
        "url_stats":   "https://www.soccerstats.com/latest.asp?league=italy2_2025"
    },
    "Serie C - Girone A": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=italy3",
        "url_stats":   "https://www.soccerstats.com/latest.asp?league=italy3_2025"
    },
    "Serie C - Girone B": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=italy4",
        "url_stats":   "https://www.soccerstats.com/latest.asp?league=italy4_2025"
    },
    "Serie C - Girone C": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=italy5",
        "url_stats":   "https://www.soccerstats.com/latest.asp?league=italy5_2025"
    },
    "Premier League": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=england",
        "url_stats":   "https://www.soccerstats.com/latest.asp?league=england_2025"
    },
    "La Liga": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=spain",
        "url_stats":   "https://www.soccerstats.com/latest.asp?league=spain_2025"
    },
    "Bundesliga": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=germany",
        "url_stats":   "https://www.soccerstats.com/latest.asp?league=germany_2025"
    },
    "Ligue 1": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=france",
        "url_stats":   "https://www.soccerstats.com/latest.asp?league=france_2025"
    },
    "Eredivisie": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=netherlands",
        "url_stats":   "https://www.soccerstats.com/latest.asp?league=netherlands_2025"
    },
    "Liga Portugal": {
        "url_current": "https://www.soccerstats.com/latest.asp?league=portugal",
        "url_stats":   "https://www.soccerstats.com/latest.asp?league=portugal_2025"
    }
}

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

def get_dates_from_current(url):
    """Scarica SOLO le date dalla stagione in corso."""
    print(f"   📅 Cerco date su: {url} ...", end="")
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            print(f" ❌ Err {response.status_code}")
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        text = soup.get_text(" ", strip=True)
        
        # Cerca pattern date tipo "17 Aug" o "29 Mar"
        # Spesso appaiono come "Matches played... 17 Aug - 25 May"
        match_date = re.search(r'(\d{1,2}\s(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))', text)
        
        if match_date:
            date_str = match_date.group(1)
            print(f" ✅ Inizio trovato: {date_str}")
            return date_str
        else:
            print(" ⚠️ Data non trovata")
            return None
    except Exception as e:
        print(f" ❌ Errore: {e}")
        return None

def get_stats_from_past(url):
    """Scarica SOLO la media gol dalla stagione passata."""
    print(f"   ⚽ Cerco statistiche su: {url} ...", end="")
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            print(f" ❌ Err {response.status_code}")
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        rows = soup.find_all('tr')
        
        for row in rows:
            text = row.get_text(" ", strip=True)
            if "Goals per match" in text:
                match = re.search(r'Goals per match.*?(\d+\.\d+)', text)
                if match:
                    val = float(match.group(1))
                    print(f" ✅ Media Gol: {val}")
                    return val
        
        print(" ⚠️ Media Gol non trovata")
        return None
    except Exception as e:
        print(f" ❌ Errore: {e}")
        return None

def parse_next_update(date_str):
    """Calcola la data di prossimo aggiornamento (Data Inizio - 15 gg)."""
    if not date_str: return "Manuale"
    try:
        months = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                  'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
        day, month_str = date_str.split()
        month = months.get(month_str)
        
        current_year = datetime.datetime.now().year
        dt_start = datetime.datetime(current_year, month, int(day))
        
        # Se la data d'inizio è già passata quest'anno (es. siamo a Dicembre e inizio era Agosto),
        # allora ci riferiamo all'inizio della PROSSIMA stagione (Agosto prossimo).
        if dt_start < datetime.datetime.now() - datetime.timedelta(days=30): # margine 30gg
             dt_start = dt_start.replace(year=current_year + 1)
        
        dt_check = dt_start - datetime.timedelta(days=15)
        return dt_check.strftime("%Y-%m-%d")
    except:
        return "Manuale"

def main():
    print("🚀 AVVIO AGGIORNAMENTO MEDIE GOL (Metodo Doppio Binario)...")
    print("   1. Link 'Current' -> Per le date")
    print("   2. Link '2025'    -> Per la media gol consolidata\n")
    
    final_stats = {}
    
    for league_name, config in LEAGUES_CONFIG.items():
        print(f"🔍 Elaboro: {league_name}")
        
        # 1. Prendi la data dal campionato IN CORSO
        start_date = get_dates_from_current(config["url_current"])
        
        # 2. Prendi la media gol dal campionato PASSATO
        avg_goals = get_stats_from_past(config["url_stats"])
        
        # Fallback se la media gol non si trova (es. link 404)
        if avg_goals is None:
            print(f"   ⚠️ Fallimento link storico. Provo link corrente per media gol...")
            avg_goals = get_stats_from_past(config["url_current"])
            if avg_goals is None:
                avg_goals = 2.50 # Default estremo
        
        next_update = parse_next_update(start_date)
        
        final_stats[league_name] = {
            "avg_goals": avg_goals,
            "season_start": start_date,
            "next_update_check": next_update,
            "last_updated": datetime.datetime.now().strftime("%Y-%m-%d")
        }
        
        print(f"   💾 Salvato: Media {avg_goals} | Next Check: {next_update}")
        time.sleep(1) 

    # Crea cartella se non esiste
    if not os.path.exists(os.path.dirname(OUTPUT_FILE)):
        os.makedirs(os.path.dirname(OUTPUT_FILE))
        
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_stats, f, indent=4)
    
    print(f"\n✅ AGGIORNAMENTO COMPLETATO. File salvato in: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
