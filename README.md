# 송도 러닝·산책 코스 메이커 (MVP)

## 로컬 실행
    pip install -r requirements.txt
    python -m uvicorn app:app --port 8000     # http://localhost:8000
시뮬레이션(GPS 없이 추적 화면 테스트): http://localhost:8000/?sim=1

## 송도 그래프 재생성 (선택)
    pip install -r requirements-build.txt
    python build_graph.py

## 배포 (Render)
1. 이 폴더를 GitHub 저장소로 올린다.
2. Render → New → Blueprint(또는 Web Service) → 저장소 선택. `render.yaml`을 자동 인식한다.
3. 발급된 `https://…onrender.com` 주소를 폰에서 열면 GPS(HTTPS)가 동작한다.
4. (선택) 환경변수 `OPENAI_API_KEY`(모델 변경 시 `OPENAI_MODEL`)를 추가하면 GPT 문구가 켜진다.
