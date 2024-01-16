def is_at_least_8_chars(val: str) -> str:
    assert len(val) >= 8, "Password must be at least 8 characters"
    return val


def has_uppercase(val: str) -> str:
    assert any(
        ch.isupper() for ch in val
    ), "Password must have at least one uppercase character"
    return val


def has_lowercase(val: str) -> str:
    assert any(
        ch.islower() for ch in val
    ), "Password must have at least one lowercase character"
    return val


def has_one_digit(val: str) -> str:
    assert any(ch.isdigit() for ch in val), "Password must have at least one digit"
    return val
