import cv2
import numpy as np
from matplotlib import pyplot as plt

def get_mesh_coordinates(image_path, grid_size=20, margin=15):
    """
    윤곽선에서 마진을 둔 내부 점들의 좌표를 리스트로 반환하고 시각화합니다.
    """
    img = cv2.imread(image_path)
    if img is None:
        print("이미지를 찾을 수 없습니다.")
        return []
    
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)

    # 윤곽선 및 마스크 생성
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mask = np.zeros_like(gray)
    cv2.drawContours(mask, contours, -1, 255, -1)

    # 거리 변환 (윤곽선으로부터의 거리 계산)
    dist_transform = cv2.distanceTransform(mask, cv2.DIST_L2, 5)

    # --- 좌표 추출 부분 ---
    mesh_list = [] # 좌표를 담을 순수 파이썬 리스트
    
    for y in range(0, h, grid_size):
        for x in range(0, w, grid_size):
            if dist_transform[y, x] > margin:
                # [x, y] 형태로 리스트에 추가
                mesh_list.append([int(x), int(y)])
    
    # ---------------------

    # 결과 시각화
    plt.figure(figsize=(8, 8))
    plt.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    if mesh_list:
        pts = np.array(mesh_list)
        plt.scatter(pts[:, 0], pts[:, 1], c='red', s=15, label='Mesh Points')
    plt.title(f"Extracted {len(mesh_list)} Points")
    plt.legend()
    plt.show()

    return mesh_list # 좌표 리스트 반환

# --- 사용 예시 ---
image_path = 'mesh_making/heart.png'
# 좌표 리스트를 변수에 저장
points_result = get_mesh_coordinates(image_path, grid_size=50, margin=20)

#grid_size를 늘리면 meshpoint의 간격이 넓어지고
#margin을 늘리면 윤곽선과 최초 meshpoint의 사이가 넓어진다.

# 상위 5개 좌표만 출력해서 확인
print("추출된 좌표 리스트 (상위 5개):")
print(points_result[:5])

# 전체 좌표 개수 확인
print(f"총 점의 개수: {len(points_result)}개")