"""시연용 배경 사건을 사진과 함께 만든다. 다시 돌리면 지난 시드 사건만 바꾼다.

홈 목록·지도·실종자 탭이 사건 한 건만으로 비어 보이지 않게, **인천논현역 반경
3km**(남동구 논현동·소래포구·호구포) 안에 사건 6건(진행 중 5 · 발견 완료 1)과 제보를 넣는다. 사진은
`seed/` 폴더에서 읽고, 등록 사진의 얼굴 벡터는 **진짜로 뽑는다** — 이 사건들에
라이브로 제보해도 실제 분석이 된다.

    seed/1/          1번 사람 등록 사진 1~3장 (얼굴이 정면으로 크게)
    seed/1/reports/  1번 사건의 제보 사진 (선택 — 없으면 제보에 사진이 없다)
    ...
    seed/6/

어떤 사람 사진이 필요한지는 아래 CASES의 `photo` 설명과 `seed/README.md`에 있다.

사용법 (서버를 끈 채로, 진짜 얼굴 인식 가상환경으로):

    .venv\\Scripts\\python.exe seed.py            # 지난 시드 사건만 지우고 다시 넣는다
    .venv\\Scripts\\python.exe seed.py --reset    # DB를 비우고 넣는다 (계정·기기 등록은 남긴다)

- **5번 한복순만 골든타임(실종 3시간) 안**이다. 홈 긴급 배너에 뜨는 사건이고
  보호자 계정이 붙는다.
  실종 시각이 넣은 시점 기준 1시간 전이라 **2시간 뒤에는 배너에서 빠진다** — 촬영이
  늦어지면 다시 돌린다. 나머지 진행 중 사건은 3시간이 지난 사건이다
- `--reset`은 지우기 전에 db.json과 uploads를 `../db-backup/<시각>/`에 옮겨 둔다
- 푸시 알림은 보내지 않는다
"""
import argparse
import os
import random
import shutil
import sys
from datetime import datetime, timedelta

import db as database
import face_service
from app import UPLOAD_DIR, make_thumbnail, recompute_route_indexes
from utils import now_kst

HERE = os.path.dirname(os.path.abspath(__file__))
SEED_DIR = os.path.join(HERE, "seed")
BACKUP_ROOT = os.path.join(os.path.dirname(HERE), "db-backup")
PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".webp")
SEED_DEVICE = "seed"

