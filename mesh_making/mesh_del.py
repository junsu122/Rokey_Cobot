import cv2
import numpy as np
from matplotlib import pyplot as plt
from scipy.spatial import Delaunay

def get_bounded_mesh_with_centroids(image_path, target_count=300, margin=15):
    # 1. 전처리 (이전 로직 동일)
    img = cv2.imread(image_path)
    if img is None: return [], [], []
    h, w = img.shape[:2]
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)

    # 2. 마스크 및 윤곽선 점 추출 (Edge Points)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mask = np.zeros_like(gray)
    cv2.drawContours(mask, contours, -1, 255, -1)
    
    edge_points = []
    for cnt in contours:
        approx = cv2.approxPolyDP(cnt, 0.005 * cv2.arcLength(cnt, True), True)
        for pt in approx:
            edge_points.append(pt[0])
    edge_points = np.array(edge_points)

    # 3. 내부 메쉬 점 추출 (Internal Points)
    area = np.sum(mask == 255)
    auto_grid_size = int(np.sqrt(area / target_count))
    dist_transform = cv2.distanceTransform(mask, cv2.DIST_L2, 5)

    internal_points = []
    for y in range(0, h, auto_grid_size):
        for x in range(0, w, auto_grid_size):
            if dist_transform[y, x] > margin:
                internal_points.append([x, y])
    internal_points = np.array(internal_points)

    # 4. 점 병합 및 들로네 분할
    all_points = np.vstack((edge_points, internal_points))
    tri = Delaunay(all_points)

    # 5. [중요] 내부 삼각형 필터링 및 중심점 계산
    internal_simplices = []
    centroids = [] # 삼각형 중심점을 담을 리스트
    
    for simplex in tri.simplices:
        nodes = all_points[simplex]
        # 삼각형의 무게중심(Centroid) 계산 (세 꼭짓점의 평균)
        centroid = np.mean(nodes, axis=0).astype(int)
        
        # 중심점이 하트 마스크(흰색) 안에 있을 때만 추가
        if 0 <= centroid[1] < h and 0 <= centroid[0] < w:
            if mask[centroid[1], centroid[0]] == 255:
                internal_simplices.append(simplex)
                centroids.append(centroid) # 중심점 좌표 저장
    
    centroids = np.array(centroids)

    # 6. 시각화
    plt.figure(figsize=(12, 12))
    plt.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    
    # [A] 하늘색 삼각형 메쉬 (투명도 조절)
    plt.triplot(all_points[:, 0], all_points[:, 1], internal_simplices, color='cyan', lw=1, alpha=0.6)
    
    # [B] 기존 점들 (윤곽선 파랑, 내부 빨강)
    plt.scatter(edge_points[:, 0], edge_points[:, 1], c='blue', s=8, label='Edge Points', alpha=0.5)
    plt.scatter(internal_points[:, 0], internal_points[:, 1], c='red', s=15, label='Internal Points', alpha=0.7)
    
    # [C] [핵심 추가] 삼각형 중심점 (노란색 점)
    if len(centroids) > 0:
        plt.scatter(centroids[:, 0], centroids[:, 1], c='yellow', s=12, edgecolors='black', label='Triangle Centroids', zorder=10)
    
    plt.title(f"Mesh with Centroids\nPoints: {len(all_points)}, Triangles & Centroids: {len(centroids)}")
    plt.legend()
    plt.axis('off')
    plt.show()

    return all_points.tolist(), internal_simplices, centroids.tolist()

# --- 실행 ---
image_path = 'mesh_making/heart.png'
points, mesh_data, centroid_points = get_bounded_mesh_with_centroids(image_path, target_count=11, margin=20) ####값 바꾸는곳####

# 상위 5개 중심점 좌표 출력 확인
print("추출된 삼각형 중심점 좌표 (상위 5개):")
print(len(centroid_points))
print(centroid_points)

# ### 사용법
# 윤곽선을 따고, 그 윤곽선을 기준으로 들로네 삼각분할을 진행하여 메쉬화를 시킴
# target_count는 내부 점의 개수를 조절하고, margin은 윤곽선과 내부 점의 처음 간격을 지정.
# 들로네 삼각분할을 통해 생성된 삼각형의 무게중심을 좌표로 추출
# ###