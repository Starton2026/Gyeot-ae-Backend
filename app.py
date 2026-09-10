"""곁애 (Gyeot-ae) 백엔드 — Flask 엔트리 + 라우팅."""
import os
from datetime import datetime

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

import db as database
import face_service
import firebase_service

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB


def _save_photo(file, prefix):
    """업로드 파일 저장 후 파일명 반환."""
    filename = secure_filename(file.filename) or "photo.jpg"
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    saved_name = f"{prefix}_{stamp}_{filename}"
    file.save(os.path.join(UPLOAD_DIR, saved_name))
    return saved_name


# ── 1) 실종자 등록 (보호자) ──────────────────────────────
@app.route("/missing", methods=["POST"])
def register_missing():
    photo = request.files.get("photo")
    name = request.form.get("name")
    description = request.form.get("description", "")
    last_lat = request.form.get("last_lat")
    last_lng = request.form.get("last_lng")

    if not photo or not name or last_lat is None or last_lng is None:
        return jsonify({"error": "name, last_lat, last_lng, photo는 필수입니다."}), 400

    try:
        last_lat, last_lng = float(last_lat), float(last_lng)
    except ValueError:
        return jsonify({"error": "last_lat/last_lng는 숫자여야 합니다."}), 400

    saved_name = _save_photo(photo, "missing")
    encoding = face_service.get_face_encoding(os.path.join(UPLOAD_DIR, saved_name))
    if encoding is None:
        os.remove(os.path.join(UPLOAD_DIR, saved_name))
        return jsonify({"error": "사진에서 얼굴을 찾지 못했습니다. 얼굴이 잘 보이는 사진을 올려주세요."}), 400

    db = database.load_db()
    missing = {
        "id": database.new_id(),
        "name": name,
        "description": description,
        "last_lat": last_lat,
        "last_lng": last_lng,
        "photo": saved_name,
        "encoding": encoding.tolist(),
        "registered_at": datetime.now().isoformat(),
        "status": "실종중",
    }
    db["missing"].append(missing)
    database.save_db(db)
    firebase_service.push_missing(missing)  # 관제 화면 실시간 반영

    return jsonify({
        "message": "실종자 등록 완료",
        "missing_id": missing["id"],
        "name": missing["name"],
    }), 201


# ── 2) 제보 접수 (시민) — 얼굴대조 실행 ─────────────────
@app.route("/report", methods=["POST"])
def submit_report():
    photo = request.files.get("photo")
    missing_id = request.form.get("missing_id")
    lat = request.form.get("lat")
    lng = request.form.get("lng")

    if not photo or not missing_id or lat is None or lng is None:
        return jsonify({"error": "missing_id, lat, lng, photo는 필수입니다."}), 400

    try:
        lat, lng = float(lat), float(lng)
    except ValueError:
        return jsonify({"error": "lat/lng는 숫자여야 합니다."}), 400

    db = database.load_db()
    missing = database.find_missing(db, missing_id)
    if missing is None:
        return jsonify({"error": f"존재하지 않는 missing_id입니다: {missing_id}"}), 404

    saved_name = _save_photo(photo, "report")
    similarity, face_found, is_match = face_service.compare_faces(
        missing["encoding"], os.path.join(UPLOAD_DIR, saved_name)
    )

    now = datetime.now()
    report = {
        "id": database.new_id(),
        "missing_id": missing_id,
        "lat": lat,
        "lng": lng,
        "photo": saved_name,
        "similarity": similarity,
        "face_found": face_found,
        "is_match": is_match,
        "reported_at": now.isoformat(),
        "timestamp": now.timestamp(),
    }
    db["reports"].append(report)
    database.save_db(db)
    firebase_service.push_report(report, missing["name"])  # 관제 화면 실시간 반영

    if not face_found:
        message, alert = "사진에서 얼굴을 찾지 못했습니다.", False
    elif is_match:
        message, alert = f"{missing['name']}님과 유사한 인물이 제보되었습니다!", True
    else:
        message, alert = "제보가 접수되었으나 유사도가 낮습니다.", False

    return jsonify({
        "message": message,
        "report_id": report["id"],
        "similarity": similarity,
        "face_found": face_found,
        "is_match": is_match,
        "alert": alert,
    }), 201


# ── 3) 제보 목록/경로 (관제 지도) ────────────────────────
@app.route("/reports/<missing_id>", methods=["GET"])
def get_reports(missing_id):
    db = database.load_db()
    if database.find_missing(db, missing_id) is None:
        return jsonify({"error": f"존재하지 않는 missing_id입니다: {missing_id}"}), 404

    only_match = request.args.get("only_match") == "1"
    reports = [r for r in db["reports"] if r["missing_id"] == missing_id]
    if only_match:
        reports = [r for r in reports if r["is_match"]]

    reports.sort(key=lambda r: r["timestamp"])
    path = [{"lat": r["lat"], "lng": r["lng"], "time": r["reported_at"]} for r in reports]

    return jsonify({
        "missing_id": missing_id,
        "count": len(reports),
        "reports": reports,
        "path": path,
    })


# ── 4) 실종자 목록 ───────────────────────────────────────
@app.route("/missing", methods=["GET"])
def list_missing():
    db = database.load_db()
    result = [{k: v for k, v in m.items() if k != "encoding"} for m in db["missing"]]
    return jsonify({"count": len(result), "missing": result})


# ── 5) 사진 서빙 ─────────────────────────────────────────
@app.route("/uploads/<path:filename>", methods=["GET"])
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