# ── 사건 ─────────────────────────────────────────────────
# folder: seed/ 아래 폴더 이름. photo: 그 폴더에 넣을 사진 설명.
# hours_ago: 실종 시각. reports: (실종 뒤 분, 위도, 경도, 유사도 또는 None, 장소)
CASES = [
    {
        "folder": "1",
        "photo": "8살 전후 남자아이",
        "name": "이준서", "age": 8, "gender": "male", "category": "child",
        "description": "노란 후드티, 검정 백팩, 청바지. 버스 노선도를 오래 들여다보는 버릇이 있습니다.",
        "height_cm": 128, "weight_kg": 27,
        "last_lat": 37.4006, "last_lng": 126.7226,
        "last_address": "인천 남동구 논현동 인천논현역 2번 출구",
        "hours_ago": 5, "status": "active",
        "reports": [
            # 제보 사진은 seed/1/reports/ 파일 이름 순서대로 붙는다
            (40, 37.4045, 126.7262, 81.2, "인천논현역 버스정류장 노선도 앞"),
            (150, 37.4036, 126.7290, 58.4, "논현동 중심상가 앞 광장"),
        ],
    },
    {
        "folder": "2",
        "photo": "80대 여성 어르신",
        "name": "박순자", "age": 81, "gender": "female", "category": "elderly",
        "description": "올림머리, 베이지색 카디건이나 하늘색 꽃무늬 블라우스, 남색 바지, 초록색 천 가방. 나무 지팡이를 짚으십니다.",
        "height_cm": 150, "weight_kg": 45,
        "last_lat": 37.4003, "last_lng": 126.7343,
        "last_address": "인천 남동구 논현동 소래포구 종합어시장 앞",
        "hours_ago": 9, "status": "active",
        "reports": [
            (60, 37.4048, 126.7288, 66.8, "소래포구 어시장 뒷골목"),
            (210, 37.4080, 126.7262, None, "논현동 주택가 골목 (뒷모습)"),
            (330, 37.4112, 126.7228, 61.2, "소래포구역 승강장 벤치"),
        ],
    },
    {
        "folder": "3",
        "photo": "10살 전후 여자아이",
        "name": "최서윤", "age": 10, "gender": "female", "category": "child",
        "description": "분홍색 후드티, 검정 백팩, 청바지, 분홍 운동화. 낯선 사람이 부르면 대답하지 않습니다.",
        "height_cm": 138, "weight_kg": 31,
        "last_lat": 37.4101, "last_lng": 126.7155,
        "last_address": "인천 남동구 논현동 늘솔길공원 놀이터",
        "hours_ago": 20, "status": "active",
        "reports": [
            (120, 37.4063, 126.7172, 72.5, "논현고잔동 행정복지센터 앞 광장"),
            # 옷을 갈아입은 사진이라 낮게 둔다 — 걸러내지 않고 "확인 필요"로 남는 장면
            (400, 37.4030, 126.7120, 36.4, "고잔동 주택가 골목 (다른 옷차림)"),
        ],
    },
    {
        "folder": "4",
        "photo": "70대 남성 어르신",
        "name": "김영수", "age": 76, "gender": "male", "category": "elderly",
        "description": "흰머리, 분홍색 후드티, 검정 백팩. 추우면 베이지색 누빔 점퍼와 빨간 목도리를 두르고 지팡이를 짚으십니다.",
        "height_cm": 168, "weight_kg": 62,
        "last_lat": 37.4078, "last_lng": 126.7300,
        "last_address": "인천 남동구 논현동 논현사거리",
        "hours_ago": 30, "status": "active",
        "reports": [
            (180, 37.4082, 126.7295, None, "논현사거리 앞 광장 (먼 거리)"),
            (300, 37.4065, 126.7268, 49.8, "논현동 골목길"),
            (420, 37.4006, 126.7226, 71.0, "인천논현역 승강장"),
        ],
    },
    {
        "folder": "5",
        "photo": "80대 여성 어르신 (2번과 다른 사람) — 긴급 사건",
        "name": "한복순", "age": 84, "gender": "female", "category": "elderly",
        "description": "짧은 파마머리, 분홍색 꽈배기 니트, 회색 바지, 나무 지팡이. 공원 벤치에 오래 앉아 계십니다.",
        "height_cm": 149, "weight_kg": 44,
        "last_lat": 37.4072, "last_lng": 126.7430,
        "last_address": "인천 남동구 논현동 소래습지생태공원",
        "hours_ago": 1, "status": "active",  # 골든타임 안 — 홈 긴급 배너
        "guardian": True,  # 보호자 계정을 붙인다 — 보호자 푸시·보호자 메뉴·발견 완료 장면용
        # 제보는 비워 둔다. seed/5/reports/1_한복순2.png를 시민 폰 앨범에서 골라 라이브로
        # 제보하면 실제 분석이 77%(높음)로 나온다 — 시드 사진 중 70%를 넘는 조합은 이것뿐이다
        "reports": [],
    },
    {
        "folder": "6",
        "photo": "6살 전후 남자아이",
        "name": "오민재", "age": 6, "gender": "male", "category": "child",
        "description": "회색 패딩, 빨간 목도리, 동그란 안경. 장난감 자동차를 늘 손에 쥐고 있습니다.",
        "height_cm": 115, "weight_kg": 21,
        "last_lat": 37.4013, "last_lng": 126.7086,
        "last_address": "인천 남동구 논현동 호구포역 앞",
        "hours_ago": 120, "status": "resolved", "resolved_after_hours": 3,
        "reports": [
            (70, 37.4032, 126.7101, 74.6, "호구포근린공원 안내판 앞"),
            (140, 37.4013, 126.7086, 81.3, "호구포역 승강장"),
            (160, 37.4014, 126.7089, 44.0, "호구포역 승강장 (다른 옷차림)"),
        ],
    },
]


