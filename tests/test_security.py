from core.security import verify_password


def test_correct_password_accepted():
    assert verify_password("BlueCoffee42", "BlueCoffee42") is True


def test_wrong_password_rejected():
    assert verify_password("wrong-password", "BlueCoffee42") is False


def test_non_text_rejected():
    assert verify_password(None, "BlueCoffee42") is False