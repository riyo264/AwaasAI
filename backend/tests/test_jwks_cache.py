"""Unit tests for the JWKS Key Cache module."""

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

from gateway.jwks_cache import (
    JWKSCache,
    JWKSFetchError,
    KeyNotFoundError,
    _base64url_decode,
    _jwk_to_rsa_public_key,
)


def _generate_rsa_key_pair():
    """Generate an RSA key pair for testing."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    return private_key


def _int_to_base64url(value: int) -> str:
    """Convert an integer to base64url string (no padding)."""
    import base64

    byte_length = (value.bit_length() + 7) // 8
    value_bytes = value.to_bytes(byte_length, byteorder="big")
    return base64.urlsafe_b64encode(value_bytes).rstrip(b"=").decode("ascii")


def _make_jwks_response(keys: list[dict]) -> dict:
    """Create a JWKS response with the given key dicts."""
    return {"keys": keys}


def _rsa_key_to_jwk(private_key, kid: str) -> dict:
    """Convert an RSA private key to a JWK dict."""
    pub = private_key.public_key().public_numbers()
    return {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": _int_to_base64url(pub.n),
        "e": _int_to_base64url(pub.e),
    }


class TestBase64UrlDecode:
    def test_decode_standard_value(self):
        import base64

        original = b"hello world"
        encoded = base64.urlsafe_b64encode(original).rstrip(b"=").decode()
        assert _base64url_decode(encoded) == original

    def test_decode_with_padding_needed(self):
        import base64

        original = b"test"
        encoded = base64.urlsafe_b64encode(original).rstrip(b"=").decode()
        assert _base64url_decode(encoded) == original


class TestJwkToRsaPublicKey:
    def test_converts_valid_jwk(self):
        private_key = _generate_rsa_key_pair()
        jwk = _rsa_key_to_jwk(private_key, "test-kid")
        public_key = _jwk_to_rsa_public_key(jwk)

        # Verify the key matches the original
        original_pub = private_key.public_key().public_numbers()
        converted_pub = public_key.public_numbers()
        assert original_pub.n == converted_pub.n
        assert original_pub.e == converted_pub.e


class TestJWKSCache:
    @pytest.fixture
    def jwks_url(self):
        return "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_abc123/.well-known/jwks.json"

    @pytest.fixture
    def rsa_key(self):
        return _generate_rsa_key_pair()

    @pytest.fixture
    def jwk_data(self, rsa_key):
        return _rsa_key_to_jwk(rsa_key, "kid-1")

    @pytest.fixture
    def jwks_response(self, jwk_data):
        return _make_jwks_response([jwk_data])

    def test_is_stale_when_never_fetched(self, jwks_url):
        cache = JWKSCache(jwks_url, cache_ttl_seconds=3600)
        assert cache.is_stale is True

    def test_is_not_stale_after_fetch(self, jwks_url):
        cache = JWKSCache(jwks_url, cache_ttl_seconds=3600)
        cache._last_fetched = time.time()
        assert cache.is_stale is False

    def test_is_stale_after_ttl_expires(self, jwks_url):
        cache = JWKSCache(jwks_url, cache_ttl_seconds=10)
        cache._last_fetched = time.time() - 11
        assert cache.is_stale is True

    @pytest.mark.asyncio
    async def test_get_key_fetches_and_caches(self, jwks_url, jwks_response, rsa_key):
        cache = JWKSCache(jwks_url, cache_ttl_seconds=3600)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = jwks_response

        with patch("gateway.jwks_cache.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            key = await cache.get_key("kid-1")

        # Verify we got a valid RSA public key
        assert key is not None
        original_pub = rsa_key.public_key().public_numbers()
        assert key.public_numbers().n == original_pub.n

    @pytest.mark.asyncio
    async def test_get_key_uses_cache_on_second_call(self, jwks_url, jwks_response):
        cache = JWKSCache(jwks_url, cache_ttl_seconds=3600)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = jwks_response

        with patch("gateway.jwks_cache.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            # First call: fetches
            await cache.get_key("kid-1")
            # Second call: uses cache (no additional fetch)
            await cache.get_key("kid-1")

            # Should only have fetched once (cache is not stale yet)
            assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_get_key_raises_key_not_found(self, jwks_url, jwks_response):
        cache = JWKSCache(jwks_url, cache_ttl_seconds=3600)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = jwks_response

        with patch("gateway.jwks_cache.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(KeyNotFoundError, match="unknown-kid"):
                await cache.get_key("unknown-kid")

    @pytest.mark.asyncio
    async def test_get_key_returns_cached_on_fetch_failure(self, jwks_url, jwks_response, rsa_key):
        cache = JWKSCache(jwks_url, cache_ttl_seconds=1)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = jwks_response

        with patch("gateway.jwks_cache.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            # First call succeeds and caches
            key = await cache.get_key("kid-1")
            assert key is not None

        # Wait for TTL to expire
        cache._last_fetched = time.time() - 2

        # Now make fetch fail
        with patch("gateway.jwks_cache.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("Connection refused")
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            # Should still return cached key
            key = await cache.get_key("kid-1")
            assert key is not None

    @pytest.mark.asyncio
    async def test_get_key_raises_503_on_fetch_failure_no_cache(self, jwks_url):
        cache = JWKSCache(jwks_url, cache_ttl_seconds=3600)

        with patch("gateway.jwks_cache.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("Connection refused")
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(JWKSFetchError, match="Authentication service unavailable"):
                await cache.get_key("kid-1")

    @pytest.mark.asyncio
    async def test_get_key_force_refetch_for_unknown_kid(self, jwks_url):
        """If kid not in cache after initial fetch, force a refetch (key rotation)."""
        key1 = _generate_rsa_key_pair()
        key2 = _generate_rsa_key_pair()

        jwk1 = _rsa_key_to_jwk(key1, "kid-1")
        jwk2 = _rsa_key_to_jwk(key2, "kid-2")

        # First response has only kid-1
        response1 = MagicMock()
        response1.status_code = 200
        response1.raise_for_status = MagicMock()
        response1.json.return_value = _make_jwks_response([jwk1])

        # Second response has kid-1 and kid-2 (after rotation)
        response2 = MagicMock()
        response2.status_code = 200
        response2.raise_for_status = MagicMock()
        response2.json.return_value = _make_jwks_response([jwk1, jwk2])

        with patch("gateway.jwks_cache.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = [response1, response2]
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            cache = JWKSCache(jwks_url, cache_ttl_seconds=3600)

            # Request kid-2 which is not in initial fetch — triggers refetch
            result = await cache.get_key("kid-2")
            assert result is not None
            assert result.public_numbers().n == key2.public_key().public_numbers().n


# Need httpx imported for the ConnectError used in tests
import httpx
