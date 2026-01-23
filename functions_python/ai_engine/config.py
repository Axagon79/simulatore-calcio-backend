# config.py - FILE DI CONFIGURAZIONE CENTRALE
# GESTISCE LA CONNESSIONE A MONGODB CON DOTENV E PERCORSI CORRETTI

import sys
import os
import io
from pathlib import Path
from dotenv import load_dotenv
import pymongo

# ✅ REDIRECT TUTTI I PRINT A STDERR (non vanno in stdout/JSON)
def debug_print(*args, **kwargs):
    print(*args, **kwargs, file=sys.stderr)

# Debug info
debug_print(f" config.py eseguito da: {__file__}")
debug_print(f" Directory corrente: {os.getcwd()}")
debug_print(f" Python path: {sys.path[:3]}")

# 🔥 CORREZIONE CRITICA: PERCORSO .env CORRETTO 🔥
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / '.env'

debug_print(f" BASE_DIR: {BASE_DIR}")
debug_print(f" ENV_PATH: {ENV_PATH}")

# Verifica se .env esiste
if ENV_PATH.exists():
    debug_print(f" .env trovato in: {ENV_PATH}")
else:
    debug_print(f"  .env NON trovato in: {ENV_PATH}")
    current_env = Path.cwd() / '.env'
    if current_env.exists():
        debug_print(f" .env trovato in directory corrente: {current_env}")
        ENV_PATH = current_env
    else:
        debug_print("  Nessun .env trovato. Verrà usata la variabile d'ambiente MONGO_URI")

# Carica le variabili d'ambiente
load_dotenv(dotenv_path=ENV_PATH)

# Ottieni MONGO_URI
MONGO_URI = os.getenv('MONGO_URI')
if not MONGO_URI:
    debug_print(f" ERRORE: MONGO_URI non trovato nel file .env: {ENV_PATH}")
    debug_print("   Contenuto .env (se esiste):")
    if ENV_PATH.exists():
        try:
            with open(ENV_PATH, 'r') as f:
                content = f.read()
                safe_content = content.replace('mongodb://', 'mongodb://***:***@')
                debug_print(safe_content)
        except Exception as e:
            debug_print(f"   Errore lettura .env: {e}")
    
    MONGO_URI = "mongodb://localhost:27017/simulatore_calcio"
    debug_print(f"  Usando MONGO_URI di default: {MONGO_URI.replace('://', '://***:***@')}")

debug_print(" Connessione MongoDB...")

try:
    # Connessione a MongoDB
    client = pymongo.MongoClient(MONGO_URI)
    
    # Estrae il nome del database dalla URI
    db_name = MONGO_URI.rsplit('/', 1)[-1].split('?', 1)[0]
    db = client[db_name]
    
    # Test connessione
    client.admin.command('ping')
    debug_print(f" Connesso a MongoDB: {db_name}")
    
except Exception as e:
    debug_print(f" Errore connessione MongoDB: {e}")
    debug_print("  Assicurati che MongoDB sia in esecuzione!")
    raise

# Conta documenti nelle collezioni principali
debug_print(f" Database: {db_name}")

collections_to_check = ['teams', 'matches_history_betexplorer', 'raw_h2h_data_v2', 'h2h_by_round']
for collection in collections_to_check:
    if collection in db.list_collection_names():
        count = db[collection].count_documents({})
        debug_print(f"    {collection}: {count} documenti")
    else:
        debug_print(f"     {collection}: collezione non trovata")

debug_print(" Configurazione completata con successo")