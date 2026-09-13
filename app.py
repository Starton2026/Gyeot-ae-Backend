"""곁애 (Gyeot-ae) 백엔드 — Flask 엔트리 + 라우팅.

2026-09-12 디자인 확정본 API 명세 1순위 구현:
- POST /reports/analyze + POST /reports  (분석·제보 2단계 분리)
- POST /missing (사진 다중 + 필드 확장), GET /missing (검색·필터·정렬·긴급도)
- GET /missing/<id>, GET /missing/<id>/reports (path + time_range + gap/bearing)
- 구 경로(POST /report, GET /reports/<id>)는 하위 호환 어댑터로 유지
"""
import os
import shutil
from datetime import timedelta

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

import db as database
import face_service
import firebase_service
from utils import bearing_8, elapsed_minutes, haversine_km, now_kst, parse_dt

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
TMP_DIR = os.path.join(UPLOAD_DIR, "tmp")  # 분석 임시 사진 (TTL 10분)
os.makedirs(TMP_DIR, exist_ok=True)

ANALYSIS_TTL_MINUTES = 10
RATE_LIMIT_COUNT = 3       # 게스트 제한: 사건 1건당 기기 기준
RATE_LIMIT_WINDOW_MIN = 10

app = Flask(__name__)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32MB (다중 사진)


# ── 공통 헬퍼 ────────────────────────────────────────────

def api_error(code, message, status, field=None):
    """명세 공통 에러 포맷."""
    err = {"code": code, "message": message}
    if field:
        err["field"] = field
    return jsonify({"error": err}), status


def save_photo(file, prefix, directory=UPLOAD_DIR):
    """업로드 파일 저장 후 파일명 반환. 이미지는 썸네일({이름}_thumb.jpg)도 생성."""
    filename = secure_filename(file.filename) or "photo.jpg"
    stamp = now_kst().strftime("%Y%m%d%H%M%S%f")
    saved_name = f"{prefix}_{stamp}_{filename}"
    path = os.path.join(directory, saved_name)
    file.save(path)
    if directory == UPLOAD_DIR:
        make_thumbnail(path)
    return saved_name


def make_thumbnail(path, width=400):
    """{이름}_thumb.jpg 규칙으로 목록용 썸네일 생성. 실패해도 무시."""
    try:
        from PIL import Image
        img = Image.open(path)
        img.thumbnail((width, width * 2))
        base, _ = os.path.splitext(path)
        img.convert("RGB").save(base + "_thumb.jpg", "JPEG", quality=80)
    except Exception:
        pass


def thumb_name(filename):
    base, _ = os.path.splitext(filename)
    thumb = base + "_thumb.jpg"
    if os.path.exists(os.path.join(UPLOAD_DIR, thumb)):
        return thumb
    return filename  # 썸네일 생성 실패 시 원본


def purge_expired_analyses(db):
    """TTL 지난 분석 결과와 임시 사진 삭제."""
    now = now_kst()
    kept = []
    for a in db["analyses"]:
        if parse_dt(a["expires_at"]) > now:
            kept.append(a)
        else:
            tmp = os.path.join(TMP_DIR, a["photo"])
            if os.path.exists(tmp):
                os.remove(tmp)
    db["analyses"] = kept


def recompute_route_indexes(db, missing_id):
    """유사도 40% 이상 + 표시 상태 제보를 observed_at 순으로 1..n 재부여."""
    reports = [
        r for r in database.case_reports(db, missing_id)
        if r["status"] == "visible" and r["face_found"]
        and (r["similarity"] or 0) >= face_service.SIMILARITY_ROUTE
    ]
    reports.sort(key=lambda r: r["observed_at"])
    indexed = {r["id"]: i + 1 for i, r in enumerate(reports)}
    changed = []
    for r in database.case_reports(db, missing_id):
        new_index = indexed.get(r["id"])
        if r.get("route_index") != new_index:
            r["route_index"] = new_index
            changed.append(r)
    return changed


def last_report_at(db, missing):
    reports = database.case_reports(db, missing["id"])
    if not reports:
        return missing["missing_at"]
    return max(r["observed_at"] for r in reports)


