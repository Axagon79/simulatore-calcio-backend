import sys
import os
sys.path.insert(0, r"C:\Progetti\simulatore-calcio-backend")
from config import db

teams = db.teams

# Lista campionati da verificare
campionati = [
    "Allsvenskan",
    "Eliteserien", 
    "League of Ireland Premier Division",
    "Brasileirão Serie A",
    "Primera División",
    "Major League Soccer",
    "J1 League"
]

print("="*80)
print("SQUADRE NEL DATABASE PER CAMPIONATO")
print("="*80)

for campionato in campionati:
    print(f"\n🏆 {campionato}")
    print("-" * 80)
    
    squadre = teams.find({"league": campionato}, {"name": 1, "aliases": 1}).sort("name", 1)
    
    count = 0
    for sq in squadre:
        aliases = sq.get('aliases', [])
        aliases_str = f" (alias: {', '.join(aliases[:3])})" if aliases else ""
        print(f"  • {sq['name']}{aliases_str}")
        count += 1
    
    print(f"  📊 Totale: {count} squadre")

print("\n" + "="*80)
