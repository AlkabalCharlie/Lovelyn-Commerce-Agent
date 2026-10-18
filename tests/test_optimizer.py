from services.optimizer import decide_action


def test_clicks_mean_winner():
    assert decide_action(5, 2, 4, None) == "winner"


def test_stale_views_mean_revive():
    assert decide_action(5, 0, 4, None) == "revive"


def test_too_young_to_judge():
    assert decide_action(5, 0, 1, None) is None


def test_flagged_campaigns_left_alone():
    assert decide_action(5, 0, 9, "revived") is None