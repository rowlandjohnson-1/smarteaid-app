# app/core/security.py
"""
Security module for handling Kinde JWT authentication.

Provides functionality for:
- JWKS (JSON Web Key Set) fetching and caching using lru_cache.
- JWT token validation (signature, expiry, claims: iss, aud).
- FastAPI dependency for protecting endpoints.
- Custom exceptions for specific security errors.
- Cache management utilities.

Security Considerations:
- Uses lru_cache for JWKS to prevent excessive network calls.
- Uses proper error handling and logging.
- Validates required token claims (iss, aud, exp, signature).

Example Usage in Endpoints:
    ```python
    from fastapi import APIRouter, Depends, HTTPException
    from typing import Dict, Any
    from ...core.security import get_current_user_payload # Adjust import path

    router = APIRouter()

    @router.get("/protected-resource")
    async def get_protected_resource(
        payload: Dict[str, Any] = Depends(get_current_user_payload)
    ):
        # If code reaches here, token is valid. Payload contains claims.
        user_id = payload.get("sub")
        # ... process request using user_id or other claims ...
        return {"message": f"Hello user {user_id}", "claims": payload}
    ```
"""

import logging
import requests
from typing import Dict, Any, Optional
from functools import lru_cache
from datetime import datetime # Needed for cache info timestamp

# --- JOSE & JWT Imports ---
from jose import jwt, exceptions as jose_exceptions
from jose.exceptions import JOSEError

# --- FastAPI Imports ---
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# --- Config Imports ---
# Import Kinde settings from config
# Adjust the relative path '.' based on where security.py is relative to 'core'
from .config import KINDE_DOMAIN, KINDE_AUDIENCE

# Setup logging
logger = logging.getLogger(__name__)
# Ensure logging is configured elsewhere (e.g., main.py or logging config)
# logging.basicConfig(level=logging.INFO) # Avoid configuring basicConfig here if done elsewhere

# --- Custom Exceptions ---
class SecurityError(Exception):
    """Base class for security-related exceptions."""
    pass

class JWKSFetchError(SecurityError):
    """Raised when there is an error fetching or parsing the JWKS."""
    pass

class TokenValidationError(SecurityError):
    """Raised when token validation fails (expiry, signature, claims, etc.)."""
    pass

# --- JWKS Handling ---

# Construct the JWKS URL based on the Kinde domain from config
JWKS_URL: Optional[str] = None
if KINDE_DOMAIN:
    # Ensure domain doesn't have trailing slash for clean URL join
    domain = KINDE_DOMAIN.rstrip('/')
    JWKS_URL = f"{domain}/.well-known/jwks.json"
else:
    logger.error("KINDE_DOMAIN is not configured. Cannot determine JWKS URL.")


@lru_cache(maxsize=1) # Cache only the most recent JWKS result
def get_jwks() -> Dict[str, Any]:
    """
    Fetches the JWKS keys from the Kinde instance's well-known endpoint.
    Uses lru_cache for simple in-memory caching. Raises JWKSFetchError on failure.

    Returns:
        The JWKS dictionary containing the keys.

    Raises:
        JWKSFetchError: If fetching or parsing fails, or config is missing.
    """
    if not JWKS_URL:
        err_msg = "Cannot fetch JWKS: JWKS URL is not configured (KINDE_DOMAIN missing?)."
        logger.error(err_msg)
        raise JWKSFetchError(err_msg)

    # Log only when actually fetching (cache miss)
    # Note: lru_cache doesn't easily expose miss events without wrappers
    logger.info(f"Attempting to fetch JWKS keys from {JWKS_URL}...")
    try:
        response = requests.get(JWKS_URL, timeout=10) # Network timeout
        response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)

        jwks = response.json()
        # Basic validation of the received JWKS structure
        if "keys" not in jwks or not isinstance(jwks["keys"], list):
            raise JWKSFetchError("Invalid JWKS format received: 'keys' array not found.")

        logger.info(f"Successfully fetched and cached {len(jwks['keys'])} JWKS keys.")
        return jwks # Return the whole JWKS dict including the 'keys' list

    except requests.exceptions.Timeout as e:
        raise JWKSFetchError(f"Timeout while trying to fetch JWKS from {JWKS_URL}: {e}")
    except requests.exceptions.RequestException as e:
        # Includes connection errors, HTTP errors, etc.
        raise JWKSFetchError(f"Network error fetching JWKS from {JWKS_URL}: {e}")
    except ValueError as e: # Includes JSONDecodeError
        raise JWKSFetchError(f"Error parsing JWKS JSON response from {JWKS_URL}: {e}")
    except Exception as e: # Catch any other unexpected errors
        logger.error(f"Unexpected error during JWKS fetch: {e}", exc_info=True)
        raise JWKSFetchError(f"Unexpected error during JWKS fetch: {e}")


# --- JWT Validation Function ---

