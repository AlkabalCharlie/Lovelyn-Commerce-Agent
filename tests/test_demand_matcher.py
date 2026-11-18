from services.demand_matcher import score_demand


def test_matches_relevant_approved_product():
    products = [{
        "id": "debt-1",
        "name": "Be Free from Debt",
        "description": (
            "A practical guide to debt repayment, budgeting, "
            "managing multiple debts and financial planning."
        ),
        "status": "approved",
    }]

    result = score_demand(
        "How can I manage multiple debts?",
        "I need a practical debt repayment plan and budgeting help.",
        products,
    )

    assert result["matched_product_id"] == "debt-1"
    assert result["qualified"] is True
    assert result["relevance_score"] > 0
    assert result["intent_score"] > 0


def test_rejects_unapproved_product():
    products = [{
        "id": "debt-1",
        "name": "Be Free from Debt",
        "description": "Debt repayment and budgeting guide.",
        "status": "rejected",
    }]

    result = score_demand(
        "How do I repay my debt?",
        "I need a debt repayment plan.",
        products,
    )

    assert result["matched_product_id"] is None
    assert result["qualified"] is False


def test_does_not_match_unrelated_product():
    products = [{
        "id": "game-1",
        "name": "HTML5 Games",
        "description": "Browser games and HTML5 game bundle.",
        "status": "approved",
    }]

    result = score_demand(
        "How can I reduce my monthly debt payments?",
        "I need help with budgeting and repayment.",
        products,
    )

    assert result["matched_product_id"] is None
    assert result["qualified"] is False


def test_purchase_intent_scores_higher_than_general_question():
    products = [{
        "id": "debt-1",
        "name": "Be Free from Debt",
        "description": "Debt repayment and budgeting guide.",
        "status": "approved",
    }]

    general = score_demand(
        "How do I manage debt?",
        "I need help with debt repayment and budgeting.",
        products,
    )

    buyer = score_demand(
        "Where can I buy a debt repayment guide?",
        "I need a practical budgeting and debt repayment guide.",
        products,
    )

    assert buyer["intent_score"] > general["intent_score"]


def test_empty_post_is_not_qualified():
    result = score_demand("", "", [])

    assert result["qualified"] is False
    assert result["matched_product_id"] is None