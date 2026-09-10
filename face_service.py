"""얼굴대조 AI 로직 (face_recognition / dlib 기반)."""
import face_recognition
import numpy as np

SIMILARITY_THRESHOLD = 60  # 이 값(%) 이상이면 매칭으로 판단


def get_face_encoding(path):
    """사진 경로 → 128차원 얼굴 인코딩 벡터. 얼굴이 없으면 None."""
    image = face_recognition.load_image_file(path)
    encodings = face_recognition.face_encodings(image)
    if not encodings:
        return None
    return encodings[0]  # 여러 명이면 첫 번째 얼굴 사용


def compare_faces(known_encoding, path):
    """등록된 실종자 인코딩과 제보 사진을 비교.

    returns: (similarity %, face_found, is_match)
    - 얼굴 미검출 시 similarity=0, face_found=False
    - 유사도% = (1 - face_distance) * 100, 소수 1자리 반올림
    """
    report_encoding = get_face_encoding(path)
    if report_encoding is None:
        return 0.0, False, False

    distance = face_recognition.face_distance(
        [np.array(known_encoding)], report_encoding
    )[0]
    # numpy 타입은 JSON 직렬화가 안 되므로 파이썬 기본 타입으로 변환
    similarity = round(max(0.0, float(1 - distance)) * 100, 1)
    is_match = bool(similarity >= SIMILARITY_THRESHOLD)
    return similarity, True, is_match
