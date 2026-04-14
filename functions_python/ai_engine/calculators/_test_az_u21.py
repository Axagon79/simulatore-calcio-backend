"""Verifica AZ Alkmaar U21 in classifiche."""
import os, sys, json

sys.path.insert(0, 'C:/Progetti/simulatore-calcio-backend/functions_python/ai_engine')
from config import db

doc = db.classifiche.find_one({"league": "Eerste Divisie"}, {"table": 1, "table_home": 1, "table_away": 1})

if not doc:
    print("Non trovata")
    sys.exit()

# Cerca AZ in tutte le tabelle
for tbl_key in ["table", "table_home", "table_away"]:
    print(f"\n=== {tbl_key} ===")
    for row in doc.get(tbl_key, []):
        if "AZ" in row.get("team", "") or "Alkmaar" in row.get("team", ""):
            print(json.dumps(row, indent=2, default=str))
