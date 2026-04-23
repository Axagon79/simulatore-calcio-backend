"""Cache HTML condivisa per scraper FBref. Auto-invalidazione giornaliera."""
import os
import hashlib
from datetime import datetime, timedelta

CACHE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "_cache_fbref")
)
os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_path(url: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    h = hashlib.md5(url.encode()).hexdigest()[:16]
    return os.path.join(CACHE_DIR, f"{today}_{h}.html")


def get_cached(url: str):
    """Ritorna HTML cached se presente e di oggi, altrimenti None."""
    path = _cache_path(url)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return None
    return None


def save_cache(url: str, html: str):
    """Salva HTML in cache per oggi."""
    try:
        path = _cache_path(url)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception:
        pass


def cleanup_old(days: int = 2):
    """Rimuove file cache piu' vecchi di N giorni."""
    try:
        cutoff = datetime.now() - timedelta(days=days)
        for fn in os.listdir(CACHE_DIR):
            if not fn.endswith(".html"):
                continue
            try:
                date_str = fn.split("_")[0]
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                if file_date < cutoff:
                    os.remove(os.path.join(CACHE_DIR, fn))
            except Exception:
                continue
    except Exception:
        pass
