import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config import db

def align_ids():
    print("🔄 Inizio allineamento ID Transfermarkt...")

    # Collezione corretta
    source_col = db['players_availability_tm']
    teams_col = db['teams']

    print(f"   🔍 Scansione {source_col.name} per trovare team_id...")

    # Mappa: Nome Squadra -> ID Transfermarkt
    name_to_id = {}
    
    try:
        # Leggiamo TUTTI i nomi squadra disponibili nella collezione giocatori
        cursor = source_col.find(
            {"team_id": {"$exists": True}, "team_name": {"$exists": True}},
            {"team_id": 1, "team_name": 1, "team_slug": 1}
        )
        
        for doc in cursor:
            t_name = doc.get("team_name")
            t_id = doc.get("team_id")
            t_slug = doc.get("team_slug", "")
            
            if t_name and t_id:
                t_name = t_name.strip()
                # Salviamo la prima occorrenza che troviamo
                if t_name not in name_to_id:
                    name_to_id[t_name] = {"id": t_id, "slug": t_slug}

    except Exception as e:
        print(f"   ⚠️ Errore scansione: {e}")
        return

    print(f"   ✅ Trovati {len(name_to_id)} ID univoci da usare come riferimento.")

    # 2. Aggiorniamo teams
    print("   💾 Aggiornamento collezione 'teams'...")
    
    updated = 0
    missing = 0

    all_teams = teams_col.find({})
    
    for team in all_teams:
        db_name = team.get("name")
        tm_alias = team.get("aliases_transfermarkt")

        match = None

        # 1. TENTATIVO ALIAS TRANSFERMARKT
        if tm_alias and tm_alias in name_to_id:
            match = name_to_id[tm_alias]
        
        # 2. TENTATIVO DIRETTO
        if not match and db_name in name_to_id:
            match = name_to_id[db_name]
        
        # 3. TENTATIVO VECCHI ALIAS
        if not match:
            aliases = team.get("aliases", [])
            for alias in aliases:
                if alias in name_to_id:
                    match = name_to_id[alias]
                    break
        
        if match:
            teams_col.update_one(
                {"_id": team["_id"]},
                {"$set": {
                    "transfermarkt_id": match["id"],
                    "transfermarkt_slug": match["slug"]
                }}
            )
            updated += 1
        else:
            print(f"      ❌ {db_name} (Alias: {tm_alias}) -> ID NON TROVATO")
            
            # SUGGERIMENTI INTELLIGENTI
            # Cerca nomi simili nella lista dei disponibili
            possibili = []
            db_clean = db_name.lower().replace("fc", "").strip()
            
            for available_name in name_to_id.keys():
                av_clean = available_name.lower()
                # Se uno contiene l'altro (es. "Arsenal" in "Arsenal FC")
                if db_clean in av_clean or av_clean in db_clean:
                    possibili.append(available_name)
            
            if possibili:
                # Limitiamo a 3 suggerimenti per non intasare
                print(f"         💡 Suggerimenti trovati nel DB: {possibili[:3]}")
            
            missing += 1

    print(f"\n🏁 Finito. Aggiornati: {updated} | Mancanti: {missing}")

if __name__ == "__main__":
    align_ids()
