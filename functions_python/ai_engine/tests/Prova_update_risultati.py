import os
import sys
import re
import requests
from bs4 import BeautifulSoup

# --- CONFIGURAZIONE PERCORSI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_dir = os.path.dirname(os.path.dirname(current_dir))
project_root = os.path.dirname(ai_engine_dir)

if ai_engine_dir not in sys.path:
    sys.path.insert(0, ai_engine_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from config import db
    print(f"✅ DB Connesso (Lettura): {db.name}")
except ImportError:
    print("❌ Errore Import Config")
    sys.exit(1)

# --- CONFIGURAZIONE ---
COLLECTION_NAME = "h2h_by_round"
TARGET_SEASON = "2025"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

# Testiamo SOLO la Serie C Girone C dove c'era il problema
LEAGUE_TEST = {"name": "Serie C - Girone C", "url": f"https://www.transfermarkt.it/serie-c-girone-c/gesamtspielplan/wettbewerb/IT3C/saison_id/{TARGET_SEASON}"}

def extract_round_number(text):
    if not text: return None
    match = re.search(r'(\d+)', text)
    return match.group(1) if match else None

def analyze_score_candidate(text):
    """
    Analizza una stringa X:Y e decide se è un Punteggio o un Orario.
    Ritorna (IsScore, Reason)
    """
    if not text or ":" not in text:
        return False, "Formato errato"
    
    parts = text.split(":")
    if len(parts) != 2:
        return False, "Non binario"
        
    try:
        p1 = int(parts[0])
        p2 = int(parts[1])
        
        # LOGICA FILTRO ORARIO
        # Nessuna partita di calcio finisce 14-30 o 20-45.
        # Soglia di sicurezza: 10 gol.
        if p1 > 10 or p2 > 10:
            return False, f"Orario Rilevato ({p1}:{p2} > 10)"
            
        return True, "Punteggio Valido"
    except ValueError:
        return False, "Non numerico"

def test_score_logic():
    print(f"\n🧪 TEST LOGICA ESTRAZIONE PUNTEGGI (SOLA LETTURA)")
    print(f"🌍 Analisi: {LEAGUE_TEST['name']}...\n")
    
    col = db[COLLECTION_NAME]
    
    resp = requests.get(LEAGUE_TEST['url'], headers=HEADERS, timeout=15)
    soup = BeautifulSoup(resp.content, "html.parser")
    headers = soup.find_all("div", class_="content-box-headline")

    for header in headers:
        round_name = header.get_text(strip=True)
        round_num = extract_round_number(round_name)
        
        # Ci concentriamo sulla giornata 19 (quella dello screenshot)
        if round_num != "19": 
            continue

        print(f"   🔍 ANALISI GIORNATA {round_num}")
        
        table = header.find_next("table")
        if not table: continue
        rows = table.find_all("tr")

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 5: continue

            team_links = row.find_all("a", href=lambda x: x and "/verein/" in x)
            if len(team_links) < 2: continue
            
            home = team_links[0].get_text(strip=True)
            away = team_links[-1].get_text(strip=True)
            
            full_row_text = row.get_text(" ", strip=True)
            
            # 1. Trova tutti i candidati "digit:digit" nella riga
            candidates = re.findall(r'(\d+:\d+)', full_row_text)
            
            print(f"      ⚽ {home} vs {away}")
            print(f"         Testo grezzo trovato: {candidates}")
            
            valid_score_found = None
            
            for cand in candidates:
                is_score, reason = analyze_score_candidate(cand)
                if is_score:
                    print(f"         ✅ CANDIDATO '{cand}': ACCETTATO ({reason})")
                    valid_score_found = cand
                    # Se troviamo un punteggio valido, ci fermiamo (priorità al primo valido o logica specifica?)
                    # Solitamente il risultato è centrale, ma testiamo.
                else:
                    print(f"         ⛔ CANDIDATO '{cand}': SCARTATO ({reason})")
            
            if valid_score_found:
                print(f"      🏆 RISULTATO FINALE ELETTO: {valid_score_found}")
            else:
                print(f"      ⚠️ NESSUN RISULTATO VALIDO TROVATO")
            print("-" * 40)

if __name__ == "__main__":
    test_score_logic()