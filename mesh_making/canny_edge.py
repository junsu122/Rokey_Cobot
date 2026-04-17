import cv2
import numpy as np
from matplotlib import pyplot as plt

def detect_edges(image_path, low_threshold=50, high_threshold=150):
    """
    그레이스케일 -> 가우시안 블러 -> 캐니언 에지를 사용하여 윤곽선을 추출합니다.
    
    :param image_path: 원본 이미지 파일 경로
    :param low_threshold: 캐니언 에지의 하한 임계값
    :param high_threshold: 캐니언 에지의 상한 임계값
    """
    # 1. 원본 이미지 불러오기
    original_img = cv2.imread(image_path)
    if original_img is None:
        print(f"Error: 이미지를 불러올 수 없습니다. 경로를 확인하세요: {image_path}")
        return

    # 2. 그레이스케일 변환 (Gray-scale)
    # - 색상 정보를 없애고 밝기 정보만 남겨 연산 속도를 높이고 노이즈를 줄입니다.
    gray_img = cv2.cvtColor(original_img, cv2.COLOR_BGR2GRAY)

    # 3. 가우시안 블러 (Gaussian Blur)
    # - 이미지를 부드럽게 만들어 미세한 노이즈를 제거합니다. 에지 검출 성능을 높입니다.
    # - (5, 5)는 커널 크기로, 숫자가 클수록 더 많이 흐려집니다. 홀수여야 합니다.
    blurred_img = cv2.GaussianBlur(gray_img, (5, 5), 0)

    # 4. 캐니언 에지 검출 (Canny Edge Detection)
    # - 이미지에서 밝기가 급격하게 변하는 부분(에지)을 찾습니다.
    # - 하한/상한 임계값을 조절하여 원하는 세부 수준의 윤곽선을 얻을 수 있습니다.
    edges_img = cv2.Canny(blurred_img, low_threshold, high_threshold)

    # 5. 결과 시각화 (Matplotlib 사용)
    titles = ['Original', 'Gray-scale', 'Gaussian Blur', 'Canny Edges']
    images = [original_img, gray_img, blurred_img, edges_img]

    plt.figure(figsize=(12, 8))
    for i in range(4):
        plt.subplot(2, 2, i+1)
        if i == 0: # 원본은 BGR을 RGB로 변환하여 출력
            plt.imshow(cv2.cvtColor(images[i], cv2.COLOR_BGR2RGB))
        else: # 나머지는 그레이스케일로 출력
            plt.imshow(images[i], 'gray')
        plt.title(titles[i])
        plt.axis('off') # 축 표시 안 함
    
    plt.tight_layout()
    plt.show()

    # 결과 이미지 저장 (원한다면)
    # cv2.imwrite('edges_result.png', edges_img)

# --- 사용 예시 ---
# 준수님의 이미지 파일 경로로 변경해서 실행해 보세요.
# 예: image_path = '/home/junsu/cobot_ws/src/my_package/images/robot.jpg'
image_path = 'your_image_path_here.jpg' # 본인의 이미지 경로로 수정하세요!

# 기본 임계값으로 실행
detect_edges(image_path)

# 임계값을 조절하여 윤곽선 세부 조절 (예: 더 미세한 에지 검출)
# detect_edges(image_path, low_threshold=30, high_threshold=100)