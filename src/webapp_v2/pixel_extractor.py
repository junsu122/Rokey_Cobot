from PIL import Image, ImageOps


# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────
ROWS, COLS = 8, 9
NORMALIZE_W, NORMALIZE_H = 180, 160

OUTPUT_AREA_W = 200.0
OUTPUT_AREA_H = 200.0
OUTPUT_GAP = 2.0
OUTPUT_BASE_X = 300.0
OUTPUT_BASE_Z = 40.0


# ─────────────────────────────────────────────
# 1. 이미지 전처리 담당
# ─────────────────────────────────────────────
class ImagePreprocessor:
    """
    원본 이미지 → 정규화된 그리드 마스크(Image)
    """

    def __init__(self, rows: int = ROWS, cols: int = COLS):
        self.rows = rows
        self.cols = cols

    def to_grayscale(self, image: Image.Image) -> Image.Image:
        return image.convert("L")

    def to_binary_mask(self, gray_img: Image.Image, threshold: int) -> Image.Image:
        return gray_img.point(lambda p: 0 if p < threshold else 255)

    def crop_to_content(self, binary_img: Image.Image) -> Image.Image:
        bbox = ImageOps.invert(binary_img).getbbox()
        return binary_img.crop(bbox) if bbox else binary_img

    def normalize_to_canvas(self, cropped_img: Image.Image, margin: int) -> Image.Image:
        w, h = cropped_img.size
        if w <= 0 or h <= 0:
            return Image.new("L", (NORMALIZE_W, NORMALIZE_H), 255)

        usable_w = max(1, NORMALIZE_W - 2 * margin)
        usable_h = max(1, NORMALIZE_H - 2 * margin)
        scale = min(usable_w / w, usable_h / h)

        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))

        resized = cropped_img.resize((new_w, new_h), Image.NEAREST)
        canvas = Image.new("L", (NORMALIZE_W, NORMALIZE_H), 255)
        canvas.paste(resized, ((NORMALIZE_W - new_w) // 2, (NORMALIZE_H - new_h) // 2))
        return canvas

    def apply_horizontal_symmetry(self, mask: Image.Image) -> Image.Image:
        result = mask.copy()
        for row in range(self.rows):
            for col in range(self.cols // 2):
                mirror = self.cols - 1 - col
                if result.getpixel((col, row)) == 0 or result.getpixel((mirror, row)) == 0:
                    result.putpixel((col, row), 0)
                    result.putpixel((mirror, row), 0)
        return result

    def to_grid_mask(self, normalized_img: Image.Image, symmetry: bool) -> Image.Image:
        small = normalized_img.resize((self.cols, self.rows), Image.NEAREST)
        if symmetry:
            small = self.apply_horizontal_symmetry(small)
        return small

    def run(
        self,
        image: Image.Image,
        threshold: int = 160,
        margin: int = 12,
        symmetry: bool = True,
        include_stages: bool = False,
    ) -> dict:
        """
        반환값:
            mask        : 그리드 마스크 Image (COLS×ROWS, 0=채워짐 255=빔)
            stages      : 단계별 이미지 dict (include_stages=True 일 때만)
        """
        gray       = self.to_grayscale(image)
        binary     = self.to_binary_mask(gray, threshold)
        cropped    = self.crop_to_content(binary)
        normalized = self.normalize_to_canvas(cropped, margin)
        mask       = self.to_grid_mask(normalized, symmetry)

        result: dict = {"mask": mask}

        if include_stages:
            result["stages"] = {
                "gray": gray,
                "binary": binary,
                "cropped": cropped,
                "normalized": normalized,
                "mask": mask,
            }

        return result


# ─────────────────────────────────────────────
# 2. 좌표 추출 담당
# ─────────────────────────────────────────────
class CoordExtractor:
    """
    그리드 마스크(Image) → 좌표 dict / grid 배열 / 텍스트 미리보기
    """

    def __init__(self, rows: int = ROWS, cols: int = COLS):
        self.rows = rows
        self.cols = cols

    def to_bool_array(self, mask: Image.Image) -> list[list[int]]:
        return [
            [1 if mask.getpixel((col, row)) == 0 else 0 for col in range(self.cols)]
            for row in range(self.rows)
        ]

    def to_text_preview(self, mask: Image.Image) -> str:
        lines = []
        for row in range(self.rows):
            lines.append(
                " ".join("■" if mask.getpixel((col, row)) == 0 else "□"
                         for col in range(self.cols))
            )
        return "\n".join(lines)

    def to_coords(self, mask: Image.Image) -> dict:
        cell_w = OUTPUT_AREA_W / self.cols
        cell_h = OUTPUT_AREA_H / self.rows

        coords: dict = {}
        idx = 0
        for row in reversed(range(self.rows)):
            for col in range(self.cols):
                if mask.getpixel((col, row)) == 0:
                    x = OUTPUT_BASE_X + cell_w / 2 + col * (cell_w + OUTPUT_GAP)
                    z = cell_h / 2 + (self.rows - 1 - row) * cell_h + OUTPUT_BASE_Z
                    coords[idx] = [round(x, 1), 100.0, round(z, 1), 0.0, 180.0, 0.0]
                    idx += 1
        return coords

    def run(self, mask: Image.Image) -> dict:
        """
        반환값:
            coords       : {0: [x, y, z, rx, ry, rz], ...}
            grid         : [[0/1, ...], ...]
            text_preview : "■ □ ■ ..."
        """
        return {
            "coords":       self.to_coords(mask),
            "grid":         self.to_bool_array(mask),
            "text_preview": self.to_text_preview(mask),
        }