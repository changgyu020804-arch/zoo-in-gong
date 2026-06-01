from datetime import datetime
from html import escape
import logging
import os
import re

from ai_client import Image, client, generate_gemini_content
from persona_prompt import build_caption_persona_prompt_text
from text_utils import clean_multi_line_text, clean_single_line_text, meaningful_text_length, normalize_ai_text


logger = logging.getLogger(__name__)
AI_IMAGE_MAX_SIDE = int(os.environ.get("AI_IMAGE_MAX_SIDE", "640"))
HASHTAG_RE = re.compile(r"(?<![&\w])#[0-9A-Za-z가-힣_]+")
CAPTION_SYSTEM_INSTRUCTION = (
    "You write short Korean social captions for Zoo-In-Gong. "
    "Speak in the pet dog's first person, keep it playful, and output only the caption."
)

CAPTION_VARIATION_STYLES = [
    "산책 뒤 혼잣말처럼 시작하고, 마지막은 집사에게 가볍게 한마디 건넨다.",
    "강아지의 속마음 독백처럼 시작하고, 집사에게 한마디 툭 던진다.",
    "냄새, 발바닥, 꼬리 같은 감각을 앞세워 생생하게 시작한다.",
    "집사를 촬영 담당, 칭찬 담당, 문 열어주는 담당처럼 장난스럽게 부른다.",
    "오늘 좋았던 순간을 자랑하듯 시작하고, 살짝 잘난 척을 섞는다.",
    "평범한 순간을 강아지 눈에는 대단했던 일처럼 귀엽게 바꾼다.",
    "일기장에 몰래 적은 고백처럼 쓰되, 한 문장은 엉뚱하게 꺾는다.",
    "먹방, 패션쇼, 팬미팅, 재판 중 하나의 분위기를 빌려 짧고 웃기게 쓴다.",
    "집사의 행동을 강아지 시점에서 귀엽게 오해한 것처럼 쓴다.",
    "사진 속 표정을 증거처럼 다루고, 결론은 엉뚱하게 낸다.",
    "강아지가 자기 하루를 예능 자막처럼 살짝 과장해서 말한다.",
    "집사에게 쓰담이나 관심을 슬쩍 요구하듯 장난스럽게 쓴다.",
    "한 장면을 영화 포스터 문구처럼 짧게 밀어붙인다.",
    "강아지가 자기 팬클럽 공지를 올리는 것처럼 쓴다.",
    "평범한 행동을 내 기준의 대단한 성취처럼 말한다.",
]

CAPTION_CREATIVE_DEVICES = [
    "강아지의 짧은 일기처럼 쓰고, 마지막에 집사에게 귀여운 역할을 맡긴다.",
    "강아지 머릿속 독백처럼 쓴다. 결론 같은 단어는 꼭 필요할 때만 자연스럽게 1번 쓴다.",
    "짧은 놀이 중계처럼 쓴다. 발바닥, 꼬리, 코끝이 신나게 반응하는 느낌을 낸다.",
    "귀여운 탐정놀이처럼 쓴다. 단서, 발견, 결론 중 1~2개만 골라 과하지 않게 쓴다.",
    "왕국 생활 기록처럼 쓴다. 장소를 새로 만들지 말고 실제 활동 내용을 작은 사건처럼 바꾼다.",
    "집사에게 보내는 장난스러운 후기처럼 쓴다. 칭찬과 잔소리를 귀엽게 섞는다.",
    "강아지가 스스로를 오늘의 주인공으로 소개하되, 허세를 아주 작게만 넣는다.",
    "냄새를 날씨 예보처럼 다룬다. 냄새 흐림, 꼬리 맑음 같은 표현을 한 번만 쓴다.",
    "작은 재판처럼 쓴다. 판결, 증거, 인정 같은 표현을 귀엽게 섞는다.",
    "짧은 영화 예고편처럼 쓴다. 하지만 과장 광고처럼 길어지지 않게 2~3문장으로 끝낸다.",
    "팬미팅 후기처럼 쓴다. 관객은 집사 한 명뿐이어도 당당하게 쓴다.",
    "강아지 쇼핑 목록처럼 쓴다. 필요한 것은 칭찬, 쓰담, 관심 같은 것들로 제한한다.",
    "작은 소문처럼 쓴다. 이야기는 귀엽고 사소해야 한다.",
    "짧은 예능 자막처럼 쓴다. 괄호나 과한 유행어 없이 상황 반전만 살린다.",
    "집사의 마음속 대사를 강아지가 이미 다 안다는 식으로 장난친다.",
    "강아지가 자기 사진을 심사하는 심사위원처럼 말한다.",
    "오늘의 표정을 박물관 전시품처럼 소개한다.",
    "강아지의 머릿속 검색 기록처럼 말하되, 검색어는 한 번만 자연스럽게 넣는다.",
    "집사에게 슬쩍 바라는 걸 말하되, 바라는 것은 칭찬/쓰담/관심 중 하나로 제한한다.",
    "강아지가 집사에게 작은 영수증을 내미는 것처럼 쓴다. 청구 항목은 쓰담, 관심, 한 번 더 보기 중 하나다.",
    "사진 속 표정을 강아지식 뉴스 속보처럼 다루되, 사건은 아주 작고 귀엽게 끝낸다.",
    "집사가 모르는 강아지 내부 규칙이 있는 것처럼 말한다. 규칙은 과하지 않고 한 문장 안에서만 쓴다.",
    "강아지가 오늘의 장면을 자체 시상식처럼 소개한다. 상 이름은 짧고 웃기게 만든다.",
    "강아지와 꼬리가 서로 다른 의견을 낸 것처럼 쓰고, 마지막엔 꼬리가 이긴다.",
]

