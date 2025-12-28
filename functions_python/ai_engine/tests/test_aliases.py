import os
import sys

# Setup percorsi
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_dir = os.path.dirname(os.path.dirname(current_dir))
project_root = os.path.dirname(ai_engine_dir)

if ai_engine_dir not in sys.path: sys.path.insert(0, ai_engine_dir)
if project_root not in sys.path: sys.path.insert(0, project_root)

try:
    from config import db
    print(f"✅ DB Connesso: {db.name}\n")
except ImportError:
    sys.path.append(r"C:\Progetti\simulatore-calcio-backend\ai_engine")
    try: 
        from config import db
    except: 
        print("❌ Impossibile connettersi al DB")
        sys.exit(1)

# Lista delle squadre problematiche dal tuo report
PROBLEMATIC_TEAMS = [
    "Forlì",
    "Bor. M'gladbach", 
    "Avs FS",
    "Carpi",
    "Ascoli",
    "Perugia",
    "Wolfsburg",
    "Magonza",
    "Dortmund",
    "Sporting",
    "Rio Ave",
    "Nacional"
]

print("="*80)
print("🔍 TEST LETTURA ALIASES DAL DATABASE")
print("="*80)
print("\nVerifichiamo cosa legge lo scraper per ogni squadra problematica:\n")

for team_name in PROBLEMATIC_TEAMS:
    print(f"\n{'='*80}")
    print(f"🏟️  SQUADRA: {team_name}")
    print(f"{'='*80}")
    
    # Cerca nel database (esattamente come fa lo scraper)
    team_doc = db.teams.find_one({"name": team_name})
    
    if not team_doc:
        print(f"❌ NON TROVATA nel database con name='{team_name}'")
        
        # Prova una ricerca case-insensitive
        team_doc_insensitive = db.teams.find_one({"name": {"$regex": f"^{team_name}$", "$options": "i"}})
        if team_doc_insensitive:
            print(f"⚠️  Trovata con nome diverso: '{team_doc_insensitive['name']}'")
            team_doc = team_doc_insensitive
        else:
            # Cerca se esiste in un alias
            team_in_alias = db.teams.find_one({"aliases": team_name})
            if team_in_alias:
                print(f"⚠️  Trovata come alias di: '{team_in_alias['name']}'")
            else:
                print("💡 Suggerimento: Controlla che il nome nel DB sia ESATTAMENTE come quello nel campo 'name'")
            continue
    
    print(f"✅ Trovata nel DB")
    print(f"   Nome esatto nel DB: '{team_doc['name']}'")
    print(f"   Lega: {team_doc.get('league', 'N/A')}")
    
    # Verifica campo aliases
    if 'aliases' in team_doc:
        aliases = team_doc['aliases']
        print(f"\n📋 Campo 'aliases' presente: {type(aliases)}")
        
        if isinstance(aliases, list):
            if aliases:
                print(f"   Numero di aliases: {len(aliases)}")
                print(f"   Aliases:")
                for i, alias in enumerate(aliases, 1):
                    print(f"      {i}. '{alias}' (tipo: {type(alias).__name__})")
            else:
                print(f"   ⚠️ Lista vuota!")
        else:
            print(f"   ❌ ERRORE: 'aliases' non è una lista! È: {type(aliases)}")
            print(f"   Valore: {aliases}")
    else:
        print(f"\n❌ Campo 'aliases' NON PRESENTE nel documento")
        print(f"   Campi disponibili: {list(team_doc.keys())}")
    
    # Mostra anche altri campi alias-like
    if 'aliases_transfermarkt' in team_doc:
        print(f"\n📝 Campo 'aliases_transfermarkt': {team_doc['aliases_transfermarkt']}")

print("\n\n" + "="*80)
print("📊 RIEPILOGO")
print("="*80)

# Conta quante squadre hanno aliases
total = len(PROBLEMATIC_TEAMS)
found = 0
with_aliases = 0

for team_name in PROBLEMATIC_TEAMS:
    team_doc = db.teams.find_one({"name": team_name})
    if team_doc:
        found += 1
        if 'aliases' in team_doc and team_doc['aliases']:
            with_aliases += 1

print(f"Squadre cercate: {total}")
print(f"Squadre trovate nel DB: {found}")
print(f"Squadre con campo 'aliases' compilato: {with_aliases}")
print(f"Squadre SENZA aliases: {found - with_aliases}")

if found - with_aliases > 0:
    print(f"\n⚠️ PROBLEMA IDENTIFICATO:")
    print(f"   Alcune squadre non hanno il campo 'aliases' o è vuoto!")
    print(f"   Lo scraper non può usare aliases che non esistono nel DB.")

print("\n💡 COSA FARE:")
print("   1. Controlla che i nomi nel DB siano ESATTI (maiuscole, accenti, apostrofi)")
print("   2. Verifica che il campo 'aliases' sia un array/lista")
print("   3. Aggiungi gli alias mancanti usando MongoDB Compass")
print("   4. Ricontrolla con questo script prima di rieseguire lo scraper")