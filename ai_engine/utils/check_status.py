import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

avail = db["players_availability_tm"]

# TUTTI gli status presenti in Serie C
all_status = avail.distinct("events.status", {"league_code": "ITA3A"})

print("📋 TUTTI GLI STATUS NEL DATABASE:\n")
for status in sorted(all_status):
    print(f"  - {status}")