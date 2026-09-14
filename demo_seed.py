"""시연 영상용 사건 한 건을 만든다. 다시 돌리면 지우고 새로 만든다.

실제 폰으로 찍은 사진은 얼굴 검출·유사도가 들쭉날쭉해서, 영상의 **경로·타임라인
장면**이 촬영 때마다 달라진다. 이 스크립트는 사진은 진짜로 쓰되 제보의 위치·시각·
유사도를 정해 둔 값으로 넣는다. 영상에서 **라이브로 올리는 제보는 실제 분석**을
탄다 — 그래서 등록 사진의 얼굴 벡터는 진짜로 뽑는다.

준비 — 백엔드 폴더 아래에 사진을 둔다(`demo/`는 git에 올라가지 않는다):

    demo/register/   실종자 등록 사진. 얼굴이 정면으로 잘 보이는 사진 1~4장
    demo/reports/    제보 사진. 파일 이름 순서대로 아래 경로에 붙는다(모자라면 돌려 씀)

사용법 (서버를 끈 채로, 진짜 얼굴 인식 가상환경으로):

    .venv\\Scripts\\python.exe demo_seed.py
    .venv\\Scripts\\python.exe demo_seed.py --guardian 심재윤 --minutes-ago 100
    .venv\\Scripts\\python.exe demo_seed.py --remove          # 시연 사건만 지운다

- 보호자는 기본으로 **가장 최근에 사건을 등록한 계정**이다. 그 계정으로 로그인한
  폰에서 상세를 열면 보호자 모드가 보인다
- 실종 시각은 기본 110분 전이다. 골든타임(3시간) 안이라 홈 긴급 배너에 뜨고,
  촬영할 시간이 70분쯤 남는다. 늦어지면 다시 돌리면 된다
- 푸시 알림은 보내지 않는다. 알림 장면은 라이브로 찍는다
"""
import argparse
import os
import shutil
import sys
from datetime import timedelta

import db as database
import face_service
from app import UPLOAD_DIR, make_thumbnail, recompute_route_indexes
from utils import now_kst

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTER_DIR = os.path.join(HERE, "demo", "register")
REPORTS_DIR = os.path.join(HERE, "demo", "reports")
PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".webp")

# ── 시연 사건 ────────────────────────────────────────────
# 영상에 보일 값이다. 필요하면 여기만 고친다.
CASE = {
    "name": "김하준",
    "age": 7,
    "gender": "male",
    "category": "child",
    "description": "노란 후드티, 검정 백팩, 파란 운동화. 말수가 적고 버스와 간판을 오래 쳐다봅니다.",
    "height_cm": 122,
    "weight_kg": 24,
    "last_lat": 37.4497,
    "last_lng": 126.6571,
    "last_address": "인천 미추홀구 인하로 100 인하공전 도서관 앞",
}

# 실종 뒤 몇 분에 어디서 봤는지, 유사도는 얼마인지. 유사도 None은 얼굴 미검출.
#   - 40% 미만(확인 필요)과 미검출을 하나씩 섞는다. 걸러지지 않고 남는 것을 보여준다
#   - 2번과 5번 사이를 70분 띄운다. 타임라인에 "⋯ 1시간 10분 공백"이 뜬다
PATH = [
    # (분, 위도, 경도, 유사도, 장소)
    (10, 37.4486, 126.6560, 88.4, "인하공전 정문"),
    (25, 37.4508, 126.6537, 73.2, "인하대 후문 사거리"),
    (35, 37.4535, 126.6510, 35.1, "용현시장 입구"),
    (40, 37.4549, 126.6498, None, "용현시장 골목"),
    (95, 37.4480, 126.6488, 64.7, "인하대역 1번 출구"),
    (105, 37.4441, 126.6522, 91.6, "학익동 버스정류장"),
]

DEMO_DEVICE = "demo-seed"


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
    base, _ = os.path.splitext(filename)
    for path in (os.path.join(UPLOAD_DIR, filename), os.path.join(UPLOAD_DIR, base + "_thumb.jpg")):
        if os.path.exists(path):
            os.remove(path)


def remove_demo(db):
    """지난번에 만든 시연 사건과 그 제보·알림·사진을 지운다. 다른 데이터는 건드리지 않는다."""
    demo_ids = {m["id"] for m in db["missing"] if m.get("demo")}
    if not demo_ids:
        return 0

    for m in db["missing"]:
        if m["id"] in demo_ids:
            for photo in m.get("photos", []):
                remove_file(photo)
    for r in db["reports"]:
        if r["missing_id"] in demo_ids and r.get("photo"):
            remove_file(r["photo"])

    db["missing"] = [m for m in db["missing"] if m["id"] not in demo_ids]
    db["reports"] = [r for r in db["reports"] if r["missing_id"] not in demo_ids]
    db["notifications"] = [n for n in db["notifications"] if n["missing_id"] not in demo_ids]
    return len(demo_ids)


