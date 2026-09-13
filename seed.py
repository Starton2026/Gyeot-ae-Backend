"""데모용 가짜 실종자/제보 생성 스크립트 (신규 스키마 + Firestore 푸시).

- 등록된 실종자가 없으면: 가짜 실종자 1명 생성 (인코딩은 랜덤 벡터 — 지도 데모용)
- 첫 번째 활성 실종자에 대해 시간순으로 이동하는 가짜 제보 5건 생성
- Firestore가 활성화되어 있으면 시드 데이터도 함께 푸시 (관제 화면에 바로 표시)

사용법: python seed.py
※ 실제 얼굴대조 데모를 하려면 POST /missing 으로 진짜 사진을 등록한 뒤 실행할 것.
"""
import random
from datetime import timedelta

import db as database
import face_service
import firebase_service
from utils import now_kst

# 서울 시청 → 남산 방향으로 이동하는 경로 (lat, lng, 유사도, 몇 분 전, 위치명)
FAKE_PATH = [
    (37.5665, 126.9780, 82.3, 50, "시청역 4번 출구"),
    (37.5651, 126.9895, 78.1, 40, "을지로입구역 인근"),
    (37.5610, 126.9948, 35.6, 30, "명동성당 앞"),          # 저신뢰 제보 (경로 제외)
    (37.5563, 126.9723, 71.4, 20, "회현동 주민센터"),
    (37.5512, 126.9882, 88.2, 10, "남산 케이블카 승강장"),
]


def seed_missing(db):
    """가짜 실종자 1명 생성. 인코딩은 랜덤 128차원 벡터(실제 대조 불가, 지도 데모용)."""
    now = now_kst()
    missing = {
        "id": database.new_id("m_"),
        "name": "김순자",
        "age": 78,
        "gender": "female",
        "category": "elderly",
        "description": "빨간 패딩, 검은 바지. 시장 골목과 버스정류장에 자주 감",
        "height_cm": 152,
        "weight_kg": 48,
        "last_lat": 37.5665,
        "last_lng": 126.9780,
        "last_address": "서울 중구 태평로1가",
        "missing_at": (now - timedelta(hours=1)).isoformat(),
        # 사진 파일은 만들지 않는다. 파일 없이 이름만 적어두면 앱이 그 주소를
        # 불러 404를 받는다. 비워두면 앱이 제 실루엣 자리표시자를 그린다.
        # 진짜 사진으로 보려면 POST /missing 으로 등록할 것.
        "photos": [],
        "encoded_photos": [],
        "encodings": [[random.uniform(-0.2, 0.2) for _ in range(128)]],
        "status": "active",
        "created_at": now.isoformat(),
    }
    db["missing"].append(missing)
    firebase_service.push_missing(missing)
    print(f"가짜 실종자 생성: {missing['name']} ({missing['id']}) — 사진 없음")
    return missing


def seed_reports(db, missing):
    """실종자에 대해 시간순 이동 경로를 그리는 가짜 제보들 생성."""
    now = now_kst()
    reports = []
    route_index = 0
    for lat, lng, similarity, minutes_ago, place in FAKE_PATH:
        t = now - timedelta(minutes=minutes_ago)
        grade = face_service.grade_of(similarity, True)
        on_route = similarity >= face_service.SIMILARITY_ROUTE
        if on_route:
            route_index += 1
        reports.append({
            "id": database.new_id("r_"),
            "missing_id": missing["id"],
            "photo": missing["photos"][0],  # 데모용: 실종자 사진 재사용
            "lat": lat,
            "lng": lng,
            "place_name": place,
            "observed_at": t.isoformat(),
            "created_at": t.isoformat(),
            "timestamp": t.timestamp(),
            "similarity": similarity,
            "face_found": True,
            "grade": grade,
            "route_index": route_index if on_route else None,
            "status": "visible",
            "confirmed": False,
            "device_hash": "seed",
        })
    db["reports"].extend(reports)
    firebase_service.push_case_reports(reports, missing["name"])
    print(f"가짜 제보 {len(reports)}건 생성 완료 (missing_id={missing['id']})")


def main():
    db = database.load_db()
    active = [m for m in db["missing"] if m["status"] == "active"]
    missing = active[0] if active else seed_missing(db)
    seed_reports(db, missing)
    database.save_db(db)


if __name__ == "__main__":
    main()
