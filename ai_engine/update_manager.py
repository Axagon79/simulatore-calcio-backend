import os
import sys
import subprocess
import time
from datetime import datetime

# ------------------------------------------------------------------------------
# CONFIGURAZIONE PERCORSI
# ------------------------------------------------------------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# Assumendo che questo script sia nella cartella 'Aggiornamenti/frequenti' o 'ai_engine'
# Cerchiamo di determinare le cartelle in modo dinamico ma robusto

# Se il file scraper è nella stessa cartella di questo script:
FREQUENT_DIR = CURRENT_DIR 

# Per i calcolatori, dobbiamo risalire:
# Se siamo in ai_engine/Aggiornamenti/frequenti -> ../../calculators
CALCULATORS_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", "calculators"))

# Controllo di sicurezza: se non esiste la cartella calculators lì, proviamo un livello sopra
if not os.path.exists(CALCULATORS_DIR):
    CALCULATORS_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "calculators"))


# ------------------------------------------------------------------------------
# LISTA DEI TASK (Sequenza precisa 1-13)
# Formato: (Nome_File, Titolo_Display, Spiegazione_Impatto, Cartella_Opzionale)
# ------------------------------------------------------------------------------

SCRAPER_SEQUENCE = [
      ("scraper_results_fbref.py", "📊 [1/13] Risultati & xG (FBref)", "Mancano risultati recenti e xG", FREQUENT_DIR),
      
      # ⭐ NOME FILE CORRETTO APPENA INSERITO ⭐
      ("scrape_lucifero_betexplorer_safe.py", "🔥 [2/13] Lucifero & Serie C (BetExplorer)", "Il Lucifero non funziona senza questo", FREQUENT_DIR),
      
      ("scraper_quote_storiche_betexplorer.py", "💰 [3/13] Quote Storiche", "Calcolo Affidabilità/BVS impossibile", FREQUENT_DIR),
      ("scraper_soccerstats_ranking_unified.py", "🏆 [4/13] Classifica & Gol", "Calcolo Forza Attacco/Difesa sballato", FREQUENT_DIR),
    
      ("fbref_scraper_att.py", "⚽ [5/13] Stats Attaccanti", "Analisi attacco imprecisa", FREQUENT_DIR),
      ("fbref_scraper_mid.py", "🧠 [6/13] Stats Centrocampisti", "Analisi centrocampo imprecisa", FREQUENT_DIR),
      ("fbref_scraper_def.py", "🛡️ [7/13] Stats Difensori", "Analisi difesa imprecisa", FREQUENT_DIR),
      ("scraper_gk_fbref.py", "🧤 [8/13] Stats Portieri", "Analisi portieri imprecisa", FREQUENT_DIR),
    
      ("scraper_tm_multi_campionato.py", "🚑 [9/13] Infortuni (TM)", "Si rischia di puntare su assenti", FREQUENT_DIR),
      ("scraper_calendario_h2h_TF_completo.py", "📅 [10/13] Calendario H2H", "Analisi scontri diretti incompleta", FREQUENT_DIR),
    
      # ⭐ Questo sta nella cartella calculators
      ("calculate_h2h_v2.py", "🧠 [11/13] Elaborazione H2H Pro", "Mancano medie gol e punteggi storici", CALCULATORS_DIR),
    
      ("scraper_fixtures.py", "📆 [12/13] Partite Future", "Il motore non saprà cosa simulare", FREQUENT_DIR),
      ("scraper_odds_oddsmath.py", "💎 [13/13] Quote Future", "Manca confronto con bookmaker", FREQUENT_DIR),
]


# ------------------------------------------------------------------------------
# FUNZIONI DI SERVIZIO
# ------------------------------------------------------------------------------

def run_single_script(filename, description, folder_path):
    # Costruiamo il path completo
    full_path = os.path.join(folder_path, filename)
    print("\n" + "-"*70)
    print(f"▶ {description}")
    
    # Controllo esistenza file
    if not os.path.exists(full_path):
        print(f"❌ Errore: File non trovato in {full_path}")
        return False, "File non trovato"

    start_time = time.time()
    
    try:
        # --- SETUP AMBIENTE UTF-8 ---
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        # ----------------------------

        # Esecuzione script
        subprocess.run(
            [sys.executable, full_path], 
            check=True, capture_output=False, text=True, encoding='utf-8', errors='replace',
            env=env
        )
        
        elapsed = time.time() - start_time
        print(f"   ✅ COMPLETATO in {elapsed:.2f}s")
        return True, None
        
    except subprocess.CalledProcessError as e:
        print("   🔴 ERRORE SCRIPT (Vedi output sopra)")
        return False, "Script fallito (Exit Code != 0)"
        
    except Exception as e:
        return False, str(e)


def main():
    print("\n" + "="*80)
    print("🎩 DIRETTORE D'ORCHESTRA 3.1: ORA CON LUCIFERO")
    print("="*80)

    report = []

    for filename, desc, impact, folder in SCRAPER_SEQUENCE:
        ok, err_msg = run_single_script(filename, desc, folder)
        report.append({
            "file": filename,
            "status": "✅ OK" if ok else "❌ KO",
            "error": err_msg,
            "impact": impact,
            "folder": folder
        })
        if ok: time.sleep(2)


    # --- REPORT FINALE ---
    print("\n\n" + "="*90)
    print("📊 REPORT AGGIORNAMENTO")
    print("="*90)
    print(f"{'STATO':<6} | {'FILE (Script)':<35} | {'IMPATTO (Se fallisce)'}")
    print("-" * 90)

    failures = []
    for item in report:
        print(f"{item['status']:<6} | {item['file']:<35} | {item['impact']}")
        if item['status'] == "❌ KO":
            failures.append(item)


    # --- DETTAGLIO ERRORI ---
    if failures:
        print("\n" + "="*90)
        print("⚠️  ANALISI FALLIMENTI")
        print("="*90)
        for fail in failures:
            print(f"🔴 {fail['file']}")
            print(f"   └─ Errore: {fail['error']}")
            print(f"   └─ Conseguenza: {fail['impact']}")
            print("-" * 40)
    else:
        print("\n✨ SISTEMA PERFETTAMENTE AGGIORNATO (H2H + LUCIFERO)!")

    print("\n")


if __name__ == "__main__":
    main()
