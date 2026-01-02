import os
import sys
import time
import importlib

# 1. CONFIGURAZIONE PERCORSI
# CURRENT_DIR = ...\ai_engine\Aggiornamenti\frequenti
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# Risaliamo di 3 livelli per arrivare a ...\simulatore-calcio-backend
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(CURRENT_DIR)))

# Percorso verso la cartella dove si trovano i file fisici: ...\ai_engine\calculators
CALCULATORS_PATH = os.path.join(PROJECT_ROOT, "ai_engine", "calculators")

# Aggiungiamo i percorsi al sistema affinché importlib sappia dove guardare
sys.path.append(PROJECT_ROOT)
sys.path.append(CALCULATORS_PATH)

def run_all():
    start_time = time.time()
    print("\n🚀 --- AVVIO AUTOMAZIONE DNA SYSTEM (IMPORT DINAMICO) --- 🚀")

    try:
        # FASE 1: ATT e DIF
        print("➡️  Caricamento iniettore ATT/DIF...")
        inj_att_def = importlib.import_module("injector_att_def_dna")
        inj_att_def.run_injection_v3() #
        print("✅ Fase 1 completata.")

        # FASE 2: TEC e FORMAZIONI
        print("\n➡️  Caricamento iniettore TEC/FORMAZIONI...")
        inj_tec = importlib.import_module("injector_dna_tec_e_formazioni")
        inj_tec.run_injection() #
        print("✅ Fase 2 completata.")

        # FASE 3: VAL
        print("\n➡️  Caricamento iniettore VALORE...")
        inj_val = importlib.import_module("injector_dna_val")
        inj_val.run_injection_val() #
        print("✅ Fase 3 completata.")

        end_time = time.time()
        print(f"\n🏆 TUTTO AGGIORNATO IN {round(end_time - start_time, 2)}s")

    except Exception as e:
        print(f"\n❌ ERRORE DURANTE L'ESECUZIONE: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_all()