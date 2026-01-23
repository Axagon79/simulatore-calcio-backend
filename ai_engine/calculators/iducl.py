import os
import sys

# --- FIX PERCORSI ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db

"""
AGGIUNGE ALIAS FBREF - Europa League
Aggiunge gli alias mancanti per le 3 squadre problematiche
"""

# Squadre e alias da aggiungere (NOMI CORRETTI DAL DB!)
TEAMS_TO_UPDATE = [
    {
        "official_name": "PAOK Salonicco",  # ✅ Corretto da "PAOK Saloniki"
        "alias_to_add": "PAOK"
    },
    {
        "official_name": "Ferencvárosi TC",  # ✅ Corretto da "Ferencvarosi TC" (con accento!)
        "alias_to_add": "Ferencváros"
    },
    {
        "official_name": "Red Bull Salisburgo",  # ✅ Corretto da "Red Bull Salzburg"
        "alias_to_add": "RB Salzburg"
    }
]

def add_alias(team_info):
    """Aggiunge un alias a una squadra"""
    official_name = team_info["official_name"]
    alias = team_info["alias_to_add"]
    
    print(f"\n{'─'*70}")
    print(f"🔧 {official_name}")
    print(f"{'─'*70}")
    
    col = db["teams_europa_league"]
    
    # Verifica se la squadra esiste
    team = col.find_one({"name": official_name})
    
    if not team:
        print(f"   ❌ Squadra NON trovata nel DB!")
        return False
    
    # Controlla se l'alias esiste già
    current_aliases = team.get("aliases", [])
    
    if alias in current_aliases:
        print(f"   ℹ️  Alias '{alias}' già presente")
        return True
    
    # Aggiunge l'alias
    result = col.update_one(
        {"name": official_name},
        {"$addToSet": {"aliases": alias}}
    )
    
    if result.modified_count > 0:
        print(f"   ✅ Alias '{alias}' aggiunto con successo!")
        
        # Verifica
        updated_team = col.find_one({"name": official_name})
        updated_aliases = updated_team.get("aliases", [])
        print(f"   📋 Aliases aggiornati: {updated_aliases}")
        return True
    else:
        print(f"   ⚠️  Nessuna modifica effettuata")
        return False

def main():
    print("\n" + "="*70)
    print("🔧 AGGIUNTA ALIAS FBREF - EUROPA LEAGUE")
    print("="*70)
    
    success_count = 0
    
    for team in TEAMS_TO_UPDATE:
        if add_alias(team):
            success_count += 1
    
    # REPORT FINALE
    print("\n" + "="*70)
    print("📊 REPORT FINALE")
    print("="*70)
    print(f"\n✅ Alias aggiunti: {success_count}/{len(TEAMS_TO_UPDATE)}")
    
    if success_count == len(TEAMS_TO_UPDATE):
        print("\n🎉 PERFETTO! Tutti gli alias sono stati aggiunti!")
        print("\n🚀 PROSSIMO PASSO:")
        print("   Rilancia l'injector per Europa League:")
        print("   python injector_dna_tec_e_formazioni.py")
        print("   Scegli opzione '9' (Europa League)")
    else:
        print(f"\n⚠️  Alcune squadre non sono state aggiornate.")
        print("   Controlla i messaggi sopra per i dettagli.")
    
    print("\n" + "="*70 + "\n")

if __name__ == "__main__":
    main()