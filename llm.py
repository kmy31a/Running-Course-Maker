"""코스 설명·운동 팁 생성. OPENAI_API_KEY가 있으면 LLM(GPT), 없으면 규칙 기반 문구.
역할 분리: 거리·칼로리 계산은 engine(코드), 설명·팁·동기부여 문구만 여기서 생성."""
import os, json

def _load_env(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")):
    """songdo/.env 의 KEY=VALUE 줄을 환경변수로 읽는다 (이미 설정된 값은 유지)."""
    if os.path.exists(path):
        for line in open(path, encoding="utf-8-sig"):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("\"'"))
_load_env()

GOALS = ("다이어트", "기록", "힐링")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6-luna")   # 모델명은 .env의 OPENAI_MODEL로 바꿀 수 있다

GOAL_TIP = {
    "다이어트": "일정한 속도로 쉬지 않고 움직이면 지방 연소에 도움이 돼요.",
    "기록": "처음 5분은 천천히 풀고, 마지막 5분에 속도를 조금 올려 보세요.",
    "힐링": "이어폰을 빼고 풍경과 숨소리에 집중해 보세요. 기록은 신경 쓰지 않아도 괜찮아요.",
}
GOAL_MOTIVE = {
    "다이어트": "오늘 한 걸음이 내일의 가벼운 몸이 돼요!",
    "기록": "어제보다 한 걸음 더, 기록은 꾸준함이 만들어요!",
    "힐링": "잠시 멈춰 숨 돌리는 시간, 오늘도 잘 오셨어요.",
}

def enabled():
    return bool(os.environ.get("OPENAI_API_KEY"))

def rule_fill(courses, ctx):
    """LLM 없이 규칙 기반 설명·팁·응원 문구를 채운다 (즉시 응답용 / LLM 실패 시 대체)."""
    scen = "·".join(ctx["scenery"])
    for c in courses:
        c["description"] = (f"{ctx['start']}에서 출발해 {scen} 풍경을 따라 약 {c['distance_km']}km를 "
                            f"{c['minutes']}분 동안 돌아오는 순환 코스예요.")
        c["tips"] = c["tips"] + [GOAL_TIP[ctx["goal"]]]
        c["motivation"] = GOAL_MOTIVE[ctx["goal"]]
        c["ai"] = False

def _parse(text, n):
    """LLM 응답에서 JSON 배열을 꺼내 검증한다. 형식이 틀리면 ValueError."""
    try:
        data = json.loads(text)
    except ValueError:
        data = json.loads(text[text.index("["): text.rindex("]") + 1])
    if isinstance(data, dict):
        data = data.get("courses")
    if not isinstance(data, list) or len(data) != n:
        raise ValueError(f"코스 {n}개가 필요한데 {len(data) if isinstance(data, list) else '?'}개 응답")
    for d in data:
        if not (isinstance(d.get("description"), str) and isinstance(d.get("motivation"), str)
                and isinstance(d.get("tips"), list) and all(isinstance(t, str) for t in d["tips"])):
            raise ValueError("description/tips/motivation 형식 오류")
    return data

def _prompt(courses, ctx):
    hill = ctx["type"] == "오르막"
    facts = []
    for c in courses:
        f = {"분": c["minutes"], "거리km": c["distance_km"], "칼로리kcal": c["kcal"],
             "기본팁(이미 화면에 있음)": c.get("tips", [])}
        if c.get("interval_plan"): f["인터벌구성"] = c["interval_plan"]
        if hill: f["다리·육교구간m"] = c["uphill_m"]   # 오르막이 아닌 코스에선 다리 정보를 주지 않는다(모순처럼 읽혀서)
        facts.append(f)
    night = "야경" in ctx["scenery"]
    rules = [
        "수치(거리·칼로리·분·세트 수)는 아래 사실에 있는 값만 쓰고 바꾸거나 새로 만들지 말 것.",
        "단위는 km, kcal, 분만 사용하고 숫자에 붙여 쓸 것(예: 2.3km, 152kcal, 20분).",
        "세 코스의 description·motivation은 서로 다른 표현으로 써서 같은 문장을 반복하지 말 것(시간 길이에 맞는 분위기로).",
        "풍경 일치율(%)이나 점수는 문장에 넣지 말 것.",
        f"'페이스 {ctx['pace']}' 같은 어색한 합성어 대신 '{ctx['pace']}'처럼 자연스럽게 쓸 것.",
        "tips는 '기본팁'과 겹치거나 상충하지 않는 새로운 내용으로, 목표에 맞게 정확히 2개.",
        "description은 1~2문장, 친근한 존댓말. 출발지 이름은 한 번만 쓰고 '(인천 송도)'는 붙이지 말 것.",
        "motivation은 1문장.",
    ]
    if hill: rules.append("오르막은 '다리·육교 구간'이라고만 표현하고 경사·고도·언덕은 언급하지 말 것.")
    else: rules.append("다리·육교·경사·고도는 언급하지 말 것.")
    if night: rules.append("'야경'은 조명 데이터가 아니라 공원·수변 구간으로 추정한 값이므로, 야경이 보인다고 단정하지 말고 "
                           "'저녁에 걷기 좋은 공원·수변 길' 정도로만 표현할 것.")
    return (f"러닝·산책 코스 앱 '송도 코스 메이커'의 문구를 써줘. 출발지 {ctx['start']}, 페이스 {ctx['pace']}, "
            f"난이도 {ctx['type']}, 목표 {ctx['goal']}, 선호 풍경 {'·'.join(ctx['scenery'])}.\n"
            f"코스 사실: {json.dumps(facts, ensure_ascii=False)}\n"
            "규칙:\n" + "\n".join(f"- {r}" for r in rules) + "\n"
            'JSON 배열만 출력: [{"description":"..","tips":["..",".."],"motivation":".."}, ...] '
            f"(코스 순서 동일, 총 {len(courses)}개)")

def narrate(courses, ctx):
    """GPT로 코스별 {description, ai_tips, motivation} 목록을 만든다. 실패하면 예외."""
    from openai import OpenAI
    res = OpenAI(timeout=45.0, max_retries=1).chat.completions.create(
        model=MODEL, messages=[{"role": "user", "content": _prompt(courses, ctx)}])
    data = _parse(res.choices[0].message.content, len(courses))
    return [{"description": d["description"].strip(), "ai_tips": [t.strip() for t in d["tips"][:3]],
             "motivation": d["motivation"].strip()} for d in data]

def enrich(courses, ctx):
    """(스크립트·테스트용) 한 번에 채운다. 사용한 방식 'llm' | 'rule'을 돌려준다."""
    rule_fill(courses, ctx)
    if enabled():
        try:
            for c, d in zip(courses, narrate(courses, ctx)):
                c.update(description=d["description"], motivation=d["motivation"], ai_tips=d["ai_tips"], ai=True)
            return "llm"
        except Exception as e:
            print("LLM 실패, 규칙 기반으로 대체:", type(e).__name__, e)
    return "rule"
