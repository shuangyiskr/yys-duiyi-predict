"""Stable content fingerprints for user confirmations of locally refreshed caches."""
import hashlib
import json


def fingerprint(snapshot, content_key):
    content = snapshot.get(content_key)
    if content is None:
        raise ValueError(f"Snapshot has no {content_key}")
    encoded = json.dumps(content, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