def urgency_score(db, m, user_lat=None, user_lng=None):
    """긴급도 = 골든타임 × 취약도 × 거리 × 제보공백 (부스트는 3순위)."""
    h = elapsed_minutes(m["missing_at"]) / 60
    golden = 3.0 if h < 3 else 2.0 if h < 12 else 1.5 if h < 48 else 1.0
    vuln = 1.5 if m.get("category") in ("child", "elderly") else 1.0
    dist = 1.0
    if user_lat is not None:
        km = haversine_km(m["last_lat"], m["last_lng"], user_lat, user_lng)
        dist = 2.0 if km <= 3 else 1.3 if km <= 10 else 1.0
    gap = 1.3 if elapsed_minutes(last_report_at(db, m)) > 60 else 1.0
    return round(golden * vuln * dist * gap, 1)


def urgency_level(m):
    if m["status"] == "resolved":
        return "resolved"
    h = elapsed_minutes(m["missing_at"]) / 60
    return "critical" if h < 3 else "high" if h < 12 else "normal"


def missing_summary(db, m, user_lat=None, user_lng=None):
    """목록 카드용 요약."""
    item = {
        "id": m["id"],
        "name": m["name"],
        "age": m.get("age"),
        "gender": m.get("gender"),
        "category": m.get("category"),
        "description": m.get("description", ""),
        "thumbnail": f"/uploads/{thumb_name(m['photos'][0])}" if m.get("photos") else None,
        "last_lat": m["last_lat"],
        "last_lng": m["last_lng"],
        "last_address": m.get("last_address"),
        "missing_at": m["missing_at"],
        "elapsed_minutes": elapsed_minutes(m["missing_at"]),
        "status": m["status"],
        "report_count": len(database.case_reports(db, m["id"])),
        "urgency_score": urgency_score(db, m, user_lat, user_lng),
        "urgency_level": urgency_level(m),
    }
    if user_lat is not None:
        item["distance_km"] = round(
            haversine_km(m["last_lat"], m["last_lng"], user_lat, user_lng), 1
        )
    return item


def report_public(r):
    """제보 응답 공통 형태."""
    return {
        "id": r["id"],
        "route_index": r.get("route_index"),
        "lat": r["lat"],
        "lng": r["lng"],
        "place_name": r.get("place_name"),
        "observed_at": r["observed_at"],
        "created_at": r["created_at"],
        "similarity": r["similarity"],
        "grade": r["grade"],
        "face_found": r["face_found"],
        "photo_url": f"/uploads/{r['photo']}",
        "status": r["status"],
        "confirmed": r.get("confirmed", False),
    }


# ── 5) 실종자 등록 — S7 ─────────────────────────────────
@app.route("/missing", methods=["POST"])
def register_missing():
    photos = request.files.getlist("photos") or request.files.getlist("photos[]")
    if not photos and request.files.get("photo"):  # 구버전 단일 photo 호환
        photos = [request.files["photo"]]
    name = request.form.get("name")

    if not name:
        return api_error("VALIDATION_ERROR", "name은 필수입니다.", 400, "name")
    if not photos:
        return api_error("VALIDATION_ERROR", "photos는 1장 이상 필수입니다.", 400, "photos")
    try:
        last_lat = float(request.form["last_lat"])
        last_lng = float(request.form["last_lng"])
    except (KeyError, ValueError):
        return api_error("VALIDATION_ERROR", "last_lat/last_lng는 숫자로 필수입니다.", 400, "last_lat")

    # 사진 저장 + 얼굴 인코딩 (얼굴 있는 사진의 벡터를 전부 저장)
    saved, encodings, encoded_photos = [], [], []
    for f in photos:
        fname = save_photo(f, "m")
        saved.append(fname)
        enc = face_service.get_face_encoding(os.path.join(UPLOAD_DIR, fname))
        if enc is not None:
            encodings.append(enc.tolist())
            encoded_photos.append(fname)

    if not encodings:  # 모든 사진에서 얼굴 미검출 → 등록 거부
        for fname in saved:
            for p in (fname, thumb_name(fname)):
                path = os.path.join(UPLOAD_DIR, p)
                if os.path.exists(path):
                    os.remove(path)
        return api_error(
            "FACE_NOT_FOUND",
            "사진에서 얼굴을 찾지 못했습니다. 얼굴이 잘 보이는 사진을 한 장 이상 올려주세요.",
            400, "photos",
        )

    now = now_kst()
    missing_at = request.form.get("missing_at")
    try:
        missing_at = parse_dt(missing_at).isoformat() if missing_at else now.isoformat()
    except ValueError:
        return api_error("VALIDATION_ERROR", "missing_at 형식이 올바르지 않습니다.", 400, "missing_at")

    db = database.load_db()
    missing = {
        "id": database.new_id("m_"),
        "name": name,
        "age": int(request.form["age"]) if request.form.get("age") else None,
        "gender": request.form.get("gender"),
        "category": request.form.get("category", "other"),
        "description": request.form.get("description", ""),
        "height_cm": int(request.form["height_cm"]) if request.form.get("height_cm") else None,
        "weight_kg": int(request.form["weight_kg"]) if request.form.get("weight_kg") else None,
        "last_lat": last_lat,
        "last_lng": last_lng,
        "last_address": request.form.get("last_address"),
        "missing_at": missing_at,
        "guardian_phone": request.form.get("guardian_phone", ""),  # 제보자 비공개
        "photos": saved,
        "encoded_photos": encoded_photos,  # encodings[i]가 어떤 사진의 벡터인지
        "encodings": encodings,
        "status": "active",
        "created_at": now.isoformat(),
    }
    db["missing"].append(missing)
    database.save_db(db)
    firebase_service.push_missing(missing)  # 관제 화면 실시간 반영

    return jsonify({
        "id": missing["id"],
        "name": missing["name"],
        "photos": [f"/uploads/{p}" for p in saved],
        "face_encoding_count": len(encodings),
        "notified_devices": 0,  # 푸시 인프라는 2순위 — 스텁
    }), 201


