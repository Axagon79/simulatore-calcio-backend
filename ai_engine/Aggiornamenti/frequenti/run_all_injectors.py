import os
import sys
import time
import importlib

# 1. CONFIGURAZIONE PERCORSI
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# Risaliamo alla root del progetto
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(CURRENT_DIR)))
CALCULATORS_PATH = os.path.join(PROJECT_ROOT, "ai_engine", "calculators")

# Aggiungiamo i percorsi per trovare i moduli
sys.path.append(CURRENT_DIR)
sys.path.append(PROJECT_ROOT)
sys.path.append(CALCULATORS_PATH)

def run_all():
    start_time = time.time()
    print(f"\n{'='*70}")
    print(f"🎻 DIRETTORE D'ORCHESTRA - AVVIO AUTOMAZIONE DNA SYSTEM")
    print(f"📅 Data: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")

    try:
        # --- FASE 1: ATTACCO E DIFESA ---
        # File: injector_att_def_dna.py
        print("\n🔹 [1/4] Caricamento 'injector_att_def_dna'...")
        try:
            inj_att_def = importlib.import_module("injector_att_def_dna")
            
            # Chiama la funzione con modalità silenziosa (interactive=False)
            if hasattr(inj_att_def, 'run_injection_att_def'):
                inj_att_def.run_injection_att_def(interactive=False)
            else:
                # Fallback per sicurezza
                print("⚠️  Attenzione: Funzione principale non trovata, provo legacy...")
                if hasattr(inj_att_def, 'run_injection_v3'):
                    inj_att_def.run_injection_v3()
                
            print("✅ Fase 1 (ATT/DEF) completata.")
        except Exception as e:
            print(f"❌ ERRORE CRITICO FASE 1: {e}")

        # --- FASE 2: TECNICA E FORMAZIONI ---
        # File: injector_dna_tec_e_formazioni.py
        print("\n🔹 [2/4] Caricamento 'injector_dna_tec_e_formazioni'...")
        try:
            # Carichiamo ESATTAMENTE il nome del file che mi hai dato
            inj_tec = importlib.import_module("injector_dna_tec_e_formazioni")
            
            # Chiama la funzione con modalità silenziosa (interactive=False)
            if hasattr(inj_tec, 'run_injection'):
                inj_tec.run_injection(interactive=False)
            else:
                print("❌ Errore: Funzione 'run_injection' non trovata in injector_dna_tec_e_formazioni.")
                
            print("✅ Fase 2 (TEC/FORM) completata.")
        except ImportError:
            print(f"❌ ERRORE IMPORT FASE 2: Non trovo il file 'injector_dna_tec_e_formazioni.py'.")
        except Exception as e:
            print(f"❌ ERRORE CRITICO FASE 2: {e}")

        # --- FASE 3: VALORE ROSA ---
        # File: injector_dna_val.py
        print("\n🔹 [3/4] Caricamento 'injector_dna_val'...")
        try:
            inj_val = importlib.import_module("injector_dna_val")
            
            # MODIFICA FONDAMENTALE: interactive=False
            # Così non mostra il menu e fa tutti i campionati in automatico
            if hasattr(inj_val, 'run_injection_val'):
                inj_val.run_injection_val(interactive=False)
                print("✅ Fase 3 (VAL) completata.")
            else:
                print("⚠️ Funzione 'run_injection_val' non trovata.")
        except ImportError:
            print("⚠️ Modulo 'injector_dna_val' non trovato (saltato).")
        except Exception as e:
            print(f"❌ ERRORE CRITICO FASE 3: {e}")

        # --- FASE 4: FORMAZIONI NO-FBREF (Serie C + Liga Portugal 2 + 1. Lig) ---
        print("\n🔹 [4/4] Formazioni No-FBref (Sportradar)...")
        try:
            from scrape_sportradar_serie_c import scrape_all_teams, inject_formations
            scrape_all_teams()
            inject_formations()
            print("✅ Fase 4 (No-FBref Sportradar) completata.")
        except ImportError:
            print("⚠️ Modulo 'scrape_sportradar_serie_c' non trovato (saltato).")
        except Exception as e:
            print(f"❌ ERRORE FASE 4: {e}")

        # --- RIEPILOGO FINALE ---
        end_time = time.time()
        elapsed = end_time - start_time
        print(f"\n{'='*70}")
        print(f"🏆 SEQUENZA COMPLETATA IN {elapsed:.2f} secondi.")
        print(f"{'='*70}")

    except Exception as e:
        print(f"\n❌ ERRORE GENERALE DI SISTEMA: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_all()