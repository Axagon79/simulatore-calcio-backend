import os
import sys
from datetime import datetime

# CONFIGURAZIONE PATH
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
sys.path.append(PROJECT_ROOT)

try:
    from config import db
    print("✅ Connessione al database stabilita.")
except ImportError:
    print("❌ Errore: Assicurati che config.py sia nel percorso corretto.")
    sys.exit(1)

def run_grouped_diagnostic():
    gk_col = db["players_stats_fbref_gk"]
    teams_col = db["teams"]
    
    report_path = os.path.join(CURRENT_DIR, "report_mapping_per_campionato.txt")
    
    # 1. Recupera tutte le leghe uniche presenti nella collezione portieri
    leghe_presenti = gk_col.distinct("league_name")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"REPORT DIAGNOSTICA PER CAMPIONATO (Generato il {datetime.now().strftime('%d/%m/%Y %H:%M')})\n")
        f.write("="*85 + "\n")
        f.write(f"Leghe totali rilevate su FBref GK: {len(leghe_presenti)}\n")
        f.write("="*85 + "\n\n")

        for lega in sorted(leghe_presenti):
            f.write(f"🏆 CAMPIONATO: {lega}\n")
            f.write("-" * 40 + "\n")
            
            # Recupera le squadre uniche per questa specifica lega
            squadre_lega = gk_col.distinct("team_name_fbref", {"league_name": lega})
            
            sincronizzate = 0
            mancanti = []

            for fb_name in squadre_lega:
                if not fb_name: continue
                
                # Cerca in Teams
                query = {
                    "$or": [
                        {"name": fb_name},
                        {"aliases": fb_name},
                        {"aliases_transfermarkt": fb_name}
                    ]
                }
                team_match = teams_col.find_one(query)
                
                if team_match:
                    sincronizzate += 1
                else:
                    mancanti.append(fb_name)
            
            f.write(f"📊 Statistiche: {len(squadre_lega)} squadre totali | ✅ {sincronizzate} OK | ❌ {len(mancanti)} Mancanti\n")
            
            if mancanti:
                f.write("🔍 Squadre da mappare in questo campionato:\n")
                for m in mancanti:
                    f.write(f"   - {m}\n")
            else:
                f.write("✅ Tutte le squadre di questo campionato sono correttamente mappate.\n")
            
            f.write("\n" + "."*85 + "\n\n")

    print(f"🏁 Diagnostica completata per {len(leghe_presenti)} campionati.")
    print(f"📄 Il report dettagliato è pronto: {report_path}")

if __name__ == "__main__":
    run_grouped_diagnostic()