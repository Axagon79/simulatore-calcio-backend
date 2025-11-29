"""
ANALISI MODULI CON CONTEGGIO FINALE
Trova il modulo più utilizzato dopo le conversioni
"""

import pymongo
from collections import Counter

MONGO_URI = "mongodb+srv://Database_User:LPmYAZkzEVxjSaAd@pup-pals-cluster.y1h2r.mongodb.net/"
DB_NAME = "pup_pals_db"

client = pymongo.MongoClient(MONGO_URI)
db = client[DB_NAME]
teams_col = db["teams"]

# Dizionario conversione moduli a 4 cifre
FORMATION_MAPPING = {
    "3-4-2-1": "3-4-3",
    "4-2-2-2": "4-4-2",
    "4-2-3-1": "4-5-1",
    "4-3-1-2": "4-3-3",
}


def convert_formation(formation_str):
    """
    Converte moduli a 4 cifre in 3 cifre usando il mapping
    """
    if not formation_str:
        return None
    
    formation_clean = formation_str.strip()
    
    # Se è nel mapping, converti
    if formation_clean in FORMATION_MAPPING:
        return FORMATION_MAPPING[formation_clean]
    
    # Altrimenti lascia invariato
    return formation_clean


def analyze_formations_with_conversion():
    """
    Analizza tutti i moduli e trova il più comune dopo conversione
    """
    print("\n" + "="*70)
    print("🔍 ANALISI MODULI CON CONVERSIONE")
    print("="*70)
    
    all_teams = list(teams_col.find({}, {"name": 1, "league": 1, "formation": 1, "_id": 0}))
    
    print(f"\n📊 Totale squadre: {len(all_teams)}")
    
    # Conta moduli PRIMA della conversione
    original_formations = []
    converted_formations = []
    missing_count = 0
    
    for team in all_teams:
        original = team.get("formation", None)
        
        if not original:
            missing_count += 1
            continue
        
        original_formations.append(original)
        converted = convert_formation(original)
        converted_formations.append(converted if converted else original)
    
    # RISULTATI PRIMA CONVERSIONE
    print("\n" + "="*70)
    print("📋 TOP 10 MODULI ORIGINALI (prima conversione)")
    print("="*70)
    
    original_counter = Counter(original_formations)
    for formation, count in original_counter.most_common(10):
        percentage = (count / len(all_teams)) * 100
        converted = convert_formation(formation)
        if converted != formation:
            print(f"   {formation:10} → {converted:10} | {count:3} squadre ({percentage:5.1f}%)")
        else:
            print(f"   {formation:10}              | {count:3} squadre ({percentage:5.1f}%)")
    
    # RISULTATI DOPO CONVERSIONE
    print("\n" + "="*70)
    print("🎯 TOP 10 MODULI FINALI (dopo conversione)")
    print("="*70)
    
    converted_counter = Counter(converted_formations)
    for formation, count in converted_counter.most_common(10):
        percentage = (count / len(all_teams)) * 100
        print(f"   {formation:10} | {count:3} squadre ({percentage:5.1f}%)")
    
    # MODULO PIÙ COMUNE
    most_common_formation = converted_counter.most_common(1)[0][0]
    most_common_count = converted_counter.most_common(1)[0][1]
    most_common_percentage = (most_common_count / len(all_teams)) * 100
    
    print("\n" + "="*70)
    print("⭐ MODULO DI DEFAULT CONSIGLIATO")
    print("="*70)
    print(f"   Modulo: {most_common_formation}")
    print(f"   Utilizzato da: {most_common_count}/{len(all_teams)} squadre ({most_common_percentage:.1f}%)")
    print(f"   ✅ Questo sarà il modulo di fallback per errori/valori non validi")
    
    # RIEPILOGO
    print("\n" + "="*70)
    print("📊 RIEPILOGO")
    print("="*70)
    print(f"   Totale squadre: {len(all_teams)}")
    print(f"   Con modulo valido: {len(converted_formations)}")
    print(f"   Senza modulo: {missing_count}")
    print(f"   Moduli univoci (dopo conversione): {len(converted_counter)}")
    print(f"   Modulo default: {most_common_formation}")
    print("="*70 + "\n")
    
    return most_common_formation


if __name__ == "__main__":
    default_formation = analyze_formations_with_conversion()
    
    print(f"\n💾 SALVA QUESTO VALORE NEL CODICE:")
    print(f"   DEFAULT_FORMATION = \"{default_formation}\"")
    print()
