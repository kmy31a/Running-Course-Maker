"""룰 베이스 코스 엔진: 시간·난이도 → 목표거리 → 순환 코스 → 풍경 점수화 → 팁."""
import math, random
import os
import numpy as np
import networkx as nx

PACES = {"걷기": 4.5, "조깅": 7.0, "러닝": 9.0}        # km/h 기본 속도
TYPES = ("평지", "오르막", "인터벌")
MET = {"걷기": 3.5, "조깅": 7.0, "러닝": 9.0}
TYPE_MET = {"평지": 1.0, "오르막": 1.1, "인터벌": 1.1}   # 오르막·인터벌은 강도 보정
DEFAULT_WEIGHT = 65
DURATIONS = (20, 40, 60)
SCENERY = ("공원", "수변", "도심", "야경")

START_POINTS = {   # OSM 실제 좌표 (공원 중심/역 기준)
    "센트럴파크": (37.3934, 126.6345),
    "트리플스트리트": (37.3796, 126.6612),
    "해돋이공원": (37.3877, 126.6546),
    "달빛축제공원": (37.4061, 126.6372),
}
BBOX = (37.34, 37.44, 126.60, 126.70)

_HERE = os.path.dirname(os.path.abspath(__file__))
G = nx.read_graphml(os.path.join(_HERE, "data", "songdo.graphml"))   # osmnx 없이 읽어 서버 메모리를 줄인다
for _, a in G.nodes(data=True):
    a["x"], a["y"] = float(a["x"]), float(a["y"])
_IDS = list(G.nodes)
_LAT = np.array([G.nodes[n]["y"] for n in _IDS])
_LON = np.array([G.nodes[n]["x"] for n in _IDS])

def nearest_node(lat, lon):
    """위경도에서 가장 가까운 그래프 노드 (위도 1° ≈ 111km, 경도 1° ≈ 88km 근사)."""
    return _IDS[int(np.argmin(((_LAT - lat) * 111) ** 2 + ((_LON - lon) * 88) ** 2))]
for _, _, d in G.edges(data=True):
    d["length"] = float(d["length"])
    s = d.get("scenery", "도심")
    d["tags"] = s.strip("[]'").replace("'", "").split(", ") if isinstance(s, str) else s

FAST, SLOW = 1.3, 0.7   # 인터벌: 빠르게/천천히 속도 배율

def interval_plan(pace, minutes):
    """워밍업5 + (빠르게·천천히)×n + 쿨다운5. 세트 수가 10을 넘지 않도록 40분 초과는 한 세트를 길게(2분+3분) 잡는다."""
    base = PACES[pace]
    f, w = (1, 2) if minutes <= 40 else (2, 3)       # 빠르게 f분 + 천천히 w분
    n = (minutes - 10) // (f + w)
    rest = minutes - 10 - n * (f + w)
    km = (5 * SLOW + n * (f * FAST + w * SLOW) + rest * SLOW + 5 * SLOW) * base / 60
    text = (f"워밍업 5분 → (빠르게 {f}분 + 천천히 {w}분) × {n}세트"
            + (f" + 천천히 {rest}분" if rest else "") + " → 쿨다운 5분")
    return km / minutes * 60, text

def speed_of(pace, typ, minutes):
    return interval_plan(pace, minutes)[0] if typ == "인터벌" else PACES[pace]

def target_km(pace, typ, minutes):
    return speed_of(pace, typ, minutes) * minutes / 60

def in_songdo(lat, lon):
    return BBOX[0] <= lat <= BBOX[1] and BBOX[2] <= lon <= BBOX[3]

def _is_up(d):
    """송도는 매립지라 고도 데이터가 없어, 다리·육교·계단 구간을 '오르막'으로 간주한다."""
    h = str(d.get("highway", ""))
    return d.get("bridge") not in (None, "no") or "steps" in h

def _edge_score(d, prefs):
    tags = set(d["tags"])
    if "야경" in prefs and tags & {"수변", "공원"}:
        return 1.0   # 조명 정비된 공원·수변 구간을 야경 후보로 간주 (MVP 단순화)
    return 1.0 if tags & set(prefs) else 0.0

def _route_edges(path):
    for u, v in zip(path, path[1:]):
        d = min(G[u][v].values(), key=lambda e: e["length"])
        yield u, v, d

