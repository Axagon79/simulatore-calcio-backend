#!/usr/bin/env python3
"""
Script diagnostico per capire la struttura dei dati H2H
"""
import sys
import os

# Setup path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from config import db

print("="*70)
print("🔍 DIAGNOSTICA H2H - Struttura Dati")
print("="*70)

# 1. Verifica teams_identity
print("\n📋 SAMPLE db.teams_identity:")
sample_identity = db.teams_identity.find_one()
if sample_identity:
    print(f"   _id: {sample_identity.get('_id')}")
    print(f"   canonical_name: {sample_identity.get('canonical_name')}")
    print(f"   all_names: {sample_identity.get('all_names', [])[:3]}...")
else:
    print("   ❌ VUOTA!")

# 2. Verifica raw_h2h_data_v2
print("\n📋 SAMPLE db.raw_h2h_data_v2:")
sample_h2h = db.raw_h2h_data_v2.find_one()
if sample_h2h:
    print(f"   _id: {sample_h2h.get('_id')}")
    print(f"   team_a: {sample_h2h.get('team_a')}")
    print(f"   team_b: {sample_h2h.get('team_b')}")
    print(f"   team_a_id: {sample_h2h.get('team_a_id', 'MISSING!')}")
    print(f"   team_b_id: {sample_h2h.get('team_b_id', 'MISSING!')}")
    print(f"   matches count: {len(sample_h2h.get('matches', []))}")
else:
    print("   ❌ VUOTA!")

# 3. Conta totale
total_h2h = db.raw_h2h_data_v2.count_documents({})
total_identity = db.teams_identity.count_documents({})
print(f"\n📊 TOTALI:")
print(f"   raw_h2h_data_v2: {total_h2h:,} documenti")
print(f"   teams_identity: {total_identity:,} documenti")

# 4. Verifica indici
print(f"\n🔑 INDICI db.raw_h2h_data_v2:")
indexes = db.raw_h2h_data_v2.index_information()
for idx_name, idx_info in indexes.items():
    print(f"   {idx_name}: {idx_info['key']}")

# 5. Test matching Famalicão–Estoril
print(f"\n🧪 TEST MATCHING: Famalicão vs Estoril")

# Cerca in teams_identity
test_names = ["famalicao", "estoril"]
for name in test_names:
    doc = db.teams_identity.find_one({"all_names": name})
    if doc:
        print(f"   ✅ {name} → ID: {doc['_id']} (canonical: {doc.get('canonical_name')})")
    else:
        print(f"   ❌ {name} → NON TROVATO in teams_identity")

# Cerca in raw_h2h_data_v2
h2h_doc = db.raw_h2h_data_v2.find_one({
    "$or": [
        {"team_a": {"$regex": "famalicao", "$options": "i"}},
        {"team_a": {"$regex": "estoril", "$options": "i"}}
    ]
})
if h2h_doc:
    print(f"\n   ✅ Documento H2H trovato:")
    print(f"      team_a: {h2h_doc.get('team_a')}")
    print(f"      team_b: {h2h_doc.get('team_b')}")
    print(f"      team_a_id: {h2h_doc.get('team_a_id', 'MISSING')}")
    print(f"      team_b_id: {h2h_doc.get('team_b_id', 'MISSING')}")
else:
    print(f"\n   ❌ Nessun documento H2H trovato per Famalicão/Estoril")

print("\n" + "="*70)
print("💡 ANALISI:")

if not sample_h2h.get('team_a_id'):
    print("   ⚠️  PROBLEMA: raw_h2h_data_v2 non ha team_a_id/team_b_id")
    print("   📝 SOLUZIONE: Esegui script di popolamento ID (vedi sotto)")
elif not sample_identity:
    print("   ⚠️  PROBLEMA: teams_identity è vuota")
    print("   📝 SOLUZIONE: Popola teams_identity prima")
else:
    print("   ✅ Struttura OK - Problema è nel matching dei nomi")

print("="*70)