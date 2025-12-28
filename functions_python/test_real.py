import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

# Fix: chiama la funzione PRINCIPALE del tuo simulatore
from ai_engine.universal_simulator import universal_simulator  # Nome corretto!

print("🚀 SIMULATORE ORIGINALE CON MENU!")
print("Rispondi alle domande come fai sempre...")

# LANCIA IL TUO MENU INTERATTIVO
if __name__ == "__main__":
    universal_simulator()
