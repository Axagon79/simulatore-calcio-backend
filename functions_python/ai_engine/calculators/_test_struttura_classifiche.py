"""Verifica struttura table_home e table_away nella collection classifiche."""
import os, sys, json

sys.path.insert(0, 'C:/Progetti/simulatore-calcio-backend/functions_python/ai_engine')
from config import db

# Prendo Eerste Divisie come esempio
doc = db.classifiche.find_one({"league": "Eerste Divisie"}, {"table": 1, "table_home": 1, "table_away": 1})

if not doc:
    print("Eerste Divisie non trovata")
    sys.exit()

print("=== PRIMO ELEMENTO table ===")
if doc.get("table"):
    print(json.dumps(doc["table"][0], indent=2, default=str))

print("\n=== PRIMO ELEMENTO table_home ===")
if doc.get("table_home"):
    print(json.dumps(doc["table_home"][0], indent=2, default=str))

print("\n=== PRIMO ELEMENTO table_away ===")
if doc.get("table_away"):
    print(json.dumps(doc["table_away"][0], indent=2, default=str))
