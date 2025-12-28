#!/usr/bin/env python3
"""
VERSIONE ULTRA-VELOCE: Approccio diretto senza bulk
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

print("="*70)
print("⚡ POPOLAMENTO ULTRA-VELOCE (Update diretti)")
print("="*70)

# Costruisci mapping: nome_raw → team_id
print("\n1️⃣ Costruzione mapping...")
name_to_id = {}

for team in db.teams.find({}):
    team_id = team['_id']
    
    # Nome ufficiale
    name_to_id[team['name']] = team_id
    
    # Aliases
    if 'aliases' in team:
        for alias in team['aliases']:
            if alias:
                name_to_id[alias] = team_id

print(f"   ✅ {len(name_to_id)} mappature pronte")

# Conta quanti mancano
missing = db.raw_h2h_data_v2.count_documents({
    "$or": [
        {"team_a_id": {"$exists": False}},
        {"team_b_id": {"$exists": False}},
        {"team_a_id": None},
        {"team_b_id": None}
    ]
})

print(f"\n📊 Da aggiornare: {missing:,} documenti")

if missing == 0:
    print("✅ Già tutti popolati!")
    exit(0)

# Strategia: Update per nome esatto (VELOCISSIMO)
print("\n2️⃣ Aggiornamento documenti...")
updated = 0
total_teams = len(name_to_id)
current = 0

for team_name, team_id in name_to_id.items():
    current += 1
    
    # Update per team_a
    result_a = db.raw_h2h_data_v2.update_many(
        {
            "team_a": team_name,
            "$or": [
                {"team_a_id": {"$exists": False}},
                {"team_a_id": None}
            ]
        },
        {"$set": {"team_a_id": team_id}}
    )
    
    # Update per team_b
    result_b = db.raw_h2h_data_v2.update_many(
        {
            "team_b": team_name,
            "$or": [
                {"team_b_id": {"$exists": False}},
                {"team_b_id": None}
            ]
        },
        {"$set": {"team_b_id": team_id}}
    )
    
    count = result_a.modified_count + result_b.modified_count
    updated += count
    
    # Progress bar
    pct = (current / total_teams) * 100
    bar_len = int(pct / 2)
    bar = "█" * bar_len + "░" * (50 - bar_len)
    print(f"   [{bar}] {pct:.0f}% | {current}/{total_teams} squadre | {updated} aggiornati", end="\r")

print(f"\n\n📊 RISULTATI:")
print(f"   ✅ Aggiornati: {updated:,}")

# Verifica finale
remaining = db.raw_h2h_data_v2.count_documents({
    "$or": [
        {"team_a_id": {"$exists": False}},
        {"team_b_id": {"$exists": False}},
        {"team_a_id": None},
        {"team_b_id": None}
    ]
})

print(f"   ⏳ Ancora da fare: {remaining:,}")

if remaining > 0:
    print("\n⚠️  Alcuni documenti non hanno match esatto.")
    print("   Probabilmente i nomi in raw_h2h_data_v2 sono diversi da db.teams")

# Crea indici
print("\n3️⃣ Creazione indici...")
try:
    db.raw_h2h_data_v2.create_index([("team_a_id", 1), ("team_b_id", 1)])
    print("   ✅ Indice creato")
except Exception as e:
    print(f"   ⚠️  {e}")

print("\n✅ COMPLETATO!")
print("="*70)