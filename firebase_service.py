"""Firestore 연동 — 제보/실종자 데이터를 실시간으로 관제 화면에 푸시.

serviceAccountKey.json(Firebase 콘솔에서 발급)이 프로젝트 루트에 있으면 활성화되고,
없으면 조용히 비활성화되어 기존 JSON DB만으로 동작한다.

프론트(관제 화면)는 Firestore를 onSnapshot으로 구독해서
제보가 들어오는 순간 지도·타임라인에 실시간 반영할 수 있다.

컬렉션 구조:
- missing/{missing_id}  : 실종자 정보 (encodings 제외)
- reports/{report_id}   : 제보 (observed_at, similarity, grade, route_index, photo_url ...)
"""
import os

# macOS에서 gRPC 내장 DNS(c-ares)가 조회에 실패하는 경우가 있어 시스템 리졸버 사용
os.environ.setdefault("GRPC_DNS_RESOLVER", "native")

KEY_PATH = os.path.join(os.path.dirname(__file__), "serviceAccountKey.json")

# 사진 공개 URL의 베이스 (ngrok 사용 시: BASE_URL=https://xxxx.ngrok.io python app.py)
BASE_URL = os.environ.get("BASE_URL", "http://localhost:5001")

_db = None

if os.path.exists(KEY_PATH):
    import firebase_admin
    from firebase_admin import credentials, firestore

    cred = credentials.Certificate(KEY_PATH)
    firebase_admin.initialize_app(cred)
    _db = firestore.client()
    print("[firebase] Firestore 연동 활성화")
else:
    print("[firebase] serviceAccountKey.json 없음 → Firestore 비활성 (JSON DB만 사용)")


def is_enabled():
    """Firestore 연동 여부."""
    return _db is not None


def photo_url(filename):
    """업로드 파일명 → 프론트가 <img>로 바로 쓸 수 있는 공개 URL."""
    return f"{BASE_URL}/uploads/{filename}"


def push_missing(missing):
    """실종자 등록/변경을 Firestore에 기록 (encodings는 제외)."""
    if _db is None:
        return
    try:
        doc = {k: v for k, v in missing.items() if k != "encodings"}
        doc["photo_urls"] = [photo_url(p) for p in missing.get("photos", [])]
        doc["thumbnail_url"] = photo_url(missing["photos"][0]) if missing.get("photos") else None
        _db.collection("missing").document(missing["id"]).set(doc)
    except Exception as e:  # Firestore 장애가 본 API를 죽이면 안 됨
        print(f"[firebase] missing 푸시 실패: {e}")


def push_report(report, missing_name):
    """제보를 Firestore에 기록 → 관제 화면이 실시간으로 수신."""
    if _db is None:
        return
    try:
        doc = dict(report)
        doc["missing_name"] = missing_name
        doc["photo_url"] = photo_url(report["photo"]) if report.get("photo") else None
        _db.collection("reports").document(report["id"]).set(doc)
    except Exception as e:
        print(f"[firebase] report 푸시 실패: {e}")


def push_case_reports(reports, missing_name):
    """사건의 제보들을 일괄 갱신 (route_index 재계산 후 사용)."""
    if _db is None:
        return
    for r in reports:
        push_report(r, missing_name)
