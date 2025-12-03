import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

def test_scrape_map():
    url = "https://www.transfermarkt.it/virtus-verona/bilanzdetail/verein/29251/saison_id/0/wettbewerb_id//datum_von/0000-00-00/datum_bis/0000-00-00/gegner_id/4271/day/0/plus/1"
    print(f"🔍 SCARICO: {url}")
    
    resp = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(resp.content, "html.parser")
    rows = soup.select("table.items tbody tr")

    print(f"📊 Righe trovate: {len(rows)}")
    
    # Cerchiamo una riga "piena" (es. la terza o la quinta, per evitare quelle future senza risultato)
    # Proviamo la riga 3 (Indice 2) o 5 (Indice 4)
    target_row = None
    for r in rows:
        # Cerchiamo una riga che abbia un risultato numerico (es. contenente ":")
        if ":" in r.get_text() and "-:-" not in r.get_text():
            target_row = r
            break
    
    if not target_row:
        print("❌ Nessuna riga con risultato giocato trovata. Uso la prima disponibile.")
        target_row = rows[0]

    cols = target_row.find_all("td")
    print("\n--- MAPPA INDICI (Per la riga selezionata) ---")
    for i, col in enumerate(cols):
        print(f"[{i}] -> '{col.get_text(strip=True)}'")

if __name__ == "__main__":
    test_scrape_map()
