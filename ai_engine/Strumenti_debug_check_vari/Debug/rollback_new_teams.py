"""
Cancella TUTTE le squadre dei nuovi campionati aggiunti
Ripristina il database com'era prima
"""
import sys
sys.path.insert(0, r"C:\Progetti\simulatore-calcio-backend")
from config import db

# Lista dei campionati aggiunti
NEW_LEAGUES = [
    "Championship",
    "LaLiga 2",
    "2. Bundesliga",
    "Ligue 2",
    "Scottish Premiership",
    "Allsvenskan",
    "Eliteserien",
    "Superligaen",
    "Jupiler Pro League",
    "Süper Lig",
    "League of Ireland Premier Division",
    "Brasileirão Serie A",
    "Primera División",
    "Major League Soccer",
    "J1 League"
]

print("🔄 ROLLBACK - Cancellazione squadre nuovi campionati")
print(f"   Campionati da cancellare: {len(NEW_LEAGUES)}\n")

total_deleted = 0

for league in NEW_LEAGUES:
    result = db.teams.delete_many({"league": league})
    if result.deleted_count > 0:
        print(f"   ✅ {league}: {result.deleted_count} squadre cancellate")
        total_deleted += result.deleted_count
    else:
        print(f"   ⏭️  {league}: nessuna squadra trovata")

print(f"\n✅ ROLLBACK COMPLETATO! {total_deleted} squadre totali rimosse")
print("   Database ripristinato com'era prima")