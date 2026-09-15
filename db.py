"""JSON 파일 DB 읽기/쓰기 헬퍼."""
import json
import os
import threading
import uuid

DB_PATH = os.path.join(os.path.dirname(__file__), "db.json")

_DEFAULT = {
    "missing": [], "reports": [], "analyses": [], "users": [], "devices": [],
    # 앱 알림함. 푸시를 보낼 때 받는 사람마다 한 줄씩 남긴다(push_service).
    "notifications": [],
}


# Flask 개발 서버는 요청을 스레드로 동시에 처리한다. 잠금 없이 두 요청이 같은
# 임시 파일에 쓰면 짧은 내용 뒤에 긴 내용의 꼬리가 남아 db.json이 깨졌고
# (2026-09-14, 09-15 두 번), Windows는 읽는 중인 파일을 os.replace하면
# PermissionError를 낸다. 읽기·쓰기를 같은 잠금으로 묶는다.
_LOCK = threading.RLock()


def load_db():
    with _LOCK:
        if not os.path.exists(DB_PATH):
            return json.loads(json.dumps(_DEFAULT))
        with open(DB_PATH, "r", encoding="utf-8") as f:
            db = json.load(f)
    for key in _DEFAULT:  # 구버전 db.json 호환
        db.setdefault(key, [])
    return db


def save_db(db):
    """임시 파일에 먼저 쓰고 rename — 도중에 실패해도 db.json이 손상되지 않게."""
    with _LOCK:
        # 임시 파일 이름을 저장마다 다르게 — 다른 프로세스(seed 등)와도 겹치지 않게.
        tmp_path = f"{DB_PATH}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(db, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, DB_PATH)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


def new_id(prefix=""):
    """8자리 고유 id. prefix 예: 'm_', 'r_', 'an_'."""
    return prefix + uuid.uuid4().hex[:8]


def find_missing(db, missing_id):
    for m in db["missing"]:
        if m["id"] == missing_id:
            return m
    return None


def find_report(db, report_id):
    for r in db["reports"]:
        if r["id"] == report_id:
            return r
    return None


def find_analysis(db, analysis_id):
    for a in db["analyses"]:
        if a["id"] == analysis_id:
            return a
    return None


def find_user(db, user_id):
    for u in db["users"]:
        if u["id"] == user_id:
            return u
    return None


def find_device(db, device_hash):
    for d in db["devices"]:
        if d["device_hash"] == device_hash:
            return d
    return None


def find_user_by_kakao(db, kakao_id):
    for u in db["users"]:
        if u["kakao_id"] == kakao_id:
            return u
    return None


def case_reports(db, missing_id):
    return [r for r in db["reports"] if r["missing_id"] == missing_id]
