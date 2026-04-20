import firebase_admin
from firebase_admin import credentials, db
import time
from datetime import datetime

# 1. 초기화
cred = credentials.Certificate("/home/junsu/Downloads/rokey-cobot-firebase-adminsdk-fbsvc-f2b3ddb804.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://rokey-cobot-default-rtdb.asia-southeast1.firebasedatabase.app'
})

def handle_new_data(event):
    data = event.data
    if data:
        coords = data.get('coords', {})
        ts = data.get('updated_at', 0) / 1000.0
        time_str = datetime.fromtimestamp(ts).strftime('%H:%M:%S')
        
        print(f"\n[🔔 {time_str}] 새로운 좌표 수신!")

        # --- 수정된 부분: 리스트인지 딕셔너리인지 확인 ---
        if isinstance(coords, list):
            # 리스트인 경우 (0, 1, 2... 순서대로 나옵니다)
            for i, val in enumerate(coords):
                if val is not None: # Firebase 리스트의 빈 값 방지
                    print(f"  📍 Point {i}: {val}")
        else:
            # 딕셔너리인 경우
            for key, val in coords.items():
                print(f"  📍 Point {key}: {val}")
        
        print("-" * 30)

# 2. 'robot/commands' 경로를 실시간 감시 시작
print("🛰️ 실시간 감시 중... 새로운 데이터가 오면 자동으로 출력됩니다.")
db.reference('robot/commands').listen(handle_new_data)

# 프로그램이 종료되지 않게 유지
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n감시를 종료합니다.")