import tkinter as tk
from tkinter import colorchooser, filedialog
import firebase_admin
from firebase_admin import credentials, db


try:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String # 메시지 타입은 상황에 맞게 변경 가능합니다.
except ImportError:
    # ROS 2 환경이 아닐 경우를 대비한 예외 처리
    print("ROS 2 환경이 아닙니다. 토픽 발행 기능이 제한됩니다.")

try:
    from PIL import Image, ImageTk, ImageOps
except ImportError:
    raise ImportError("Pillow가 필요합니다. python -m pip install pillow 로 설치하세요.")


# class PixelPainter:
#     def __init__(self, root, rows=8, cols=9):
#         # --- 수정: ROS 2 노드 초기화 ---
#         if 'rclpy' in globals():
#             if not rclpy.ok():
#                 rclpy.init()
#             self.node = Node('pixel_painter_node')
#             # 'make_shape_parameter' 토픽 퍼블리셔 생성
#             self.publisher = self.node.create_publisher(String, 'make_shape_parameter', 10)
class PixelPainter:
    def __init__(self, root, rows=8, cols=9):
        # --- 1. Firebase 초기화 ---
        try:
            # 초기화 중복 방지
            if not firebase_admin._apps:
                cred = credentials.Certificate("/home/junsu/Downloads/rokey-cobot-firebase-adminsdk-fbsvc-f2b3ddb804.json")
                firebase_admin.initialize_app(cred, {
                    'databaseURL': 'https://rokey-cobot-default-rtdb.asia-southeast1.firebasedatabase.app'
                })
            self.db_ref = db.reference('robot/commands')
            print("🚀 Firebase 연결 성공!")
        except Exception as e:
            print(f"❌ Firebase 초기화 실패: {e}")

        self.root = root
        self.root.title("이미지 -> 픽셀 좌표 추출 프로그램")
        self.root.geometry("1350x900")
        self.root.minsize(1100, 800)

        self.rows = rows
        self.cols = cols

        self.current_color = "#000000"
        self.empty_color = "white"

        self.threshold = 160
        self.normalize_w = 180
        self.normalize_h = 160
        self.margin = 12
        self.symmetry_enabled = True

        self.original_image = None
        self.gray_image = None
        self.binary_mask = None
        self.cropped_mask = None
        self.normalized_mask = None
        self.small_mask = None

        self.tk_original = None
        self.tk_gray = None
        self.tk_binary = None
        self.tk_crop = None
        self.tk_normalized = None
        self.tk_small = None

        self.cell_colors = {}
        self.cells = {}

        for row in range(self.rows):
            for col in range(self.cols):
                self.cell_colors[(row, col)] = self.empty_color

        self.build_ui()

        self.pixel_size = 1
        self.offset_x = 0
        self.offset_y = 0

    def build_ui(self):
        top_frame = tk.Frame(self.root)
        top_frame.pack(padx=10, pady=8, fill=tk.X)

        self.load_button = tk.Button(top_frame, text="이미지 불러오기", command=self.load_image)
        self.load_button.pack(side=tk.LEFT, padx=4)

        self.color_button = tk.Button(top_frame, text="색상 선택", command=self.choose_color)
        self.color_button.pack(side=tk.LEFT, padx=4)

        self.clear_button = tk.Button(top_frame, text="전체 지우기", command=self.clear_grid)
        self.clear_button.pack(side=tk.LEFT, padx=4)

        self.print_button = tk.Button(top_frame, text="좌표 출력", command=self.print_filled_centers)
        self.print_button.pack(side=tk.LEFT, padx=4)

        self.reprocess_button = tk.Button(top_frame, text="다시 전처리", command=self.reprocess_current_image)
        self.reprocess_button.pack(side=tk.LEFT, padx=4)

        self.info_label = tk.Label(
            top_frame,
            text="현재 색상: {} | threshold: {}".format(self.current_color, self.threshold)
        )
        self.info_label.pack(side=tk.LEFT, padx=12)

        control_frame = tk.Frame(self.root)
        control_frame.pack(padx=10, pady=5, fill=tk.X)

        tk.Label(control_frame, text="Threshold").pack(side=tk.LEFT, padx=5)
        self.threshold_scale = tk.Scale(
            control_frame,
            from_=0,
            to=255,
            orient=tk.HORIZONTAL,
            length=220,
            command=self.on_threshold_change
        )
        self.threshold_scale.set(self.threshold)
        self.threshold_scale.pack(side=tk.LEFT, padx=5)

        tk.Label(control_frame, text="Margin").pack(side=tk.LEFT, padx=15)
        self.margin_scale = tk.Scale(
            control_frame,
            from_=0,
            to=40,
            orient=tk.HORIZONTAL,
            length=180,
            command=self.on_margin_change
        )
        self.margin_scale.set(self.margin)
        self.margin_scale.pack(side=tk.LEFT, padx=5)

        self.symmetry_var = tk.IntVar(value=1)
        self.symmetry_check = tk.Checkbutton(
            control_frame,
            text="좌우 대칭 보정",
            variable=self.symmetry_var,
            command=self.on_symmetry_toggle
        )
        self.symmetry_check.pack(side=tk.LEFT, padx=15)

        preview_title = tk.Label(self.root, text="전처리 시각화", font=("Arial", 12, "bold"))
        preview_title.pack(pady=(10, 4))

        self.preview_frame = tk.Frame(self.root)
        self.preview_frame.pack(fill=tk.X, padx=10, pady=5)

        self.preview_panels = []
        self.panel_titles = [
            "원본",
            "그레이스케일",
            "이진 마스크",
            "여백 제거",
            "정규화",
            "최종 격자"
        ]

        for title in self.panel_titles:
            panel = self.create_preview_panel(self.preview_frame, title)
            self.preview_panels.append(panel)

        lower_frame = tk.Frame(self.root)
        lower_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left_frame = tk.Frame(lower_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        right_frame = tk.Frame(lower_frame)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))

        grid_title = tk.Label(left_frame, text="최종 픽셀 격자", font=("Arial", 12, "bold"))
        grid_title.pack(pady=(0, 5))

        self.canvas = tk.Canvas(left_frame, bg="gray")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.bind("<Configure>", self.on_resize)
        self.canvas.bind("<Button-1>", self.on_click)

        text_title = tk.Label(right_frame, text="전처리 로그 / 좌표 출력", font=("Arial", 12, "bold"))
        text_title.pack(pady=(0, 5))

        self.text = tk.Text(right_frame, height=25)
        self.text.pack(fill=tk.BOTH, expand=True)

    def create_preview_panel(self, parent, title):
        frame = tk.Frame(parent, bd=1, relief=tk.SOLID)
        frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)

        label = tk.Label(frame, text=title)
        label.pack(pady=4)

        canvas = tk.Canvas(frame, width=200, height=160, bg="white")
        canvas.pack(padx=5, pady=5)

        return {
            "frame": frame,
            "label": label,
            "canvas": canvas
        }

    def on_threshold_change(self, value):
        self.threshold = int(value)
        self.update_info()
        if self.original_image is not None:
            self.process_loaded_image()

    def on_margin_change(self, value):
        self.margin = int(value)
        if self.original_image is not None:
            self.process_loaded_image()

    def on_symmetry_toggle(self):
        self.symmetry_enabled = bool(self.symmetry_var.get())
        if self.original_image is not None:
            self.process_loaded_image()

    def reprocess_current_image(self):
        if self.original_image is None:
            messagebox.showinfo("안내", "먼저 이미지를 불러오세요.")
            return
        self.process_loaded_image()

    def update_info(self):
        self.info_label.config(
            text="현재 색상: {} | threshold: {} | margin: {} | symmetry: {}".format(
                self.current_color,
                self.threshold,
                self.margin,
                "ON" if self.symmetry_enabled else "OFF"
            )
        )

    def choose_color(self):
        color_data = colorchooser.askcolor(title="색상 선택")
        if color_data and color_data[1]:
            self.current_color = color_data[1]
            self.redraw_grid()
            self.update_info()

    def clear_grid(self):
        for key in self.cell_colors:
            self.cell_colors[key] = self.empty_color

        self.original_image = None
        self.gray_image = None
        self.binary_mask = None
        self.cropped_mask = None
        self.normalized_mask = None
        self.small_mask = None

        self.tk_original = None
        self.tk_gray = None
        self.tk_binary = None
        self.tk_crop = None
        self.tk_normalized = None
        self.tk_small = None

        self.redraw_grid()
        self.clear_previews()
        self.text.delete("1.0", tk.END)
        self.update_info()

    def clear_previews(self):
        for panel in self.preview_panels:
            panel["canvas"].delete("all")

    def load_image(self):
        file_path = filedialog.askopenfilename(
            title="이미지 선택",
            filetypes=[
                ("Image Files", "*.png;*.jpg;*.jpeg;*.bmp;*.gif"),
                ("All Files", "*.*")
            ]
        )

        if not file_path:
            return

        try:
            self.original_image = Image.open(file_path).convert("RGB")
            self.process_loaded_image()
        except Exception as e:
            messagebox.showerror("오류", "이미지를 불러오는 중 오류가 발생했습니다.\n\n{}".format(e))

    def process_loaded_image(self):
        if self.original_image is None:
            return

        self.gray_image = self.original_image.convert("L")

        self.binary_mask = self.extract_foreground_mask(self.gray_image)
        self.cropped_mask = self.crop_to_content(self.binary_mask)
        self.normalized_mask = self.normalize_to_canvas(
            self.cropped_mask,
            canvas_w=self.normalize_w,
            canvas_h=self.normalize_h,
            margin=self.margin
        )

        self.small_mask = self.normalized_mask.resize((self.cols, self.rows), Image.NEAREST)

        if self.symmetry_enabled:
            self.small_mask = self.apply_horizontal_symmetry(self.small_mask)

        self.fill_grid_from_mask(self.small_mask)
        self.redraw_grid()
        self.update_preview_images()
        self.show_process_text()
        self.update_info()

    def extract_foreground_mask(self, gray_img):
        return gray_img.point(lambda p: 0 if p < self.threshold else 255)

    def crop_to_content(self, binary_img):
        inverted = ImageOps.invert(binary_img)
        bbox = inverted.getbbox()

        if bbox is None:
            return binary_img

        return binary_img.crop(bbox)

    def normalize_to_canvas(self, cropped_img, canvas_w=180, canvas_h=160, margin=12):
        w, h = cropped_img.size

        if w <= 0 or h <= 0:
            return Image.new("L", (canvas_w, canvas_h), 255)

        usable_w = max(1, canvas_w - 2 * margin)
        usable_h = max(1, canvas_h - 2 * margin)

        scale = min(float(usable_w) / float(w), float(usable_h) / float(h))

        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))

        resized = cropped_img.resize((new_w, new_h), Image.NEAREST)

        canvas = Image.new("L", (canvas_w, canvas_h), 255)

        offset_x = (canvas_w - new_w) // 2
        offset_y = (canvas_h - new_h) // 2

        canvas.paste(resized, (offset_x, offset_y))
        return canvas

    def apply_horizontal_symmetry(self, small_mask):
        result = small_mask.copy()

        for row in range(self.rows):
            for col in range(self.cols // 2):
                mirror_col = self.cols - 1 - col

                left_pixel = result.getpixel((col, row))
                right_pixel = result.getpixel((mirror_col, row))

                left_filled = (left_pixel == 0)
                right_filled = (right_pixel == 0)

                if left_filled or right_filled:
                    result.putpixel((col, row), 0)
                    result.putpixel((mirror_col, row), 0)

        return result

    def fill_grid_from_mask(self, small_mask):
        for row in range(self.rows):
            for col in range(self.cols):
                pixel_value = small_mask.getpixel((col, row))
                if pixel_value == 0:
                    self.cell_colors[(row, col)] = self.current_color
                else:
                    self.cell_colors[(row, col)] = self.empty_color

    def update_preview_images(self):
        self.tk_original = self.make_preview_tk(self.original_image)
        self.tk_gray = self.make_preview_tk(self.gray_image)
        self.tk_binary = self.make_preview_tk(self.binary_mask)
        self.tk_crop = self.make_preview_tk(self.cropped_mask)
        self.tk_normalized = self.make_preview_tk(self.normalized_mask)

        enlarged_small = self.small_mask.resize((180, 160), Image.NEAREST)
        self.tk_small = ImageTk.PhotoImage(enlarged_small)

        images = [
            self.tk_original,
            self.tk_gray,
            self.tk_binary,
            self.tk_crop,
            self.tk_normalized,
            self.tk_small
        ]

        for i in range(len(self.preview_panels)):
            canvas = self.preview_panels[i]["canvas"]
            canvas.delete("all")
            canvas.create_image(100, 80, image=images[i])

    def make_preview_tk(self, pil_image):
        preview = pil_image.copy()
        preview.thumbnail((190, 150))
        return ImageTk.PhotoImage(preview)

    def show_process_text(self):
        self.text.delete("1.0", tk.END)

        self.text.insert(tk.END, "[전처리 단계]\n")
        self.text.insert(tk.END, "1. 원본 이미지 불러오기\n")
        self.text.insert(tk.END, "2. 그레이스케일 변환\n")
        self.text.insert(tk.END, "3. threshold {} 기준 이진 마스크 생성\n".format(self.threshold))
        self.text.insert(tk.END, "4. 도형의 bounding box 기준 여백 제거\n")
        self.text.insert(tk.END, "5. {}x{} 표준 캔버스에 중앙 정렬\n".format(self.normalize_w, self.normalize_h))
        self.text.insert(tk.END, "6. {}x{} 최종 격자로 축소\n".format(self.cols, self.rows))
        self.text.insert(
            tk.END,
            "7. 좌우 대칭 보정: {}\n\n".format("적용" if self.symmetry_enabled else "미적용")
        )

        self.text.insert(tk.END, "[최종 픽셀 미리보기]\n")
        for row in range(self.rows):
            line = ""
            for col in range(self.cols):
                if self.cell_colors[(row, col)] != self.empty_color:
                    line += "■ "
                else:
                    line += "□ "
            self.text.insert(tk.END, line + "\n")

        self.text.insert(tk.END, "\n[안정화 팁]\n")
        self.text.insert(tk.END, "- 같은 하트인데 결과가 달라지면 threshold를 조금 조절해보세요.\n")
        self.text.insert(tk.END, "- 여백이 많은 이미지는 자동 크롭 후 정규화됩니다.\n")
        self.text.insert(tk.END, "- 하트처럼 좌우 대칭 도형은 대칭 보정을 켜는 것이 유리합니다.\n")

    def on_resize(self, event):
        canvas_width = event.width
        canvas_height = event.height

        self.pixel_size = min(canvas_width // self.cols, canvas_height // self.rows)
        if self.pixel_size < 1:
            self.pixel_size = 1

        self.grid_width = self.cols * self.pixel_size
        self.grid_height = self.rows * self.pixel_size

        self.offset_x = (canvas_width - self.grid_width) // 2
        self.offset_y = (canvas_height - self.grid_height) // 2

        self.redraw_grid()

    def get_filled_pixel_order(self):
        filled_order = {}
        idx = 1

        for row in reversed(range(self.rows)):
            for col in range(self.cols):
                if self.cell_colors[(row, col)] != self.empty_color:
                    filled_order[(row, col)] = idx
                    idx += 1

        return filled_order

    def redraw_grid(self):
        self.canvas.delete("all")
        self.cells = {}

        filled_order = self.get_filled_pixel_order()

        for row in range(self.rows):
            for col in range(self.cols):
                x1 = self.offset_x + col * self.pixel_size
                y1 = self.offset_y + row * self.pixel_size
                x2 = x1 + self.pixel_size
                y2 = y1 + self.pixel_size

                rect = self.canvas.create_rectangle(
                    x1,
                    y1,
                    x2,
                    y2,
                    fill=self.cell_colors[(row, col)],
                    outline="black"
                )
                self.cells[(row, col)] = rect

                if (row, col) in filled_order:
                    text_color = "white" if self.cell_colors[(row, col)] != "white" else "black"
                    font_size = max(8, int(self.pixel_size / 3))

                    self.canvas.create_text(
                        x1 + self.pixel_size / 2,
                        y1 + self.pixel_size / 2,
                        text="p{}".format(filled_order[(row, col)]),
                        fill=text_color,
                        font=("Arial", font_size, "bold")
                    )

    def on_click(self, event):
        col = (event.x - self.offset_x) // self.pixel_size
        row = (event.y - self.offset_y) // self.pixel_size

        if 0 <= row < self.rows and 0 <= col < self.cols:
            current = self.cell_colors[(row, col)]
            if current == self.empty_color:
                self.cell_colors[(row, col)] = self.current_color
            else:
                self.cell_colors[(row, col)] = self.empty_color

            self.redraw_grid()

    def print_filled_centers(self):
        self.text.delete("1.0", tk.END)

        area_w = 200.0
        area_h = 200.0
        cell_w = area_w / self.cols
        cell_h = area_h / self.rows
        gap = 2.0

        # DB에 올릴 딕셔너리 구조
        coords_dict = {}
        
        # 화면 출력용 텍스트 리스트
        lines = ["POS_COORDS = {"]

        idx = 0
        # 로봇 좌표계에 맞춰 아래에서 위로 스캔
        for row in reversed(range(self.rows)):
            for col in range(self.cols):
                if self.cell_colors[(row, col)] != self.empty_color:
                    real_x = 300 + cell_w / 2 + col * (cell_w + gap)
                    real_z = cell_h / 2 + (self.rows - 1 - row) * cell_h + 40
                    
                    # 1. 딕셔너리에 데이터 담기 (DB용)
                    # 키값을 idx가 아닌 문자열로 주면 리스트 변환 문제를 방지할 수 있습니다.
                    coords_dict[str(idx)] = [round(real_x, 1), 100.0, round(real_z, 1), 0.0, 180.0, 0.0]
                    
                    # 2. 화면 출력용 텍스트 만들기
                    lines.append(f"    {idx}: {coords_dict[str(idx)]},")
                    idx += 1

        lines.append("}")

        # UI 텍스트창 업데이트
        for line in lines:
            self.text.insert(tk.END, line + "\n")
        
        # --- 3. Firebase 실시간 업로드 ---
        try:
            self.db_ref.set({
                'coords': coords_dict,
                'updated_at': {".sv": "timestamp"},
                'status': 'NEW_DATA_AVAILABLE',
                'total_points': idx
            })
            self.text.insert(tk.END, f"\n✅ [Firebase] {idx}개의 좌표 업로드 완료!")
        except Exception as e:
            self.text.insert(tk.END, f"\n❌ [Firebase] 업로드 실패: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = PixelPainter(root, rows=8, cols=9)
    try:
        root.mainloop()
    finally:
        if 'rclpy' in globals() and rclpy.ok():
            rclpy.shutdown()