# ── 6) 실종자 목록 — S1·S2·S5 ───────────────────────────
@app.route("/missing", methods=["GET"])
def list_missing():
    db = database.load_db()
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "all")
    status = request.args.get("status", "active")
    sort = request.args.get("sort", "urgency")
    user_lat = request.args.get("lat", type=float)
    user_lng = request.args.get("lng", type=float)
    radius_km = request.args.get("radius_km", type=float)
    limit = request.args.get("limit", default=20, type=int)
    cursor = request.args.get("cursor", default=0, type=int)

    items = db["missing"]
    if status != "all":
        items = [m for m in items if m["status"] == status]
    if category != "all":
        items = [m for m in items if m.get("category") == category]
    if q:
        items = [m for m in items
                 if q in m["name"] or q in (m.get("last_address") or "")]
    if radius_km and user_lat is not None:
        items = [m for m in items
                 if haversine_km(m["last_lat"], m["last_lng"], user_lat, user_lng) <= radius_km]

    summaries = [missing_summary(db, m, user_lat, user_lng) for m in items]
    if sort == "recent":
        summaries.sort(key=lambda s: s["missing_at"], reverse=True)
    elif sort == "distance" and user_lat is not None:
        summaries.sort(key=lambda s: s.get("distance_km", 1e9))
    else:  # urgency (기본)
        summaries.sort(key=lambda s: s["urgency_score"], reverse=True)

    page = summaries[cursor:cursor + limit]
    next_cursor = str(cursor + limit) if cursor + limit < len(summaries) else None
    return jsonify({"count": len(summaries), "next_cursor": next_cursor, "items": page})


# ── 7) 실종자 상세 — S3 ─────────────────────────────────
@app.route("/missing/<missing_id>", methods=["GET"])
def missing_detail(missing_id):
    db = database.load_db()
    m = database.find_missing(db, missing_id)
    if m is None:
        return api_error("NOT_FOUND", f"존재하지 않는 실종자입니다: {missing_id}", 404)

    reports = database.case_reports(db, missing_id)
    detail = {
        "id": m["id"], "name": m["name"], "age": m.get("age"),
        "gender": m.get("gender"), "category": m.get("category"),
        "description": m.get("description", ""),
        "height_cm": m.get("height_cm"), "weight_kg": m.get("weight_kg"),
        "photos": [f"/uploads/{p}" for p in m.get("photos", [])],
        "last_lat": m["last_lat"], "last_lng": m["last_lng"],
        "last_address": m.get("last_address"),
        "missing_at": m["missing_at"],
        "elapsed_minutes": elapsed_minutes(m["missing_at"]),
        "status": m["status"],
        "report_count": len(reports),
        "match_count": sum(1 for r in reports if r.get("route_index")),
        "is_guardian": False,      # 인증은 2순위
        "boost_available": False,  # 부스트는 3순위
    }
    return jsonify(detail)