def pick_guardian(db, name):
    users = db.get("users", [])
    if name:
        found = [u for u in users if u.get("name") == name]
        if not found:
            sys.exit(f"그 이름의 계정이 없습니다: {name} (있는 계정: {', '.join(u.get('name', '?') for u in users)})")
        return found[0]
    # 가장 최근에 사건을 등록한 계정. 시연하는 사람이 방금까지 쓰던 계정이다.
    for m in sorted(db["missing"], key=lambda m: m.get("created_at", ""), reverse=True):
        user = database.find_user(db, m.get("guardian_id"))
        if user:
            return user
    return None


def main():
    parser = argparse.ArgumentParser(description="시연 영상용 사건을 만든다")
    parser.add_argument("--guardian", help="보호자로 둘 카카오 닉네임 (기본: 최근 사건 등록자)")
    parser.add_argument("--minutes-ago", type=int, default=110, help="실종 시각 (기본 110분 전)")
    parser.add_argument("--remove", action="store_true", help="시연 사건만 지우고 끝낸다")
    args = parser.parse_args()

    db = database.load_db()
    removed = remove_demo(db)
    if removed:
        print(f"지난 시연 사건 {removed}건을 지웠습니다.")
    if args.remove:
        database.save_db(db)
        return

    if args.minutes_ago <= PATH[-1][0]:
        sys.exit(f"--minutes-ago는 마지막 제보({PATH[-1][0]}분)보다 커야 합니다. 미래 시각의 제보가 생깁니다.")

    register_photos = photos_in(REGISTER_DIR)
    report_photos = photos_in(REPORTS_DIR)
    if not register_photos:
        sys.exit(f"등록 사진이 없습니다: {REGISTER_DIR}")
    if not report_photos:
        sys.exit(f"제보 사진이 없습니다: {REPORTS_DIR}")

    guardian = pick_guardian(db, args.guardian)
    now = now_kst()
    missing_at = now - timedelta(minutes=args.minutes_ago)
    missing_id = database.new_id("m_")

    # 등록 사진은 얼굴 벡터를 진짜로 뽑는다. 라이브 제보가 이 벡터와 비교된다.
    photos, encoded_photos, encodings = [], [], []
    for i, src in enumerate(register_photos):
        filename = copy_photo(src, f"{missing_id}_{i}")
        photos.append(filename)
        encoding = face_service.get_face_encoding(os.path.join(UPLOAD_DIR, filename))
        if encoding is None:
            print(f"  얼굴 못 찾음 — 대조에서 뺍니다: {os.path.basename(src)}")
            continue
        encoded_photos.append(filename)
        encodings.append(list(map(float, encoding)))
    if not encodings:
        for photo in photos:
            remove_file(photo)
        sys.exit("등록 사진 전부에서 얼굴을 못 찾았습니다. 정면 사진으로 바꿔 주세요.")

    db["missing"].append({
        "id": missing_id,
        **CASE,
        "missing_at": missing_at.isoformat(),
        "photos": photos,
        "encoded_photos": encoded_photos,
        "encodings": encodings,
        "status": "active",
        "guardian_id": guardian["id"] if guardian else None,
        "created_at": missing_at.isoformat(),
        "demo": True,
    })

    for i, (minutes, lat, lng, similarity, place) in enumerate(PATH):
        report_id = database.new_id("r_")
        observed = missing_at + timedelta(minutes=minutes)
        face_found = similarity is not None
        db["reports"].append({
            "id": report_id,
            "missing_id": missing_id,
            "photo": copy_photo(report_photos[i % len(report_photos)], report_id),
            "lat": lat,
            "lng": lng,
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
            "device_hash": DEMO_DEVICE,
            "reporter_id": None,
        })

    recompute_route_indexes(db, missing_id)
    database.save_db(db)

    who = f"{guardian['name']} ({guardian['id']})" if guardian else "없음 — 보호자 모드는 안 보입니다"
    print(f"시연 사건을 만들었습니다: {CASE['name']} ({missing_id})")
    print(f"  보호자: {who}")
    print(f"  등록 사진 {len(photos)}장 중 얼굴 {len(encodings)}장 · 제보 {len(PATH)}건")
    print(f"  실종 시각: {missing_at:%H:%M} (골든타임은 {missing_at + timedelta(hours=3):%H:%M}까지)")
    print("  서버를 켜면 앱에 바로 보입니다.")


if __name__ == "__main__":
    main()
