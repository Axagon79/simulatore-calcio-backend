"""
Script per indicizzare i file raw del vault AI Simulator in MongoDB Atlas
con embedding generati da Mistral.

Esegue:
1. Legge tutti i file in g:/AI_Simulator_vault/raw/sessioni/
2. Per ogni file non ancora indicizzato (controlla collezione raw_chunks_index):
   - Lo divide in chunk da ~500 parole (overlap 50)
   - Per ogni chunk: chiama Mistral API per ottenere embedding (mistral-embed, 1024 dim)
   - Inserisce in collezione raw_chunks: { text, embedding, file_path, chunk_id, indexed_at }
3. Marca il file come indicizzato in raw_chunks_index

Uso: python index_raw_to_vector.py [--force] [--vault-path PATH]
"""

import os
import sys
import argparse
import hashlib
from pathlib import Path
from datetime import datetime, timezone
import time

import requests
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne


VAULT_DEFAULT = Path("g:/AI_Simulator_vault/raw/sessioni")
CHUNK_WORDS = 500
CHUNK_OVERLAP = 50
MISTRAL_EMBED_URL = "https://api.mistral.ai/v1/embeddings"
MISTRAL_MODEL = "mistral-embed"
EMBED_DIM = 1024
COLLECTION_CHUNKS = "raw_chunks"
COLLECTION_INDEX = "raw_chunks_index"


def load_env():
    here = Path(__file__).resolve().parent.parent
    env_path = here / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    api_key = os.getenv("MISTRAL_API_KEY")
    mongo_uri = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY non trovato in .env")
    if not mongo_uri:
        raise RuntimeError("MONGODB_URI non trovato in .env")
    return api_key, mongo_uri


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            h.update(block)
    return h.hexdigest()


def chunk_text(text: str, size_words: int = CHUNK_WORDS, overlap: int = CHUNK_OVERLAP):
    words = text.split()
    if not words:
        return []
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i + size_words])
        chunks.append(chunk)
        if i + size_words >= len(words):
            break
        i += size_words - overlap
    return chunks


def mistral_embed(api_key: str, texts: list, retries: int = 3) -> list:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": MISTRAL_MODEL, "input": texts}
    for attempt in range(retries):
        try:
            r = requests.post(MISTRAL_EMBED_URL, json=payload, headers=headers, timeout=60)
            r.raise_for_status()
            data = r.json()
            return [d["embedding"] for d in data["data"]]
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise
            wait = 2 ** attempt
            print(f"  ⚠ Mistral retry {attempt + 1}/{retries} in {wait}s ({e})")
            time.sleep(wait)
    return []


def index_file(api_key: str, db, file_path: Path, force: bool = False) -> int:
    chunks_col = db[COLLECTION_CHUNKS]
    index_col = db[COLLECTION_INDEX]
    fhash = file_hash(file_path)
    existing = index_col.find_one({"file_path": str(file_path)})
    if existing and existing.get("file_hash") == fhash and not force:
        return 0  # già indicizzato e identico

    text = file_path.read_text(encoding="utf-8")
    chunks = chunk_text(text)
    if not chunks:
        return 0

    print(f"📄 {file_path.name}: {len(chunks)} chunks...")

    # Cancella chunk vecchi di questo file (in caso di reindicizzazione)
    chunks_col.delete_many({"file_path": str(file_path)})

    # Embed in batch (Mistral accetta liste)
    BATCH = 16
    all_docs = []
    for i in range(0, len(chunks), BATCH):
        batch = chunks[i:i + BATCH]
        embeddings = mistral_embed(api_key, batch)
        for j, (chunk, emb) in enumerate(zip(batch, embeddings)):
            all_docs.append({
                "file_path": str(file_path),
                "file_name": file_path.name,
                "chunk_id": i + j,
                "text": chunk,
                "embedding": emb,
                "indexed_at": datetime.now(timezone.utc),
            })

    if all_docs:
        chunks_col.insert_many(all_docs)

    index_col.update_one(
        {"file_path": str(file_path)},
        {"$set": {
            "file_path": str(file_path),
            "file_hash": fhash,
            "n_chunks": len(chunks),
            "indexed_at": datetime.now(timezone.utc),
        }},
        upsert=True,
    )
    return len(chunks)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Reindicizza anche file invariati")
    parser.add_argument("--vault-path", default=str(VAULT_DEFAULT), help="Path a raw/sessioni/")
    args = parser.parse_args()

    api_key, mongo_uri = load_env()
    vault = Path(args.vault_path)
    if not vault.exists():
        print(f"❌ Vault path non esiste: {vault}")
        sys.exit(1)

    print(f"🔌 Connessione MongoDB...")
    client = MongoClient(mongo_uri)
    db = client.get_database("football_simulator_db")

    md_files = sorted(vault.glob("*.md"))
    print(f"📂 Trovati {len(md_files)} file in {vault}")

    total_chunks = 0
    indexed_files = 0
    for fp in md_files:
        try:
            n = index_file(api_key, db, fp, force=args.force)
            if n > 0:
                indexed_files += 1
                total_chunks += n
        except Exception as e:
            print(f"❌ Errore su {fp.name}: {e}")

    print(f"\n✅ Fatto. {indexed_files} file indicizzati, {total_chunks} chunk totali.")
    print(f"   Collezioni: {COLLECTION_CHUNKS} (chunks), {COLLECTION_INDEX} (index meta)")


if __name__ == "__main__":
    main()