CAPTION_MICRO_TWISTS = [
    "결론: 집사는 이 장면을 최소 세 번 더 봐야 한다.",
    "꼬리는 이미 이 장면에 만점을 줬다.",
    "내 표정은 집사 눈에 오래 남았을 것 같다.",
    "집사 심장에는 미리 사과한다.",
    "이 정도면 우리 집에서 한 번 더 봐야 하는 장면이다.",
    "발바닥은 오늘도 만족 쪽으로 기울었다.",
    "카메라를 든 집사에게는 작은 칭찬을 준다.",
    "내가 봐도 이 각도는 저장감이다.",
    "오늘의 귀여움 예산은 여기서 다 썼다.",
    "집사는 아직 모르지만, 이건 내 공식 자랑 자료다.",
    "꼬리가 이미 집사에게 재방송을 요청했다.",
    "내 표정 심사위원단은 전원 합격을 줬다.",
    "집사 눈빛이 흔들린 순간, 나는 성공을 직감했다.",
    "이 장면은 내 마음속 앨범 1번 칸에 들어갔다.",
]

CAPTION_FUNNY_ANGLES = [
    "집사를 살짝 놀리는 농담을 한 번만 넣는다.",
    "꼬리, 발바닥, 코끝 중 하나를 의인화해서 짧게 말하게 한다.",
    "강아지만 아는 비밀 규칙처럼 한 문장을 만든다.",
    "귀여운 허세를 아주 작게 넣고 바로 현실적인 감각으로 돌아온다.",
    "집사에게 쓰담, 박수, 한 번 더 보기 중 하나를 장난스럽게 요구한다.",
    "강아지식 시상식, 속보, 판정 중 하나의 느낌을 아주 짧게 섞는다.",
    "활동 메모의 실제 행동을 엉뚱한 사건명처럼 바꾸되 새 장소는 만들지 않는다.",
]

CAPTION_OPENING_BANS = [
    "오늘",
    "나는",
    "사진",
    "산책",
    "기분",
    "집사야",
    "보고",
    "코끝",
]

HASHTAG_BANKS = {
    "산책 리더형": [
        "#집사호출완료",
        "#바깥공기좋아",
        "#꼬리기분좋음",
        "#발바닥기록",
        "#발바닥대장",
        "#문앞에서두근",
        "#동네한바퀴기분",
        "#오늘도앞장섬",
        "#발자국로그",
        "#집사따라와",
        "#꼬리신호ON",
        "#바깥공기수집",
    ],
    "탐험 탐정형": [
        "#냄새단서확보",
        "#현장조사완료",
        "#수상한귀여움",
        "#코탐정출동",
        "#증거는발바닥에",
        "#킁킁파일",
        "#단서수집중",
        "#호기심레이더",
        "#오늘의발견",
        "#미스터리댕",
        "#발바닥수사대",
        "#냄새사건접수",
    ],
    "애교 스트라이커형": [
        "#눈빛공격성공",
        "#쓰담대기중",
        "#꼬리로말해요",
        "#애교탄착완료",
        "#칭찬기다리는중",
        "#눈빛한방",
        "#쓰담예약",
        "#심장공격멍",
        "#귀여움슛",
        "#집사무장해제",
        "#꼬리하트",
        "#애교경기MVP",
    ],
    "집사 껌딱지형": [
        "#집사옆이안전구역",
        "#30센치행복권",
        "#붙어있기전문",
        "#조심조심용기냄",
        "#품속대기중",
        "#옆자리예약",
        "#집사그림자",
        "#붙어야안심",
        "#무릎근처대기",
        "#살짝용기냄",
        "#안전거리제로",
        "#집사충전중",
    ],
    "인정욕구형": [
        "#오늘의주인공",
        "#박수는꼬리로",
        "#포즈값청구",
        "#시선강탈댕",
        "#무대체질",
        "#주목해주세요",
        "#칭찬환영",
        "#포즈천재",
        "#댕댕런웨이",
        "#사진값했다",
        "#집사박수대기",
        "#관심먹고자람",
    ],
    "평화주의 명상형": [
        "#햇볕명상중",
        "#천천히좋아",
        "#마음이포근한날",
        "#고요한꼬리",
        "#작은순간큰평온",
        "#느긋한하루",
        "#햇살저장",
        "#평온수집",
        "#조용한행복",
        "#꼬리도쉬는중",
        "#몽글몽글멍",
        "#오늘은느림표",
    ],
}

