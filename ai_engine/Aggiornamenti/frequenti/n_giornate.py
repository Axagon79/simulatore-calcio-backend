import os
import sys
# --- FIX PERCORSI UNIVERSALE ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)
from config import db
from collections import defaultdict

print("="*100)
print("VERIFICA CORRETTEZZA CAMPO 'country' PER SQUADRA")
print("="*100)

teams_col = db["teams"]

# Mappatura CORRETTA campionato → country
league_country_mapping = {
    # ITALIA
    "Serie A": "Italy",
    "Serie B": "Italy",
    "Serie C - Girone A": "Italy",
    "Serie C - Girone B": "Italy",
    "Serie C - Girone C": "Italy",
    
    # EUROPA TOP
    "Premier League": "England",
    "La Liga": "Spain",
    "Bundesliga": "Germany",
    "Ligue 1": "France",
    "Eredivisie": "Netherlands",
    "Liga Portugal": "Portugal",
    
    # EUROPA SERIE B
    "Championship": "England",
    "LaLiga 2": "Spain",
    "2. Bundesliga": "Germany",
    "Ligue 2": "France",
    
    # EUROPA NORDICI + EXTRA
    "Scottish Premiership": "Scotland",
    "Allsvenskan": "Sweden",
    "Eliteserien": "Norway",
    "Superligaen": "Denmark",
    "Jupiler Pro League": "Belgium",
    "Süper Lig": "Turkey",
    "League of Ireland Premier Division": "Ireland",
    
    # AMERICHE
    "Brasileirão Serie A": "Brazil",
    "Primera División": "Argentina",
    "Major League Soccer": "USA",
    
    # ASIA
    "J1 League": "Japan"
}

print("\n🔍 Verifica in corso...\n")

problemi_trovati = []
campionati_ok = 0
campionati_errati = 0

for league, country_corretto in sorted(league_country_mapping.items()):
    # Trova tutti i country presenti per questo campionato
    countries_trovati = teams_col.distinct("country", {"league": league})
    
    # Rimuovi None e stringhe vuote
    countries_trovati = [c for c in countries_trovati if c]
    
    # Conta teams per country
    teams_per_country = {}
    for country in countries_trovati:
        count = teams_col.count_documents({"league": league, "country": country})
        teams_per_country[country] = count
    
    total_teams = teams_col.count_documents({"league": league})
    
    # CASO 1: Tutti i country sono corretti
    if len(countries_trovati) == 1 and countries_trovati[0] == country_corretto:
        campionati_ok += 1
        continue
    
    # CASO 2: Ci sono problemi
    campionati_errati += 1
    
    problema = {
        "league": league,
        "country_corretto": country_corretto,
        "countries_trovati": countries_trovati,
        "teams_per_country": teams_per_country,
        "total_teams": total_teams
    }
    
    # Trova squadre con country errato
    squadre_errate = list(teams_col.find(
        {
            "league": league,
            "country": {"$ne": country_corretto}
        },
        {"name": 1, "country": 1}
    ))
    
    problema["squadre_errate"] = squadre_errate
    problemi_trovati.append(problema)

print("="*100)
print("📊 RIEPILOGO VERIFICA")
print("="*100)
print(f"   ✅ Campionati corretti:         {campionati_ok}")
print(f"   ❌ Campionati con errori:       {campionati_errati}")
print(f"   {'─'*47}")
print(f"   📊 TOTALE:                      {len(league_country_mapping)}")
print("="*100)

if not problemi_trovati:
    print()
    print("="*100)
    print("✅ TUTTI I CAMPIONATI HANNO IL COUNTRY CORRETTO!")
    print("="*100)
else:
    print()
    print("="*100)
    print("❌ DETTAGLIO PROBLEMI")
    print("="*100)
    
    for p in problemi_trovati:
        print()
        print("─"*100)
        print(f"🔴 {p['league']}")
        print("─"*100)
        print(f"   Country CORRETTO:  {p['country_corretto']}")
        print(f"   Country TROVATI:   {', '.join(p['countries_trovati'])}")
        print(f"   Teams totali:      {p['total_teams']}")
        print()
        print("   Distribuzione:")
        for country, count in p['teams_per_country'].items():
            status = "✅" if country == p['country_corretto'] else "❌"
            print(f"      {status} {country:20s} → {count:2d} teams")
        
        # Mostra squadre errate (max 10)
        if p['squadre_errate']:
            print()
            print(f"   Squadre con country ERRATO ({len(p['squadre_errate'])} totali):")
            for i, team in enumerate(p['squadre_errate'][:10], 1):
                country_attuale = team.get('country', '---')
                print(f"      {i:2d}. {team['name']:40s} | country: {country_attuale}")
            
            if len(p['squadre_errate']) > 10:
                print(f"      ... e altre {len(p['squadre_errate']) - 10} squadre")
    
    print()
    print("="*100)
    print("🔧 CORREZIONE AUTOMATICA")
    print("="*100)
    print()
    
    total_da_correggere = sum(len(p['squadre_errate']) for p in problemi_trovati)
    
    response = input(f"⚠️  Vuoi correggere {total_da_correggere} squadre? (s/n): ").lower()
    
    if response == 's':
        print("\n🔄 Correzione in corso...\n")
        print("="*100)
        
        total_corretti = 0
        
        for p in problemi_trovati:
            league = p['league']
            country_corretto = p['country_corretto']
            
            # Correggi tutte le squadre del campionato con country errato
            result = teams_col.update_many(
                {
                    "league": league,
                    "country": {"$ne": country_corretto}
                },
                {"$set": {"country": country_corretto}}
            )
            
            if result.modified_count > 0:
                print(f"   ✅ {league:45s} → {result.modified_count:2d} teams corretti")
                total_corretti += result.modified_count
        
        print("="*100)
        print()
        print("="*100)
        print("✅ CORREZIONE COMPLETATA!")
        print("="*100)
        print(f"📊 Totale squadre corrette: {total_corretti}")
        print("="*100)
        
        # Verifica finale
        print("\n🔍 Verifica finale...\n")
        print("="*100)
        print("📊 STATO FINALE")
        print("="*100)
        print()
        
        errori_rimanenti = 0
        
        for league, country_corretto in league_country_mapping.items():
            errati = teams_col.count_documents({
                "league": league,
                "country": {"$ne": country_corretto}
            })
            
            if errati > 0:
                errori_rimanenti += errati
                print(f"   ⚠️  {league}: {errati} squadre ancora errate")
        
        if errori_rimanenti == 0:
            print("   ✅ TUTTI I CAMPIONATI HANNO IL COUNTRY CORRETTO!")
        
        print("="*100)
    else:
        print("\n❌ Correzione annullata")
        print("="*100)
