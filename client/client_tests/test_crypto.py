import pytest
import base64

from resana_secure.crypto import (
    encrypt_parsec_key,
    decrypt_parsec_key,
    CryptoError,
    _js_string_to_bytes,
    _bytes_to_js_string,
)


@pytest.fixture
def parsec_key():
    return "Sword,MeetEvil!"


@pytest.fixture
def user_password():
    return "Evil,MyMeetSword"


@pytest.fixture
def encrypted_key(parsec_key, user_password):
    return encrypt_parsec_key(user_password, parsec_key)


def test_crypto_encrypt_decrypt(parsec_key, user_password):
    encrypted_parsec_key = encrypt_parsec_key(user_password, parsec_key)
    # Hopefully we can at least pass this check
    assert encrypted_parsec_key != parsec_key

    decrypted_parsec_key = decrypt_parsec_key(user_password, encrypted_parsec_key)
    assert decrypted_parsec_key == parsec_key


def test_crypto_incorrect_user_password(encrypted_key):
    with pytest.raises(CryptoError) as exc_info:
        decrypt_parsec_key("Boo", encrypted_key)
    assert str(exc_info.value) == "Cannot decrypt"


def test_crypto_invalid_encrypted_key(user_password, encrypted_key):
    # Not base64encoded
    with pytest.raises(CryptoError) as exc_info:
        decrypt_parsec_key(user_password, "The butts of evil await my bootprint!")
    assert str(exc_info.value) == "Invalid format: not base64"

    # Not the right format (no /)
    with pytest.raises(CryptoError) as exc_info:
        decrypt_parsec_key(
            user_password,
            base64.b64encode(
                "Boo points, I punch - it's a very simple relationship, but it is effective!".encode()
            ).decode(),
        )
    assert str(exc_info.value) == "Invalid format: cannot retrieve iv and encrypted key"

    # Serialized IV not looking right
    with pytest.raises(CryptoError) as exc_info:
        decrypt_parsec_key(
            user_password,
            base64.b64encode("Swords, not words!/34,12,66,132,187,23,46,97".encode()).decode(),
        )
    assert str(exc_info.value) == "Invalid format: cannot deserialize"

    # Serialized key not looking right
    with pytest.raises(CryptoError) as exc_info:
        decrypt_parsec_key(
            user_password,
            base64.b64encode(
                "84,98,2,252,92/Feel the burning stare of my HAMSTER and change your ways!".encode()
            ).decode(),
        )
    assert str(exc_info.value) == "Invalid format: cannot deserialize"

    # Invalid IV
    with pytest.raises(CryptoError) as exc_info:
        _, enc_data = base64.b64decode(encrypted_key).decode().split("/")
        decrypt_parsec_key(
            user_password,
            base64.b64encode(f"84,98,2,252,92,23,98,232,23/{enc_data}".encode()).decode(),
        )
    assert str(exc_info.value) == "Cannot decrypt"


def test_js_string():
    s = _bytes_to_js_string(b"abcd*")
    assert s == "97,98,99,100,42"
    b = _js_string_to_bytes(s)
    assert b == b"abcd*"
