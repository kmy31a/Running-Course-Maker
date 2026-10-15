import os, time, collections
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import engine, llm

_HERE = os.path.dirname(os.path.abspath(__file__))
app = FastAPI(title="송도 러닝·산책 코스 메이커")

class Req(BaseModel):
    start: str | None = None
    lat: float | None = None
    lon: float | None = None
    minutes: int = 40          # 1순위 강조용
    pace: str = "조깅"
    type: str = "평지"
    scenery: list[str] = ["공원"]
    goal: str = "다이어트"
    weight: float = engine.DEFAULT_WEIGHT   # 칼로리 계산용(kg)

@app.get("/api/meta")
def meta():
    return {"starts": engine.START_POINTS, "paces": list(engine.PACES), "types": list(engine.TYPES), "scenery": list(engine.SCENERY), "goals": list(llm.GOALS)}

@app.post("/api/recommend")
def recommend(r: Req):
    """코스·거리·칼로리를 코드로 계산해 규칙 문구와 함께 즉시 돌려준다. GPT 문구는 /api/narrate 로 따로 받는다."""
    if r.pace not in engine.PACES: raise HTTPException(400, "페이스는 걷기/조깅/러닝 중 하나")
    if r.type not in engine.TYPES: raise HTTPException(400, "난이도는 평지/오르막/인터벌 중 하나")
    lat, lon = (r.lat, r.lon)
    if r.start: lat, lon = engine.START_POINTS[r.start]
    if lat is None or lon is None: raise HTTPException(400, "출발지가 필요해요")
    if not engine.in_songdo(lat, lon): raise HTTPException(400, "현재 위치가 송도 밖이에요. 센트럴파크 등 송도 내 대표 출발지를 선택해 주세요.")
    if r.goal not in llm.GOALS: raise HTTPException(400, "목표는 다이어트/기록/힐링 중 하나")
    courses = engine.recommend(lat, lon, r.pace, r.type, r.scenery, min(max(r.weight, 30), 200))
    llm.rule_fill(courses, {"start": r.start or "현재 위치", "pace": r.pace, "type": r.type, "goal": r.goal, "scenery": r.scenery})
    return {"primary": r.minutes, "llm": llm.enabled(), "text_source": "rule", "courses": courses}

# ---- GPT 문구 (코스를 먼저 보여준 뒤 화면이 따로 요청한다) ----
class CourseFacts(BaseModel):
    minutes: int = Field(ge=1, le=180)
    distance_km: float = Field(ge=0, le=100)
    kcal: int = Field(ge=0, le=10000)
    uphill_m: int = Field(default=0, ge=0, le=100000)
    interval_plan: str | None = Field(default=None, max_length=120)
    tips: list[str] = Field(default=[], max_length=8)

class NarrateReq(BaseModel):
    start: str = Field(max_length=20)
    pace: str
    type: str
    goal: str
    scenery: list[str] = Field(max_length=4)
    courses: list[CourseFacts] = Field(min_length=1, max_length=3)

_calls = collections.defaultdict(list)   # IP별 최근 호출 시각 — 공개 서버에서 남이 내 API 키를 소진하지 못하게 제한
LIMIT, WINDOW = 8, 60                    # 1분에 8번

@app.post("/api/narrate")
def narrate(r: NarrateReq, request: Request):
    if not llm.enabled(): return {"ok": False, "reason": "no_key"}
    if r.pace not in engine.PACES or r.type not in engine.TYPES or r.goal not in llm.GOALS \
            or any(s not in engine.SCENERY for s in r.scenery):
        raise HTTPException(400, "입력값이 올바르지 않아요")
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    now = time.time()
    _calls[ip] = [t for t in _calls[ip] if now - t < WINDOW]
    if len(_calls[ip]) >= LIMIT: raise HTTPException(429, "잠시 후 다시 시도해 주세요")
    _calls[ip].append(now)
    courses = [c.model_dump() for c in r.courses]
    for c in courses: c["tips"] = [t[:80] for t in c["tips"]]
    try:
        items = llm.narrate(courses, {"start": r.start, "pace": r.pace, "type": r.type, "goal": r.goal, "scenery": r.scenery})
    except Exception as e:
        print("LLM 실패:", type(e).__name__, e)
        return {"ok": False, "reason": "error"}
    return {"ok": True, "items": items}

@app.get("/")
def index(): return FileResponse(os.path.join(_HERE, "static", "index.html"))
app.mount("/static", StaticFiles(directory=os.path.join(_HERE, "static")), name="static")
