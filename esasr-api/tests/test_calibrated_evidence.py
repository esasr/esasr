from services.calibrated_evidence import calibrated_base_score, egrr_decision


def test_calibrated_base_score_is_bounded():
    score = calibrated_base_score(0.1, 0.2, 0.3)
    assert 0.0 <= score <= 1.0


def test_egrr_decision_exposes_features_and_threshold():
    decision = egrr_decision({"retrieval", "evidence"}, [{"retrieval"}])
    assert isinstance(decision["route"], bool)
    assert isinstance(decision["predictedMarginalGain"], float)
    assert decision["threshold"] > 0
    assert set(decision["features"]) == {
        "normalizedQueryLength",
        "bestTop10Coverage",
        "meanTop10Coverage",
        "top20Uniqueness",
    }
