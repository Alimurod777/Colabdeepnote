import json
import os
from config import DB_URI

_cache = {}  # in-memory cache: {chat_id: user_data}
_use_mongo = False
_db = None

# Absolute path anchored to project root (db.py is at database/db.py)
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_LOCAL_FILE = os.path.join(_PROJECT_ROOT, "sessions", "local_db.json")


def _init():
    global _use_mongo, _db
    if not DB_URI:
        return
    try:
        from pymongo import MongoClient
        client = MongoClient(DB_URI, serverSelectionTimeoutMS=5000)
        client.server_info()
        _db = client.userdb.sessions
        _use_mongo = True
    except Exception as e:
        print(f"MongoDB ulanmadi, local JSON ishlatiladi: {e}")


def _load_local():
    if not os.path.exists(_LOCAL_FILE):
        return []
    try:
        with open(_LOCAL_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_local(data):
    os.makedirs(os.path.dirname(_LOCAL_FILE), exist_ok=True)
    with open(_LOCAL_FILE, "w") as f:
        json.dump(data, f)


def find_one(query):
    key = query.get("chat_id")
    if key and key in _cache:
        return _cache[key]
    if _use_mongo:
        result = _db.find_one(query)
        if result and key:
            _cache[key] = result
        return result
    # local fallback
    records = _load_local()
    for r in records:
        if all(r.get(k) == v for k, v in query.items()):
            if key:
                _cache[key] = r
            return r
    return None


def insert_one(doc):
    key = doc.get("chat_id")
    existing = find_one({"chat_id": key}) if key else None
    if existing:
        return
    if _use_mongo:
        _db.insert_one(doc)
    else:
        records = _load_local()
        records.append(doc)
        _save_local(records)
    if key:
        _cache[key] = doc


def update_one(filter_query, update, upsert=False):
    set_data = update.get("$set", {})
    unset_fields = update.get("$unset", {})

    # Determine cache key
    key = filter_query.get("chat_id")
    if not key:
        # Try to find by _id in cache values
        doc_id = filter_query.get("_id")
        if doc_id:
            key = _cache_key_by_id(doc_id)

    if _use_mongo:
        _db.update_one(filter_query, update, upsert=upsert)
    else:
        records = _load_local()
        matched = False
        for r in records:
            # Match by chat_id if present in filter, else by _id
            if filter_query.get("chat_id"):
                if r.get("chat_id") == filter_query["chat_id"]:
                    r.update(set_data)
                    for uf in unset_fields:
                        r.pop(uf, None)
                    matched = True
            elif filter_query.get("_id"):
                # In local mode, _id is not auto-set — match via cache lookup
                if key and r.get("chat_id") == key:
                    r.update(set_data)
                    for uf in unset_fields:
                        r.pop(uf, None)
                    matched = True
        if not matched and upsert:
            # Upsert: yangi hujjat yaratish
            new_doc = dict(filter_query)
            new_doc.update(set_data)
            records.append(new_doc)
            if not key:
                key = new_doc.get("chat_id")
            if key:
                _cache[key] = new_doc
            matched = True
        if matched:
            _save_local(records)

    # Update cache
    if key and key in _cache:
        _cache[key].update(set_data)
        for uf in unset_fields:
            _cache[key].pop(uf, None)


def _cache_key_by_id(doc_id):
    for k, v in _cache.items():
        if v.get("_id") == doc_id:
            return k
    return None


# Initialize at import time
_init()

# Expose as database object — same interface as before
database = type("DB", (), {
    "find_one": staticmethod(find_one),
    "insert_one": staticmethod(insert_one),
    "update_one": staticmethod(update_one),
})()
