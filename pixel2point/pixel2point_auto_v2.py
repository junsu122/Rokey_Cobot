import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox

try:
    from PIL import Image, ImageTk, ImageOps
except ImportError:
    raise ImportError("Pillow가 필요합니다. python -m pip install pillow 로 설치하세요.")


# ─────────────────────────────────────────────
# 상수 정의
# ─────────────────────────────────────────────
ROWS, COLS = 8, 9
EMPTY_COLOR = "white"
DEFAULT_PAINT_COLOR = "#000000"

PREVIEW_W, PREVIEW_H = 200, 160
NORMALIZE_W, NORMALIZE_H = 180, 160

PANEL_TITLES = ["원본", "그레이스케일", "이진 마스크", "여백 제거", "정규화", "최종 격자"]

OUTPUT_AREA_W = 200.0
OUTPUT_AREA_H = 200.0
OUTPUT_GAP = 2.0
OUTPUT_BASE_X = 0.0
OUTPUT_BASE_Z = 0.0


# ─────────────────────────────────────────────
# 이미지 전처리 담당
# ─────────────────────────────────────────────
class ImageProcessor:
    def __init__(self, rows: int, cols: int):
        self.rows = rows
        self.cols = cols

    def to_grayscale(self, image: Image.Image) -> Image.Image:
        return image.convert("L")

    def to_binary_mask(self, gray_img: Image.Image, threshold: int) -> Image.Image:
        return gray_img.point(lambda p: 0 if p < threshold else 255)

    def crop_to_content(self, binary_img: Image.Image) -> Image.Image:
        bbox = ImageOps.invert(binary_img).getbbox()
        return binary_img.crop(bbox) if bbox else binary_img

    def normalize_to_canvas(
        self, cropped_img: Image.Image, margin: int
    ) -> Image.Image:
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

    def process(
        self,
        original: Image.Image,
        threshold: int,
        margin: int,
        symmetry: bool,
    ) -> dict:
        gray = self.to_grayscale(original)
        binary = self.to_binary_mask(gray, threshold)
        cropped = self.crop_to_content(binary)
        normalized = self.normalize_to_canvas(cropped, margin)
        small = normalized.resize((self.cols, self.rows), Image.NEAREST)

        if symmetry:
            small = self.apply_horizontal_symmetry(small)

        return {
            "gray": gray,
            "binary": binary,
            "cropped": cropped,
            "normalized": normalized,
            "small": small,
        }


# ─────────────────────────────────────────────
# 격자 상태 및 좌표 출력 담당
# ─────────────────────────────────────────────
class GridManager:
    def __init__(self, rows: int, cols: int):
        self.rows = rows
        self.cols = cols
        self.cell_colors: dict = {
            (r, c): EMPTY_COLOR for r in range(rows) for c in range(cols)
        }

    def clear(self):
        for key in self.cell_colors:
            self.cell_colors[key] = EMPTY_COLOR

    def fill_from_mask(self, mask: Image.Image, color: str):
        for row in range(self.rows):
            for col in range(self.cols):
                pixel = mask.getpixel((col, row))
                self.cell_colors[(row, col)] = color if pixel == 0 else EMPTY_COLOR

    def toggle_cell(self, row: int, col: int, color: str):
        if self.cell_colors[(row, col)] == EMPTY_COLOR:
            self.cell_colors[(row, col)] = color
        else:
            self.cell_colors[(row, col)] = EMPTY_COLOR

    def get_filled_order(self) -> dict:
        filled = {}
        idx = 1
        for row in reversed(range(self.rows)):
            for col in range(self.cols):
                if self.cell_colors[(row, col)] != EMPTY_COLOR:
                    filled[(row, col)] = idx
                    idx += 1
        return filled

    def to_coord_dict(self) -> list[str]:
        cell_w = OUTPUT_AREA_W / self.cols
        cell_h = OUTPUT_AREA_H / self.rows

        lines = ["POS_COORDS = {"]
        idx = 0
        for row in reversed(range(self.rows)):
            for col in range(self.cols):
                if self.cell_colors[(row, col)] != EMPTY_COLOR:
                    x = OUTPUT_BASE_X + cell_w / 2 + col * (cell_w + OUTPUT_GAP)
                    z = cell_h / 2 + (self.rows - 1 - row) * cell_h + OUTPUT_BASE_Z
                    lines.append(f"    {idx}: [{x:.1f}, 2.0, {z:.1f}, 0.0, 180.0, 0.0],")
                    idx += 1
        lines.append("}")
        return lines

    def to_text_preview(self) -> str:
        lines = []
        for row in range(self.rows):
            lines.append("".join(
                "■ " if self.cell_colors[(row, col)] != EMPTY_COLOR else "□ "
                for col in range(self.cols)
            ))
        return "\n".join(lines)


