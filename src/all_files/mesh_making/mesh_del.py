import cv2
import numpy as np
from matplotlib import pyplot as plt
from scipy.spatial import Delaunay

def get_bounded_mesh_with_transformed_centroids(image_path, target_count=300, margin=15, target_w=300, target_h=300):
    # 1. 전처리 (기존 로직 동일)
    img = cv2.imread(image_path)
    if img is None: return [], [], [], []
    h_img, w_img = img.shape[:2]
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)

    # 2. 마스크 및 윤곽선 점 추출 (기존 유지)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mask = np.zeros_like(gray)
    cv2.drawContours(mask, contours, -1, 255, -1)
    
    edge_points = []
    for cnt in contours:
        approx = cv2.approxPolyDP(cnt, 0.005 * cv2.arcLength(cnt, True), True)
        for pt in approx:
            edge_points.append(pt[0])
    edge_points = np.array(edge_points)

    # 3. 내부 메쉬 점 추출 (기존 유지)
    area = np.sum(mask == 255)
    auto_grid_size = int(np.sqrt(area / target_count))
    dist_transform = cv2.distanceTransform(mask, cv2.DIST_L2, 5)

    internal_points = []
    for y in range(0, h_img, auto_grid_size):
        for x in range(0, w_img, auto_grid_size):
            if dist_transform[y, x] > margin:
                internal_points.append([x, y])
    internal_points = np.array(internal_points)

    # 4. 점 병합 및 들로네 분할 (기존 유지)
    all_points = np.vstack((edge_points, internal_points))
    tri = Delaunay(all_points)

    # 5. 내부 삼각형 필터링 및 중심점 계산 (기존 유지)
    internal_simplices = []
    centroids_px = [] # 픽셀 좌표 (시각화용)
    
    for simplex in tri.simplices:
        nodes = all_points[simplex]
        centroid = np.mean(nodes, axis=0)
        
        if 0 <= int(centroid[1]) < h_img and 0 <= int(centroid[0]) < w_img:
            if mask[int(centroid[1]), int(centroid[0])] == 255:
                internal_simplices.append(simplex)
                centroids_px.append(centroid)
    
    centroids_px = np.array(centroids_px)

    # 6. [추가] 좌표계 변환 로직 (좌하단 0,0 / 우상단 target_w, target_h / 소수점 2자리)
    transformed_centroids = []
    for pt in centroids_px:
        # X 변환: (현재X / 이미지폭) * 목표폭
        new_x = (pt[0] / w_img) * target_w
        # Y 변환: (1 - (현재Y / 이미지높이)) * 목표높이 (좌하단 0,0 기준 상하반전)
        new_y = (1 - (pt[1] / h_img)) * target_h
        transformed_centroids.append([round(new_x, 2), round(new_y, 2)])

    # 7. 시각화 (기존 시각화 기능 유지 - 원본 픽셀 좌표 기준)
    plt.figure(figsize=(12, 12))
    plt.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    
    plt.triplot(all_points[:, 0], all_points[:, 1], internal_simplices, color='cyan', lw=1, alpha=0.6)
    plt.scatter(edge_points[:, 0], edge_points[:, 1], c='blue', s=8, label='Edge Points', alpha=0.5)
    plt.scatter(internal_points[:, 0], internal_points[:, 1], c='red', s=15, label='Internal Points', alpha=0.7)
    
    if len(centroids_px) > 0:
        plt.scatter(centroids_px[:, 0], centroids_px[:, 1], c='yellow', s=12, edgecolors='black', label='Triangle Centroids', zorder=10)
    
    plt.title(f"Visual: Pixel Space | Data: {target_w}x{target_h} Space\nTriangles: {len(centroids_px)}")
    plt.legend()
    plt.axis('off')
    plt.show()

    # 원본 데이터와 변환 데이터를 모두 반환
    return all_points.tolist(), internal_simplices, centroids_px.tolist(), transformed_centroids

# --- 실행 ---
image_path = 'mesh_making/heart.png'
# 파라미터: 이미지 경로, 타겟 개수, 마진, 변환할 너비, 변환할 높이
points, mesh_data, raw_centroids, final_coords = get_bounded_mesh_with_transformed_centroids(
    image_path, target_count=11, margin=20, target_w=300, target_h=300
)

# 결과 확인
print(f"총 추출된 점 개수: {len(final_coords)}")
print("--- 변환된 좌표 (좌하단 (0,0), 우상단 (300,300), 소수점 2자리) ---")
for i, pt in enumerate(final_coords[:5]):
    print(f"Point {i+1}: {pt}")