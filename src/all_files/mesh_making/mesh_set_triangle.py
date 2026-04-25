import cv2
import numpy as np
from matplotlib import pyplot as plt
from scipy.spatial import Delaunay

def get_balanced_mesh_transformed(image_path, internal_density=20, edge_sample_rate=0.01, 
                                  margin=20, target_w=300, target_h=300):
    """
    internal_density: 내부 점 간격 (삼각형 크기 조절)
    edge_sample_rate: 윤곽선 점 밀도
    target_w, target_h: 변환할 좌표계의 최대 범위 (우상단 좌표)
    """
    img = cv2.imread(image_path)
    if img is None: return [], [], [], []
    h_img, w_img = img.shape[:2]
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)

    # 1. 윤곽선 점 추출 조절
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mask = np.zeros_like(gray)
    cv2.drawContours(mask, contours, -1, 255, -1)
    
    edge_points = []
    for cnt in contours:
        approx = cv2.approxPolyDP(cnt, edge_sample_rate * cv2.arcLength(cnt, True), True)
        for pt in approx:
            edge_points.append(pt[0])
    edge_points = np.array(edge_points)

    # 2. 내부 점 간격 조절 (고정 밀도 방식)
    dist_transform = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    internal_points = []
    for y in range(0, h_img, internal_density):
        for x in range(0, w_img, internal_density):
            if dist_transform[y, x] > margin:
                internal_points.append([x, y])
    internal_points = np.array(internal_points)

    # 3. 점 병합 및 들로네 분할
    all_points = np.vstack((edge_points, internal_points))
    tri = Delaunay(all_points)

    # 4. 내부 삼각형 및 픽셀 중심점 계산
    internal_simplices = []
    centroids_px = []
    
    for simplex in tri.simplices:
        nodes = all_points[simplex]
        centroid = np.mean(nodes, axis=0)
        
        if 0 <= int(centroid[1]) < h_img and 0 <= int(centroid[0]) < w_img:
            if mask[int(centroid[1]), int(centroid[0])] == 255:
                internal_simplices.append(simplex)
                centroids_px.append(centroid)
    
    centroids_px = np.array(centroids_px)

    # 5. [핵심] 좌하단 (0,0) 기준 및 300x300 스케일 변환
    transformed_centroids = []
    for pt in centroids_px:
        # X 변환: (현재X / 이미지폭) * target_w
        new_x = (pt[0] / w_img) * target_w
        # Y 변환: (1 - (현재Y / 이미지높이)) * target_h (상하 반전)
        new_y = (1 - (pt[1] / h_img)) * target_h
        transformed_centroids.append([round(new_x, 2), round(new_y, 2)])

    # 6. 시각화 (기존 시각화 기능 유지)
    plt.figure(figsize=(10, 10))
    plt.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    plt.triplot(all_points[:, 0], all_points[:, 1], internal_simplices, color='cyan', lw=1, alpha=0.6)
    
    if len(centroids_px) > 0:
        plt.scatter(centroids_px[:, 0], centroids_px[:, 1], c='yellow', s=15, edgecolors='black', label='Centroids')
    
    plt.title(f"Density: {internal_density} | Target Scale: {target_w}x{target_h}\nTriangles: {len(centroids_px)}")
    plt.legend()
    plt.axis('off')
    plt.show()

    # 원본 점, 메쉬 인덱스, 픽셀 중심점, 변환된 좌표 순으로 반환
    return all_points.tolist(), internal_simplices, centroids_px.tolist(), transformed_centroids

# --- 실행 및 파라미터 조정 ---
image_path = 'mesh_making/heart.png'

# 원하는 삼각형 크기와 좌표 범위를 설정하세요.
points, mesh, raw_centroids, final_coords = get_balanced_mesh_transformed(
    image_path, 
    internal_density=70,    # 숫자를 키우면 삼각형이 커집니다.
    edge_sample_rate=0.008, # 윤곽선 점 밀도
    margin=15,              # 테두리 여유
    target_w=300,           # 변환 좌표 X 범위
    target_h=300            # 변환 좌표 Y 범위
)

print(f"총 추출된 중심점 개수: {len(final_coords)}")
print("--- 변환된 좌표 (좌하단 0,0 기준, Max 300,300) ---")
for i, pt in enumerate(final_coords):
    print(f"Point {i+1}: {pt}")