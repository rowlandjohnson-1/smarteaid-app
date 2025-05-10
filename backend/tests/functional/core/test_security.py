# app/tests/core/test_security.py

import pytest
from unittest.mock import patch, MagicMock
import time
from datetime import datetime, timedelta, timezone
from jose import jwt
from jose.utils import base64url_encode
import json

from app.core.security import (
    get_jwks,
    validate_token,
    clear_jwks_cache,
    get_jwks_cache_info,
    JWKSFetchError,
    TokenValidationError,
    RateLimitError,
    SecurityError
)

# --- Test Data ---
MOCK_JWKS = {
    "keys": [
        {
            "kid": "test_key_1",
            "kty": "RSA",
            "n": "test_n",
            "e": "AQAB",
            "use": "sig",
            "alg": "RS256"
        }
    ]
}

# Structurally valid mock token with a kid that matches MOCK_JWKS
_mock_header = {"alg": "RS256", "typ": "JWT", "kid": "test_key_1"}
_mock_header_b64 = base64url_encode(json.dumps(_mock_header).encode('utf-8')).decode('utf-8')
_mock_payload_empty_b64 = base64url_encode(b'{}').decode('utf-8') # Empty payload for simplicity as jwt.decode is mocked
_mock_signature_b64 = base64url_encode(b"fakesignature").decode('utf-8') # Valid base64url signature
MOCK_TOKEN = f"{_mock_header_b64}.{_mock_payload_empty_b64}.{_mock_signature_b64}"

MOCK_PAYLOAD = {
    "sub": "test_user",
    "aud": "test_audience",
    "iss": "test_issuer",
    "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
}

# --- JWKS Tests ---
@pytest.mark.asyncio
async def test_get_jwks_success():
    """Test successful JWKS fetching and caching."""
    clear_jwks_cache()
    with patch('requests.get') as mock_get:
        mock_get.return_value.json.return_value = MOCK_JWKS
        mock_get.return_value.raise_for_status.return_value = None
        
        # First call should fetch from network
        result = get_jwks()
        assert result == MOCK_JWKS
        mock_get.assert_called_once()
        
        # Second call should use cache
        result = get_jwks()
        assert result == MOCK_JWKS
        assert mock_get.call_count == 1  # Still only called once

@pytest.mark.asyncio
async def test_get_jwks_failure():
    """Test JWKS fetching failure handling."""
    clear_jwks_cache()
    with patch('requests.get') as mock_get:
        mock_get.side_effect = Exception("Network error")
        
        with pytest.raises(JWKSFetchError):
            get_jwks()

@pytest.mark.asyncio
async def test_get_jwks_rate_limiting():
    """Test JWKS fetching rate limiting (currently expecting JWKSFetchError on retry without specific rate limit logic)."""
    clear_jwks_cache()
    with patch('requests.get') as mock_get:
        mock_get.side_effect = Exception("Network error")
        
        # First failure
        with pytest.raises(JWKSFetchError):
            get_jwks()
        
        # Immediate retry should also result in JWKSFetchError as no specific RateLimitError is implemented in get_jwks
        # If RateLimitError is implemented in get_jwks, this test should be updated.
        mock_get.reset_mock()
        mock_get.side_effect = Exception("Network error on retry")
        with pytest.raises(JWKSFetchError):
            get_jwks()

# --- Token Validation Tests ---
@pytest.mark.asyncio
async def test_validate_token_success():
    """Test successful token validation."""
    clear_jwks_cache()
    with patch('app.core.security.get_jwks') as mock_get_jwks:
        mock_get_jwks.return_value = MOCK_JWKS
        
        # Mock JWT decode
        with patch('jose.jwt.decode') as mock_decode:
            with patch('app.core.security.KINDE_DOMAIN', "test_issuer"), \
                 patch('app.core.security.KINDE_AUDIENCE', "test_audience"):
                mock_decode.return_value = MOCK_PAYLOAD
                
                result = validate_token(MOCK_TOKEN)
                assert result == MOCK_PAYLOAD
                mock_decode.assert_called_once_with(
                    MOCK_TOKEN,
                    MOCK_JWKS['keys'][0],
                    algorithms=["RS256"],
                    audience="test_audience",
                    issuer="test_issuer"
                )

@pytest.mark.asyncio
async def test_validate_token_expired():
    """Test expired token validation."""
    clear_jwks_cache()
    with patch('app.core.security.get_jwks') as mock_get_jwks:
        mock_get_jwks.return_value = MOCK_JWKS
        
        with patch('app.core.security.KINDE_DOMAIN', "test_issuer"), \
             patch('app.core.security.KINDE_AUDIENCE', "test_audience"):
            with patch('jose.jwt.decode', side_effect=jwt.ExpiredSignatureError("Token has expired")) as mock_decode:
                with pytest.raises(TokenValidationError, match="Expired signature"):
                    validate_token(MOCK_TOKEN)

@pytest.mark.asyncio
async def test_validate_token_invalid_kid():
    """Test token validation with invalid key ID."""
    clear_jwks_cache()
    with patch('app.core.security.get_jwks') as mock_get_jwks:
        mock_get_jwks.return_value = {"keys": []}  # No matching key
        with patch('app.core.security.KINDE_DOMAIN', "test_issuer"), \
             patch('app.core.security.KINDE_AUDIENCE', "test_audience"):
            with pytest.raises(TokenValidationError, match="Public key with kid 'test_key_1' not found"):
                validate_token(MOCK_TOKEN)

# --- Cache Management Tests ---
@pytest.mark.asyncio
async def test_clear_jwks_cache():
    """Test JWKS cache clearing."""
    clear_jwks_cache()
    with patch('requests.get') as mock_get:
        mock_get.return_value.json.return_value = MOCK_JWKS
        mock_get.return_value.raise_for_status.return_value = None
        
        # First call populates cache
        get_jwks()
        assert mock_get.call_count == 1, "requests.get should be called once to populate cache"
        
        # Clear cache
        clear_jwks_cache()
        
        # Next call should fetch again
        get_jwks()
        assert mock_get.call_count == 2, "requests.get should be called again after cache clear"

@pytest.mark.asyncio
async def test_get_jwks_cache_info():
    """Test JWKS cache info retrieval."""
    clear_jwks_cache()
    with patch('requests.get') as mock_get:
        mock_get.return_value.json.return_value = MOCK_JWKS
        mock_get.return_value.raise_for_status.return_value = None
        
        # Populate cache
        get_jwks()
        get_jwks()
        
        # Get cache info
        cache_info = get_jwks_cache_info()
        assert isinstance(cache_info, dict)
        assert "hits" in cache_info
        assert "misses" in cache_info
        assert "maxsize" in cache_info
        assert "currsize" in cache_info

# --- Error Handling Tests ---
@pytest.mark.asyncio
async def test_security_error_hierarchy():
    """Test security error class hierarchy."""
    assert issubclass(JWKSFetchError, SecurityError)
    assert issubclass(TokenValidationError, SecurityError)
    assert issubclass(RateLimitError, SecurityError)

@pytest.mark.asyncio
async def test_error_messages():
    """Test error message formatting."""
    with pytest.raises(JWKSFetchError, match="Test error"):
        raise JWKSFetchError("Test error") 