def _score(path, prefs, goal_m, typ):
    total = match = up = 0.0
    for _, _, d in _route_edges(path):
        total += d["length"]; match += d["length"] * _edge_score(d, prefs)
        if _is_up(d): up += d["length"]
    ratio = match / total if total else 0
    err = abs(total - goal_m) / goal_m
    s = ratio - 2 * err
    if typ == "오르막": s += 1.5 * up / total if total else 0
    elif typ == "평지": s -= 2 * up / total if total else 0
    return total, ratio, s, up

def _loop(start, goal_m, rng, prefs, typ, k=1.0):
    """start → A → B → start 삼각 순환. 이미 쓴 간선엔 페널티를 줘 왕복을 피한다."""
    r = goal_m / 4.5 * k   # 도로 우회를 감안한 반경 (k는 시행마다 보정)
    lat0, lon0 = G.nodes[start]["y"], G.nodes[start]["x"]
    ang = rng.uniform(0, 2 * math.pi)
    pts = []
    for k in (0, 1):
        a = ang + k * 2 * math.pi / 3 * rng.uniform(0.8, 1.2)
        pts.append((lat0 + r * math.sin(a) / 111000, lon0 + r * math.cos(a) / 88000))
    mids = [nearest_node(la, lo) for la, lo in pts]
    used = set()
    def w(u, v, d):
        e = min(d.values(), key=lambda e: e["length"])
        bonus = 1 - 0.4 * _edge_score(e, prefs)
        if typ == "오르막" and _is_up(e): bonus *= 0.4
        elif typ != "오르막" and _is_up(e): bonus *= 3
        return e["length"] * bonus * (3 if (u, v) in used or (v, u) in used else 1)
    full = [start]
    for a, b in zip([start] + mids, mids + [start]):
        if a == b: continue
        seg = nx.shortest_path(G, a, b, weight=w)
        for u, v in zip(seg, seg[1:]): used.add((u, v))
        full += seg[1:]
    return full

def tip(pace, typ, minutes, prefs):
    t = ["5분 가볍게 걷기로 준비운동, 끝난 뒤 스트레칭을 해요."]
    t.append({"걷기": "대화가 가능한 속도를 유지하고 무리하지 마세요.",
              "조깅": "호흡이 약간 찰 정도의 속도를 유지하고 수분을 보충하세요.",
              "러닝": "초반 속도를 아끼고 마지막 5분은 쿨다운으로 마무리하세요."}[pace])
    if typ == "인터벌": t.append("빠른 구간에서도 자세를 무너뜨리지 말고, 느린 구간엔 호흡을 충분히 돌려요.")
    if typ == "오르막": t.append("다리·육교 구간에서는 보폭을 줄이고 팔을 크게 흔들어 보세요.")
    if minutes == 60: t.append("중간에 물을 마시고 신발·양말 상태를 점검하세요.")
    if "수변" in prefs: t.append("송도 해안·수변 구간은 바람이 강하니 겉옷을 챙기세요.")
    if "야경" in prefs: t.append("야간엔 조명이 있는 센트럴파크·수변 구간 위주로 이용하세요.")
    return t

def kcal(pace, typ, minutes, weight):
    return round(MET[pace] * TYPE_MET[typ] * weight * minutes / 60)   # MET × 체중(kg) × 시간(h)

def recommend(lat, lon, pace, typ, prefs, weight=DEFAULT_WEIGHT, tries=20, seed=None):
    prefs = [p for p in prefs if p in SCENERY] or ["공원"]
    start = nearest_node(lat, lon)
    out = []
    for m in DURATIONS:
        goal = target_km(pace, typ, m) * 1000
        rng = random.Random(seed if seed is not None else (start, m, pace, typ, tuple(prefs)).__hash__() & 0xFFFF)
        best = None; k = 1.0
        for _ in range(tries):
            try: path = _loop(start, goal, rng, prefs, typ, k)
            except nx.NetworkXNoPath: continue
            total, ratio, s, up = _score(path, prefs, goal, typ)
            k *= (goal / total) ** 0.8
            if best is None or s > best[0]: best = (s, path, total, ratio, up)
        if not best: continue
        _, path, total, ratio, up = best
        c = {
            "minutes": m, "target_km": round(goal / 1000, 1),
            "distance_km": round(total / 1000, 2),
            "kcal": kcal(pace, typ, m, weight),
            "scenery_match": round(ratio * 100),
            "uphill_m": round(up),
            "path": [[G.nodes[n]["y"], G.nodes[n]["x"]] for n in path],
            "tips": tip(pace, typ, m, prefs),
        }
        if typ == "인터벌": c["interval_plan"] = interval_plan(pace, m)[1]
        out.append(c)
    return out