FOCUS_HASHTAGS = {
    "간식파": ["#코끝반응", "#기다리는중", "#꼬리두근", "#냠냠상상중", "#맛있는예감", "#간식은나중에"],
    "놀이파": ["#장난감출동", "#한번더놀자", "#발바닥엔진가동", "#공놀이대기", "#놀자신호", "#에너지방출"],
}

GENERAL_HASHTAGS = [
    "#오늘도주인공",
    "#꼬리로그",
    "#댕댕모먼트",
    "#집사야봐줘",
    "#귀여움발견",
    "#멍스타그램",
    "#하루한장",
    "#표정이말함",
    "#발바닥일기",
    "#집사야봤지",
    "#작은사건",
    "#기분좋은날",
    "#댕댕기록",
    "#우리집스타",
    "#꼬리기록",
    "#저장각",
    "#집사심장조심",
    "#표정박물관",
    "#오늘의증거",
    "#귀여움한장",
    "#댕댕일상",
    "#포즈성공",
    "#주인공모먼트",
]

ACTIVITY_HASHTAGS = {
    "공원": ["#공원모먼트", "#풀냄새좋아", "#바람맛집", "#잔디체크", "#햇살냠냠"],
    "사진": ["#사진값했다", "#찰칵성공", "#카메라친구", "#표정천재", "#오늘의컷"],
    "놀이": ["#놀이시간", "#장난감친구", "#한번더모드", "#신남충전", "#발바닥엔진"],
    "공": ["#공놀이대장", "#공따라눈반짝", "#굴러가면출동", "#놀이본능", "#집중력최고"],
    "집": ["#집콕행복", "#소파근처", "#집사옆자리", "#포근한기록", "#우리집평화"],
    "친구": ["#친구만난날", "#꼬리인사", "#반가움폭발", "#사회성충전", "#같이있어좋아"],
    "목욕": ["#뽀송해졌개", "#털결회복", "#향기나는날", "#물방울사건", "#집사수고했어"],
    "잠": ["#낮잠모드", "#꿈속질주", "#포근충전", "#눈꺼풀휴식", "#잠깐쉬어가개"],
    "억울": ["#억울한척장인", "#무죄눈빛", "#집사재판", "#해명필요", "#눈빛증거"],
    "기다": ["#기다림의미학", "#눈빛반짝", "#기대중", "#꼬리대기", "#곧좋은일"],
    "표정": ["#표정박물관", "#얼굴이서사", "#눈빛한컷", "#표정으로말함", "#저장각"],
    "주인공": ["#주인공모먼트", "#포즈값완료", "#오늘의센터", "#시선예약", "#무대체질"],
    "담요": ["#담요속평화", "#포근한기록", "#따뜻한자리", "#몽글타임", "#쉬는중"],
}

OVERUSED_TERMS = ("순찰", "리드줄", "코스", "산책")
OVERUSED_TERM_REPLACEMENTS = {
    "순찰": ["바깥 구경", "새 냄새 확인", "동네 한 바퀴"],
    "리드줄": ["함께 걷는 길", "출발 신호", "문 앞 약속"],
    "코스": ["오늘 길", "발걸음", "우리 길"],
    "산책": ["바깥 구경", "발바닥 시간", "동네 한 바퀴"],
}
OVERUSED_TAG_REPLACEMENTS = {
    "순찰": ["바깥구경", "새냄새확인", "동네한바퀴"],
    "리드줄": ["함께걷는길", "출발신호", "문앞약속"],
    "코스": ["오늘길", "발걸음", "우리길"],
    "산책": ["바깥구경", "발바닥시간", "동네한바퀴"],
}
OVERUSED_TERMS_RE = re.compile("|".join(re.escape(term) for term in OVERUSED_TERMS))
AWKWARD_CAPTION_REPLACEMENTS = {
    "상황 파악 완료": "집사 표정은 이미 읽었어",
    "판단 완료": "알아챘어",
    "작전명": "오늘 표정",
    "현장에서 확인 결과": "내가 보기엔",
    "현장 확인 결과": "내가 보기엔",
    "현장 조사 결과": "내 코 기준으로는",
    "탐정 수사 결과": "내 코 기준으로는",
    "수사 결과": "내 코 기준으로는",
    "수사 완료": "확인 끝",
    "코스 승인": "오늘 길",
    "냄새 지도": "새 냄새",
    "발바닥 컨디션": "발걸음",
    "발바닥 회의": "발바닥 기분",
    "작은 칭찬 타이밍": "쓰담 타이밍",
    "리드줄 담당자": "집사",
    "표정 관리팀": "표정",
    "표정 관리템": "표정",
    "입맛 회의": "맛있는 예감",
    "작전 보고": "오늘 이야기",
    "임무 보고": "오늘 이야기",
    "집사 손": "같이 걷는 길",
    "순찰완료보고": "바깥구경완료",
    "코스승인완료": "오늘길좋음",
    "리드줄담당자소환": "집사같이걷자",
    "냄새지도업데이트": "새냄새좋아",
    "보상협상중": "칭찬기대중",
    "보상 협상": "칭찬 기대",
    "간식 협상": "기분 전환",
}

