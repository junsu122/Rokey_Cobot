# Rokey_Cobot
두산루키 7기 B-3조 협동로봇(no visual sensor) 프로젝트

https://drawing-flower.web.app/

https://www.notion.so/1-3429c0a50e0d8080a62ec49c508a4a99?source=copy_link



### Exceptions ###

1. 꽃 못잡음
   -> 모니터링에서 신호 발생
1-1. 사람이 못 줌
1-2. 디스펜서 고장
     -> 로봇이 디스펜서를 흔든다


2. 꽃 못꽂음
   -> 꽃을 꽂고 그리퍼를 열었다가 다시 잡아본다. (힘체크)


3. 안전사고
3-1. 사람과 충돌함
3-2. 주변 지형지물과 충돌함


4. 고객의 주문취소
   -> 작업중지


5. 특이점 도달


6. 액자 설치 실패

모니터링 노드 실행 시 필요
pip install textual
pip install textual-plotext
