#!/usr/bin/env python3
"""
Diagnostica veloce: quali squadre NON matchano
"""
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from config import db

def normalize_name(name):
    if not name:
        return ""
    name = name.lower().strip()
    replacements = {
        "ü": "u", "ö": "o", "ä": "a",
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "á": "a", "à": "a", "â": "a", "ã": "a",
        "í": "i", "ì": "i", "î": "i",
        "ó": "o", "ò": "o", "ô": "o",
        "ú": "u", "ù": "u",
        "ñ": "n", "ç": "c",
    }
    for k, v in replacements.items():
        name = name.replace(k, v)
    return name.strip()

print("🔍 ANALISI RAPIDA SQUADRE MANCANTI")
print("="*70)

# Costruisci cache
cache = {}
for team in db.teams.find({}):
    cache[normalize_name(team['name'])] = team['_id']
    if 'aliases' in team:
        for alias in team['aliases']:
            if alias:
                cache[normalize_name(alias)] = team['_id']

print(f"✅ Cache: {len(cache)} varianti da db.teams")

# Trova squadre uniche in raw_h2h_data_v2
unique_teams = set()
for doc in db.raw_h2h_data_v2.find({}, {"team_a": 1, "team_b": 1}).limit(200):
    if doc.get("team_a"):
        unique_teams.add(doc["team_a"])
    if doc.get("team_b"):
        unique_teams.add(doc["team_b"])

print(f"📊 Analizzate {len(unique_teams)} squadre uniche (prime 200 doc)\n")

# Controlla quali NON matchano
missing = []
found = 0

for team in sorted(unique_teams):
    normalized = normalize_name(team)
    if normalized in cache:
        found += 1
    else:
        missing.append(team)

print(f"✅ Trovate: {found}")
print(f"❌ Mancanti: {len(missing)}\n")

if missing:
    print("⚠️  TOP 20 SQUADRE NON MATCHATE:")
    for team in missing[:20]:
        normalized = normalize_name(team)
        print(f"   • '{team}' → normalizzato: '{normalized}'")
    
    if len(missing) > 20:
        print(f"   ... e altre {len(missing) - 20}")

print("\n" + "="*70)
print("💡 SOLUZIONE:")
print("   1. Aggiungi aliases in db.teams per queste squadre")
print("   2. Oppure usa normalize_name() più aggressivo")
print("="*70)