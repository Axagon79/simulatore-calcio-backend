"""
test_sportradar_explore.py — Trova tutti i season ID da Sportradar/SNAI
Naviga nelle pagine category per trovare i link season delle nostre leghe.
"""
import sys
import os
import time
import re

current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_dir = os.path.dirname(os.path.dirname(current_dir))
if ai_engine_dir not in sys.path:
    sys.path.insert(0, ai_engine_dir)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from scrape_snai_odds import init_driver
from selenium.webdriver.common.by import By

BASE = "https://s5.sir.sportradar.com/snai/it"

# Paesi con category ID (da pagina root) + leghe che cerchiamo
COUNTRIES = [
    {"name": "Italia", "cat_id": 31, "leagues": ["Serie A", "Serie B", "Serie C"]},
    {"name": "Inghilterra", "cat_id": 1, "leagues": ["Premier League", "Championship"]},
    {"name": "Spagna", "cat_id": 32, "leagues": ["La Liga", "Segunda"]},
    {"name": "Germania", "cat_id": 30, "leagues": ["Bundesliga", "2. Bundesliga"]},
    {"name": "Francia", "cat_id": 7, "leagues": ["Ligue 1", "Ligue 2"]},
    {"name": "Olanda", "cat_id": 35, "leagues": ["Eredivisie"]},
    {"name": "Portogallo", "cat_id": 44, "leagues": ["Liga Portugal"]},
    {"name": "Scozia", "cat_id": 22, "leagues": ["Premiership"]},
    {"name": "Svezia", "cat_id": 9, "leagues": ["Allsvenskan"]},
    {"name": "Norvegia", "cat_id": 5, "leagues": ["Eliteserien"]},
    {"name": "Danimarca", "cat_id": 8, "leagues": ["Superliga"]},
    {"name": "Belgio", "cat_id": 33, "leagues": ["Jupiler", "Pro League"]},
    {"name": "Turchia", "cat_id": 46, "leagues": ["Super Lig"]},
    {"name": "Irlanda", "cat_id": 51, "leagues": ["Premier Division"]},
    {"name": "Brasile", "cat_id": 13, "leagues": ["Serie A", "Brasileirao"]},
    {"name": "Argentina", "cat_id": 48, "leagues": ["Primera"]},
    {"name": "Stati Uniti", "cat_id": 26, "leagues": ["MLS"]},
    {"name": "Giappone", "cat_id": 52, "leagues": ["J1"]},
]

driver = init_driver()

try:
    all_seasons = []

    for country in COUNTRIES:
        url = f"{BASE}/category/{country['cat_id']}"
        print(f"\n{'─' * 80}")
        print(f"  🌍 {country['name']} — {url}")
        print(f"{'─' * 80}")

        driver.get(url)
        time.sleep(3)

        # Trova tutti i link nella pagina
        links = driver.find_elements(By.CSS_SELECTOR, "a")
        season_links = []
        for a in links:
            href = a.get_attribute("href") or ""
            text = a.text.strip()
            if "/season/" in href and text:
                season_id = re.search(r'/season/(\d+)', href)
                if season_id:
                    season_links.append({
                        "text": text,
                        "href": href,
                        "season_id": season_id.group(1),
                    })

        if season_links:
            for sl in season_links:
                print(f"    📋 \"{sl['text']}\"  →  season/{sl['season_id']}")
                all_seasons.append({
                    "country": country["name"],
                    "league": sl["text"],
                    "season_id": sl["season_id"],
                    "url": sl["href"],
                })
        else:
            # Forse la pagina mostra tournament links
            all_links = [(a.text.strip(), a.get_attribute("href") or "") for a in links if a.text.strip()]
            print(f"    ⚠️  Nessun /season/ trovato. Link disponibili:")
            for text, href in all_links:
                if "tournament" in href or "category" in href:
                    print(f"       \"{text}\"  →  {href}")

    # RIEPILOGO
    print("\n\n" + "=" * 100)
    print("RIEPILOGO — TUTTI I SEASON ID TROVATI")
    print("=" * 100)
    for s in all_seasons:
        print(f"  {s['country']:20s} | {s['league']:40s} | season/{s['season_id']}")

    print(f"\n  Totale: {len(all_seasons)} stagioni trovate")

finally:
    driver.quit()
    print("\n✅ Fine esplorazione")
