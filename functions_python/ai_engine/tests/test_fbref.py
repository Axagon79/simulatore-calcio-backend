import cloudscraper
from bs4 import BeautifulSoup
import time
import random

# URL SERIE A (Solo per test)
URL = "https://fbref.com/en/comps/11/schedule/Serie-A-Scores-and-Fixtures"

def test_debug_xg():
    print(f"🕵️‍♂️ TEST DIAGNOSTICO: Controllo se FBref ci dà gli xG...")
    
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    
    try:
        response = scraper.get(URL)
        print(f"📡 Status Code: {response.status_code}")
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Cerchiamo tabelle
        tables = soup.find_all('table')
        target_table = None
        for t in tables:
            if 'score' in str(t) or 'Risultato' in str(t):
                target_table = t
                break
        
        if not target_table:
            print("❌ ERRORE: Non trovo nessuna tabella dei risultati!")
            return

        rows = target_table.find('tbody').find_all('tr')
        print(f"✅ Tabella trovata. Analizzo le prime 5 partite giocate...\n")
        
        count = 0
        for row in rows:
            if count >= 5: break # Ci bastano 5 esempi
            
            # Ignora intestazioni
            if 'class' in row.attrs and 'thead' in row.attrs['class']: continue
            
            home_team = row.find('td', {'data-stat': 'home_team'})
            score = row.find('td', {'data-stat': 'score'})
            
            # CELLE XG
            xg_home_cell = row.find('td', {'data-stat': 'home_xg'})
            xg_away_cell = row.find('td', {'data-stat': 'away_xg'})
            
            if home_team and score and score.text.strip():
                print(f"⚽ Partita: {home_team.text.strip()} | Risultato: {score.text.strip()}")
                
                # CONTROLLO DIRETTO SUL CONTENUTO HTML
                if xg_home_cell:
                    txt = xg_home_cell.text.strip()
                    print(f"   Variabile xg_home_cell: TROVATA")
                    print(f"   Valore testo dentro: '{txt}'")
                else:
                    print(f"   Variabile xg_home_cell: NON TROVATA (HTML diverso?)")
                
                print("-" * 40)
                count += 1

    except Exception as e:
        print(f"❌ Errore: {e}")

if __name__ == "__main__":
    test_debug_xg()