def photos_in(folder):
    if not os.path.isdir(folder):
        return []
    return sorted(
        os.path.join(folder, f) for f in os.listdir(folder)
        if f.lower().endswith(PHOTO_EXTS)
    )


def copy_photo(src, name):
    """uploads/로 복사하고 썸네일을 만든다. 저장한 파일 이름을 돌려준다."""
    ext = os.path.splitext(src)[1].lower()
    filename = f"{name}{ext}"
    dst = os.path.join(UPLOAD_DIR, filename)
    shutil.copyfile(src, dst)
    make_thumbnail(dst)
    return filename


def remove_file(filename):
    if not filename:
        return
    base, _ = os.path.splitext(filename)
    for path in (os.path.join(UPLOAD_DIR, filename), os.path.join(UPLOAD_DIR, base + "_thumb.jpg")):
        if os.path.exists(path):
            os.remove(path)


def remove_seed(db):
    """지난번 시드 사건과 그 제보·알림·사진만 지운다. 다른 사건은 건드리지 않는다."""
    seed_ids = {m["id"] for m in db["missing"] if m.get("seed")}
    for m in db["missing"]:
        if m["id"] in seed_ids:
            for photo in m.get("photos", []):
                remove_file(photo)
    for r in db["reports"]:
        if r["missing_id"] in seed_ids:
            remove_file(r.get("photo"))
    db["missing"] = [m for m in db["missing"] if m["id"] not in seed_ids]
    db["reports"] = [r for r in db["reports"] if r["missing_id"] not in seed_ids]
    db["notifications"] = [n for n in db["notifications"] if n["missing_id"] not in seed_ids]
    return len(seed_ids)


def reset_db(db):
    """사건·제보·분석·알림과 사진을 비운다. 계정과 기기 등록(푸시 토큰)은 남긴다.

    계정을 지우면 폰에 저장된 로그인이 깨지고, 기기를 지우면 앱을 다시 켤
    때까지 푸시가 안 온다. 지우기 전에 통째로 백업한다.
    """
    backup = os.path.join(BACKUP_ROOT, datetime.now().strftime("%Y%m%d-%H%M%S"))
    os.makedirs(backup)
    if os.path.exists(database.DB_PATH):
        shutil.copyfile(database.DB_PATH, os.path.join(backup, "db.json"))
    if os.path.isdir(UPLOAD_DIR):
        shutil.move(UPLOAD_DIR, os.path.join(backup, "uploads"))
    os.makedirs(os.path.join(UPLOAD_DIR, "tmp"), exist_ok=True)

    for key in ("missing", "reports", "analyses", "notifications"):
        db[key] = []
    print(f"DB를 비웠습니다 (계정 {len(db['users'])} · 기기 {len(db['devices'])}는 남김). 백업: {backup}")


def check_photos():
    """사진 폴더가 다 찼는지 먼저 본다. 하나라도 비었으면 아무것도 바꾸지 않는다."""
    missing = [c for c in CASES if not photos_in(os.path.join(SEED_DIR, c["folder"]))]
    if missing:
        lines = "\n".join(f"  seed/{c['folder']}/  ← {c['photo']} ({c['name']})" for c in missing)
        sys.exit(f"등록 사진이 없는 폴더가 있습니다. DB는 바꾸지 않았습니다.\n{lines}")


def encode(filename):
    encoding = face_service.get_face_encoding(os.path.join(UPLOAD_DIR, filename))
    return None if encoding is None else list(map(float, encoding))