def validate_token(token: str) -> Dict[str, Any]:
    """
    Decodes and validates a JWT token using Kinde's public keys.

    Args:
        token: The encoded JWT string (access token).

    Returns:
        The decoded token payload (dictionary) if validation is successful.

    Raises:
        TokenValidationError: If Kinde config is missing or token validation fails
                              (e.g., signature, expiry, claims).
        JWKSFetchError: If fetching the required JWKS keys fails.
    """
    if not KINDE_DOMAIN or not KINDE_AUDIENCE:
        raise TokenValidationError("Kinde domain or audience not configured.")

    # 1. Get the JWKS keys (will use cache or raise JWKSFetchError)
    # Wrap JWKS fetch in try...except specific to JWKS errors
    try:
        jwks = get_jwks()
    except JWKSFetchError as e:
         # Re-raise as TokenValidationError or let JWKSFetchError propagate?
         # Let's re-raise for simplicity in the dependency handler
         raise TokenValidationError(f"Token validation failed: Could not retrieve JWKS keys - {e}")

    # 2. Get the Key ID (kid) from the unverified token header
    try:
        unverified_header = jwt.get_unverified_header(token)
        if "kid" not in unverified_header:
             raise TokenValidationError("JWT header does not contain 'kid' (Key ID).")
        rsa_key_kid = unverified_header["kid"]
    except jose_exceptions.JWTError as e:
        raise TokenValidationError(f"Error getting unverified header from token: {e}")

    # 3. Find the key in JWKS that matches the token's 'kid'
    key_found = None
    for key in jwks["keys"]:
        if key.get("kid") == rsa_key_kid:
            key_found = key
            break

    if not key_found:
        # Key not found, potentially due to key rotation. Clear cache and retry once?
        # For simplicity now, just raise error. Consider adding retry logic later.
        clear_jwks_cache() # Clear cache as keys might have rotated
        logger.warning(f"Public key with kid '{rsa_key_kid}' not found in JWKS. Cache cleared.")
        raise TokenValidationError(f"Public key with kid '{rsa_key_kid}' not found in JWKS (cache cleared, retry might succeed).")

    # 4. Decode and validate the token
    try:
        # Note: Ensure KINDE_DOMAIN accurately reflects the 'iss' claim in the token.
        # It might need a trailing slash, e.g., "https://your-org.kinde.com/"
        payload = jwt.decode(
            token,
            key_found, # The specific key matching the token's kid
            algorithms=["RS256"], # Kinde typically uses RS256
            audience=KINDE_AUDIENCE, # Verify the 'aud' claim
            issuer=KINDE_DOMAIN      # Verify the 'iss' claim
        )
        logger.info("Token successfully validated.")
        return payload # Return the dictionary of claims

    except jose_exceptions.ExpiredSignatureError:
        raise TokenValidationError("Token validation failed: Expired signature.")
    except jose_exceptions.JWTClaimsError as e:
        # Handles audience, issuer, and other standard claim validation errors
        raise TokenValidationError(f"Token validation failed: Invalid claims - {e}")
    except jose_exceptions.JWTError as e:
        # General JWT errors (e.g., invalid signature, malformed token)
        raise TokenValidationError(f"Token validation failed: Invalid token - {e}")
    except Exception as e:
        # Catch any other unexpected errors during validation
        logger.error(f"An unexpected error occurred during token validation: {e}", exc_info=True)
        raise TokenValidationError(f"Unexpected error during token validation: {e}")


# --- FastAPI Dependency for Authentication ---

# Define the OAuth2 scheme - extracts Bearer token from Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)
# Set auto_error=False to handle missing token within our dependency for clearer error

async def get_current_user_payload(
    token: Optional[str] = Depends(oauth2_scheme) # Make token optional here
) -> Dict[str, Any]:
    """
    FastAPI dependency to validate Kinde token and return payload.

    Usage: Add `payload: Dict[str, Any] = Depends(get_current_user_payload)`
           to endpoint function signatures.

    Raises:
        HTTPException(401): If token is missing, invalid, expired, or fails validation.
        HTTPException(500): If an unexpected internal error occurs.

    Returns:
        Dict[str, Any]: The decoded and validated JWT payload upon success.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    internal_error_exception = HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An internal error occurred during authentication.",
    )

    if token is None:
         logger.warning("Authentication attempt failed: No token provided.")
         raise credentials_exception # Raise 401 if token is missing

    try:
        # Call the validation function which raises specific errors
        payload = validate_token(token)
        return payload
    except TokenValidationError as e:
        # If validate_token raises an error, catch it and raise HTTPException 401
        logger.warning(f"Authentication failed: {e}") # Log the specific validation error
        # Raise the original 401 exception for consistency
        raise credentials_exception from e
    except JWKSFetchError as e:
         # If fetching keys fails, treat as internal server error for the client
         logger.error(f"Authentication failed due to JWKS fetch error: {e}")
         raise internal_error_exception from e
    except Exception as e:
        # Catch any other unexpected errors during validation process
        logger.error(f"Unexpected error during authentication dependency: {e}", exc_info=True)
        raise internal_error_exception from e


# --- Cache Management Functions ---

def clear_jwks_cache():
    """Clears the JWKS cache, forcing a fresh fetch on the next call to get_jwks."""
    get_jwks.cache_clear()
    logger.info("JWKS cache cleared.")

def get_jwks_cache_info() -> Dict[str, Any]:
    """Gets information about the current JWKS cache state (from lru_cache)."""
    cache_info = get_jwks.cache_info()
    return {
        "hits": cache_info.hits,
        "misses": cache_info.misses,
        "maxsize": cache_info.maxsize,
        "currsize": cache_info.currsize,
    }
