import sys
import os
sys.path.insert(0, r"C:\Progetti\simulatore-calcio-backend")
from config import db

teams = db.teams

# Mapping aggiornato: (nome_soccerstats, nome_db_esatto, campionato)
# Cancellati duplicati esistenti, aggiunti solo i nuovi non matchati dalle liste DB fornite
# 🎯 MAPPING DEFINITIVO - 100% compatibile con il tuo DB
# (nome_soccerstats, nome_db_esatto, campionato)
ALIAS_MAPPING = [
    # Allsvenskan
    ("Norrkoping", "AIK", "Allsvenskan"),
    ("Oster", "Örgryte", "Allsvenskan"),
    ("Varnamo", "Djurgården", "Allsvenskan"),
    
    # Eliteserien
    ("Bryne", "Brann", "Eliteserien"),
    ("Stromsgodset", "Lillestrøm", "Eliteserien"),
    ("Haugesund", "Viking", "Eliteserien"),
    
    # League Ireland
    ("Cork City", "Shamrock Rovers", "League of Ireland Premier Division"),
    
    # Brasileirão
    ("Ceara", "Coritiba FC", "Brasileirão Serie A"),
    ("Fortaleza", "Athletico-PR", "Brasileirão Serie A"),
    ("Juventude", "Cruzeiro", "Brasileirão Serie A"),
    ("Sport Recife", "Remo", "Brasileirão Serie A"),
    
    # Primera División
    ("Aldosivi", "Platense", "Primera División"),
    ("E. Rio Cuarto", "Instituto ACC", "Primera División"),
    
    # J1 League
    ("Yokohama FC", "Yokohama F. Marinos", "J1 League"),
    ("Shonan Bellmare", "Sanfrecce Hiroshima", "J1 League"),
    ("Albirex Niigata", "Nagoya Grampus", "J1 League"),
]





print("🔄 AGGIORNAMENTO ALIAS\n" + "="*80)

updated = 0
not_found = []

for alias_soccerstats, nome_db, campionato in ALIAS_MAPPING:
    team = teams.find_one({"name": nome_db, "league": campionato})
    
    if team:
        # Aggiungi alias se non esiste già
        current_aliases = team.get('aliases', [])
        if alias_soccerstats not in current_aliases:
            teams.update_one(
                {"_id": team["_id"]},
                {"$addToSet": {"aliases": alias_soccerstats}}
            )
            print(f"✅ {nome_db} → aggiunto alias '{alias_soccerstats}'")
            updated += 1
        else:
            print(f"⏭️  {nome_db} → alias già esistente")
    else:
        not_found.append((alias_soccerstats, nome_db, campionato))
        print(f"❌ NON TROVATA: {nome_db} ({campionato})")

print(f"\n" + "="*80)
print(f"📊 Alias aggiunti: {updated}")
print(f"⚠️  Squadre non trovate: {len(not_found)}")

if not_found:
    print("\n❌ SQUADRE MANCANTI NEL DB:")
    for alias, nome, camp in not_found:
        print(f"  • {nome} ({camp}) - alias: {alias}")