SNACK_TERMS = ("간식", "보상", "보급", "협상", "한입")
SNACK_TERM_REPLACEMENTS = {
    "간식": "재미",
    "보상": "칭찬",
    "보급": "응원",
    "협상": "기대",
    "한입": "한 번",
}
SNACK_TAG_REPLACEMENTS = {
    "간식": "재미",
    "보상": "칭찬",
    "보급": "응원",
    "협상": "기대",
    "한입": "코끝",
}
SNACK_TERMS_RE = re.compile("|".join(re.escape(term) for term in SNACK_TERMS))

PERSONALITY_FALLBACK_LINES = {
    "장난꾸러기": "얌전한 척했지만 꼬리가 먼저 들킨 건 비밀이다.",
    "차분한": "천천히 확인했더니 마음까지 편안해졌다.",
    "애교많은": "집사야, 이 정도면 쓰담 한 번은 받아도 되지 않을까.",
    "호기심 많은": "새 냄새가 많아서 그냥 지나칠 수 없었다.",
    "용감한": "처음 보는 길도 내가 먼저 씩씩하게 확인했다.",
    "소심한": "조금 낯설었지만 집사 옆이라 괜찮았다.",
    "활발한": "발바닥이 먼저 신나서 출발 신호를 보냈다.",
    "느긋한": "급하지 않게 천천히 즐겨도 충분히 좋은 하루였다.",
    "똑똑한": "집사 표정을 보니 오늘도 꽤 괜찮은 선택이었던 것 같다.",
    "먹보": "맛있는 냄새 생각은 살짝 접어두고, 코 기록부터 남겨야겠다.",
}

WALK_ACTIVITY_KEYWORDS = ("산책", "공원", "바깥", "밖", "외출", "걷", "걸었", "한강", "길", "리드줄")
OUTFIT_ACTIVITY_KEYWORDS = ("옷", "입혔", "입었", "코스튬", "군대", "모자", "목도리", "하네스")
SLEEP_ACTIVITY_KEYWORDS = ("잠", "졸", "자는", "잔다", "피곤", "눈꺼풀")


def is_supported_image_file(image_path):
    if Image is None:
        return True
    try:
        with Image.open(image_path) as image:
            image.verify()
        return True
    except Exception:
        return False


def open_ai_image(image_path):
    image = Image.open(image_path)
    original_size = image.size
    image = image.convert("RGB")
    if max(image.size) > AI_IMAGE_MAX_SIDE:
        image.thumbnail((AI_IMAGE_MAX_SIDE, AI_IMAGE_MAX_SIDE), Image.Resampling.LANCZOS)
    prepared = image.copy()
    image.close()
    if prepared.size != original_size:
        logger.info("AI image resized original=%sx%s prepared=%sx%s", *original_size, *prepared.size)
    return prepared


def _is_observer_caption_line(line):
    banned_fragments = [
        "사진 분위기는",
        "모습입니다",
        "강아지가",
        "고생했어",
        "챙겨받길",
        "바라!",
        "바랍니다",
        "보입니다",
        "있는 모습",
    ]
    return any(fragment in line for fragment in banned_fragments)


def _has_snack_term(text):
    return any(term in text for term in SNACK_TERMS)


def _limit_snack_terms(text, allowed_count=1, tag=False):
    replacements = SNACK_TAG_REPLACEMENTS if tag else SNACK_TERM_REPLACEMENTS
    used = 0

    def replace_match(match):
        nonlocal used
        term = match.group(0)
        if used < allowed_count:
            used += 1
            return term
        return replacements.get(term, "")

    return SNACK_TERMS_RE.sub(replace_match, text), used