# ── 13) 사진 분석 — S4-1 ★ ──────────────────────────────
@app.route("/reports/analyze", methods=["POST"])
def analyze_report():
    photo = request.files.get("photo")
    missing_id = request.form.get("missing_id")
    if not photo or not missing_id:
        return api_error("VALIDATION_ERROR", "missing_id, photo는 필수입니다.", 400, "photo")

    db = database.load_db()
    purge_expired_analyses(db)
    m = database.find_missing(db, missing_id)
    if m is None:
        return api_error("NOT_FOUND", f"존재하지 않는 실종자입니다: {missing_id}", 404)

    analysis_id = database.new_id("an_")
    ext = os.path.splitext(secure_filename(photo.filename) or "p.jpg")[1] or ".jpg"
    tmp_name = f"{analysis_id}{ext}"
    photo.save(os.path.join(TMP_DIR, tmp_name))

    similarity, face_found, best_idx = face_service.best_similarity(
        m["encodings"], os.path.join(TMP_DIR, tmp_name)
    )
    grade = face_service.grade_of(similarity, face_found)
    matched_photo = m["encoded_photos"][best_idx] if face_found else None

    now = now_kst()
    analysis = {
        "id": analysis_id,
        "missing_id": missing_id,
        "photo": tmp_name,
        "similarity": similarity,
        "face_found": face_found,
        "grade": grade,
        "matched_photo": matched_photo,
        "expires_at": (now + timedelta(minutes=ANALYSIS_TTL_MINUTES)).isoformat(),
    }
    db["analyses"].append(analysis)
    database.save_db(db)

    return jsonify({
        "analysis_id": analysis_id,
        "similarity": similarity,
        "grade": grade,
        "face_found": face_found,
        "photo_url": f"/uploads/tmp/{tmp_name}",
        "matched_photo_url": f"/uploads/{matched_photo}" if matched_photo else None,
        "expires_at": analysis["expires_at"],
    })


# ── 14) 제보 확정 — S4 ★ ────────────────────────────────
@app.route("/reports", methods=["POST"])
def create_report():
    data = request.get_json(silent=True) or {}
    analysis_id = data.get("analysis_id")
    if not analysis_id:
        return api_error("VALIDATION_ERROR", "analysis_id는 필수입니다.", 400, "analysis_id")
    try:
        lat, lng = float(data["lat"]), float(data["lng"])
    except (KeyError, TypeError, ValueError):
        return api_error("VALIDATION_ERROR", "lat/lng는 숫자로 필수입니다.", 400, "lat")

    db = database.load_db()
    purge_expired_analyses(db)
    analysis = database.find_analysis(db, analysis_id)
    if analysis is None:
        return api_error("ANALYSIS_EXPIRED", "분석 결과가 만료되었습니다. 다시 분석해 주세요.", 410)
    m = database.find_missing(db, analysis["missing_id"])
    if m is None:
        return api_error("NOT_FOUND", "실종자 정보를 찾을 수 없습니다.", 404)

    # 게스트 남용 방지: 사건 1건당 기기 기준 10분 내 3회
    device_hash = request.headers.get("X-Device-Hash", "anonymous")
    now = now_kst()
    recent = [
        r for r in database.case_reports(db, m["id"])
        if r.get("device_hash") == device_hash
        and elapsed_minutes(r["created_at"]) < RATE_LIMIT_WINDOW_MIN
    ]
    if len(recent) >= RATE_LIMIT_COUNT:
        return jsonify({"error": {
            "code": "RATE_LIMITED", "message": "잠시 후 다시 시도해 주세요.",
            "retry_after": RATE_LIMIT_WINDOW_MIN * 60,
        }}), 429

    observed_at = data.get("observed_at")
    try:
        observed_at = parse_dt(observed_at).isoformat() if observed_at else now.isoformat()
    except ValueError:
        return api_error("VALIDATION_ERROR", "observed_at 형식이 올바르지 않습니다.", 400, "observed_at")

    report_id = database.new_id("r_")
    # 임시 사진 → 정식 경로 이동
    ext = os.path.splitext(analysis["photo"])[1]
    final_name = f"{report_id}{ext}"
    shutil.move(os.path.join(TMP_DIR, analysis["photo"]),
                os.path.join(UPLOAD_DIR, final_name))
    make_thumbnail(os.path.join(UPLOAD_DIR, final_name))
    db["analyses"].remove(analysis)

    report = {
        "id": report_id,
        "missing_id": m["id"],
        "photo": final_name,
        "lat": lat,
        "lng": lng,
        "place_name": data.get("place_name"),
        "observed_at": observed_at,
        "created_at": now.isoformat(),
        "timestamp": parse_dt(observed_at).timestamp(),  # 정렬용 epoch
        "similarity": analysis["similarity"],
        "face_found": analysis["face_found"],
        "grade": analysis["grade"],
        "route_index": None,  # 아래 재계산에서 부여
        "status": "visible",
        "confirmed": False,
        "device_hash": device_hash,
    }
    db["reports"].append(report)
    changed = recompute_route_indexes(db, m["id"])
    database.save_db(db)

    # 관제 화면 실시간 반영 (route_index 바뀐 제보 포함)
    to_push = {r["id"]: r for r in changed}
    to_push[report["id"]] = report
    firebase_service.push_case_reports(to_push.values(), m["name"])

    return jsonify({
        "id": report["id"],
        "missing_id": m["id"],
        "similarity": report["similarity"],
        "grade": report["grade"],
        "route_index": report["route_index"],
        "photo_url": f"/uploads/{final_name}",
        "observed_at": report["observed_at"],
        "created_at": report["created_at"],
        "guardian_notified": firebase_service.is_enabled(),
    }), 201


