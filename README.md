# 🌸 Rokey_Cobot: Drawing Flower Project
**두산 로봇 ROKEY Boot Camp 7기 B-3조** 비주얼 센서 없이 정밀한 좌표 제어와 클라우드 연동을 통한 **협동로봇 꽃꽂이 서비스**입니다.

[🌐 Web App](https://drawing-flower.web.app/) | [📋 Project Notion](https://www.notion.so/1-3429c0a50e0d8080a62ec49c508a4a99) | [🔥 Firebase Console](https://console.firebase.google.com/project/drawing-flower/overview)

---

## 🏗️ System Architecture
본 프로젝트는 **React(Frontend) - Firebase(Cloud) - ROS2(Backend)**가 유기적으로 연결된 분산 시스템 구조를 가집니다.

### 1. Node Architecture
* **`App.jsx`**: 사용자 UI/UX 및 이미지 픽셀화 좌표 생성
* **`publisher_v4.py`**: Firebase의 명령을 ROS2 토픽(`/new_parameter`)으로 전환 (Downlink)
* **`drawing_flower_final.py`**: 로봇의 메인 동작 제어 및 FSM(Finite State Machine) 관리
* **`monitor_node_v4.py`**: 로봇 상태를 TUI로 표시하고 Firebase에 업로드 (Uplink)

### 2. Control Flow

1. **주문**: Web 앱에서 좌표 생성 → Firebase 저장
2. **중계**: Publisher 노드가 좌표 수신 → ROS2 토픽 발행
3. **실행**: 메인 노드가 좌표에 따라 로봇 이동 및 그리퍼 제어
4. **보고**: 모니터 노드가 실시간 진행률 및 HW 상태를 다시 Web으로 전송

---

## 💻 Environment & Equipment
### Operating System & Software
- **OS**: Ubuntu 22.04 LTS
- **ROS2**: Humble
- **Language**: Python 3.10, React (Vite)
- **Database**: Firebase (Firestore, Storage)

### Hardware List
- **Robot**: Doosan Robotics M0609
- **Gripper**: DH-Robotics PGE-50-26
- **Server**: Mini PC (ROS2 Humble 환경)

---

## 📦 Dependencies
프로젝트 실행을 위해 아래 라이브러리 설치가 필요합니다.

```bash
# Firebase Admin SDK
pip install firebase-admin

# TUI Monitoring Library
pip install textual
pip install textual-plotext


🚀 Execution Guide패키지를 빌드한 후 아래 순서대로 노드를 실행하세요.1. BuildBashcolcon build --packages-select main_robot robot_monitoring
source install/setup.bash
2. Run Nodes (순서 권장)전용 런치 파일이 없는 경우, 각각의 터미널에서 아래 스크립트를 실행합니다.명령 수신 노드 (Firebase → ROS2)Bashros2 run main_robot command_downlink
상태 보고 노드 (ROS2 → Firebase)Bashros2 run robot_monitoring status_uplink
로봇 메인 제어 노드Bashros2 run main_robot drawing_flower
⚠️ Exception Handling작업 중 발생할 수 있는 예외 상황에 대해 다음과 같은 대응 로직이 포함되어 있습니다.상황대응 프로세스1. 꽃 취득 실패모니터링 노드 에러 신호 발생 → 디스펜서 보정(로봇이 흔들기) 수행2. 삽입 실패힘 체크(Force Check) 후 그리퍼 재파지 및 재시도3. 안전사고충돌 감지 시 즉시 Protective Stop → Web에 경고 모달 표시4. 주문 취소사용자 취소 신호 수신 시 즉시 작업 중단 및 Home 위치 복귀5. 특이점 도달Singularity 회피 경로 재계산
