"""
Script per indicizzare le pagine WIKI del vault AI Simulator in MongoDB Atlas
con embedding generati da Mistral.

Gemello di index_raw_to_vector.py (stessa logica, sorgente diversa):
- Sorgente: g:/AI_Simulator_vault/wiki/ (ricorsivo, tutti i .md)
- Collection: wiki_chunks + wiki_chunks_index
- Vector index Atlas: wiki_index (da creare manualmente da web UI Atlas)

Step pipeline notturna: [41/42] dopo l'indicizzazione raw.

Uso: python index_wiki_to_vector.py [--force] [--vault-path PATH]
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
from pymongo import MongoClient


VAULT_DEFAULT = Path("g:/AI_Simulator_vault/wiki")
CHUNK_WORDS = 500
CHUNK_OVERLAP = 50
MISTRAL_EMBED_URL = "https://api.mistral.ai/v1/embeddings"
MISTRAL_MODEL = "mistral-embed"
EMBED_DIM = 1024
COLLECTION_CHUNKS = "wiki_chunks"
COLLECTION_INDEX = "wiki_chunks_index"


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
            print(f"  Mistral retry {attempt + 1}/{retries} in {wait}s ({e})")
            time.sleep(wait)
    return []


def relative_to_vault(file_path: Path, vault_root: Path) -> str:
    """Path relativo alla root del vault, con / come separatore (cross-platform)."""
    try:
        return str(file_path.relative_to(vault_root)).replace("\\", "/")
    except ValueError:
        return str(file_path).replace("\\", "/")


def index_file(api_key: str, db, file_path: Path, vault_root: Path, force: bool = False) -> int:
    chunks_col = db[COLLECTION_CHUNKS]
    index_col = db[COLLECTION_INDEX]
    fhash = file_hash(file_path)
    existing = index_col.find_one({"file_path": str(file_path)})
    if existing and existing.get("file_hash") == fhash and not force:
        return 0

    text = file_path.read_text(encoding="utf-8")
    chunks = chunk_text(text)
    if not chunks:
        return 0

    rel_path = relative_to_vault(file_path, vault_root)
    print(f"  {rel_path}: {len(chunks)} chunks...")

    chunks_col.delete_many({"file_path": str(file_path)})

    BATCH = 16
    all_docs = []
    for i in range(0, len(chunks), BATCH):
        batch = chunks[i:i + BATCH]
        embeddings = mistral_embed(api_key, batch)
        for j, (chunk, emb) in enumerate(zip(batch, embeddings)):
            all_docs.append({
                "file_path": str(file_path),
                "file_name": file_path.name,
                "rel_path": rel_path,
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
            "rel_path": rel_path,
            "file_hash": fhash,
            "n_chunks": len(chunks),
            "indexed_at": datetime.now(timezone.utc),
        }},
        upsert=True,
    )
    return len(chunks)


def cleanup_deleted_files(db, vault_root: Path, current_files: set) -> int:
    """Rimuove dall'index e dai chunks i file che non esistono più nel vault."""
    chunks_col = db[COLLECTION_CHUNKS]
    index_col = db[COLLECTION_INDEX]
    indexed = list(index_col.find({}, {"file_path": 1}))
    deleted = 0
    for doc in indexed:
        fp = doc.get("file_path")
        if fp and fp not in current_files:
            chunks_col.delete_many({"file_path": fp})
            index_col.delete_one({"file_path": fp})
            deleted += 1
    return deleted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Reindicizza anche file invariati")
    parser.add_argument("--vault-path", default=str(VAULT_DEFAULT), help="Path alla wiki/")
    parser.add_argument("--no-cleanup", action="store_true", help="Salta rimozione file eliminati")
    args = parser.parse_args()

    api_key, mongo_uri = load_env()
    vault = Path(args.vault_path)
    if not vault.exists():
        print(f"Vault path non esiste: {vault}")
        sys.exit(1)

    print(f"Connessione MongoDB...")
    client = MongoClient(mongo_uri)
    db = client.get_database("football_simulator_db")

    md_files = sorted(vault.rglob("*.md"))
    print(f"Trovati {len(md_files)} file in {vault} (ricorsivo)")

    current_files = {str(fp) for fp in md_files}

    total_chunks = 0
    indexed_files = 0
    for fp in md_files:
        try:
            n = index_file(api_key, db, fp, vault, force=args.force)
            if n > 0:
                indexed_files += 1
                total_chunks += n
        except Exception as e:
            print(f"Errore su {fp.name}: {e}")

    deleted = 0
    if not args.no_cleanup:
        deleted = cleanup_deleted_files(db, vault, current_files)
        if deleted:
            print(f"Cleanup: rimossi {deleted} file non più presenti nel vault")

    print(f"\nFatto. {indexed_files} file indicizzati, {total_chunks} chunk totali.")
    print(f"   Collezioni: {COLLECTION_CHUNKS} (chunks), {COLLECTION_INDEX} (index meta)")


if __name__ == "__main__":
    main()
