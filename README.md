# No-Look (노룩)
> **"당신이 스마트폰을 보는 사이, AI는 회의에 집중합니다."**
> 실시간 시선 감지 기반 영상 스위칭 및 지능형 자동 응답 시스템

---

## Project Overview
**No-Look**은 화상 회의 중 사용자의 이탈(딴짓)을 실시간으로 감지하고, AI가 생성한 가짜 영상과 자동 채팅 기능을 통해 사용자의 부재를 완벽히 은닉하는 솔루션입니다. 7일간의 집중 개발을 통해 기술적 한계를 '트릭'과 '자동화'로 극복한 프로젝트입니다.

---

## Team & Roles

### 1팀: AI & Trigger (AI Part)
**멤버: 임은상, 변지환, 박성빈**
- **Head Pose & Eye Tracking:** MediaPipe를 이용한 고개 각도 및 시선 이탈 실시간 추적.
- **Object Detection:** 손 영역 주변의 스마트폰 객체 탐지 시 즉시 트리거 신호 송출.
- **Optimization:** 브라우저 연산 부하 방지를 위한 Web Worker 기반 추론 최적화.

### 2팀: Video Engine (Back-end Part)
**멤버: 김민재, 양승준**
- **Seamless Switcher:** `Canvas API` 기반의 실제 캠 ↔ 가짜 영상 간 **Cross-fade(0.5s)** 전환 처리.
- **Lighting Matcher:** 실시간 환경 광원을 분석하여 가짜 영상의 밝기/대조를 동기화하는 필터 구현.
- **Virtual Bridge:** 최종 스트림을 `OBS Virtual Camera`를 통해 Zoom/Meet으로 송출하는 파이프라인 구축.

### 3팀: Dashboard & Macro Bot (Front-end Part)
**멤버: 김유나**
- **Control Panel:** 실시간 감지 로그 및 AI 생성 영상 미리보기를 포함한 React 기반 대시보드.
- **STT & AI Chat:** `Web Speech API`를 통한 회의 내용 텍스트화 및 GPT 기반 최적 답변 생성.
- **Auto-Chat Bot:** `Flask` 로컬 서버와 `PyAutoGUI`를 연동하여 Zoom 채팅창에 답변을 자동 입력하는 매크로 구현.

---

## Key Technical Features

### 1. 실시간 상태 감지 (The Detector)
MediaPipe Face Mesh를 통해 얼굴의 468개 랜드마크를 추출하고, 눈동자의 위치와 안면 회전 행렬을 계산합니다.
- **Trigger Condition 1:** 고개 각도가 정면 기준 30도 이상 숙여질 때.
- **Trigger Condition 2:** 시선이 화면 하단(스마트폰 위치)에 1초 이상 머물 때.

### 2. 가짜 영상 및 리액션 생성 (The Deepfake & Bot)
실시간 딥페이크의 한계를 극복하기 위한 '최적화된 트릭'을 사용합니다.
- **Looped Deepfake:** 사전에 촬영된 고화질 경청 영상으로 자연스러운 루프 구현.
- **Natural Transition:** `cv2.addWeighted()` 원리를 이용한 알파 블렌딩 전환 효과.

### 3. OS 레벨 매크로 자동화 (The Bridge)
브라우저의 보안 제약을 우회하여 실제 업무 환경에 적용합니다.
1. **Detection:** 상사가 내 이름을 부르거나 질문하는 것을 STT로 감지.
2. **Thinking:** OpenAI GPT API가 상황에 맞는 답변 생성.
3. **Execution:** 로컬 Python 스크립트가 줌(Zoom) 채팅창 좌표를 자동 클릭하여 답변 타이핑 후 엔터 전송.

---

## Tech Stack
- **Frontend:** React, Next.js, Tailwind CSS
- **AI/ML:** @mediapipe/face_mesh, @mediapipe/hands, TensorFlow.js
- **Backend/Logic:** Python (Flask), OpenCV, PyAutoGUI
- **Streaming:** OBS Virtual Camera, WebRTC
