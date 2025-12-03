import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

from datetime import datetime

avail = db["players_availability_tm"]

# 🔍 ULTIMI EVENTI (infortunati/squalificati)
print("🔍 GIOCATORI INFORTUNATI/SQUALIFICATI (ultimi eventi):")
injured = []
suspended = []

for doc in avail.find().limit(100):  # Sample
    # Ultimo evento del giocatore
    last_event = doc.get("events", [])[-1] if doc.get("events") else {}
    status = last_event.get("status")
    
    if status == "OUT_INJ":
        injured.append(f"❌ {doc['player_name']} ({doc['team_name']})")
    elif status == "SUSPENDED":
        suspended.append(f"🚫 {doc['player_name']} ({doc['team_name']})")

print(f"\nInfortuni recenti: {len(injured)}")
for i in injured[:10]:
    print(i)

print(f"\nSqualifiche recenti: {len(suspended)}") 
for s in suspended[:10]:
    print(s)