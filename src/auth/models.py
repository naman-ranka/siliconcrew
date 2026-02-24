from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel

class AuthProfile(BaseModel):
    id: Optional[int] = None
    provider: str  # 'openai', 'anthropic', 'google'
    profile_id: str # e.g. 'default', 'user-1', 'personal-key'
    type: str # 'api_key', 'oauth'
    access_token: str # Encrypted
    refresh_token: Optional[str] = None # Encrypted
    expires_at: Optional[datetime] = None
    meta: Optional[Dict[str, Any]] = None
    is_active: bool = True
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()
