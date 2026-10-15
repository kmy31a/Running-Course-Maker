from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
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
    if r.pace not in engine.PACES: raise HTTPException(400, "페이스는 걷기/조깅/러닝 중 하나")
    if r.type not in engine.TYPES: raise HTTPException(400, "난이도는 평지/오르막/인터벌 중 하나")
    lat, lon = (r.lat, r.lon)
    if r.start: lat, lon = engine.START_POINTS[r.start]
    if lat is None or lon is None: raise HTTPException(400, "출발지가 필요해요")
    if not engine.in_songdo(lat, lon): raise HTTPException(400, "현재 위치가 송도 밖이에요. 센트럴파크 등 송도 내 대표 출발지를 선택해 주세요.")
    if r.goal not in llm.GOALS: raise HTTPException(400, "목표는 다이어트/기록/힐링 중 하나")
    courses = engine.recommend(lat, lon, r.pace, r.type, r.scenery, min(max(r.weight, 30), 200))
    src = llm.enrich(courses, {"start": r.start or "현재 위치", "pace": r.pace, "type": r.type, "goal": r.goal, "scenery": r.scenery})
    return {"primary": r.minutes, "text_source": src, "courses": courses}

@app.get("/")
def index(): return FileResponse(os.path.join(_HERE, "static", "index.html"))
app.mount("/static", StaticFiles(directory=os.path.join(_HERE, "static")), name="static")
