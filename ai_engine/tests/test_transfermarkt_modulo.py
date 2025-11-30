"""
TEST DEBUG - Vediamo cosa scarica realmente
"""

import cloudscraper
from bs4 import BeautifulSoup


def create_scraper():
    scraper = cloudscraper.create_scraper(
        browser={
            "browser": "chrome",
            "platform": "windows",
            "desktop": True,
        },
        delay=10,
    )
    scraper.headers.update({
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.google.com/",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    return scraper


url = "https://www.transfermarkt.it/fc-lumezzane/startseite/verein/4103/saison_id/2025"
scraper = create_scraper()

try:
    resp = scraper.get(url, timeout=40)
    print(f"Status: {resp.status_code}")
    
    # Salva HTML
    with open("transfermarkt_full.html", "w", encoding="utf-8") as f:
        f.write(resp.text)
    
    print("💾 HTML salvato in transfermarkt_full.html")
    print(f"📏 Lunghezza: {len(resp.text)} caratteri")
    
    # Cerca "formation-subtitle" nel testo
    if "formation-subtitle" in resp.text:
        print("✅ 'formation-subtitle' trovato nel HTML!")
    else:
        print("❌ 'formation-subtitle' NON presente")
        
    # Cerca pattern modulo nel testo
    import re
    formations = re.findall(r'\d-\d-\d(?:-\d)?', resp.text)
    if formations:
        print(f"⚽ Pattern moduli trovati: {set(formations)}")
    
except Exception as e:
    print(f"Errore: {e}")
