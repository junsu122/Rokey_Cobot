# run.py
import io, sys
import firebase_admin
from firebase_admin import credentials, storage, firestore
from PIL import Image
from pixel_extractor import ImagePreprocessor, CoordExtractor

cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred, {
    "storageBucket": "drawing-flower.firebasestorage.app"
})

def process_and_save(file_name: str):
    db     = firestore.client()
    bucket = storage.bucket()
    doc_id = f"images_{file_name}"

    # 1. Firestore pixel_jobs에서 파라미터 읽기
    job    = db.collection("pixel_jobs").document(doc_id).get()
    params = job.to_dict().get("params", {}) if job.exists else {}
    threshold = params.get("threshold", 160)
    margin    = params.get("margin", 12)
    symmetry  = params.get("symmetry", True)
    print(f"파라미터: threshold={threshold}, margin={margin}, symmetry={symmetry}")

    # 2. Storage에서 이미지 다운로드
    image_bytes = bucket.blob(f"images/{file_name}").download_as_bytes()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    print(f"이미지 다운로드 완료: images/{file_name}")

    # 3. 전처리 (단계별 이미지 포함)
    preprocessor = ImagePreprocessor()
    pre_result   = preprocessor.run(
        image,
        threshold=threshold,
        margin=margin,
        symmetry=symmetry,
        include_stages=True,
    )

    # 4. 정규화 이미지 → Storage 업로드
    normalized_buf = io.BytesIO()
    pre_result["stages"]["normalized"].convert("RGB").save(normalized_buf, format="PNG")
    normalized_buf.seek(0)
    normalized_path = f"previews/{doc_id}_normalized.png"
    bucket.blob(normalized_path).upload_from_file(normalized_buf, content_type="image/png")
    print(f"정규화 이미지 업로드: {normalized_path}")

    # 5. 픽셀화 이미지 → Storage 업로드 (9×8 → 180×160 확대)
    pixel_buf = io.BytesIO()
    pre_result["stages"]["mask"].resize((180, 160), Image.NEAREST).convert("RGB").save(pixel_buf, format="PNG")
    pixel_buf.seek(0)
    pixel_path = f"previews/{doc_id}_pixel.png"
    bucket.blob(pixel_path).upload_from_file(pixel_buf, content_type="image/png")
    print(f"픽셀화 이미지 업로드: {pixel_path}")

    # 6. text_preview 생성
    extractor    = CoordExtractor()
    text_preview = extractor.to_text_preview(pre_result["mask"])
    print(text_preview)

    # 7. Firestore에 저장 (status: "preprocessed" → 좌표는 저장 안 함)
    #    UI에서 ACCEPT 버튼을 누르면 coords + status: "done" 으로 업데이트됨
    db.collection("pixel_coords").document(doc_id).set({
        "file":            f"images/{file_name}",
        "normalized_path": normalized_path,
        "pixel_path":      pixel_path,
        "text_preview":    text_preview,
        "status":          "preprocessed",
    })
    print(f"Firestore 저장 완료 (preprocessed): {doc_id}")

if __name__ == "__main__":
    file_name = sys.argv[1] if len(sys.argv) > 1 else "heart.png"
    process_and_save(file_name)
