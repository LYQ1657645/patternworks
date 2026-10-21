"""Content identity includes schema, row order, nulls and complete cell values."""
import hashlib
import json


def row_digest(row_id, cells):
    return hashlib.sha256(json.dumps([row_id, cells], ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).digest()


def content_digest(columns, ordered_digests):
    digest = hashlib.sha256(b'patternworks-content-v1\0')
    digest.update(json.dumps(columns, sort_keys=True, ensure_ascii=False,
        separators=(',', ':')).encode('utf-8'))
    for value in ordered_digests:
        digest.update(value)
    return digest.hexdigest()
