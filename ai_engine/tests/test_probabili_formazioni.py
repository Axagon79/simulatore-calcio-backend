"""
TEST ACCESSO - probabiliformazioni.it
Verifica se il sito è scrapabile senza Selenium
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
    })
    return scraper


def test_site():
    url = "https://www.probabiliformazioni.it/seriea/"
    
    print(f"\n🔍 Test accesso: {url}")
    
    scraper = create_scraper()
    
    try:
        resp = scraper.get(url, timeout=30)
        print(f"✅ Status Code: {resp.status_code}")
        
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Cerca titolo pagina
            title = soup.find("title")
            print(f"📄 Titolo: {title.text if title else 'Non trovato'}")
            
            # Cerca formazioni (divs, tables, etc)
            matches = soup.find_all("div", class_=lambda x: x and "match" in x.lower() if x else False)
            print(f"🎯 Elementi 'match' trovati: {len(matches)}")
            
            # Stampa primi 500 caratteri HTML per debug
            print("\n📋 Primi 1000 caratteri HTML:")
            print(resp.text[:1000])
            print("\n" + "="*60)
            
            # Salva HTML completo per analisi
            with open("probabili_formazioni_debug.html", "w", encoding="utf-8") as f:
                f.write(resp.text)
            print("💾 HTML completo salvato in: probabili_formazioni_debug.html")
            
        else:
            print(f"❌ Errore HTTP: {resp.status_code}")
            
    except Exception as e:
        print(f"❌ Errore: {e}")


if __name__ == "__main__":
    test_site()
