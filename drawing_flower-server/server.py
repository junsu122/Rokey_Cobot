"""
Render 배포용 Flask 서버
POST /process  →  이미지 수신 → 픽셀 처리 → Firestore 저장
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from PIL import Image, ImageOps
import firebase_admin
from firebase_admin import credentials, firestore
import io
import os

app = Flask(__name__)
CORS(app)  # React 로컬/배포 도메인 허용

# ── Firebase 초기화 ──────────────────────────────────────────────
# Render 환경변수에 서비스 계정 JSON 경로 또는 내용을 설정
# (방법 A) 파일 경로
import json
cred_json = json.loads(os.environ["FIREBASE_CREDENTIALS_JSON"])
cred = credentials.Certificate(cred_json)

# (방법 B) JSON 문자열 환경변수로 직접 주입하는 경우 아래 주석 해제
# import json
# cred_json = json.loads(os.environ["FIREBASE_CREDENTIALS_JSON"])
# cred = credentials.Certificate(cred_json)


firebase_admin.initialize_app(cred)
db = firestore.client()


# ─────────────────────────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────────────────────────
ROWS, COLS     = 8, 9
NORMALIZE_W    = 180
NORMALIZE_H    = 160
DEFAULT_THRESH = 160
DEFAULT_MARGIN = 12
OUTPUT_AREA_W  = 200.0
OUTPUT_AREA_H  = 200.0
OUTPUT_GAP     = 2.0
OUTPUT_BASE_X  = 300.0
OUTPUT_BASE_Z  = 40.0


# ─────────────────────────────────────────────────────────────────
# 엔드포인트
# ─────────────────────────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    """Render 헬스체크용"""
    return jsonify({"status": "ok"})


@app.route("/process", methods=["POST"])
def process():
    """
    React에서 multipart/form-data로 이미지 + jobId 전송
    → 픽셀 처리 → Firestore 저장 → 결과 반환
    """
    job_id = request.form.get("jobId")
    image_file = request.files.get("image")

    if not job_id or not image_file:
        return jsonify({"error": "jobId와 image가 필요합니다"}), 400

    job_ref = db.collection("pixel_jobs").document(job_id)

    try:
        job_ref.set({"status": "processing"})

        image = Image.open(io.BytesIO(image_file.read())).convert("RGB")

        threshold = int(request.form.get("threshold", DEFAULT_THRESH))
        margin    = int(request.form.get("margin", DEFAULT_MARGIN))
        symmetry  = request.form.get("symmetry", "true").lower() == "true"

        coords = process_image(image, threshold, margin, symmetry)

        job_ref.update({"status": "complete", "coords": coords})

        return jsonify({"status": "complete", "coords": coords})

    except Exception as e:
        job_ref.update({"status": "error", "error": str(e)})
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────
# 픽셀 처리 파이프라인
# ─────────────────────────────────────────────────────────────────
def process_image(image, threshold=DEFAULT_THRESH, margin=DEFAULT_MARGIN, symmetry=True):
    gray       = image.convert("L")
    binary     = _to_binary_mask(gray, threshold)
    cropped    = _crop_to_content(binary)
    normalized = _normalize_to_canvas(cropped, margin)
    small      = normalized.resize((COLS, ROWS), Image.NEAREST)
    if symmetry:
        small = _apply_horizontal_symmetry(small)
    return _mask_to_coords(small)


def _to_binary_mask(gray, threshold):
    return gray.point(lambda p: 0 if p < threshold else 255)

def _crop_to_content(binary):
    bbox = ImageOps.invert(binary).getbbox()
    return binary.crop(bbox) if bbox else binary

def _normalize_to_canvas(cropped, margin):
    w, h = cropped.size
    if w <= 0 or h <= 0:
        return Image.new("L", (NORMALIZE_W, NORMALIZE_H), 255)
    usable_w = max(1, NORMALIZE_W - 2 * margin)
    usable_h = max(1, NORMALIZE_H - 2 * margin)
    scale = min(usable_w / w, usable_h / h)
    new_w, new_h = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    resized = cropped.resize((new_w, new_h), Image.NEAREST)
    canvas = Image.new("L", (NORMALIZE_W, NORMALIZE_H), 255)
    canvas.paste(resized, ((NORMALIZE_W - new_w) // 2, (NORMALIZE_H - new_h) // 2))
    return canvas

def _apply_horizontal_symmetry(mask):
    result = mask.copy()
    for row in range(ROWS):
        for col in range(COLS // 2):
            mirror = COLS - 1 - col
            if result.getpixel((col, row)) == 0 or result.getpixel((mirror, row)) == 0:
                result.putpixel((col, row), 0)
                result.putpixel((mirror, row), 0)
    return result

def _mask_to_coords(mask):
    cell_w = OUTPUT_AREA_W / COLS
    cell_h = OUTPUT_AREA_H / ROWS
    coords = {}
    idx = 0
    for row in reversed(range(ROWS)):
        for col in range(COLS):
            if mask.getpixel((col, row)) == 0:
                x = OUTPUT_BASE_X + cell_w / 2 + col * (cell_w + OUTPUT_GAP)
                z = cell_h / 2 + (ROWS - 1 - row) * cell_h + OUTPUT_BASE_Z
                coords[str(idx)] = [round(x, 1), 100.0, round(z, 1), 0.0, 180.0, 0.0]
                idx += 1
    return coords


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