def _soften_overused_terms(text, allowed_count=1, tag=False):
    used = 0
    seed = sum(ord(char) for char in str(text or ""))
    replacements_by_term = OVERUSED_TAG_REPLACEMENTS if tag else OVERUSED_TERM_REPLACEMENTS

    def replace_match(match):
        nonlocal used
        term = match.group(0)
        if used < allowed_count:
            used += 1
            return term
        replacements = replacements_by_term[term]
        index = (seed + used + len(term)) % len(replacements)
        used += 1
        return replacements[index]

    return OVERUSED_TERMS_RE.sub(replace_match, str(text or ""))


def _soften_awkward_caption_terms(text):
    value = str(text or "")
    for before, after in AWKWARD_CAPTION_REPLACEMENTS.items():
        value = value.replace(before, after)
        value = value.replace(before.replace(" ", ""), after.replace(" ", ""))
    return value


def _rotate_items(items, seed):
    if not items:
        return []
    start = seed % len(items)
    return items[start:] + items[:start]


def _unique_hashtags(tags, limit=5):
    result = []
    seen = set()
    for tag in tags:
        value = str(tag or "").strip()
        if not value:
            continue
        if not value.startswith("#"):
            value = f"#{value}"
        value = re.sub(r"\s+", "", value)
        match = HASHTAG_RE.match(value)
        if not match:
            continue
        value = match.group(0)
        value = _soften_overused_terms(value, allowed_count=0, tag=True)
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
        if len(result) >= limit:
            break
    return result


def _trim_incomplete_sentence_tail(body):
    value = str(body or "").strip()
    if not value:
        return ""
    if value.endswith((".", "!", "?", "…", "~")):
        return value
    if value.endswith(("다", "요", "멍", "개", "네", "야", "어", "아", "지", "죠", "중", "끝", "완료")):
        return f"{value}."

    comma_index = max(value.rfind(","), value.rfind("，"), value.rfind(";"), value.rfind(":"))
    if comma_index >= 24 and len(value) - comma_index <= 18:
        return f"{value[:comma_index].rstrip()}."

    sentence_index = max(value.rfind("."), value.rfind("!"), value.rfind("?"))
    if sentence_index >= 24 and len(value) - sentence_index <= 36:
        return value[: sentence_index + 1].strip()
    return f"{value}."


def _safe_limit_caption_text(text, max_chars):
    value = str(text or "").strip()
    if len(value) <= max_chars:
        return value

    clipped = value[:max_chars].rstrip()
    sentence_index = max(clipped.rfind("."), clipped.rfind("!"), clipped.rfind("?"))
    if sentence_index >= max_chars * 0.55:
        return clipped[: sentence_index + 1].strip()
    return clipped


def is_caption_too_short(text, min_body_chars=24):
    body = HASHTAG_RE.sub("", normalize_ai_text(text))
    return meaningful_text_length(body, normalize=False) < min_body_chars


def sanitize_caption_text(text, max_body_lines=4, max_chars=520, snack_terms_allowed=True, fallback_hashtags=None):
    cleaned = _soften_awkward_caption_terms(normalize_ai_text(text)).replace("\r", "\n")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()

    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
    if not lines:
        return ""

    hashtag_lines = []
    body_lines = []
    used_snack_terms = 0
    for line in lines:
        if "#" in line:
            hashtag_lines.extend(HASHTAG_RE.findall(line))
            body_candidate = HASHTAG_RE.sub("", line).strip()
            if not body_candidate:
                continue
            line = body_candidate

        if not _is_observer_caption_line(line):
            has_snack = _has_snack_term(line)
            if has_snack and not snack_terms_allowed:
                continue
            if has_snack and used_snack_terms >= 1:
                continue
            if has_snack:
                line, added_count = _limit_snack_terms(line, 1 - used_snack_terms)
                used_snack_terms += added_count
            body_lines.append(line)

    body = "\n".join(body_lines[:max_body_lines]).strip()
    raw_tags = HASHTAG_RE.findall(" ".join(hashtag_lines)) if hashtag_lines else []
    if not raw_tags and fallback_hashtags:
        raw_tags = HASHTAG_RE.findall(_soften_awkward_caption_terms(normalize_ai_text(fallback_hashtags)))
    tags = []
    for tag in raw_tags:
        has_snack = _has_snack_term(tag)
        if has_snack and not snack_terms_allowed:
            continue
        if has_snack and used_snack_terms >= 1:
            continue
        if has_snack:
            tag, added_count = _limit_snack_terms(tag, 1 - used_snack_terms, tag=True)
            used_snack_terms += added_count
        tags.extend(_unique_hashtags([tag], limit=1))
        if len(tags) >= 3:
            break
    hashtags = " ".join(tags)
    body = _soften_overused_terms(body, allowed_count=1)
    body = _trim_incomplete_sentence_tail(body)
    final_text = f"{body}\n{hashtags}".strip() if hashtags else body
    return _safe_limit_caption_text(final_text, max_chars)


