from datetime import datetime


DAILY_MISSIONS = [
    {
        "key": "tail-moment",
        "title": "꼬리가 먼저 말한 순간",
        "prompt": "꼬리가 먼저 반응했던 순간을 찍었어요. 어떤 표정이었는지 같이 적어주세요.",
        "helper": "반가움, 기대, 신남처럼 표정이 보이는 사진에 잘 맞아요.",
        "icon": "fa-solid fa-heart",
        "angles": ["눈빛 먼저", "꼬리 증거", "집사 반응"],
    },
    {
        "key": "best-spot",
        "title": "오늘의 최애 자리",
        "prompt": "오늘 가장 마음에 들었던 자리에서 쉬거나 놀았어요. 왜 그 자리가 좋았는지 적어주세요.",
        "helper": "소파, 창가, 공원 벤치, 집사 옆자리 모두 좋아요.",
        "icon": "fa-solid fa-location-dot",
        "angles": ["자리 자랑", "햇살 점수", "편안함 인증"],
    },
    {
        "key": "tiny-brag",
        "title": "작은 자랑 하나",
        "prompt": "오늘 잘한 일을 하나 자랑하고 싶어요. 기다리기, 앉기, 예쁜 표정 같은 작은 성공을 적어주세요.",
        "helper": "훈련 성공이나 귀여운 포즈를 올릴 때 좋아요.",
        "icon": "fa-solid fa-star",
        "angles": ["칭찬 대기", "성공 인증", "표정 점수"],
    },
    {
        "key": "sniff-report",
        "title": "코끝 리포트",
        "prompt": "오늘 코끝이 제일 바빴던 순간을 기록했어요. 어떤 냄새나 장면이 궁금했는지 적어주세요.",
        "helper": "킁킁 탐색, 새 장소, 낯선 물건 사진에 잘 맞아요.",
        "icon": "fa-solid fa-magnifying-glass",
        "angles": ["단서 발견", "수상한 물건", "코끝 뉴스"],
    },
    {
        "key": "play-scene",
        "title": "놀이 하이라이트",
        "prompt": "오늘 제일 신났던 놀이 순간이에요. 장난감, 공, 달리기 중 무엇이 좋았는지 적어주세요.",
        "helper": "움직임이 있거나 신난 표정의 사진에 잘 맞아요.",
        "icon": "fa-solid fa-baseball",
        "angles": ["MVP 장면", "한 번 더", "장난감 주연"],
    },
    {
        "key": "with-human",
        "title": "집사랑 한 컷",
        "prompt": "집사랑 같이 보낸 순간을 올려요. 집사가 오늘 어떤 역할을 했는지 귀엽게 적어주세요.",
        "helper": "손, 발, 그림자, 같이 있는 분위기만 보여도 충분해요.",
        "icon": "fa-solid fa-hand-holding-heart",
        "angles": ["집사 평가", "옆자리 인증", "둘만의 순간"],
    },
    {
        "key": "sleepy-peace",
        "title": "몽글몽글 휴식",
        "prompt": "오늘 가장 포근했던 쉬는 시간을 남겨요. 어디서 어떻게 쉬었는지 적어주세요.",
        "helper": "낮잠, 햇볕, 담요, 조용한 표정에 잘 맞아요.",
        "icon": "fa-solid fa-cloud",
        "angles": ["낮잠 증거", "담요 보고", "느긋한 표정"],
    },
    {
        "key": "guilty-face",
        "title": "억울한 척 챌린지",
        "prompt": "오늘 가장 억울하거나 아무 잘못 없는 척한 표정을 찍었어요. 무슨 일이 있었는지 적어주세요.",
        "helper": "눈썹, 입꼬리, 고개 각도가 살아 있는 사진이면 반응이 좋아요.",
        "icon": "fa-regular fa-face-meh",
        "angles": ["무죄 주장", "눈빛 해명", "집사 재판"],
    },
    {
        "key": "snack-stare",
        "title": "기대 눈빛 한 컷",
        "prompt": "무언가를 기다리는 눈빛을 남겼어요. 무엇을 기대했는지 강아지 입장에서 적어주세요.",
        "helper": "밥그릇, 손, 식탁 아래, 문 앞에서 찍은 사진에 잘 맞아요.",
        "icon": "fa-solid fa-cookie-bite",
        "angles": ["눈빛 협상", "기다림 인증", "한입 상상"],
    },
    {
        "key": "before-after",
        "title": "전후 사정 있는 사진",
        "prompt": "이 사진 전후에 무슨 일이 있었는지 짧게 적어주세요. 사진만 봐도 궁금해지는 순간이면 좋아요.",
        "helper": "비포/애프터가 떠오르는 장면은 댓글을 부르기 좋아요.",
        "icon": "fa-solid fa-wand-magic-sparkles",
        "angles": ["사건 전말", "3초 전", "다음 장면"],
    },
    {
        "key": "main-character",
        "title": "오늘의 주인공 포즈",
        "prompt": "오늘 우리 강아지가 주인공처럼 보였던 순간을 올려요. 어떤 포인트가 제일 빛났는지 적어주세요.",
        "helper": "정면샷, 옆모습, 당당한 자세처럼 한눈에 캐릭터가 보이는 사진에 잘 맞아요.",
        "icon": "fa-solid fa-crown",
        "angles": ["무대 등장", "포즈값 완료", "시선 강탈"],
    },
    {
        "key": "weird-sleep",
        "title": "수상한 자세 박물관",
        "prompt": "오늘 이상하지만 귀여운 자세를 발견했어요. 왜 그렇게 있었는지 상상해서 적어주세요.",
        "helper": "잠자는 자세, 삐딱한 자세, 엉뚱한 각도 사진이 잘 어울려요.",
        "icon": "fa-solid fa-puzzle-piece",
        "angles": ["자세 해석", "편안함 논란", "수면 과학"],
    },
]


def build_daily_mission(profile, today=None):
    today = today or datetime.now().date()
    seed_text = f"{today.isoformat()}:{profile.get('username', '')}:{profile.get('persona', '')}"
    seed = sum(ord(char) for char in seed_text)
    mission = dict(DAILY_MISSIONS[seed % len(DAILY_MISSIONS)])

    persona = profile.get("persona", "")
    if "간식파" in persona:
        mission["helper"] = f"{mission['helper']} 칭찬이나 작은 기대감을 살짝 섞어도 좋아요."
        mission["angles"] = ["기대 눈빛", "한입 협상", *(mission.get("angles") or [])]
    elif "놀이파" in persona:
        mission["helper"] = f"{mission['helper']} 신난 에너지를 한 문장 더해보세요."
        mission["angles"] = ["한 번 더", "장난감 주연", *(mission.get("angles") or [])]
    elif "평화주의" in persona:
        mission["helper"] = f"{mission['helper']} 느긋하고 포근한 느낌을 살려보세요."
        mission["angles"] = ["느긋한 표정", "햇살 저장", *(mission.get("angles") or [])]

    mission["angles"] = list(dict.fromkeys(mission.get("angles") or []))[:4]
    mission["date_label"] = today.strftime("%m.%d")
    mission["cta"] = "이 미션으로 쓰기"
    return mission