# ─────────────────────────────────────────────
# 메인 앱
# ─────────────────────────────────────────────
class PixelPainter:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("이미지 → 픽셀 좌표 추출기")
        self.root.geometry("1400x900")
        self.root.minsize(1100, 800)
        self.root.configure(bg="#1e1e2e")

        self.current_color = DEFAULT_PAINT_COLOR
        self.threshold = 160
        self.margin = 12
        self.symmetry_enabled = True

        self.original_image: Image.Image | None = None
        self.stage_images: dict = {}       # gray, binary, cropped, normalized, small
        self.tk_previews: list = []        # tkinter 이미지 참조 보관

        self.processor = ImageProcessor(ROWS, COLS)
        self.grid = GridManager(ROWS, COLS)

        # 캔버스 렌더링 상태
        self.pixel_size = 1
        self.offset_x = 0
        self.offset_y = 0

        self._build_ui()

    # ─────────────────────────────────────────
    # UI 빌드
    # ─────────────────────────────────────────
    def _build_ui(self):
        self._build_toolbar()
        self._build_controls()
        self._build_preview_row()
        self._build_main_area()

    def _build_toolbar(self):
        bar = tk.Frame(self.root, bg="#2a2a3e", pady=8)
        bar.pack(fill=tk.X, padx=0)

        title = tk.Label(
            bar, text="PIXEL PAINTER",
            font=("Courier", 14, "bold"),
            bg="#2a2a3e", fg="#c9d1d9"
        )
        title.pack(side=tk.LEFT, padx=16)

        # 버튼 그룹
        btn_specs = [
            ("📂 이미지 불러오기", self.load_image, "#3b82f6"),
            ("🎨 색상 선택",       self.choose_color, "#8b5cf6"),
            ("🗑  전체 지우기",     self.clear_grid,   "#ef4444"),
            ("🔄 다시 전처리",     self.reprocess,    "#f59e0b"),
            ("📋 좌표 출력",       self.print_coords, "#10b981"),
        ]
        for text, cmd, color in btn_specs:
            tk.Button(
                bar, text=text, command=cmd,
                bg=color, fg="white",
                relief=tk.FLAT, padx=10, pady=4,
                activebackground=color, cursor="hand2",
                font=("Courier", 9, "bold")
            ).pack(side=tk.LEFT, padx=4)

        # 현재 색상 미리보기
        self.color_preview = tk.Label(
            bar, width=3, bg=self.current_color,
            relief=tk.SUNKEN, bd=2
        )
        self.color_preview.pack(side=tk.RIGHT, padx=16)

        self.info_label = tk.Label(
            bar, text="", bg="#2a2a3e", fg="#8b949e",
            font=("Courier", 9)
        )
        self.info_label.pack(side=tk.RIGHT, padx=8)
        self._update_info()

    def _build_controls(self):
        bar = tk.Frame(self.root, bg="#161625", pady=6)
        bar.pack(fill=tk.X, padx=0)

        def slider(parent, label, from_, to, init, cmd):
            tk.Label(parent, text=label, bg="#161625", fg="#8b949e",
                     font=("Courier", 9)).pack(side=tk.LEFT, padx=(12, 4))
            s = tk.Scale(
                parent, from_=from_, to=to,
                orient=tk.HORIZONTAL, length=200,
                command=cmd,
                bg="#161625", fg="#c9d1d9",
                troughcolor="#2a2a3e", highlightthickness=0,
                font=("Courier", 8)
            )
            s.set(init)
            s.pack(side=tk.LEFT)
            return s

        self.threshold_scale = slider(bar, "Threshold", 0, 255, self.threshold, self._on_threshold)
        self.margin_scale    = slider(bar, "Margin",    0,  40, self.margin,    self._on_margin)

        self.symmetry_var = tk.IntVar(value=1)
        tk.Checkbutton(
            bar, text="좌우 대칭 보정",
            variable=self.symmetry_var,
            command=self._on_symmetry,
            bg="#161625", fg="#c9d1d9",
            selectcolor="#2a2a3e",
            activebackground="#161625",
            font=("Courier", 9)
        ).pack(side=tk.LEFT, padx=16)

    def _build_preview_row(self):
        container = tk.Frame(self.root, bg="#1e1e2e")
        container.pack(fill=tk.X, padx=12, pady=(8, 0))

        tk.Label(
            container, text="전처리 시각화",
            font=("Courier", 11, "bold"),
            bg="#1e1e2e", fg="#c9d1d9"
        ).pack(anchor=tk.W, pady=(0, 4))

        panel_row = tk.Frame(container, bg="#1e1e2e")
        panel_row.pack(fill=tk.X)

        self.preview_canvases: list[tk.Canvas] = []
        for title in PANEL_TITLES:
            frame = tk.Frame(panel_row, bg="#2a2a3e", bd=0)
            frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=3)

            tk.Label(frame, text=title, bg="#2a2a3e", fg="#8b949e",
                     font=("Courier", 8)).pack(pady=(4, 2))

            c = tk.Canvas(frame, width=PREVIEW_W, height=PREVIEW_H,
                          bg="#161625", highlightthickness=0)
            c.pack(padx=4, pady=(0, 6))
            self.preview_canvases.append(c)

    def _build_main_area(self):
        lower = tk.Frame(self.root, bg="#1e1e2e")
        lower.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)

        # 왼쪽: 격자
        left = tk.Frame(lower, bg="#1e1e2e")
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        tk.Label(left, text="픽셀 격자", font=("Courier", 11, "bold"),
                 bg="#1e1e2e", fg="#c9d1d9").pack(anchor=tk.W, pady=(0, 4))

        self.canvas = tk.Canvas(left, bg="#0d1117", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<Button-1>", self._on_click)

        # 오른쪽: 로그
        right = tk.Frame(lower, bg="#1e1e2e")
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))

        tk.Label(right, text="로그 / 좌표 출력", font=("Courier", 11, "bold"),
                 bg="#1e1e2e", fg="#c9d1d9").pack(anchor=tk.W, pady=(0, 4))

        self.text = tk.Text(
            right,
            bg="#0d1117", fg="#c9d1d9",
            insertbackground="#c9d1d9",
            font=("Courier", 9),
            relief=tk.FLAT, padx=8, pady=6
        )
        self.text.pack(fill=tk.BOTH, expand=True)

    # ─────────────────────────────────────────
    # 이벤트 핸들러
    # ─────────────────────────────────────────
    def _on_threshold(self, value):
        self.threshold = int(value)
        self._update_info()
        if self.original_image:
            self._process_image()

    def _on_margin(self, value):
        self.margin = int(value)
        if self.original_image:
            self._process_image()

    def _on_symmetry(self):
        self.symmetry_enabled = bool(self.symmetry_var.get())
        if self.original_image:
            self._process_image()

    def _on_resize(self, event):
        self.pixel_size = max(1, min(event.width // COLS, event.height // ROWS))
        self.offset_x = (event.width  - COLS * self.pixel_size) // 2
        self.offset_y = (event.height - ROWS * self.pixel_size) // 2
        self._redraw_grid()

    def _on_click(self, event):
        col = (event.x - self.offset_x) // self.pixel_size
        row = (event.y - self.offset_y) // self.pixel_size
        if 0 <= row < ROWS and 0 <= col < COLS:
            self.grid.toggle_cell(row, col, self.current_color)
            self._redraw_grid()

    # ─────────────────────────────────────────
    # 버튼 커맨드
    # ─────────────────────────────────────────
    def load_image(self):
        path = filedialog.askopenfilename(
            title="이미지 선택",
            filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.bmp;*.gif"), ("All Files", "*.*")]
        )
        if not path:
            return
        try:
            self.original_image = Image.open(path).convert("RGB")
            self._process_image()
        except Exception as e:
            messagebox.showerror("오류", f"이미지를 불러오는 중 오류가 발생했습니다.\n\n{e}")

    def choose_color(self):
        result = colorchooser.askcolor(title="색상 선택")
        if result and result[1]:
            self.current_color = result[1]
            self.color_preview.config(bg=self.current_color)
            self._update_info()
            self._redraw_grid()

    def clear_grid(self):
        self.original_image = None
        self.stage_images = {}
        self.tk_previews = []
        self.grid.clear()
        self._redraw_grid()
        self._clear_previews()
        self.text.delete("1.0", tk.END)
        self._update_info()

    def reprocess(self):
        if not self.original_image:
            messagebox.showinfo("안내", "먼저 이미지를 불러오세요.")
            return
        self._process_image()

    def print_coords(self):
        lines = self.grid.to_coord_dict()
        self.text.delete("1.0", tk.END)
        output = "\n".join(lines)
        self.text.insert(tk.END, output + "\n")
        for line in lines:
            print(line)

    # ─────────────────────────────────────────
    # 이미지 처리 파이프라인
    # ─────────────────────────────────────────
    def _process_image(self):
        self.stage_images = self.processor.process(
            self.original_image,
            self.threshold,
            self.margin,
            self.symmetry_enabled,
        )
        self.grid.fill_from_mask(self.stage_images["small"], self.current_color)
        self._redraw_grid()
        self._update_previews()
        self._show_process_log()
        self._update_info()

    # ─────────────────────────────────────────
    # 격자 렌더링
    # ─────────────────────────────────────────
    def _redraw_grid(self):
        self.canvas.delete("all")
        filled_order = self.grid.get_filled_order()
        font_size = max(7, self.pixel_size // 3)

        for row in range(ROWS):
            for col in range(COLS):
                x1 = self.offset_x + col * self.pixel_size
                y1 = self.offset_y + row * self.pixel_size
                x2 = x1 + self.pixel_size
                y2 = y1 + self.pixel_size
                color = self.grid.cell_colors[(row, col)]

                self.canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline="#30363d")

                if (row, col) in filled_order:
                    text_color = "white" if color != "white" else "black"
                    self.canvas.create_text(
                        x1 + self.pixel_size / 2,
                        y1 + self.pixel_size / 2,
                        text=f"p{filled_order[(row, col)]}",
                        fill=text_color,
                        font=("Courier", font_size, "bold")
                    )

    # ─────────────────────────────────────────
    # 미리보기 패널 업데이트
    # ─────────────────────────────────────────
    def _update_previews(self):
        s = self.stage_images
        enlarged_small = s["small"].resize((NORMALIZE_W, NORMALIZE_H), Image.NEAREST)

        pil_images = [
            self.original_image,
            s["gray"],
            s["binary"],
            s["cropped"],
            s["normalized"],
            enlarged_small,
        ]

        self.tk_previews = []  # 참조 유지 (GC 방지)
        for i, (canvas, pil_img) in enumerate(zip(self.preview_canvases, pil_images)):
            preview = pil_img.copy()
            preview.thumbnail((PREVIEW_W - 10, PREVIEW_H - 10))
            tk_img = ImageTk.PhotoImage(preview)
            self.tk_previews.append(tk_img)
            canvas.delete("all")
            canvas.create_image(PREVIEW_W // 2, PREVIEW_H // 2, image=tk_img)

    def _clear_previews(self):
        for canvas in self.preview_canvases:
            canvas.delete("all")

    # ─────────────────────────────────────────
    # 로그 출력
    # ─────────────────────────────────────────
    def _show_process_log(self):
        sym_text = "적용" if self.symmetry_enabled else "미적용"
        self.text.delete("1.0", tk.END)
        self.text.insert(tk.END, (
            "[전처리 단계]\n"
            f"  1. 원본 이미지 불러오기\n"
            f"  2. 그레이스케일 변환\n"
            f"  3. threshold {self.threshold} 기준 이진 마스크 생성\n"
            f"  4. bounding box 기준 여백 제거\n"
            f"  5. {NORMALIZE_W}×{NORMALIZE_H} 캔버스에 중앙 정렬\n"
            f"  6. {COLS}×{ROWS} 최종 격자로 축소\n"
            f"  7. 좌우 대칭 보정: {sym_text}\n\n"
            "[픽셀 미리보기]\n"
        ))
        self.text.insert(tk.END, self.grid.to_text_preview())
        self.text.insert(tk.END, (
            "\n\n[안정화 팁]\n"
            "- threshold를 조절해 픽셀 밀도를 조정하세요.\n"
            "- 여백이 많은 이미지는 자동 크롭 후 정규화됩니다.\n"
            "- 좌우 대칭 도형은 대칭 보정을 켜는 것이 유리합니다.\n"
        ))

    def _update_info(self):
        sym = "ON" if self.symmetry_enabled else "OFF"
        self.info_label.config(
            text=f"색상: {self.current_color}  |  threshold: {self.threshold}  |  margin: {self.margin}  |  symmetry: {sym}"
        )


# ─────────────────────────────────────────────
# 진입점
# ─────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app = PixelPainter(root)
    root.mainloop()