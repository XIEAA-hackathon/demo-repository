from app.core.security import (
    get_password_hash,
    is_bcrypt_password_hash,
    is_sha256_password_hash,
    verify_password,
)


def test_sha256_password_hash_has_expected_format_and_verifies():
    stored = get_password_hash("Correct Horse Battery Staple")

    assert stored.startswith("sha256$")
    assert is_sha256_password_hash(stored)
    assert verify_password("Correct Horse Battery Staple", stored)


def test_sha256_password_verification_rejects_wrong_or_malformed_values():
    stored = get_password_hash("right-password")

    assert not verify_password("wrong-password", stored)
    assert not verify_password("right-password", "sha256$missing-fields")
    assert not verify_password("right-password", "$2b$12$legacybcryptisnotaccepted00000000000000000000000000000")
    assert not verify_password("right-password", "$2x$12$legacybcryptisnotaccepted00000000000000000000000000000")
    assert not verify_password("right-password", "$2$12$legacybcryptisnotaccepted000000000000000000000000000000")


def test_same_password_uses_different_random_salts():
    first = get_password_hash("same-password")
    second = get_password_hash("same-password")

    assert first != second
    assert first.split("$", 2)[1] != second.split("$", 2)[1]
    assert verify_password("same-password", first)
    assert verify_password("same-password", second)


def test_all_known_bcrypt_prefixes_are_detected_for_reset_verification():
    for prefix in ("$2$", "$2a$", "$2b$", "$2x$", "$2y$"):
        assert is_bcrypt_password_hash(f"{prefix}legacy-value")

    assert not is_bcrypt_password_hash("sha256$legacy-value")
