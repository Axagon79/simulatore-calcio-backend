import os
import sys
import subprocess
import time
from datetime import datetime, timedelta


# (FA L AGGIORNAMENTO COMPLETO FREQUENTE)
# ------------------------------------------------------------------------------
# (FA L AGGIORNAMENTO COMPLETO FREQUENTE) CONFIGURAZIONE PERCORSI (Adattata alla tua lista esistente)
# ------------------------------------------------------------------------------

# Percorso base del progetto (Fisso)
BASE_PROJECT_DIR = r"C:\Progetti\simulatore-calcio-backend"

# Qui definisco le variabili ESATTAMENTE con i nomi che usi nella lista sotto.
# Così non devi cambiare nulla nella lista.

FREQUENT_DIR = os.path.join(BASE_PROJECT_DIR, "ai_engine", "Aggiornamenti", "frequenti")

CALCULATORS_DIR = os.path.join(BASE_PROJECT_DIR, "ai_engine", "calculators")

# (Questa serve solo se qualche funzione vecchia la usa ancora)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))


# ------------------------------------------------------------------------------
# LISTA DEI TASK (Sequenza precisa 1-13)
# Formato: (Nome_File, Titolo_Display, Spiegazione_Impatto, Cartella_Opzionale)
# ------------------------------------------------------------------------------

SCRAPER_SEQUENCE = [
      ("scraper_results_fbref.py", "📊 [1/13] Risultati & xG (FBref)", "Mancano risultati recenti e xG", FREQUENT_DIR),
      
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
      # ⭐ NUOVO SCRIPT AGGIUNTO QUI ALLA FINE NELLA CARTELLA FREQUENTI
      ("nowgoal_scraper.py", "🚀 [14/14] Quote H2H Arricchite (NowGoal)", "Mancano le quote precise nel CSV", FREQUENT_DIR),
      # ⭐ NUOVO SCRIPT DI DEBUG PER FIX MATCHING QUOTE NOWGOAL
      ("debug_nowgoal_scraper.py", "🚀 [14/14] Fix Quote H2H Debug (NowGoal)", "Mancano le quote precise nel CSV", FREQUENT_DIR),
      
      # ⭐ NUOVO SCRIPT DI DEBUG PER AGGIORNARE SOLO I RISULTATI
      ("per_agg_pianificato_update_results_only.py", "🔄 [15/15] Aggiorna Solo Risultati (Debug)", "Aggiorna solo i risultati senza toccare altro", FREQUENT_DIR),
      
      # NUOVO SCRIPT DI DEBUG PER AGGIORNARE SOLO IL LUCIFERO
      ("cron_update_lucifero.py", "🔥 [16/16] Aggiorna Solo Lucifero (Debug)", "Aggiorna solo il punteggio Lucifero", FREQUENT_DIR),
      
      # NUOVO SCRIPT DI DEBUG PER AGGIORNARE SOLO IL BVS
      ("db_updater_bvs.py", "💎 [17/17] Aggiorna Solo BVS (Debug)", "Aggiorna solo il punteggio BVS", FREQUENT_DIR),
      
      # NUOVO SCRIPT DI DEBUG PER AGGIORNARE SOLO LE CLASSIFICHE
      ("scraper_classifiche_standings.py", "🏆 [18/18] Aggiorna Solo Classifiche (Debug)", "Aggiorna solo le classifiche", FREQUENT_DIR),
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
        return False, "File non trovato", 0.0

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
        return True, None, elapsed
        
    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start_time
        print("   🔴 ERRORE SCRIPT (Vedi output sopra)")
        return False, "Script fallito (Exit Code != 0)", elapsed
        
    except Exception as e:
        return False, str(e), 0.0


def main():
    print("\n" + "="*80)
    print("🎩 DIRETTORE D'ORCHESTRA 3.3: CON CRONOMETRO & DIAGNOSTICA")
    print("="*80)

    report = []
    total_start_time = time.time() # Start Cronometro Globale

    for filename, desc, impact, folder in SCRAPER_SEQUENCE:
        ok, err_msg, duration = run_single_script(filename, desc, folder)
        report.append({
            "file": filename,
            "status": "✅ OK" if ok else "❌ KO",
            "error": err_msg,
            "impact": impact,
            "folder": folder,
            "duration": duration
        })
        if ok: time.sleep(2)

    total_duration_sec = time.time() - total_start_time
    total_duration_str = str(timedelta(seconds=int(total_duration_sec))) # Converte in HH:MM:SS

    # --- REPORT FINALE ---
    print("\n\n" + "="*100)
    print(f"📊 REPORT AGGIORNAMENTO - DURATA TOTALE: {total_duration_str}")
    print("="*100)
    print(f"{'STATO':<6} | {'DURATA':<10} | {'FILE (Script)':<35} | {'IMPATTO (Se fallisce)'}")
    print("-" * 100)

    failures = []
    for item in report:
        dur_str = f"{item['duration']:.1f}s"
        print(f"{item['status']:<6} | {dur_str:<10} | {item['file']:<35} | {item['impact']}")
        if item['status'] == "❌ KO":
            failures.append(item)


    # --- DETTAGLIO ERRORI E SOLUZIONI ---
    if failures:
        print("\n" + "="*90)
        print("⚠️  ANALISI FALLIMENTI & SOLUZIONI")
        print("="*90)
        for fail in failures:
            try:
                rel_path = os.path.relpath(os.path.join(fail['folder'], fail['file']), BASE_PROJECT_DIR)
            except ValueError:
                rel_path = os.path.join(fail['folder'], fail['file'])

            print(f"🔴 {fail['file']}")
            print(f"   └─ Errore: {fail['error']}")
            print(f"   └─ Conseguenza: {fail['impact']}")
            print(f"   └─ 🔧 SOLUZIONE RAPIDA: Copia e lancia questo comando:")
            print(f"      python {rel_path}")
            print("-" * 60)
            
        print("\n❌ L'aggiornamento ha avuto dei problemi. Controlla i comandi sopra.")
    else:
        print(f"\n✨ SISTEMA PERFETTAMENTE AGGIORNATO IN {total_duration_str}!")

    print("\n")


if __name__ == "__main__":
    main()
