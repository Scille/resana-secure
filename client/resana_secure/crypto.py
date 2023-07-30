import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class CryptoError(Exception):
    pass


def _derive_password(password: str) -> bytes:
    """Derive the password using PBKDF2. Salt and options were taken from Resana code."""

    SALT = bytes([122, 205, 180, 252, 110, 57, 134, 101, 147, 170, 189, 150, 191, 228, 84, 206])

    # Same options as Resana
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        salt=SALT,
        length=32,
        iterations=100000,
    )
    return kdf.derive(password.encode())


def _bytes_to_js_string(b: bytes) -> str:
    """This fonction works as JS' Uint8Array.toString() that is used by Resana
    to serialize bytes.
    `bytes([73, 229, 86])` becomes the string `"73,229,86"`.
    """
    return ",".join(str(c) for c in b)


def _js_string_to_bytes(s: str) -> bytes:
    """This fonction works as a deserializer for `bytes_to_js_string` to deserialize
    the format used by Resana to handle bytes.
    The string `"73,229,86"` is translated into a bytes object `bytes([73, 229, 86])`.
    """
    return bytes([int(c) % 256 for c in s.split(",")])


def _encrypt(key: bytes, data: bytes) -> tuple[bytes, bytes]:
    """ " This fonction is a translation from the JavaScript code found in Resana.
    It encrypts `data` using the key `key`.
    """
    aesgcm = AESGCM(key)
    # Generate the iv
    iv: bytes = os.urandom(12)
    encrypted_data = aesgcm.encrypt(iv, data, None)
    return iv, encrypted_data


def _decrypt(key: bytes, iv: bytes, encrypted_data: bytes) -> bytes:
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(iv, encrypted_data, None)


def encrypt_parsec_key(user_password: str, parsec_key: str) -> str:
    """Encrypt the given `parsec_key` with `user_password` and returns the encrypted key
    in the same format as Resana, namely:
    BASE64( "34,56,21/67,89,34,231,194,139" )
             |   IV  |    CRYPTED KEY    |
    """

    # Derive the password
    password_derived: bytes = _derive_password(user_password)
    # Crypt the data using the derived password
    iv, encrypted_key = _encrypt(password_derived, parsec_key.encode())
    # Serialize both
    serialized_iv = _bytes_to_js_string(iv)
    serialized_encrypted_key = _bytes_to_js_string(encrypted_key)
    # Concat them with a slash
    serialized_encrypted_data = f"{serialized_iv}/{serialized_encrypted_key}"
    # B64 encode it all
    return base64.b64encode(serialized_encrypted_data.encode()).decode()


def decrypt_parsec_key(user_password: str, b64_serialized_encrypted_data: str) -> str:
    """Data is given as a base64 of the iv and the crypted key in JS Uint8.toString() format separated by a slash.
    BASE64( "34,56,21/67,89,34,231,194,139" )
             |   IV  |    CRYPTED KEY    |
    """

    try:
        # Data is b64encoded, decode it
        serialized_encrypted_data = base64.b64decode(b64_serialized_encrypted_data).decode()
    except ValueError as exc:
        raise CryptoError("Invalid format: not base64") from exc
    try:
        # Split the data between serialized iv and serialized key
        serialized_iv, serialized_encrypted_key = serialized_encrypted_data.split("/")
    except ValueError as exc:
        raise CryptoError("Invalid format: cannot retrieve iv and encrypted key") from exc
    try:
        # Deserialize both
        iv: bytes = _js_string_to_bytes(serialized_iv)
        encrypted_key: bytes = _js_string_to_bytes(serialized_encrypted_key)
    except ValueError as exc:
        raise CryptoError("Invalid format: cannot deserialize") from exc

    # Derive the password
    password_derived: bytes = _derive_password(user_password)
    # Decrypt the data using the derived password and the iv
    try:
        return _decrypt(password_derived, iv, encrypted_key).decode()
    except InvalidTag:
        # Avoid raising from here to be sure to not leak anything
        raise CryptoError("Cannot decrypt")


if __name__ == "__main__":
    import argparse

    def _decrypt_and_print(args: argparse.Namespace) -> None:
        parsec_key = decrypt_parsec_key(args.password, args.encrypted)
        print(f"Parsec key is `{parsec_key}`")

    def _encrypt_and_print(args: argparse.Namespace) -> None:
        encrypted_parsec_key = encrypt_parsec_key(args.password, args.parsec_key)
        print(f"Encrypted Parsec key is `{encrypted_parsec_key}`")

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="cmd")
    subparsers.required = True

    encrypt_parser = subparsers.add_parser("encrypt", help="Crypt a Parsec key")
    encrypt_parser.add_argument("--parsec-key", type=str, required=True)
    encrypt_parser.add_argument("--password", type=str, required=True)
    encrypt_parser.set_defaults(func=_encrypt_and_print)

    decrypt_parser = subparsers.add_parser("decrypt", help="Decrypt a Parsec key")
    decrypt_parser.add_argument("--encrypted", type=str, required=True)
    decrypt_parser.add_argument("--password", type=str, required=True)
    decrypt_parser.set_defaults(func=_decrypt_and_print)

    args = parser.parse_args()
    args.func(args)
