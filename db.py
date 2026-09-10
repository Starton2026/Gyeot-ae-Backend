"""JSON 파일 DB 읽기/쓰기 헬퍼."""
import json
import os
import uuid

DB_PATH = os.path.join(os.path.dirname(__file__), "db.json")

_DEFAULT = {"missing": [], "reports": []}


def load_db():
    if not os.path.exists(DB_PATH):
        return dict(_DEFAULT)
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_db(db):
    """임시 파일에 먼저 쓰고 rename — 도중에 실패해도 db.json이 손상되지 않게."""
    tmp_path = DB_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, DB_PATH)


def new_id():
    """8자리 고유 id."""
    return uuid.uuid4().hex[:8]


def find_missing(db, missing_id):
    for m in db["missing"]:
        if m["id"] == missing_id:
            return m
    return None
