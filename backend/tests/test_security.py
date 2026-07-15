"""Unit tests for the security primitives.

These test the pure functions in isolation. The end-to-end attacks live in
scripts/security_check.py, which runs against a live server.
"""

import time
import uuid

import pytest

from app.security import (
    create_access_token,
    decode_access_token,
    decrypt_text,
    encrypt_text,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    sign_media_cookie,
    sign_media_token,
    verify_media_cookie,
    verify_media_token,
    verify_password,
)


class TestPasswordHashing:
    def test_roundtrip(self):
        h = hash_password("correct-horse-battery-staple-9")
        assert verify_password("correct-horse-battery-staple-9", h)

    def test_wrong_password_rejected(self):
        h = hash_password("correct-horse-battery-staple-9")
        assert not verify_password("Correct-horse-battery-staple-9", h)
        assert not verify_password("", h)

    def test_hash_is_salted(self):
        """Same password, two hashes: identical hashes would mean no salt, which
        makes rainbow tables viable."""
        a = hash_password("same-password-123")
        b = hash_password("same-password-123")
        assert a != b
        assert verify_password("same-password-123", a)
        assert verify_password("same-password-123", b)

    def test_uses_argon2id(self):
        assert hash_password("whatever-123").startswith("$argon2id$")

    def test_malformed_hash_does_not_raise(self):
        """A corrupted DB row must fail closed, not 500."""
        assert not verify_password("anything", "not-a-real-hash")
        assert not verify_password("anything", "")


class TestAccessTokens:
    def test_roundtrip(self):
        user_id, session_id = uuid.uuid4(), uuid.uuid4()
        token, expires_in = create_access_token(user_id, session_id)
        payload = decode_access_token(token)

        assert payload is not None
        assert payload["sub"] == str(user_id)
        assert payload["sid"] == str(session_id)
        assert payload["type"] == "access"
        assert expires_in > 0

    def test_tampered_token_rejected(self):
        token, _ = create_access_token(uuid.uuid4(), uuid.uuid4())
        head, payload, sig = token.split(".")
        assert decode_access_token(f"{head}.{payload}.{sig[:-4]}xxxx") is None

    def test_garbage_rejected(self):
        for bad in ["", "not.a.token", "a.b.c", "Bearer x"]:
            assert decode_access_token(bad) is None

    def test_expired_token_rejected(self, monkeypatch):
        from app import security

        monkeypatch.setattr(security.settings, "access_token_ttl_minutes", -1)
        token, _ = create_access_token(uuid.uuid4(), uuid.uuid4())
        assert decode_access_token(token) is None

    def test_each_token_unique(self):
        """A repeated jti would make replay detection impossible."""
        uid, sid = uuid.uuid4(), uuid.uuid4()
        a, _ = create_access_token(uid, sid)
        b, _ = create_access_token(uid, sid)
        assert decode_access_token(a)["jti"] != decode_access_token(b)["jti"]


class TestRefreshTokens:
    def test_tokens_are_unique_and_long(self):
        tokens = {generate_refresh_token() for _ in range(200)}
        assert len(tokens) == 200
        assert all(len(t) >= 40 for t in tokens)

    def test_hash_is_deterministic(self):
        t = generate_refresh_token()
        assert hash_refresh_token(t) == hash_refresh_token(t)

    def test_different_tokens_differ(self):
        assert hash_refresh_token(generate_refresh_token()) != hash_refresh_token(generate_refresh_token())


class TestEncryption:
    def test_roundtrip(self):
        text = "Rahul said the API slips to Monday."
        assert decrypt_text(encrypt_text(text)) == text

    def test_ciphertext_does_not_leak_plaintext(self):
        secret = "acquisition price is 40 crore"
        blob = encrypt_text(secret)
        assert secret not in blob
        assert "acquisition" not in blob

    def test_nondeterministic(self):
        """Identical plaintext must produce different ciphertext, or an observer
        can tell that two meetings said the same thing."""
        assert encrypt_text("same text") != encrypt_text("same text")

    def test_tampered_ciphertext_rejected(self):
        blob = encrypt_text("important")
        with pytest.raises(ValueError):
            decrypt_text(blob[:-6] + "AAAAAA")

    def test_unicode_and_empty(self):
        for text in ["", "मीटिंग कल है", "emoji 🎙️ ok", "a" * 10_000]:
            assert decrypt_text(encrypt_text(text)) == text


class TestMediaTokens:
    def test_valid_token_accepted(self):
        m, u = uuid.uuid4(), uuid.uuid4()
        assert verify_media_token(sign_media_token(m, u), m, u)

    def test_token_bound_to_meeting(self):
        m, other, u = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        token = sign_media_token(m, u)
        assert not verify_media_token(token, other, u)

    def test_token_bound_to_owner(self):
        m, u, other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        token = sign_media_token(m, u)
        assert not verify_media_token(token, m, other)

    def test_expired_token_rejected(self):
        m, u = uuid.uuid4(), uuid.uuid4()
        assert not verify_media_token(sign_media_token(m, u, ttl_seconds=-1), m, u)

    def test_forged_signature_rejected(self):
        m, u = uuid.uuid4(), uuid.uuid4()
        expires = int(time.time()) + 300
        assert not verify_media_token(f"{expires}.deadbeef", m, u)

    def test_malformed_rejected(self):
        m, u = uuid.uuid4(), uuid.uuid4()
        for bad in ["", "nodot", "abc.def", "...", "999"]:
            assert not verify_media_token(bad, m, u)


class TestMediaCookie:
    def test_roundtrip(self):
        u = uuid.uuid4()
        assert verify_media_cookie(sign_media_cookie(u)) == u

    def test_expired_rejected(self):
        assert verify_media_cookie(sign_media_cookie(uuid.uuid4(), ttl_seconds=-1)) is None

    def test_tampered_user_rejected(self):
        """Swapping the user id in the cookie must invalidate the signature -
        otherwise anyone could impersonate any owner for media access."""
        u, attacker = uuid.uuid4(), uuid.uuid4()
        cookie = sign_media_cookie(u)
        _, expires, sig = cookie.split(".", 2)
        assert verify_media_cookie(f"{attacker}.{expires}.{sig}") is None

    def test_garbage_rejected(self):
        for bad in [None, "", "x", "a.b.c", "not-a-uuid.123.abc"]:
            assert verify_media_cookie(bad) is None
