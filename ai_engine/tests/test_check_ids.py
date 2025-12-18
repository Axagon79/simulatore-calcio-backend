# test_check_ids.py
from config import db
from bson import ObjectId

doc = db.raw_h2h_data_v2.find_one({"_id": "Genoa_vs_Inter"})

print(f"📄 Documento: {doc['_id']}")
print(f"   team_a: {doc.get('team_a')}")
print(f"   team_b: {doc.get('team_b')}")
print(f"   team_a_id: {doc.get('team_a_id')}")
print(f"   team_b_id: {doc.get('team_b_id')}")
print(f"\n🔍 Verifica in db.teams:")

# Cerca per ID salvato nel documento
team_a_in_db = db.teams.find_one({"_id": doc.get('team_a_id')})
team_b_in_db = db.teams.find_one({"_id": doc.get('team_b_id')})

print(f"   Team A ({doc.get('team_a_id')}): {team_a_in_db['name'] if team_a_in_db else 'NON TROVATO'}")
print(f"   Team B ({doc.get('team_b_id')}): {team_b_in_db['name'] if team_b_in_db else 'NON TROVATO'}")

print(f"\n🎯 ID che cerchiamo (da test):")
print(f"   Genoa: 69242272d4d47773ce4edbda")
print(f"   Inter: 69235915d4d47773ce4e95e8")

print(f"\n📊 Prime 3 partite storiche:")
for i, m in enumerate(doc['matches'][:3], 1):
    print(f"\n{i}. {m['home_team']} vs {m['away_team']}")
    print(f"   Score: {m.get('score')} | Winner: {m.get('winner')}")
    
    # test_check_ids.py (AGGIUNGI ALLA FINE)

print(f"\n📊 ANALISI 100 PARTITE:")
valid = 0
invalid_score = 0
invalid_winner = 0
old_date = 0

from datetime import datetime, timedelta
cutoff_20y = datetime.now() - timedelta(days=365*20)

for m in doc['matches']:
    score = m.get('score', '-:-')
    winner = m.get('winner', '-')
    date_str = m.get('date')
    
    # Parse data
    try:
        from datetime import datetime
        d_obj = datetime.strptime(date_str, "%d/%m/%Y")
    except:
        d_obj = None
    
    # Conteggi
    if score == "-:-":
        invalid_score += 1
    elif winner == "-":
        invalid_winner += 1
    elif d_obj and d_obj < cutoff_20y:
        old_date += 1
    else:
        valid += 1
        
print(f"   ✅ Partite valide: {valid}")
print(f"   ❌ Score -:-: {invalid_score}")
print(f"   ❌ Winner -: {invalid_winner}")
print(f"   ❌ Troppo vecchie (>20 anni): {old_date}")
print(f"   📊 TOTALE: {len(doc['matches'])}")