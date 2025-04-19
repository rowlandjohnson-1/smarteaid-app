# app/tests/core/test_security.py

import pytest
from unittest.mock import patch, MagicMock
import time
from datetime import datetime, timedelta
from jose import jwt
from jose.exceptions import JWTError

from app.core.security import (
    get_jwks,
    validate_token,
    clear_jwks_cache,
    get_jwks_cache_info,
    JWKSFetchError,
    TokenValidationError,
    RateLimitError
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

MOCK_TOKEN = "mock.jwt.token"
MOCK_PAYLOAD = {
    "sub": "test_user",
    "aud": "test_audience",
    "iss": "test_issuer",
    "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp())
}

# --- JWKS Tests ---
@pytest.mark.asyncio
async def test_get_jwks_success():
    """Test successful JWKS fetching and caching."""
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
    with patch('requests.get') as mock_get:
        mock_get.side_effect = Exception("Network error")
        
        with pytest.raises(JWKSFetchError):
            get_jwks()

@pytest.mark.asyncio
async def test_get_jwks_rate_limiting():
    """Test JWKS fetching rate limiting."""
    with patch('requests.get') as mock_get:
        mock_get.side_effect = Exception("Network error")
        
        # First failure
        with pytest.raises(JWKSFetchError):
            get_jwks()
        
        # Immediate retry should be rate limited
        with pytest.raises(RateLimitError):
            get_jwks()

# --- Token Validation Tests ---
@pytest.mark.asyncio
async def test_validate_token_success():
    """Test successful token validation."""
    with patch('app.core.security.get_jwks') as mock_get_jwks:
        mock_get_jwks.return_value = MOCK_JWKS
        
        # Mock JWT decode
        with patch('jose.jwt.decode') as mock_decode:
            mock_decode.return_value = MOCK_PAYLOAD
            
            result = validate_token(MOCK_TOKEN)
            assert result == MOCK_PAYLOAD
            mock_decode.assert_called_once()

@pytest.mark.asyncio
async def test_validate_token_expired():
    """Test expired token validation."""
    with patch('app.core.security.get_jwks') as mock_get_jwks:
        mock_get_jwks.return_value = MOCK_JWKS
        
        # Mock JWT decode to raise expired signature error
        with patch('jose.jwt.decode') as mock_decode:
            mock_decode.side_effect = JWTError("Token has expired")
            
            with pytest.raises(TokenValidationError):
                validate_token(MOCK_TOKEN)

@pytest.mark.asyncio
async def test_validate_token_invalid_kid():
    """Test token validation with invalid key ID."""
    with patch('app.core.security.get_jwks') as mock_get_jwks:
        mock_get_jwks.return_value = {"keys": []}  # No matching key
        
        with pytest.raises(TokenValidationError):
            validate_token(MOCK_TOKEN)

# --- Cache Management Tests ---
@pytest.mark.asyncio
async def test_clear_jwks_cache():
    """Test JWKS cache clearing."""
    with patch('requests.get') as mock_get:
        mock_get.return_value.json.return_value = MOCK_JWKS
        mock_get.return_value.raise_for_status.return_value = None
        
        # First call populates cache
        get_jwks()
        
        # Clear cache
        clear_jwks_cache()
        
        # Next call should fetch again
        get_jwks()
        assert mock_get.call_count == 2

@pytest.mark.asyncio
async def test_get_jwks_cache_info():
    """Test JWKS cache info retrieval."""
    with patch('requests.get') as mock_get:
        mock_get.return_value.json.return_value = MOCK_JWKS
        mock_get.return_value.raise_for_status.return_value = None
        
        # Populate cache
        get_jwks()
        
        # Get cache info
        cache_info = get_jwks_cache_info()
        assert isinstance(cache_info, dict)
        assert "hits" in cache_info
        assert "misses" in cache_info
        assert "maxsize" in cache_info
        assert "currsize" in cache_info
        assert "last_fetch_time" in cache_info
        assert "last_fetch_success" in cache_info

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
    with pytest.raises(JWKSFetchError) as exc_info:
        raise JWKSFetchError("Test error")
    assert "Test error" in str(exc_info.value) 