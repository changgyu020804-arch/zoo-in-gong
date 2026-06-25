from persona import PERSONA_QUESTIONS, derive_persona_details, score_persona_answers


def answers(*values):
    return {
        question["key"]: value
        for question, value in zip(PERSONA_QUESTIONS, values)
    }


def persona_for(source):
    stored, _base_scores, _focus_scores, answered = score_persona_answers(source)
    profile = {
        "pet_name": "테스트",
        "owner_persona_note": "",
        **stored,
    }
    return derive_persona_details(profile)["persona"], answered


def test_questionnaire_has_twelve_questions_with_three_or_four_choices():
    assert len(PERSONA_QUESTIONS) == 12
    assert all(3 <= len(question["options"]) <= 4 for question in PERSONA_QUESTIONS)


def test_active_social_play_answers_create_leader_play_persona():
    source = answers(
        "lead",
        "greet",
        "walk",
        "join",
        "inspect_camera",
        "enjoy_change",
        "check_sound",
        "window",
        "start_game",
        "lead_group",
        "choose_toy",
        "active_reward",
    )

    assert persona_for(source) == ("산책 리더형 놀이파", 12)


def test_affectionate_attention_answers_create_striker_persona():
    source = answers(
        "check_owner",
        "play_invite",
        "people",
        "join",
        "approach",
        "follow_owner",
        "call_owner",
        "owner_lap",
        "play_together",
        "make_friends",
        "choose_toy",
        "active_reward",
    )

    assert persona_for(source) == ("애교 스트라이커형 놀이파", 12)


def test_camera_and_praise_answers_create_recognition_persona():
    source = answers(
        "lead",
        "greet",
        "people",
        "appeal",
        "pose",
        "enjoy_change",
        "check_sound",
        "center",
        "show_toy",
        "enjoy_attention",
        "choose_snack",
        "praise_reward",
    )

    assert persona_for(source) == ("시선강탈 스타형 간식파", 12)


def test_calm_routine_answers_create_zen_persona():
    source = answers(
        "stay_route",
        "owner_side",
        "rest",
        "wait",
        "natural",
        "prefer_plan",
        "ignore_sound",
        "quiet_corner",
        "study_toy",
        "stay_calm",
        "choose_snack",
        "food_reward",
    )

    assert persona_for(source) == ("평화주의 명상형 간식파", 12)
