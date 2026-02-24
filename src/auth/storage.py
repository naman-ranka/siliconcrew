import sqlite3
import json
from datetime import datetime
from typing import List, Optional
from .models import AuthProfile
from .security import SecurityManager

class AuthStorage:
    def __init__(self, db_path: str, security: SecurityManager):
        self.db_path = db_path
        self.security = security
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auth_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                profile_id TEXT NOT NULL,
                type TEXT NOT NULL,
                access_token TEXT NOT NULL,
                refresh_token TEXT,
                expires_at TIMESTAMP,
                meta TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(provider, profile_id)
            )
        """)
        conn.commit()
        conn.close()

    def save_profile(self, profile: AuthProfile):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Encrypt tokens
        enc_access = self.security.encrypt(profile.access_token)
        enc_refresh = self.security.encrypt(profile.refresh_token) if profile.refresh_token else None

        meta_json = json.dumps(profile.meta) if profile.meta else "{}"

        cursor.execute("""
            INSERT OR REPLACE INTO auth_profiles
            (provider, profile_id, type, access_token, refresh_token, expires_at, meta, is_active, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            profile.provider,
            profile.profile_id,
            profile.type,
            enc_access,
            enc_refresh,
            profile.expires_at,
            meta_json,
            profile.is_active,
            datetime.now()
        ))
        conn.commit()
        conn.close()

    def get_profile(self, provider: str, profile_id: str) -> Optional[AuthProfile]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM auth_profiles WHERE provider = ? AND profile_id = ?
        """, (provider, profile_id))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return self._row_to_profile(row)

    def list_profiles(self, provider: str = None) -> List[AuthProfile]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if provider:
            cursor.execute("SELECT * FROM auth_profiles WHERE provider = ? ORDER BY updated_at DESC", (provider,))
        else:
            cursor.execute("SELECT * FROM auth_profiles ORDER BY provider, updated_at DESC")

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_profile(row) for row in rows]

    def _row_to_profile(self, row) -> AuthProfile:
        # Decrypt tokens
        access = self.security.decrypt(row["access_token"])
        refresh = self.security.decrypt(row["refresh_token"]) if row["refresh_token"] else None

        meta = json.loads(row["meta"]) if row["meta"] else {}

        expires_at = row["expires_at"]
        if isinstance(expires_at, str):
            try:
                expires_at = datetime.fromisoformat(expires_at)
            except:
                pass

        return AuthProfile(
            id=row["id"],
            provider=row["provider"],
            profile_id=row["profile_id"],
            type=row["type"],
            access_token=access,
            refresh_token=refresh,
            expires_at=expires_at,
            meta=meta,
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )
