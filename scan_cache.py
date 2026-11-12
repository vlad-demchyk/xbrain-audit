"""Cache for scan results to avoid re-scanning unchanged files.

Stores scan results keyed by file path + content hash. When a file
hasn't changed, the cached result is returned instead of re-scanning.
"""
from __future__ import annotations

import hashlib
from copy import deepcopy
import json
from pathlib import Path
from typing import Any
from cache_store import merge_cache
from platform_dirs import default_config_home


# Default cache location
# The platform config base (`%APPDATA%` on Windows), not `$XDG_CONFIG_HOME`:
# this is a module constant and kept its old, import-time-independent value.
CACHE_DIR = default_config_home() / "xanalyze" / "cache"
CACHE_FILE = CACHE_DIR / "scan_cache.json"


def _content_hash(text: str) -> str:
    """Fast hash of file content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_hash(path: str) -> str:
    """Hash the same decoded text that the scanner reads."""
    try:
        return _content_hash(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        return ""


class ScanCache:
    """Cache for scan results."""
    
    def __init__(self, cache_path: Path | None = None):
        self.cache_path = cache_path or CACHE_FILE
        self._cache: dict[str, Any] = {}
        self._load()
        self._baseline = deepcopy(self._cache)
        self._clear_pending = False
    
    def _load(self) -> None:
        """Load cache from disk."""
        if self.cache_path.exists():
            try:
                with open(self.cache_path, encoding="utf-8") as f:
                    self._cache = json.load(f)
                    if not isinstance(self._cache, dict):
                        self._cache = {}
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                self._cache = {}
    
    def _save(self) -> None:
        """Save cache to disk, atomically.

        Written to a temporary file and renamed, the way `browser_cache`
        already does it. Writing over the file in place has a window in
        which it is half a JSON document, and a second scan running at the
        same time - a perfectly ordinary thing to do - reads it there and
        throws its own cache away. The rename is atomic on every filesystem
        this runs on, so a concurrent reader sees either the old file or the
        new one.
        """
        self._cache = merge_cache(self.cache_path, self._cache, self._baseline,
                                  clear=self._clear_pending)
        self._baseline = deepcopy(self._cache)
        self._clear_pending = False
    
    def get(self, file_path: str, *, content: str | None = None) -> dict | None:
        """Get cached result for a file, or None if not cached / changed."""
        file_key = _content_hash(content) if content is not None else _file_hash(file_path)
        if not file_key:
            return None
        
        cached = self._cache.get(file_path)
        if not cached:
            return None
        
        if cached.get("hash") != file_key:
            return None
        
        return cached.get("result")
    
    def put(self, file_path: str, result: dict, *, save: bool = True,
            content: str | None = None) -> None:
        """Cache a scan result for a file.

        `save=False` keeps the entry in memory only, for a caller writing
        many entries in one pass: saving flushes the whole cache file, so a
        repository of four thousand files meant four thousand full rewrites
        of it. Such a caller must call `save()` when it is done - see
        `cli_impl.scanning._store_unchanged`.
        """
        file_key = _content_hash(content) if content is not None else _file_hash(file_path)
        if not file_key:
            return

        self._cache[file_path] = {
            "hash": file_key,
            "result": result,
        }
        if save:
            self._save()

    def save(self) -> None:
        """Flush the cache to disk. For callers that used `put(save=False)`."""
        self._save()
    
    def invalidate(self, file_path: str) -> None:
        """Remove a file from the cache."""
        self._cache.pop(file_path, None)
        self._save()
    
    def clear(self) -> None:
        """Clear the entire cache."""
        self._cache = {}
        self._clear_pending = True
        self._save()
    
    def stats(self) -> dict:
        """Return cache statistics."""
        return {
            "entries": len(self._cache),
            "size_bytes": self.cache_path.stat().st_size if self.cache_path.exists() else 0,
        }


# Global cache instance
_cache: ScanCache | None = None


def get_cache() -> ScanCache:
    """Get the global cache instance."""
    global _cache
    if _cache is None:
        _cache = ScanCache()
    return _cache
