import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

def test_scrape():
    url = "https://www.transfermarkt.it/virtus-verona/bilanzdetail/verein/29251/saison_id/0/wettbewerb_id//datum_von/0000-00-00/datum_bis/0000-00-00/gegner_id/4271/day/0/plus/1"
    print(f"🔍 SCARICO: {url}")
    
    resp = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(resp.content, "html.parser")
    rows = soup.select("table.items tbody tr")

    print(f"📊 Righe trovate: {len(rows)}")
    
    for i, row in enumerate(rows[:5]): # Guarda le prime 5
        cols = row.find_all("td")
        if len(cols) < 10: continue
        
        date = cols[3].get_text(strip=True)
        sx = cols[5].get_text(strip=True)  # Colonna 5
        res = cols[7].get_text(strip=True) # Colonna 7
        dx = cols[9].get_text(strip=True)  # Colonna 9
        
        print(f"\n--- RIGA {i+1} ({date}) ---")
        print(f"   SINISTRA (Index 5): '{sx}'")
        print(f"   RISULTATO:          '{res}'")
        print(f"   DESTRA (Index 9):   '{dx}'")

if __name__ == "__main__":
    test_scrape()
