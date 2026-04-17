import cv2
import numpy as np
from matplotlib import pyplot as plt
import math

def get_mesh_by_count(image_path, target_count=50, margin=20):
    """
    target_count: 생성하고 싶은 목표 좌표 개수
    margin: 윤곽선으로부터 띄울 거리
    """
    img = cv2.imread(image_path)
    if img is None: return []
    
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)

    # 1. 윤곽선 및 내부 마스크 생성
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mask = np.zeros_like(gray)
    cv2.drawContours(mask, contours, -1, 255, -1)

    # 2. [핵심] 면적 기반 grid_size 자동 계산
    # 마스크에서 흰색(255) 영역의 픽셀 개수가 곧 면적입니다.
    area = np.sum(mask == 255)
    
    # 마진 때문에 실제로 점이 찍힐 면적은 더 좁으므로, 이를 감안하여 계산합니다.
    # 면적 / 목표 개수의 제곱근을 구하면 이론적인 간격이 나옵니다.
    auto_grid_size = int(math.sqrt(area / target_count))
    
    # 간격이 최소 1보다는 커야 에러가 안 납니다.
    auto_grid_size = max(1, auto_grid_size)

    # 3. 거리 변환 (마진 확인용)
    dist_transform = cv2.distanceTransform(mask, cv2.DIST_L2, 5)

    # 4. 좌표 추출
    mesh_list = []
    for y in range(0, h, auto_grid_size):
        for x in range(0, w, auto_grid_size):
            if dist_transform[y, x] > margin:
                mesh_list.append([int(x), int(y)])

    # 5. 시각화
    plt.figure(figsize=(8, 8))
    plt.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    if mesh_list:
        pts = np.array(mesh_list)
        plt.scatter(pts[:, 0], pts[:, 1], c='red', s=15)
    
    plt.title(f"Target: {target_count} / Result: {len(mesh_list)}\nAuto Grid Size: {auto_grid_size}")
    plt.show()

    return mesh_list

# --- 사용 예시 ---
image_path = '/home/junsu/Downloads/heart.png'

# "나는 점이 딱 100개 정도 있었으면 좋겠어"라고 설정
points = get_mesh_by_count(image_path, target_count=80, margin=10)

print(f"최종 생성된 점의 개수: {len(points)}개")