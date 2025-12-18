# config.py - FILE DI CONFIGURAZIONE CENTRALE
# GESTISCE LA CONNESSIONE A MONGODB CON DOTENV E PERCORSI CORRETTI

import sys
import os
import io
from pathlib import Path
from dotenv import load_dotenv
import pymongo

# Debug info
print(f"🔧 config.py eseguito da: {__file__}")
print(f"🔧 Directory corrente: {os.getcwd()}")
print(f"🔧 Python path: {sys.path[:3]}")  # Solo primi 3 per leggibilità

# Forza la stampa in UTF-8 anche su Windows console vecchie
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 🔥 CORREZIONE CRITICA: PERCORSO .env CORRETTO 🔥
# Path assoluto alla root del progetto: .../simulatore-calcio-backend
BASE_DIR = Path(__file__).resolve().parent          # .../simulatore-calcio-backend
ENV_PATH = BASE_DIR / '.env'                       # ✅ CORRETTO: .../simulatore-calcio-backend/.env

print(f"🔧 BASE_DIR: {BASE_DIR}")
print(f"🔧 ENV_PATH: {ENV_PATH}")

# Verifica se .env esiste
if ENV_PATH.exists():
    print(f"✅ .env trovato in: {ENV_PATH}")
else:
    print(f"⚠️  .env NON trovato in: {ENV_PATH}")
    # Cerca .env nella directory corrente come fallback
    current_env = Path.cwd() / '.env'
    if current_env.exists():
        print(f"✅ .env trovato in directory corrente: {current_env}")
        ENV_PATH = current_env
    else:
        print("⚠️  Nessun .env trovato. Verrà usata la variabile d'ambiente MONGO_URI")

# Carica le variabili d'ambiente
load_dotenv(dotenv_path=ENV_PATH)

# Ottieni MONGO_URI
MONGO_URI = os.getenv('MONGO_URI')
if not MONGO_URI:
    print(f"❌ ERRORE: MONGO_URI non trovato nel file .env: {ENV_PATH}")
    print("   Contenuto .env (se esiste):")
    if ENV_PATH.exists():
        try:
            with open(ENV_PATH, 'r') as f:
                content = f.read()
                # Nasconde password per sicurezza
                safe_content = content.replace('mongodb://', 'mongodb://***:***@')
                print(safe_content)
        except Exception as e:
            print(f"   Errore lettura .env: {e}")
    
    # Valore di default per sviluppo locale
    MONGO_URI = "mongodb://localhost:27017/simulatore_calcio"
    print(f"⚠️  Usando MONGO_URI di default: {MONGO_URI.replace('://', '://***:***@')}")

print("🔗 Connessione MongoDB...")

try:
    # Connessione a MongoDB
    client = pymongo.MongoClient(MONGO_URI)
    
    # Estrae il nome del database dalla URI (l'ultima parte prima di '?')
    db_name = MONGO_URI.rsplit('/', 1)[-1].split('?', 1)[0]
    db = client[db_name]
    
    # Test connessione
    client.admin.command('ping')
    print(f"✅ Connesso a MongoDB: {db_name}")
    
except Exception as e:
    print(f"❌ Errore connessione MongoDB: {e}")
    print("⚠️  Assicurati che MongoDB sia in esecuzione!")
    raise

# Conta documenti nelle collezioni principali (solo se esistono)
print(f"📊 Database: {db_name}")

collections_to_check = ['teams', 'matches_history', 'raw_h2h_data_v2', 'h2h_by_round']
for collection in collections_to_check:
    if collection in db.list_collection_names():
        count = db[collection].count_documents({})
        print(f"   📦 {collection}: {count} documenti")
    else:
        print(f"   ⚠️  {collection}: collezione non trovata")

print("✅ Configurazione completata con successo")