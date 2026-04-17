import cv2
import numpy as np
from matplotlib import pyplot as plt
from scipy.spatial import Delaunay

def get_balanced_mesh(image_path, internal_density=20, edge_sample_rate=0.01, margin=20):
    """
    internal_density: 내부 점들 사이의 거리 (픽셀 단위). 
                     값이 클수록 삼각형이 커지고, 작을수록 촘촘(작게)해집니다.
    edge_sample_rate: 윤곽선 점의 밀도. 
                     값이 작을수록 윤곽선 점이 많아져서 테두리 근처 삼각형이 작아집니다.
    """
    img = cv2.imread(image_path)
    if img is None: return [], [], []
    h, w = img.shape[:2]
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)

    # 1. 윤곽선 점 추출 조절
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mask = np.zeros_like(gray)
    cv2.drawContours(mask, contours, -1, 255, -1)
    
    edge_points = []
    for cnt in contours:
        # epsilon 값을 조절하여 윤곽선 점의 개수(크기)를 조절합니다.
        # edge_sample_rate가 작을수록 더 많은 점을 남깁니다.
        approx = cv2.approxPolyDP(cnt, edge_sample_rate * cv2.arcLength(cnt, True), True)
        for pt in approx:
            edge_points.append(pt[0])
    edge_points = np.array(edge_points)

    # 2. 내부 점 간격 조절 (internal_density 사용)
    dist_transform = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    
    # 고정된 간격(internal_density)으로 점을 생성하여 삼각형 크기를 일정하게 유지합니다.
    internal_points = []
    for y in range(0, h, internal_density):
        for x in range(0, w, internal_density):
            if dist_transform[y, x] > margin:
                internal_points.append([x, y])
    internal_points = np.array(internal_points)

    # 3. 점 병합 및 들로네 분할
    all_points = np.vstack((edge_points, internal_points))
    tri = Delaunay(all_points)

    # 4. 내부 삼각형 및 중심점 계산
    internal_simplices = []
    centroids = []
    
    for simplex in tri.simplices:
        nodes = all_points[simplex]
        centroid = np.mean(nodes, axis=0).astype(int)
        
        if 0 <= centroid[1] < h and 0 <= centroid[0] < w:
            if mask[centroid[1], centroid[0]] == 255:
                internal_simplices.append(simplex)
                centroids.append(centroid)
    
    centroids = np.array(centroids)

    # 시각화
    plt.figure(figsize=(10, 10))
    plt.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    plt.triplot(all_points[:, 0], all_points[:, 1], internal_simplices, color='cyan', lw=1, alpha=0.6)
    plt.scatter(centroids[:, 0], centroids[:, 1], c='yellow', s=10, label='Centroids')
    plt.title(f"Density: {internal_density}, Edge Rate: {edge_sample_rate}\nTriangles: {len(centroids)}")
    plt.legend()
    plt.axis('off')
    plt.show()

    return all_points.tolist(), internal_simplices, centroids.tolist()

# --- 파라미터 조정하며 실행 ---
image_path = 'mesh_making/heart.png'

# internal_density를 높이면 삼각형이 커지고, 낮추면 작아집니다.
# edge_sample_rate를 조절하여 테두리 삼각형 크기를 내부와 맞춥니다.
points, mesh, centroid_pts = get_balanced_mesh(image_path, 
                                               internal_density=70, # 삼각형 크기 결정 (핵심!)
                                               edge_sample_rate=0.008, # 테두리 점 밀도
                                               margin=15)

print(f"추출된 중심점 개수: {len(centroid_pts)}")