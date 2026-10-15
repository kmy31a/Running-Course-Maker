"""코스 설명·운동 팁 생성. OPENAI_API_KEY가 있으면 LLM(GPT), 없으면 규칙 기반 문구.
역할 분리: 거리·칼로리 계산은 engine(코드), 설명·팁·동기부여 문구만 여기서 생성."""
import os, json

def _load_env(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")):
    """songdo/.env 의 KEY=VALUE 줄을 환경변수로 읽는다 (이미 설정된 값은 유지)."""
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
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

def _fallback(c, ctx):
    scen = "·".join(ctx["scenery"])
    c["description"] = (f"{ctx['start']}에서 출발해 {scen} 풍경을 따라 약 {c['distance_km']}km를 "
                        f"{c['minutes']}분 동안 돌아오는 순환 코스예요.")
    c["tips"] = c["tips"] + [GOAL_TIP[ctx["goal"]]]
    c["motivation"] = GOAL_MOTIVE[ctx["goal"]]

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

def enrich(courses, ctx):
    """courses 각 항목에 description / tips(추가) / motivation을 채우고, 사용한 방식('llm'|'rule')을 돌려준다."""
    if os.environ.get("OPENAI_API_KEY"):
        try:
            from openai import OpenAI
            facts = [{"분": c["minutes"], "거리km": c["distance_km"], "칼로리kcal": c["kcal"],
                      "풍경일치%": c["scenery_match"], "다리·육교구간m": c["uphill_m"], "인터벌구성": c.get("interval_plan")}
                     for c in courses]
            prompt = (
                f"러닝·산책 코스 앱의 문구를 써줘. 출발지 {ctx['start']}(인천 송도), 페이스 {ctx['pace']}, "
                f"난이도 {ctx['type']}, 목표 {ctx['goal']}, 선호 풍경 {ctx['scenery']}.\n"
                f"코스 사실(수치는 절대 바꾸거나 새로 만들지 말 것): {json.dumps(facts, ensure_ascii=False)}\n"
                "각 코스마다 description(1~2문장, 친근한 존댓말), tips(목표에 맞는 팁 정확히 2개, 문자열 배열), motivation(1문장). "
                "단위는 km, kcal, 분만 사용. 오르막은 '다리·육교 구간'이라고만 표현하고 경사·고도는 언급하지 말 것.\n"
                'JSON 배열만 출력: [{"description":"..","tips":["..",".."],"motivation":".."}, ...] '
                f"(코스 순서 동일, 총 {len(courses)}개)")
            res = OpenAI(timeout=20.0, max_retries=1).chat.completions.create(
                model=MODEL, messages=[{"role": "user", "content": prompt}])
            data = _parse(res.choices[0].message.content, len(courses))
            for c, d in zip(courses, data):
                c["description"], c["motivation"] = d["description"].strip(), d["motivation"].strip()
                c["ai_tips"] = [t.strip() for t in d["tips"][:3]]   # GPT가 쓴 팁은 따로 둬서 화면에서 🤖로 구분한다
                c["ai"] = True
            return "llm"
        except Exception as e:
            print("LLM 실패, 규칙 기반으로 대체:", type(e).__name__, e)
    for c in courses: _fallback(c, ctx)
    return "rule"
