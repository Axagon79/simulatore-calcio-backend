import requests
from bs4 import BeautifulSoup

URL = "https://www.centroquote.it/football/italy/serie-a/results/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

print(f"🔍 DEBUG HTML: {URL}")
try:
    resp = requests.get(URL, headers=HEADERS, timeout=10)
    soup = BeautifulSoup(resp.content, "html.parser")

    # Cerchiamo tabelle e righe
    rows = soup.find_all('tr')
    print(f"Trovate {len(rows)} righe totali.")

    count = 0
    for row in rows:
        if count >= 3: break 

        # Filtriamo righe che sembrano contenere dati
        cells = row.find_all('td')
        if len(cells) < 4: continue # Troppo poche per essere match+quote

        count += 1
        print(f"\n--- RIGA {count} ---")
        for i, cell in enumerate(cells):
            txt = cell.get_text(strip=True)
            # Limitiamo output testo lungo
            print(f"Cella [{i}]: '{txt[:50]}'")

except Exception as e:
    print(f"Errore: {e}")