def _caption_variation_hint(profile, activity_text=""):
    seed_text = f"{profile.get('pet_name', '')}{profile.get('persona', '')}{activity_text}"
    index = (sum(ord(char) for char in seed_text) + datetime.now().second) % len(CAPTION_VARIATION_STYLES)
    return CAPTION_VARIATION_STYLES[index]


def _caption_creative_device_hint(profile, activity_text=""):
    now = datetime.now()
    seed_text = f"{profile.get('pet_name', '')}{profile.get('persona', '')}{profile.get('personality', '')}{activity_text}"
    seed = sum(ord(char) for char in seed_text) + now.second + (now.microsecond // 100000)
    return CAPTION_CREATIVE_DEVICES[seed % len(CAPTION_CREATIVE_DEVICES)]


def _caption_micro_twist(profile, activity_text=""):
    seed_text = f"{profile.get('pet_name', '')}{profile.get('persona', '')}{activity_text}{datetime.now().strftime('%S%f')}"
    seed = sum(ord(char) for char in seed_text)
    return CAPTION_MICRO_TWISTS[seed % len(CAPTION_MICRO_TWISTS)]


def _caption_funny_angle(profile, activity_text=""):
    seed_text = (
        f"{profile.get('pet_name', '')}{profile.get('persona', '')}"
        f"{profile.get('personality', '')}{activity_text}{datetime.now().strftime('%M%S%f')}"
    )
    seed = sum(ord(char) for char in seed_text)
    return CAPTION_FUNNY_ANGLES[seed % len(CAPTION_FUNNY_ANGLES)]


def _caption_opening_ban_hint(profile, activity_text=""):
    now = datetime.now()
    seed_text = f"{profile.get('pet_name', '')}{activity_text}{now.minute}{now.second}"
    start = sum(ord(char) for char in seed_text) % len(CAPTION_OPENING_BANS)
    picked = CAPTION_OPENING_BANS[start:] + CAPTION_OPENING_BANS[:start]
    return ", ".join(picked[:3])


def _snack_mentions_allowed(profile, activity_text=""):
    persona = profile.get("persona", "")
    personality = profile.get("personality", "")
    if "간식파" not in persona and personality != "먹보":
        return False

    seed_text = f"{profile.get('pet_name', '')}{persona}{personality}{activity_text}{datetime.now().minute}"
    return sum(ord(char) for char in seed_text) % 2 == 0


def _caption_hashtag_hint(profile, activity_text=""):
    persona = profile.get("persona", "")
    seed_text = f"{persona}{profile.get('pet_name', '')}{activity_text}{datetime.now().strftime('%M%S%f')}"
    seed = sum(ord(char) for char in seed_text)
    candidates = []

    for keyword, tags in HASHTAG_BANKS.items():
        if keyword in persona:
            candidates.extend(_rotate_items(tags, seed)[:2])
            break

    snack_allowed = _snack_mentions_allowed(profile, activity_text)
    for keyword, tags in FOCUS_HASHTAGS.items():
        if keyword == "간식파" and not snack_allowed:
            continue
        if keyword in persona:
            candidates.extend(_rotate_items(tags, seed // 3 if seed else seed)[:1])
            break

    activity = str(activity_text or "")
    for index, (keyword, tags) in enumerate(ACTIVITY_HASHTAGS.items(), start=1):
        if keyword in activity:
            candidates.extend(_rotate_items(tags, seed + index * 7)[:1])

    candidates.extend(_rotate_items(GENERAL_HASHTAGS, seed // 5 if seed else seed)[:5])

    if not candidates:
        candidates = GENERAL_HASHTAGS

    return " ".join(_unique_hashtags(candidates, limit=7))


def _dog_activity_text(activity_text):
    activity = clean_single_line_text(activity_text, 160)
    if not activity:
        return "오늘도 내 방식대로 하루를 꼼꼼히 확인했어"

    replacements = [
        ("을했다", "했어"),
        ("를했다", "했어"),
        ("을 했다", "했어"),
        ("를 했다", "했어"),
        ("했다", "했어"),
        ("하였다", "했어"),
    ]
    result = activity
    for before, after in replacements:
        result = result.replace(before, after)
    return result


def _activity_has_any(activity_text, keywords):
    activity = str(activity_text or "")
    return any(keyword in activity for keyword in keywords)


def _fallback_activity_reaction(activity_text):
    if _activity_has_any(activity_text, OUTFIT_ACTIVITY_KEYWORDS):
        return "집사는 이걸 패션이라고 불렀고, 나는 일단 표정으로 심사했다."
    if _activity_has_any(activity_text, SLEEP_ACTIVITY_KEYWORDS):
        return "눈꺼풀은 쉬자고 했지만, 귀여움 근무는 아직 끝나지 않았다."
    return "내 방식대로 확인해보니 이 장면도 꽤 그럴듯했다."


def _fallback_body_line(profile, activity_text):
    persona = profile.get("persona", "")
    personality = profile.get("personality", "")
    activity = _dog_activity_text(activity_text)
    personality_line = PERSONALITY_FALLBACK_LINES.get(personality, "내 꼬리 기준으로는 꽤 괜찮은 기록이다.")
    snack_allowed = _snack_mentions_allowed(profile, activity_text)

    if "산책 리더형" in persona:
        ending = (
            "집사는 쓰담 타이밍만 놓치지 않으면 된다개 🐾"
            if snack_allowed
            else "집사는 내 꼬리 리듬에 맞춰 천천히 따라오라개 🐾"
        )
        if not _activity_has_any(activity_text, WALK_ACTIVITY_KEYWORDS):
            return f"{activity}. {_fallback_activity_reaction(activity_text)} {ending} {personality_line}"
        return (
            f"{activity}. 바깥 냄새도 좋고 발걸음도 가벼웠으니, "
            f"{ending} {personality_line}"
        )
    if "탐험 탐정형" in persona:
        return (
            f"{activity}. 내 코 기준으로는 오늘도 수상하게 좋은 냄새 단서가 많았다 🔎 "
            f"{personality_line}"
        )
    if "애교 스트라이커형" in persona:
        return (
            f"{activity}. 눈빛이랑 꼬리까지 총동원했으니, "
            f"쓰담 담당자는 슬쩍 다가와도 좋다개 🥺 {personality_line}"
        )
    if "집사 껌딱지형" in persona:
        return (
            f"{activity}. 집사 옆에서 확인하니까 마음이 더 안정됐다멍 🐾 "
            f"{personality_line}"
        )
    if "인정욕구형" in persona:
        ending = (
            "칭찬 담당자는 박수 한 번 크게 준비해도 좋다개 ✨"
            if not snack_allowed
            else "칭찬 담당자는 작은 한입까지는 생각해도 좋다개 ✨"
        )
        return (
            f"{activity}. 오늘의 주인공 포즈는 준비됐으니, "
            f"{ending} {personality_line}"
        )
    if "평화주의 명상형" in persona:
        return (
            f"{activity}. 바람이랑 햇볕을 천천히 확인했더니 마음이 포근해졌다 🍃 "
            f"{personality_line}"
        )

    return f"{activity}. {personality_line} 🐾"


def make_fallback_caption(profile, activity_text=""):
    # Fallback must still sound like the dog, never like an image captioner.
    body = _soften_awkward_caption_terms(
        _soften_overused_terms(_fallback_body_line(profile, activity_text), allowed_count=1)
    )
    twist = _caption_micro_twist(profile, activity_text)
    if twist and twist not in body and len(body) < 260:
        body = f"{body} {twist}"
    funny_angle = _caption_funny_angle(profile, activity_text)
    if "쓰담" in funny_angle and "쓰담" not in body and len(body) < 280:
        body = f"{body} 집사는 쓰담 담당으로 잠깐 대기해도 좋다개."
    elif "꼬리" in funny_angle and "꼬리" not in body and len(body) < 280:
        body = f"{body} 꼬리는 벌써 합격이라고 흔들렸다."
    hashtags = " ".join(_caption_hashtag_hint(profile, activity_text).split()[:3])
    return f"{body}\n{hashtags}"


def generate_caption(image_path, profile, activity_text="", analysis=None):
    analysis = analysis or {}
    activity_text = clean_multi_line_text(activity_text, 320)
    if not client:
        logger.warning("Gemini caption fallback reason=missing_client_or_api_key")
        return escape(make_fallback_caption(profile, activity_text)).replace("\n", "<br>")
    if Image is None:
        logger.warning("Gemini caption fallback reason=pillow_unavailable")
        return escape(make_fallback_caption(profile, activity_text)).replace("\n", "<br>")

    owner_note = clean_single_line_text(profile.get("owner_persona_note") or "없음", 180)
    persona_rule = build_caption_persona_prompt_text(profile.get("persona", ""), profile.get("personality", ""))
    variation_hint = _caption_variation_hint(profile, activity_text)
    creative_device = _caption_creative_device_hint(profile, activity_text)
    micro_twist = _caption_micro_twist(profile, activity_text)
    funny_angle = _caption_funny_angle(profile, activity_text)
    opening_bans = _caption_opening_ban_hint(profile, activity_text)
    snack_allowed = _snack_mentions_allowed(profile, activity_text)
    hashtag_hint = _caption_hashtag_hint(profile, activity_text)
    snack_guidance = (
        "이번 캡션에서는 간식/칭찬/기대 표현을 최대 1번만 짧게 써라."
        if snack_allowed
        else "이번 캡션에서는 간식 이야기를 쓰지 말고, 냄새/발걸음/표정/꼬리/집사 반응으로 재미를 만들어라."
    )
    creative_seed = datetime.now().strftime("%M%S%f")
    prompt = f"""
너는 반려견 SNS 'Zoo-In-Gong'의 캡션 작가다. 결과만 한국어 캡션으로 출력한다.

출력 형식:
- 강아지 1인칭 본문 2~3문장 + 해시태그 2개.
- 본문은 240자 이내로 짧게 끝낸다.
- 마지막 본문 문장은 반드시 완성된 문장으로 끝낸다. 단어 중간, "집", "내", "그리고" 같은 조각으로 끝내지 않는다.
- 제목, 설명, 번호, 따옴표 없이 캡션만 쓴다.
- 사진 설명문처럼 쓰지 말고, 강아지가 직접 느낀 감각/착각/작은 사건처럼 쓴다.
- 활동 메모를 최우선으로 반영하고, 없는 장소/사건/물건은 새로 만들지 않는다.
- 첫 문장은 {opening_bans}로 시작하지 않는다.
- 같은 요청을 여러 번 받아도 오프닝, 비유, 해시태그를 매번 다르게 고른다.
- "순찰", "산책", "리드줄", "코스" 같은 표현은 합쳐서 최대 1번만 쓴다. 대신 바깥 구경, 동네 한 바퀴, 함께 걷는 길, 발걸음, 꼬리 리듬처럼 자연스럽게 바꿔 쓴다.
- "작전", "회의", "보고서", "상황 파악 완료", "냄새 지도", "발바닥 컨디션", "관리팀"처럼 딱딱하거나 이상한 표현은 쓰지 않는다.
- 반복되는 군대식 보고 말투보다 엉뚱한 오해, 작은 허세, 집사에게 하는 농담, 꼬리/표정/발걸음 반응을 더 많이 쓴다.
- 평범한 감탄문으로 끝내지 말고, 강아지식 오해나 짧은 반전이 한 번은 느껴지게 쓴다.
- 재미 장치는 한 가지로만 제한한다. 웃기려고 활동 메모에 없는 장소, 물건, 사건을 만들지 않는다.
- 해시태그는 후보에서 2개만 고르되, 매번 같은 조합을 반복하지 말고 페르소나 태그 1개 + 상황/감정 태그 1개처럼 섞는다.
- 해시태그에는 띄어쓰기와 긴 문장을 넣지 않는다.

이번 캡션의 창의성 방향:
- 스타일: {variation_hint}
- 장난스러운 장치: {creative_device}
- 미니 반전: {micro_twist}
- 재미 각도: {funny_angle}
- 다양성 seed: {creative_seed}
- 간식 표현 규칙: {snack_guidance}

활동 메모:
{activity_text or "특별한 활동 메모 없음"}

사진 참고:
{analysis.get('scene') or '강아지 일상 사진'}.
사진은 분위기 참고용이며, 보이는 것만 살짝 반영한다.

강아지 정보:
- 이름: {profile['pet_name']}
- 견종: {profile['pet_species']}
- 나이: {profile['pet_age']}
- 페르소나: {profile['persona']}
- 좋아하는 것: {profile['pet_likes']}
- 싫어하는 것: {profile['pet_dislikes']}
- 집사 메모: {owner_note}

말투 압축 규칙:
{persona_rule}

해시태그 후보:
{hashtag_hint}
""".strip()

    try:
        with open_ai_image(image_path) as image:
            response = generate_gemini_content(
                [prompt, image],
                system_instruction=CAPTION_SYSTEM_INSTRUCTION,
                use_search=False,
                temperature=1.14,
                top_p=0.98,
                max_output_tokens=390,
            )

        raw_text = (response.text or "").strip()
        has_detailed_activity = len(activity_text.splitlines()) >= 2 or len(activity_text) >= 90
        caption_text = sanitize_caption_text(
            raw_text,
            max_body_lines=6 if has_detailed_activity else 4,
            max_chars=780 if has_detailed_activity else 580,
            snack_terms_allowed=snack_allowed,
            fallback_hashtags=hashtag_hint,
        )
        if not caption_text or is_caption_too_short(caption_text):
            logger.warning(
                "Gemini caption fallback reason=empty_or_short_response raw_chars=%s sanitized_chars=%s",
                len(raw_text),
                len(caption_text or ""),
            )
            caption_text = make_fallback_caption(profile, activity_text)

        return escape(caption_text).replace("\n", "<br>")
    except Exception as error:
        logger.exception("Gemini caption generation failed error=%s", type(error).__name__)
        return escape(make_fallback_caption(profile, activity_text)).replace("\n", "<br>")
