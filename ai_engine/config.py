from dotenv import load_dotenv
import os
import pymongo
from pathlib import Path
import sys
import io

# Forza la stampa in UTF-8 anche su Windows console vecchie
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Path assoluto alla root del progetto: .../simulatore-calcio-backend
BASE_DIR = Path(__file__).resolve().parent          # .../ai_engine
ENV_PATH = BASE_DIR.parent / '.env'                 # .../simulatore-calcio-backend/.env

# Carica sempre lo stesso .env, indipendentemente dalla cartella da cui lanci
load_dotenv(dotenv_path=ENV_PATH)

MONGO_URI = os.getenv('MONGO_URI')
if not MONGO_URI:
    raise ValueError(f"MONGO_URI non trovato nel file .env: {ENV_PATH}")

print(" Connessione MongoDB...")

client = pymongo.MongoClient(MONGO_URI)  # usa esattamente la URI del .env [web:3]
# Estrae il nome del database dalla URI (l'ultima parte prima di '?')
db_name = MONGO_URI.rsplit('/', 1)[-1].split('?', 1)[0]
db = client[db_name]

print(f" Database: {db_name}")
print(f"   Teams: {db.teams.count_documents({})}")
print(f"   Matches: {db.matches_history.count_documents({})}")
