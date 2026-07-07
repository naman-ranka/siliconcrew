"""4C (hosted-latency plan): file-cached JWKS for WorkOS token verification.

Every Codex turn spawns a fresh MCP subprocess whose first act is verifying the
caller's bearer token; PyJWKClient's in-memory cache meant a cold HTTPS JWKS
fetch per spawn. The file cache is shared across processes on one instance and
TTL'd; a kid miss forces exactly one refresh so key rotation still works.
Verification itself (RS256 signature, issuer, expiry) is unchanged and real in
these tests — only the network fetch is faked.
"""
import json

import pytest

pytest.importorskip("jwt")
pytest.importorskip("cryptography")

from src.platform_engines import identity as identity_mod
from src.platform_engines.identity import AuthError, WorkOSVerifier

ISS = "https://api.workos.com/user_management/client_x"
JWKS_URL = "https://api.workos.com/sso/jwks/client_x"


def _rsa_key():
    from cryptography.hazmat.primitives.asymmetric import rsa

    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwks_for(kid, public_key):
    import jwt

    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key))
    jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return {"keys": [jwk]}


def _signed(payload, key, kid):
    import jwt

    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": kid})


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    path = str(tmp_path / "jwks-cache.json")
    monkeypatch.setattr(identity_mod, "_jwks_cache_path", lambda url: path)
    return path


def test_jwks_fetched_once_across_verifier_instances(isolated_cache, monkeypatch):
    """Two verifier instances (stand-ins for two subprocess spawns on one
    instance) share the disk cache: one fetch, both verify for real."""
    key = _rsa_key()
    jwks = _jwks_for("kid1", key.public_key())
    fetches = []
    monkeypatch.setattr(
        identity_mod, "_fetch_jwks", lambda url: (fetches.append(url), jwks)[1]
    )

    token = _signed({"sub": "u1", "iss": ISS}, key, "kid1")
    for _ in range(2):
        v = WorkOSVerifier(issuer=ISS, audience="", jwks_url=JWKS_URL)
        assert v.verify(token).user_id == "workos_u1"
    assert len(fetches) == 1, "second spawn must hit the file cache, not the network"


def test_kid_miss_forces_one_refresh_for_rotation(isolated_cache, monkeypatch):
    """A rotated signing key (kid not in the cached set) must trigger exactly
    one forced refresh and then verify — rotation never waits out the TTL."""
    key1, key2 = _rsa_key(), _rsa_key()
    responses = [_jwks_for("kid1", key1.public_key()), _jwks_for("kid2", key2.public_key())]
    fetches = []

    def fake_fetch(url):
        fetches.append(url)
        return responses[min(len(fetches), len(responses)) - 1]

    monkeypatch.setattr(identity_mod, "_fetch_jwks", fake_fetch)

    v = WorkOSVerifier(issuer=ISS, audience="", jwks_url=JWKS_URL)
    assert v.verify(_signed({"sub": "u1", "iss": ISS}, key1, "kid1")).user_id == "workos_u1"
    # Rotate: token signed with kid2, cache still holds kid1 → forced refresh.
    assert v.verify(_signed({"sub": "u2", "iss": ISS}, key2, "kid2")).user_id == "workos_u2"
    assert len(fetches) == 2


def test_expired_cache_refetches(isolated_cache, monkeypatch):
    import os

    key = _rsa_key()
    jwks = _jwks_for("kid1", key.public_key())
    fetches = []
    monkeypatch.setattr(
        identity_mod, "_fetch_jwks", lambda url: (fetches.append(url), jwks)[1]
    )
    token = _signed({"sub": "u1", "iss": ISS}, key, "kid1")

    v = WorkOSVerifier(issuer=ISS, audience="", jwks_url=JWKS_URL)
    v.verify(token)
    os.utime(isolated_cache, (0, 0))  # back-date past the TTL
    v.verify(token)
    assert len(fetches) == 2, "an expired cache entry must re-fetch"


def test_bad_signature_still_rejected_via_cache(isolated_cache, monkeypatch):
    """The cache changes key transport only — a token signed by a DIFFERENT key
    under a cached kid must still fail signature verification (fail-closed)."""
    key, impostor = _rsa_key(), _rsa_key()
    jwks = _jwks_for("kid1", key.public_key())
    monkeypatch.setattr(identity_mod, "_fetch_jwks", lambda url: jwks)

    v = WorkOSVerifier(issuer=ISS, audience="", jwks_url=JWKS_URL)
    with pytest.raises(AuthError):
        v.verify(_signed({"sub": "u1", "iss": ISS}, impostor, "kid1"))


def test_corrupt_cache_file_recovers(isolated_cache, monkeypatch):
    key = _rsa_key()
    jwks = _jwks_for("kid1", key.public_key())
    monkeypatch.setattr(identity_mod, "_fetch_jwks", lambda url: jwks)
    with open(isolated_cache, "w", encoding="utf-8") as f:
        f.write("{not json")

    v = WorkOSVerifier(issuer=ISS, audience="", jwks_url=JWKS_URL)
    assert v.verify(_signed({"sub": "u1", "iss": ISS}, key, "kid1")).user_id == "workos_u1"
