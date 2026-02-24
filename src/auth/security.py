import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

class SecurityManager:
    def __init__(self, key_path: str = None):
        if key_path is None:
            # Default to storing key in .siliconcrew directory
            home = os.path.expanduser("~")
            key_path = os.path.join(home, ".siliconcrew", "master.key")

        self.key_path = key_path
        self._fernet = None
        self._load_or_create_key()

    def _load_or_create_key(self):
        if os.path.exists(self.key_path):
            with open(self.key_path, "rb") as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            os.makedirs(os.path.dirname(self.key_path), exist_ok=True)
            with open(self.key_path, "wb") as f:
                f.write(key)

        self._fernet = Fernet(key)

    def encrypt(self, data: str) -> str:
        """Encrypts a string."""
        if not data:
            return ""
        return self._fernet.encrypt(data.encode()).decode()

    def decrypt(self, token: str) -> str:
        """Decrypts a token."""
        if not token:
            return ""
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except Exception:
            return ""