# ── 15) 제보 목록 / 이동 경로 — S3·S5 ★ ─────────────────
@app.route("/missing/<missing_id>/reports", methods=["GET"])
def case_reports_api(missing_id):
    db = database.load_db()
    m = database.find_missing(db, missing_id)
    if m is None:
        return api_error("NOT_FOUND", f"존재하지 않는 실종자입니다: {missing_id}", 404)

    min_similarity = request.args.get("min_similarity", default=0, type=float)
    include_low = request.args.get("include_low", "true").lower() != "false"
    until = request.args.get("until")

    all_reports = [r for r in database.case_reports(db, missing_id)
                   if r["status"] == "visible"]
    if until:
        try:
            until_dt = parse_dt(until)
            all_reports = [r for r in all_reports if parse_dt(r["observed_at"]) <= until_dt]
        except ValueError:
            return api_error("VALIDATION_ERROR", "until 형식이 올바르지 않습니다.", 400, "until")

    def visible_by_filter(r):
        if min_similarity > 0 and (r["similarity"] or 0) < min_similarity:
            return False
        if not include_low and r["grade"] in ("low", "no_face"):
            return False
        return True

    shown = [r for r in all_reports if visible_by_filter(r)]
    hidden_count = len(all_reports) - len(shown)

    # 타임라인용: 최신순 + 시간순 기준의 공백/이동 방향 계산
    chrono = sorted(shown, key=lambda r: r["observed_at"])
    prev_point = {"lat": m["last_lat"], "lng": m["last_lng"], "at": m["missing_at"]}
    extra = {}
    for r in chrono:
        gap = int((parse_dt(r["observed_at"]) - parse_dt(prev_point["at"])).total_seconds() // 60)
        e = {"gap_minutes": max(0, gap)}
        if r.get("route_index"):
            e["bearing"] = bearing_8(prev_point["lat"], prev_point["lng"], r["lat"], r["lng"])
            e["distance_from_prev_km"] = round(
                haversine_km(prev_point["lat"], prev_point["lng"], r["lat"], r["lng"]), 1)
            prev_point = {"lat": r["lat"], "lng": r["lng"], "at": r["observed_at"]}
        extra[r["id"]] = e

    reports_out = []
    for r in sorted(shown, key=lambda x: x["observed_at"], reverse=True):  # 최신이 위
        item = report_public(r)
        item.update(extra[r["id"]])
        reports_out.append(item)

    # 경로: 최초 실종 지점(origin) + route_index 있는 제보를 시간순으로
    route = [r for r in chrono if r.get("route_index")]
    path = [{"lat": m["last_lat"], "lng": m["last_lng"], "at": m["missing_at"],
             "index": 0, "origin": True}]
    for i, r in enumerate(route):
        path.append({"lat": r["lat"], "lng": r["lng"], "at": r["observed_at"], "index": i + 1})

    ticks = [r["observed_at"] for r in route]
    time_range = {
        "from": m["missing_at"],
        "to": ticks[-1] if ticks else m["missing_at"],
        "ticks": ticks,
    }

    return jsonify({
        "missing_id": missing_id,
        "count": len(reports_out),
        "hidden_count": hidden_count,
        "origin": {"lat": m["last_lat"], "lng": m["last_lng"],
                   "address": m.get("last_address"), "at": m["missing_at"]},
        "reports": reports_out,
        "path": path,
        "time_range": time_range,
    })


# ── 19) 사진 서빙 ────────────────────────────────────────
@app.route("/uploads/<path:filename>", methods=["GET"])
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)