def add_case(db, case, now, guardian_id):
    missing_id = database.new_id("m_")
    missing_at = now - timedelta(hours=case["hours_ago"])
    folder = os.path.join(SEED_DIR, case["folder"])

    photos, encoded_photos, encodings = [], [], []
    for i, src in enumerate(photos_in(folder)):
        filename = copy_photo(src, f"{missing_id}_{i}")
        photos.append(filename)
        encoding = encode(filename)
        if encoding is not None:
            encoded_photos.append(filename)
            encodings.append(encoding)
    face_count = len(encodings)
    if not encodings:
        # 그래도 목록·지도에는 보여야 한다. 대신 이 사건에 라이브 제보를 하면 유사도가 엉터리다.
        print(f"  ⚠ {case['name']}: 등록 사진에서 얼굴을 못 찾았습니다 — 정면 사진으로 바꾸는 게 좋습니다")
        encoded_photos = photos[:1]
        encodings = [[random.uniform(-0.2, 0.2) for _ in range(128)]]

    record = {
        "id": missing_id,
        "name": case["name"], "age": case["age"], "gender": case["gender"], "category": case["category"],
        "description": case["description"],
        "height_cm": case.get("height_cm"), "weight_kg": case.get("weight_kg"),
        "last_lat": case["last_lat"], "last_lng": case["last_lng"], "last_address": case["last_address"],
        "missing_at": missing_at.isoformat(),
        "photos": photos,
        "encoded_photos": encoded_photos,
        "encodings": encodings,
        "status": case["status"],
        "guardian_id": guardian_id if case.get("guardian") else None,
        "created_at": missing_at.isoformat(),
        "seed": True,
    }
    if case["status"] == "resolved":
        record["resolved_at"] = (missing_at + timedelta(hours=case["resolved_after_hours"])).isoformat()
        record["resolve_note"] = None
    db["missing"].append(record)

    report_photos = photos_in(os.path.join(folder, "reports"))
    for i, (minutes, lat, lng, similarity, place) in enumerate(case["reports"]):
        report_id = database.new_id("r_")
        observed = missing_at + timedelta(minutes=minutes)
        if observed > now:
            continue
        face_found = similarity is not None
        db["reports"].append({
            "id": report_id,
            "missing_id": missing_id,
            "photo": copy_photo(report_photos[i % len(report_photos)], report_id) if report_photos else None,
            "lat": lat, "lng": lng,
            "place_name": place,
            "observed_at": observed.isoformat(),
            "created_at": observed.isoformat(),
            "timestamp": observed.timestamp(),
            "similarity": similarity,
            "face_found": face_found,
            "grade": face_service.grade_of(similarity, face_found),
            "route_index": None,  # 아래에서 서버와 같은 규칙으로 매긴다
            "status": "visible",
            "confirmed": False,
            "device_hash": SEED_DEVICE,
            "reporter_id": None,
        })
    recompute_route_indexes(db, missing_id)

    state = "진행 중" if case["status"] == "active" else "발견 완료"
    print(f"  {case['name']} ({state}) — 사진 {len(photos)}장 · 얼굴 {face_count}장 · 제보 {len(case['reports'])}건 · 제보 사진 {len(report_photos)}장")


def main():
    parser = argparse.ArgumentParser(description="시연용 배경 사건을 사진과 함께 만든다")
    parser.add_argument("--reset", action="store_true", help="DB를 비우고 넣는다 (계정·기기 등록은 남긴다)")
    args = parser.parse_args()

    check_photos()
    db = database.load_db()
    if args.reset:
        reset_db(db)
    else:
        removed = remove_seed(db)
        if removed:
            print(f"지난 시드 사건 {removed}건을 지웠습니다.")

    now = now_kst()
    # 보호자는 가장 먼저 가입한 계정(시연하는 사람). 그 계정으로 로그인한 폰에서 보호자 메뉴가 보인다.
    users = sorted(db.get("users", []), key=lambda u: u.get("created_at", ""))
    guardian = users[0] if users else None
    print("시드 사건을 넣습니다:")
    for case in CASES:
        add_case(db, case, now, guardian["id"] if guardian else None)
    if guardian:
        names = ", ".join(c["name"] for c in CASES if c.get("guardian"))
        print(f"보호자 계정: {guardian['name']} ({guardian['id']}) → {names}")
    else:
        print("⚠ 계정이 없어 보호자를 붙이지 못했습니다. 앱에서 카카오 로그인한 뒤 다시 돌리세요.")
    database.save_db(db)
    print("끝. 한복순은 넣은 시점부터 2시간 동안 홈 긴급 배너에 뜹니다.")


if __name__ == "__main__":
    main()
