"""얼굴대조 AI 로직 (face_recognition / dlib 기반).

등급 체계 (API 명세서 7절 · 기능정의서 5.2):
- high    : similarity >= 70   → route_index 부여
- medium  : 40 <= s < 70       → route_index 부여
- low     : s < 40             → 저장하되 경로 제외
- no_face : 얼굴 미검출        → 저장하되 경로 제외 (에러 아님)
"""
import face_recognition
import numpy as np

# high 등급 기준. 명세서가 정한 값이다.
#
# 실측에서는 동일 인물 정면 사진이 65.4%로 나와 이 선에 못 미친 적이 있다.
# 그래도 명세를 따른다 — 앱과 서버가 같은 기준을 써야 화면의 "높음"과 서버의
# 판단이 어긋나지 않는다. 기준을 바꿔야 한다면 명세부터 고친다.
SIMILARITY_HIGH = 70
SIMILARITY_ROUTE = 40  # 경로(route_index) 포함 기준


def get_face_encoding(path):
    """사진 경로 → 128차원 얼굴 인코딩 벡터. 얼굴이 없으면 None."""
    image = face_recognition.load_image_file(path)
    encodings = face_recognition.face_encodings(image)
    if not encodings:
        return None
    return encodings[0]  # 여러 명이면 첫 번째 얼굴 사용


def best_similarity(known_encodings, path):
    """등록 사진 인코딩들(여러 장)과 제보 사진을 비교해 최고 유사도 채택.

    returns: (similarity float|None, face_found bool, best_photo_index int|None)
    - 유사도% = (1 - face_distance) * 100, 소수 1자리 반올림
    """
    report_encoding = get_face_encoding(path)
    if report_encoding is None:
        return None, False, None

    distances = face_recognition.face_distance(
        np.array(known_encodings), report_encoding
    )
    best = int(np.argmin(distances))
    similarity = round(max(0.0, float(1 - distances[best])) * 100, 1)
    return similarity, True, best


def grade_of(similarity, face_found):
    """유사도 → 등급 문자열."""
    if not face_found:
        return "no_face"
    if similarity >= SIMILARITY_HIGH:
        return "high"
    if similarity >= SIMILARITY_ROUTE:
        return "medium"
    return "low"