# ── 하위 호환 어댑터 (deprecated) ────────────────────────
@app.route("/report", methods=["POST"])
def legacy_report():
    """구 API: 업로드+분석+저장 한 번에. 신 로직으로 위임 후 구 응답 형태 반환."""
    photo = request.files.get("photo")
    missing_id = request.form.get("missing_id")
    if not photo or not missing_id:
        return jsonify({"error": "missing_id, lat, lng, photo는 필수입니다."}), 400
    try:
        lat, lng = float(request.form["lat"]), float(request.form["lng"])
    except (KeyError, ValueError):
        return jsonify({"error": "lat/lng는 숫자여야 합니다."}), 400

    db = database.load_db()
    m = database.find_missing(db, missing_id)
    if m is None:
        return jsonify({"error": f"존재하지 않는 missing_id입니다: {missing_id}"}), 404

    report_id = database.new_id("r_")
    fname = save_photo(photo, report_id)
    similarity, face_found, _ = face_service.best_similarity(
        m["encodings"], os.path.join(UPLOAD_DIR, fname))
    grade = face_service.grade_of(similarity, face_found)
    now = now_kst()
    report = {
        "id": report_id, "missing_id": missing_id, "photo": fname,
        "lat": lat, "lng": lng, "place_name": None,
        "observed_at": now.isoformat(), "created_at": now.isoformat(),
        "timestamp": now.timestamp(),
        "similarity": similarity, "face_found": face_found, "grade": grade,
        "route_index": None, "status": "visible", "confirmed": False,
        "device_hash": request.headers.get("X-Device-Hash", "legacy"),
    }
    db["reports"].append(report)
    changed = recompute_route_indexes(db, missing_id)
    database.save_db(db)
    to_push = {r["id"]: r for r in changed}
    to_push[report["id"]] = report
    firebase_service.push_case_reports(to_push.values(), m["name"])

    is_match = face_found and similarity >= face_service.SIMILARITY_HIGH
    if not face_found:
        message = "사진에서 얼굴을 찾지 못했습니다."
    elif is_match:
        message = f"{m['name']}님과 유사한 인물이 제보되었습니다!"
    else:
        message = "제보가 접수되었으나 유사도가 낮습니다."
    return jsonify({
        "message": message, "report_id": report_id,
        "similarity": similarity if similarity is not None else 0.0,
        "face_found": face_found, "is_match": is_match, "alert": is_match,
    }), 201


@app.route("/reports/<missing_id>", methods=["GET"])
def legacy_reports(missing_id):
    """구 API: only_match=1 필터 + 구 응답 형태."""
    if missing_id.startswith("an_") or missing_id == "analyze":
        return api_error("NOT_FOUND", "잘못된 경로입니다.", 404)
    db = database.load_db()
    m = database.find_missing(db, missing_id)
    if m is None:
        return jsonify({"error": f"존재하지 않는 missing_id입니다: {missing_id}"}), 404

    only_match = request.args.get("only_match") == "1"
    reports = [r for r in database.case_reports(db, missing_id) if r["status"] == "visible"]
    if only_match:
        reports = [r for r in reports
                   if r["face_found"] and (r["similarity"] or 0) >= face_service.SIMILARITY_HIGH]
    reports.sort(key=lambda r: r["observed_at"])
    old_shape = [{
        "id": r["id"], "missing_id": r["missing_id"], "lat": r["lat"], "lng": r["lng"],
        "photo": r["photo"], "similarity": r["similarity"] or 0.0,
        "face_found": r["face_found"],
        "is_match": r["face_found"] and (r["similarity"] or 0) >= face_service.SIMILARITY_HIGH,
        "reported_at": r["observed_at"], "timestamp": r["timestamp"],
    } for r in reports]
    path = [{"lat": r["lat"], "lng": r["lng"], "time": r["observed_at"]} for r in reports]
    return jsonify({"missing_id": missing_id, "count": len(old_shape),
                    "reports": old_shape, "path": path})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
