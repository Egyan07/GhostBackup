"""
tests/test_crypto.py — Unit tests for the _CryptoHelper encryption helper

Run with:  pytest backend/tests/test_crypto.py -v
"""

import pytest

from syncer import _CryptoHelper


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def valid_key():
    """A real Fernet key generated once per session."""
    from cryptography.fernet import Fernet
    return Fernet.generate_key()


@pytest.fixture
def crypto(valid_key):
    return _CryptoHelper(valid_key)


@pytest.fixture
def no_crypto():
    """CryptoHelper with no key — no-op mode."""
    return _CryptoHelper(None)


# ── enabled flag ──────────────────────────────────────────────────────────────

class TestCryptoEnabled:
    def test_enabled_with_valid_key(self, crypto):
        assert crypto.enabled is True

    def test_disabled_without_key(self, no_crypto):
        assert no_crypto.enabled is False

    def test_invalid_key_disables_encryption(self):
        # A non-Fernet key should silently disable rather than raise
        helper = _CryptoHelper(b"not-a-valid-fernet-key")
        assert helper.enabled is False


# ── encrypt_chunks / decrypt_to round-trip ────────────────────────────────────

class TestRoundTrip:
    def test_encrypt_then_decrypt_restores_plaintext(self, crypto, tmp_path):
        plaintext = b"Hello, Red Parrot Accounting! Invoice #1234."
        src = tmp_path / "invoice.xlsx"
        src.write_bytes(plaintext)
        dst_enc = tmp_path / "invoice.xlsx.enc"
        dst_dec = tmp_path / "invoice.xlsx.dec"

        crypto.encrypt_chunks(src, dst_enc, chunk_bytes=1024)
        crypto.decrypt_to(dst_enc, dst_dec)

        assert dst_dec.read_bytes() == plaintext

    def test_encrypted_file_differs_from_plaintext(self, crypto, tmp_path):
        plaintext = b"Sensitive payroll data"
        src = tmp_path / "payroll.txt"
        src.write_bytes(plaintext)
        dst_enc = tmp_path / "payroll.txt.enc"

        crypto.encrypt_chunks(src, dst_enc, chunk_bytes=1024)

        assert dst_enc.read_bytes() != plaintext

    def test_encrypt_empty_file(self, crypto, tmp_path):
        src = tmp_path / "empty.txt"
        src.write_bytes(b"")
        dst_enc = tmp_path / "empty.txt.enc"
        dst_dec = tmp_path / "empty.txt.dec"

        crypto.encrypt_chunks(src, dst_enc, chunk_bytes=1024)
        crypto.decrypt_to(dst_enc, dst_dec)

        assert dst_dec.read_bytes() == b""

    def test_encrypt_large_file(self, crypto, tmp_path):
        # 2 MB file
        plaintext = b"x" * (2 * 1024 * 1024)
        src = tmp_path / "large.bin"
        src.write_bytes(plaintext)
        dst_enc = tmp_path / "large.bin.enc"
        dst_dec = tmp_path / "large.bin.dec"

        crypto.encrypt_chunks(src, dst_enc, chunk_bytes=65536)
        crypto.decrypt_to(dst_enc, dst_dec)

        assert dst_dec.read_bytes() == plaintext

    def test_progress_callback_called(self, crypto, tmp_path):
        src = tmp_path / "data.bin"
        src.write_bytes(b"payload data")
        dst = tmp_path / "data.bin.enc"

        calls = []
        crypto.encrypt_chunks(src, dst, chunk_bytes=1024, on_progress=calls.append)

        assert len(calls) > 0
        assert calls[0] > 0

    def test_decrypt_bytes_round_trip(self, crypto):
        plaintext = b"test payload"
        from cryptography.fernet import Fernet
        token = crypto._fernet.encrypt(plaintext)
        assert crypto.decrypt_bytes(token) == plaintext

    def test_wrong_key_cannot_decrypt(self, valid_key, tmp_path):
        from cryptography.fernet import Fernet, InvalidToken
        other_key = Fernet.generate_key()
        encryptor  = _CryptoHelper(valid_key)
        decryptor  = _CryptoHelper(other_key)

        src = tmp_path / "secret.txt"
        src.write_bytes(b"confidential")
        dst_enc = tmp_path / "secret.txt.enc"
        dst_dec = tmp_path / "secret.txt.dec"

        encryptor.encrypt_chunks(src, dst_enc, chunk_bytes=1024)

        with pytest.raises(Exception):  # InvalidToken or similar
            decryptor.decrypt_to(dst_enc, dst_dec)


# ── no-op mode (no key) ───────────────────────────────────────────────────────

class TestNoOpMode:
    def test_no_crypto_does_not_encrypt(self, no_crypto):
        assert no_crypto.enabled is False

    def test_encrypt_raises_when_disabled(self, no_crypto, tmp_path):
        src = tmp_path / "f.txt"
        src.write_bytes(b"data")
        dst = tmp_path / "f.txt.enc"
        # Calling encrypt on a disabled helper should raise AttributeError
        # (self._fernet is None)
        with pytest.raises(AttributeError):
            no_crypto.encrypt_chunks(src, dst, chunk_bytes=1024)
