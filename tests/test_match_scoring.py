from persona import persona_defaults
from services import add_match_info


def profile(**overrides):
    data = {
        "pet_name": "테스트",
        "pet_species": "푸들",
        "pet_age": 3,
        "activity_level": "보통",
        "pet_likes": "산책 공놀이",
        "pet_dislikes": "큰 소리",
        "favorite_place": "동네 공원",
        "persona": "산책 리더형 놀이파",
        **persona_defaults(),
    }
    data.update(overrides)
    return data


def test_identical_profiles_receive_a_high_match_score():
    viewer = profile()
    target = profile(pet_name="친구")

    add_match_info(viewer, target)

    assert target["match_score"] >= 90
    assert target["match_label"] == "찰떡 멍친구"
    assert "조합" in target["match_summary"]


def test_opposite_routines_and_activity_levels_lower_the_score():
    viewer = profile(
        activity_level="높음",
        persona_energy="outdoor",
        persona_social="social",
        persona_curiosity="explorer",
        persona_reaction="brave",
        persona_routine="free",
        persona_cuddle="independent",
    )
    target = profile(
        pet_name="친구",
        pet_species="진돗개",
        pet_age=11,
        activity_level="낮음",
        pet_likes="낮잠 담요",
        pet_dislikes="물",
        favorite_place="집",
        persona_energy="indoor",
        persona_social="selective",
        persona_curiosity="steady",
        persona_reaction="cautious",
        persona_routine="routine",
        persona_cuddle="cuddly",
    )

    add_match_info(viewer, target)

    assert target["match_score"] < 65
    assert target["match_label"] in {"천천히 친해질 친구", "새로 알아갈 친구"}


def test_complementary_traits_get_partial_credit_and_reason():
    viewer = profile(persona_social="social", persona_expression="affectionate")
    target = profile(
        pet_name="친구",
        persona_social="selective",
        persona_expression="cool",
    )

    add_match_info(viewer, target)

    assert target["match_score"] >= 70
    assert any("마음을 열어요" in reason or "애정 표현" in reason for reason in target["match_reasons"])


def test_shared_interests_improve_match_score():
    viewer = profile(pet_likes="산책 공놀이")
    shared = profile(pet_name="공통", pet_likes="산책 공놀이")
    different = profile(pet_name="다름", pet_likes="낮잠 담요")

    add_match_info(viewer, shared)
    add_match_info(viewer, different)

    assert shared["match_score"] > different["match_score"]
    assert any("같이 좋아해요" in reason for reason in shared["match_reasons"])
