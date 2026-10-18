from services.optimizer import decide_action


def test_clicks_mean_winner():
    assert decide_action(5, 2, 4, None) == "winner"


def test_stale_views_mean_revive():
    assert decide_action(5, 0, 4, None) == "revive"


def test_dead_page_means_kill():
    assert decide_action(12, 0, 8, None) == "kill"


def test_revived_then_dead_means_kill():
    assert decide_action(12, 0, 8, "revived") == "kill"


def test_too_young_to_judge():
    assert decide_action(5, 0, 1, None) is None


def test_flagged_winner_left_alone():
    assert decide_action(5, 2, 9, "winner") is None