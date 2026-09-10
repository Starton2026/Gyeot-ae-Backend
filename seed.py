"""데모용 가짜 실종자/제보 생성 스크립트.

- 등록된 실종자가 없으면: 가짜 실종자 1명 생성 (인코딩은 랜덤 벡터 — 지도 데모용)
- 첫 번째 실종자에 대해 시간순으로 이동하는 가짜 제보 5건 생성

사용법: python seed.py
※ 실제 얼굴대조 데모를 하려면 POST /missing 으로 진짜 사진을 등록한 뒤 실행할 것.
"""
import random
from datetime import datetime, timedelta

import db as database

# 서울 시청 → 남산 방향으로 이동하는 경로 (lat, lng, 유사도, 몇 분 전)
FAKE_PATH = [
    (37.5665, 126.9780, 82.3, 50),
    (37.5651, 126.9895, 78.1, 40),
    (37.5610, 126.9948, 85.6, 30),
    (37.5563, 126.9723, 71.4, 20),
    (37.5512, 126.9882, 88.2, 10),
]


def seed_missing(db):
    """가짜 실종자 1명 생성. 인코딩은 랜덤 128차원 벡터(실제 대조 불가, 지도 데모용)."""
    missing = {
        "id": database.new_id(),
        "name": "김순자",
        "description": "빨간 패딩, 검은 바지, 70대 여성",
        "last_lat": 37.5665,
        "last_lng": 126.9780,
        "photo": "seed_missing.jpg",
        "encoding": [random.uniform(-0.2, 0.2) for _ in range(128)],
        "registered_at": datetime.now().isoformat(),
        "status": "실종중",
    }
    db["missing"].append(missing)
    print(f"가짜 실종자 생성: {missing['name']} ({missing['id']})")
    return missing


def seed_reports(db, missing):
    """실종자에 대해 시간순 이동 경로를 그리는 가짜 제보들 생성."""
    now = datetime.now()
    for lat, lng, similarity, minutes_ago in FAKE_PATH:
        t = now - timedelta(minutes=minutes_ago)
        db["reports"].append({
            "id": database.new_id(),
            "missing_id": missing["id"],
            "lat": lat,
            "lng": lng,
            "photo": missing["photo"],  # 데모용: 실종자 사진 재사용
            "similarity": similarity,
            "face_found": True,
            "is_match": similarity >= 60,
            "reported_at": t.isoformat(),
            "timestamp": t.timestamp(),
        })
    print(f"가짜 제보 {len(FAKE_PATH)}건 생성 완료 (missing_id={missing['id']})")


def main():
    db = database.load_db()
    missing = db["missing"][0] if db["missing"] else seed_missing(db)
    seed_reports(db, missing)
    database.save_db(db)


if __name__ == "__main__":
    main()
