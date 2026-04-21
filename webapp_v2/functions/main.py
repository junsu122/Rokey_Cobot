import io
import firebase_admin
from firebase_admin import storage, firestore
from firebase_functions import storage_fn
from PIL import Image, ImageOps

firebase_admin.initialize_app()

# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────
ROWS, COLS   = 8, 9
NORM_W       = 200
NORM_H       = 200

# ─────────────────────────────────────────────
# 전처리 클래스 (pixel_extractor.py 내용 인라인)
# ─────────────────────────────────────────────
class ImagePreprocessor:
    def __init__(self, rows=ROWS, cols=COLS):
        self.rows = rows
        self.cols = cols

    def run(self, image, threshold=160, margin=12, symmetry=True):
        gray    = image.convert("L")
        binary  = gray.point(lambda p: 0 if p < threshold else 255)
        bbox    = ImageOps.invert(binary).getbbox()
        cropped = binary.crop(bbox) if bbox else binary

        w, h = cropped.size
        usable_w = max(1, NORM_W - 2 * margin)
        usable_h = max(1, NORM_H - 2 * margin)
        scale    = min(usable_w / w, usable_h / h)
        new_w    = max(1, int(round(w * scale)))
        new_h    = max(1, int(round(h * scale)))

        resized  = cropped.resize((new_w, new_h), Image.NEAREST)
        canvas   = Image.new("L", (NORM_W, NORM_H), 255)
        canvas.paste(resized, ((NORM_W - new_w) // 2, (NORM_H - new_h) // 2))
        normalized = canvas

        small = normalized.resize((self.cols, self.rows), Image.NEAREST)

        if symmetry:
            for row in range(self.rows):
                for col in range(self.cols // 2):
                    mirror = self.cols - 1 - col
                    if small.getpixel((col, row)) == 0 or small.getpixel((mirror, row)) == 0:
                        small.putpixel((col, row), 0)
                        small.putpixel((mirror, row), 0)

        text_preview = "\n".join(
            " ".join("■" if small.getpixel((c, r)) == 0 else "□" for c in range(self.cols))
            for r in range(self.rows)
        )

        return {
            "normalized": normalized,
            "mask":       small,
            "text_preview": text_preview,
        }


# ─────────────────────────────────────────────
# Cloud Functions 트리거
# images/ 폴더에 파일이 업로드되면 자동 실행
# ─────────────────────────────────────────────
@storage_fn.on_object_finalized(region="asia-northeast3")
def process_image(event: storage_fn.CloudEvent):
    file_path: str = event.data.name

    # images/ 폴더 파일만 처리
    if not file_path.startswith("images/"):
        return

    file_name = file_path.split("/")[-1]
    doc_id    = f"images_{file_name}"
    db        = firestore.client()
    bucket    = storage.bucket()

    print(f"처리 시작: {file_path}")

    # 1. Firestore pixel_jobs에서 파라미터 읽기
    job    = db.collection("pixel_jobs").document(doc_id).get()
    params = job.to_dict().get("params", {}) if job.exists else {}
    threshold = params.get("threshold", 160)
    margin    = params.get("margin", 12)
    symmetry  = params.get("symmetry", True)
    print(f"파라미터: threshold={threshold}, margin={margin}, symmetry={symmetry}")

    # 2. Storage에서 이미지 다운로드
    image_bytes = bucket.blob(file_path).download_as_bytes()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # 3. 전처리
    result = ImagePreprocessor().run(image, threshold=threshold, margin=margin, symmetry=symmetry)

    # 4. 정규화 이미지 Storage 업로드
    norm_buf = io.BytesIO()
    result["normalized"].convert("RGB").save(norm_buf, format="PNG")
    norm_buf.seek(0)
    normalized_path = f"previews/{doc_id}_normalized.png"
    bucket.blob(normalized_path).upload_from_file(norm_buf, content_type="image/png")

    # 5. 픽셀화 이미지 Storage 업로드
    pixel_buf = io.BytesIO()
    result["mask"].resize((180, 160), Image.NEAREST).convert("RGB").save(pixel_buf, format="PNG")
    pixel_buf.seek(0)
    pixel_path = f"previews/{doc_id}_pixel.png"
    bucket.blob(pixel_path).upload_from_file(pixel_buf, content_type="image/png")

    # 6. Firestore에 저장 (status: preprocessed)
    db.collection("pixel_coords").document(doc_id).set({
        "file":            file_path,
        "normalized_path": normalized_path,
        "pixel_path":      pixel_path,
        # "text_preview":    result["text_preview"],
        "status":          "preprocessed",
    })

    print(f"완료: {doc_id}")