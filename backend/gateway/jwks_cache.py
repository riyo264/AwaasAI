"""JWKS Key Cache — Fetches and caches Cognito RSA public keys in memory."""

import base64
import logging
import time

import httpx
from cryptography.hazmat.primitives.asymmetric.rsa import (
    RSAPublicKey,
    RSAPublicNumbers,
)
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)


class JWKSFetchError(Exception):
    """Raised when JWKS keys cannot be fetched and no cache is available."""
    pass


class KeyNotFoundError(Exception):
    """Raised when the requested kid is not found in the JWKS."""
    pass


def _base64url_decode(value: str) -> bytes:
    """Decode a base64url-encoded string (no padding)."""
    # Add padding if needed
    remainder = len(value) % 4
    if remainder:
        value += "=" * (4 - remainder)
    return base64.urlsafe_b64decode(value)


def _jwk_to_rsa_public_key(jwk: dict) -> RSAPublicKey:
    """Convert a JWK dict with RSA components to an RSAPublicKey object."""
    n_bytes = _base64url_decode(jwk["n"])
    e_bytes = _base64url_decode(jwk["e"])

    n_int = int.from_bytes(n_bytes, byteorder="big")
    e_int = int.from_bytes(e_bytes, byteorder="big")

    public_numbers = RSAPublicNumbers(e=e_int, n=n_int)
    return public_numbers.public_key(default_backend())


class JWKSCache:
    """Fetches and caches Cognito JWKS keys in memory.

    Keys are indexed by 'kid' (Key ID) and refreshed when the cache TTL expires.
    On fetch failure, cached keys are returned if available; otherwise a
    JWKSFetchError is raised (maps to HTTP 503 in the middleware).
    """

    def __init__(self, jwks_url: str, cache_ttl_seconds: int = 3600):
        self._jwks_url = jwks_url
        self._cache_ttl_seconds = cache_ttl_seconds
        self._keys: dict[str, RSAPublicKey] = {}
        self._last_fetched: float = 0

    @property
    def is_stale(self) -> bool:
        """Return True if the cache has never been fetched or TTL has expired."""
        if self._last_fetched == 0:
            return True
        return (time.time() - self._last_fetched) >= self._cache_ttl_seconds

    async def _fetch_keys(self) -> dict[str, RSAPublicKey]:
        """Fetch JWKS from the endpoint and parse RSA public keys."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(self._jwks_url)
            response.raise_for_status()

        jwks = response.json()
        keys: dict[str, RSAPublicKey] = {}

        for key_data in jwks.get("keys", []):
            if key_data.get("kty") != "RSA":
                continue
            if key_data.get("use") and key_data["use"] != "sig":
                continue

            kid = key_data.get("kid")
            if not kid:
                continue

            try:
                rsa_key = _jwk_to_rsa_public_key(key_data)
                keys[kid] = rsa_key
            except (KeyError, ValueError) as exc:
                logger.warning("Failed to parse JWK kid=%s: %s", kid, exc)

        return keys

    async def _refresh_if_stale(self) -> None:
        """Refresh cached keys if the TTL has expired."""
        if not self.is_stale:
            return

        try:
            new_keys = await self._fetch_keys()
            self._keys = new_keys
            self._last_fetched = time.time()
            logger.info(
                "JWKS cache refreshed: %d keys loaded from %s",
                len(new_keys),
                self._jwks_url,
            )
        except (httpx.HTTPError, httpx.StreamError, Exception) as exc:
            if self._keys:
                logger.warning(
                    "JWKS fetch failed (%s), using cached keys (%d keys available)",
                    exc,
                    len(self._keys),
                )
            else:
                raise JWKSFetchError(
                    "Unable to fetch JWKS keys and no cached keys available. "
                    "Authentication service unavailable."
                ) from exc

    async def get_key(self, kid: str) -> RSAPublicKey:
        """Return the RSA public key for the given Key ID.

        If the kid is not in cache and the cache is stale, refetch from JWKS.
        If kid is still not found after refetch, raise KeyNotFoundError.
        On network failure with no cache, raise JWKSFetchError (HTTP 503).
        """
        # Try to serve from cache first
        await self._refresh_if_stale()

        if kid in self._keys:
            return self._keys[kid]

        # kid not found — force a refresh regardless of TTL
        # (Cognito may have rotated keys)
        try:
            new_keys = await self._fetch_keys()
            self._keys = new_keys
            self._last_fetched = time.time()
        except (httpx.HTTPError, httpx.StreamError, Exception) as exc:
            if self._keys:
                logger.warning(
                    "JWKS refetch for unknown kid failed (%s), using cached keys",
                    exc,
                )
            else:
                raise JWKSFetchError(
                    "Unable to fetch JWKS keys and no cached keys available. "
                    "Authentication service unavailable."
                ) from exc

        if kid in self._keys:
            return self._keys[kid]

        raise KeyNotFoundError(
            f"Key ID '{kid}' not found in JWKS. "
            "The token may have been signed with an unknown key."
        )
