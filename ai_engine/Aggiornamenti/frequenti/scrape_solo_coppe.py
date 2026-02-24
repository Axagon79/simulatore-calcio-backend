"""
scrape_solo_coppe.py — Lancia lo scraper SNAI solo per Champions League + Europa League.
Uso: python scrape_solo_coppe.py  (una tantum, poi si ferma)
"""
import scrape_snai_odds as snai

# Filtra solo le coppe da LEAGUES_CONFIG
original_config = snai.LEAGUES_CONFIG
snai.LEAGUES_CONFIG = [l for l in original_config if l.get('is_cup')]

print(f"Leghe filtrate: {[l['name'] for l in snai.LEAGUES_CONFIG]}")

# Lancia lo scraper (si ferma da solo, niente loop)
snai.run_scraper()

# Ripristina config originale (safety)
snai.LEAGUES_CONFIG = original_config
