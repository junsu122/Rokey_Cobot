import tkinter as tk
from tkinter import colorchooser, filedialog
from PIL import Image, ImageOps

class PixelPainter:
    def __init__(self, root, rows=8, cols=9):
        self.root = root
        self.root.title("이미지 픽셀화 프로그램")
        self.root.geometry("500x700")
        self.root.minsize(400, 500)

        self.rows = rows
        self.cols = cols
        self.current_color = "#000000"
        self.empty_color = "white"

        self.cell_colors = {
            (row, col): self.empty_color
            for row in range(self.rows)
            for col in range(self.cols)
        }
        self.cells = {}

        top_frame = tk.Frame(root)
        top_frame.pack(pady=10)

        self.color_button = tk.Button(top_frame, text="색상 선택", command=self.choose_color)
        self.color_button.pack(side=tk.LEFT, padx=5)

        self.clear_button = tk.Button(top_frame, text="전체 지우기", command=self.clear_grid)
        self.clear_button.pack(side=tk.LEFT, padx=5)

        self.load_button = tk.Button(top_frame, text="이미지 불러오기", command=self.load_image)
        self.load_button.pack(side=tk.LEFT, padx=5)

        self.print_button = tk.Button(top_frame, text="좌표 출력", command=self.print_filled_centers)
        self.print_button.pack(side=tk.LEFT, padx=5)

        self.info_label = tk.Label(top_frame, text=f"현재 색상: {self.current_color}")
        self.info_label.pack(side=tk.LEFT, padx=10)

        self.canvas = tk.Canvas(root, bg="gray")
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.text = tk.Text(root, height=12)
        self.text.pack(fill=tk.X, padx=10, pady=10)

        self.canvas.bind("<Configure>", self.on_resize)
        self.canvas.bind("<Button-1>", self.on_click)

        self.pixel_size = 1
        self.offset_x = 0
        self.offset_y = 0

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
        for row in range(self.rows):
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
                    x1, y1, x2, y2,
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
                        text=f"p{filled_order[(row, col)]}",
                        fill=text_color,
                        font=("Arial", font_size, "bold")
                    )

        self.info_label.config(
            text=f"현재 색상: {self.current_color} | 픽셀 크기: {self.pixel_size}"
        )

    def on_click(self, event):
        col = (event.x - self.offset_x) // self.pixel_size
        row = (event.y - self.offset_y) // self.pixel_size

        if 0 <= row < self.rows and 0 <= col < self.cols:
            current = self.cell_colors[(row, col)]
            new_color = self.current_color if current == self.empty_color else self.empty_color
            self.cell_colors[(row, col)] = new_color
            self.redraw_grid()

    def choose_color(self):
        color = colorchooser.askcolor(title="색상 선택")[1]
        if color:
            self.current_color = color
            self.redraw_grid()

    def clear_grid(self):
        for key in self.cell_colors:
            self.cell_colors[key] = self.empty_color
        self.redraw_grid()
        self.text.delete("1.0", tk.END)

    def load_image(self):
        file_path = filedialog.askopenfilename(
            title="이미지 선택",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp *.gif")]
        )
        if not file_path:
            return

        # 1. 원본 이미지 열기
        img = Image.open(file_path).convert("L")  # 그레이스케일

        # 2. 먼저 200x200 영역 안에 비율 유지하며 맞추기
        target_size = (200, 200)
        img.thumbnail(target_size, Image.LANCZOS)

        # 3. 200x200 흰 배경 생성 후 중앙에 배치
        bg_200 = Image.new("L", target_size, 255)
        paste_x = (200 - img.width) // 2
        paste_y = (200 - img.height) // 2
        bg_200.paste(img, (paste_x, paste_y))

        # 4. 200x200 이미지를 rows x cols 로 축소해서 픽셀화용 샘플 생성
        img = ImageOps.fit(img, (150, 150), Image.LANCZOS)
        pixel_img = img.resize((self.cols, self.rows), Image.NEAREST)

        # 5. 임계값 기준으로 셀 채우기
        threshold = 200
        for row in range(self.rows):
            for col in range(self.cols):
                pixel_value = pixel_img.getpixel((col, row))
                if pixel_value < threshold:
                    self.cell_colors[(row, col)] = self.current_color
                else:
                    self.cell_colors[(row, col)] = self.empty_color

        self.redraw_grid()

    def print_filled_centers(self):
        self.text.delete("1.0", tk.END)
        self.text.insert(tk.END, "색칠된 픽셀 중심 좌표 (200x200 + x 오프셋 300)\n")
        self.text.insert(tk.END, "-" * 55 + "\n")

        print("\n색칠된 픽셀 중심 좌표 (200x200 + x 오프셋 300)")
        print("-" * 55)

        area_w = 200.0
        area_h = 200.0
        base_x = 300.0

        cell_w = area_w / self.cols
        cell_h = area_h / self.rows

        idx = 1
        for row in range(self.rows):
            for col in range(self.cols):
                if self.cell_colors[(row, col)] != self.empty_color:
                    real_x = base_x + cell_w / 2 + col * cell_w
                    real_y = cell_h / 2 + row * cell_h

                    line = f"POS{idx}_COORDS = [{real_x:.1f}, 100.0, {real_y:.1f}, 0.0, 180.0, 0.0]"

                    self.text.insert(tk.END, line + "\n")
                    print(line)
                    idx += 1


if __name__ == "__main__":
    root = tk.Tk()
    app = PixelPainter(root, rows=8, cols=9)
    root.mainloop()