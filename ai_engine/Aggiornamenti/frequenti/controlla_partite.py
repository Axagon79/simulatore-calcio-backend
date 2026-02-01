import os
import sys
from datetime import datetime, timedelta

# Imposta i percorsi per trovare la tua configurazione
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.append(project_root)

try:
    from config import db
    print(f"✅ Connesso al database: {db.name}\n")
except Exception as e:
    print(f"❌ Errore connessione: {e}")
    sys.exit()

# Cerca partite iniziate da più di 2 ore ancora in stato 'Scheduled'
soglia = datetime.now() - timedelta(minutes=120)
partite_bloccate = db["h2h_by_round"].find({
    "matches.status": "Scheduled",
    "matches.date_obj": {"$lte": soglia}
})

print("🔍 PARTITE CHE STANNO TENENDO IMPEGNATO IL DIRETTORE:")
found = False
for doc in partite_bloccate:
    for m in doc.get("matches", []):
        if m.get("status") == "Scheduled" and m.get("date_obj") and m["date_obj"] <= soglia:
            print(f"📌 {doc.get('league')} | {m.get('home')} vs {m.get('away')}")
            print(f"   Iniziata il: {m.get('date_obj')}")
            found = True

if not found:
    print("✨ Nessuna partita bloccata trovata. Il database è pulito.")