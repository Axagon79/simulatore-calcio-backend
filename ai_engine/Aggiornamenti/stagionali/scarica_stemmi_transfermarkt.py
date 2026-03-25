"""
Scarica stemmi squadre da Transfermarkt e li carica su Firebase Storage.
Usa transfermarkt_id dal DB MongoDB per costruire l'URL del logo.
Carica in: stemmi/squadre/{Country}/{mongoId}.png
"""

import os
import sys
import requests
import time
import firebase_admin
from firebase_admin import credentials, storage
from pymongo import MongoClient
from dotenv import load_dotenv

# --- Config ---
# Risalgo fino alla root del backend (3 livelli su da stagionali)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
ENV_PATH = os.path.join(BASE_DIR, '.env')
load_dotenv(ENV_PATH)
print(f"  .env: {ENV_PATH} (exists={os.path.exists(ENV_PATH)})")

MONGO_URI = os.getenv("MONGO_URI")
GOOGLE_CREDS = r"C:\Users\lollo\Desktop\CARTELLE\1\puppals-456c7-firebase-adminsdk-jan27-bd6e6528c5.json"
BUCKET_NAME = "puppals-456c7.firebasestorage.app"

# Mapping: league name in DB -> folder name in Firebase Storage
LEAGUE_TO_FOLDER = {
    "League One": "England",
    "League Two": "England",
    "Veikkausliiga": "Finland",
    "3. Liga": "Germany",
    "Liga MX": "Mexico",
    "Eerste Divisie": "Netherlands",
    "Liga Portugal 2": "Portugal",
    "1. Lig": "Turkey",
    "Saudi Pro League": "Saudi_Arabia",
    "Scottish Championship": "Scotland",
}

TM_LOGO_URL = "https://tmssl.akamaized.net/images/wappen/head/{tm_id}.png"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def init_firebase():
    if not firebase_admin._apps:
        cred = credentials.Certificate(GOOGLE_CREDS)
        firebase_admin.initialize_app(cred, {"storageBucket": BUCKET_NAME})
    return storage.bucket()


def get_teams(db, leagues):
    teams = list(db.teams.find(
        {"league": {"$in": leagues}},
        {"_id": 1, "name": 1, "league": 1, "transfermarkt_id": 1}
    ))
    return teams


def download_logo(tm_id):
    url = TM_LOGO_URL.format(tm_id=tm_id)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200 and len(resp.content) > 500:
            return resp.content
        else:
            return None
    except Exception as e:
        print(f"   Errore download TM ID {tm_id}: {e}")
        return None


def upload_to_storage(bucket, blob_path, image_data):
    blob = bucket.blob(blob_path)
    blob.upload_from_string(image_data, content_type="image/png")
    blob.make_public()
    return True


def main():
    # Filtro opzionale per singolo campionato
    filter_league = sys.argv[1] if len(sys.argv) > 1 else None

    print("=" * 60)
    print("  SCARICA STEMMI DA TRANSFERMARKT -> FIREBASE STORAGE")
    print("=" * 60)

    # MongoDB
    client = MongoClient(MONGO_URI)
    db = client.football_simulator_db

    # Firebase
    bucket = init_firebase()
    print(f"  Firebase bucket: {BUCKET_NAME}")

    leagues = list(LEAGUE_TO_FOLDER.keys())
    if filter_league:
        leagues = [l for l in leagues if filter_league.lower() in l.lower()]
        print(f"  Filtro: {leagues}")

    teams = get_teams(db, leagues)
    print(f"  Squadre trovate: {len(teams)}")

    ok = 0
    skip = 0
    fail = 0

    for i, team in enumerate(teams):
        mongo_id = str(team["_id"])
        name = team.get("name", "???")
        league = team.get("league", "???")
        tm_id = team.get("transfermarkt_id")
        folder = LEAGUE_TO_FOLDER.get(league, "Altro")

        blob_path = f"stemmi/squadre/{folder}/{mongo_id}.png"

        # Controlla se esiste gia
        blob = bucket.blob(blob_path)
        if blob.exists():
            print(f"  [{i+1}/{len(teams)}] {name} ({league}) -> GIA PRESENTE, skip")
            skip += 1
            continue

        if not tm_id:
            print(f"  [{i+1}/{len(teams)}] {name} ({league}) -> NO transfermarkt_id, SKIP")
            fail += 1
            continue

        # Download da Transfermarkt
        image_data = download_logo(tm_id)
        if not image_data:
            print(f"  [{i+1}/{len(teams)}] {name} ({league}) TM:{tm_id} -> DOWNLOAD FALLITO")
            fail += 1
            continue

        # Upload su Firebase
        try:
            upload_to_storage(bucket, blob_path, image_data)
            print(f"  [{i+1}/{len(teams)}] {name} ({league}) TM:{tm_id} -> OK ({folder}/{mongo_id}.png)")
            ok += 1
        except Exception as e:
            print(f"  [{i+1}/{len(teams)}] {name} ({league}) -> UPLOAD FALLITO: {e}")
            fail += 1

        # Rate limit: 1 richiesta al secondo per non farsi bloccare
        time.sleep(1)

    print()
    print("=" * 60)
    print(f"  RISULTATO: {ok} caricati, {skip} gia presenti, {fail} falliti")
    print("=" * 60)

    client.close()


if __name__ == "__main__":
    main()
