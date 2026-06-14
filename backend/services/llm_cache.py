"""
LLM Response Cache — DynamoDB-backed shared cache.

Saves tokens by caching identical or near-identical LLM requests in DynamoDB.
All instances share the same cache table, so a response cached by Instance 1
is immediately available to Instance 2.

DynamoDB TTL handles automatic expiry — no cleanup jobs needed.

Table: SmartHome_LLMCache
  PK: cache_key (SHA-256 hash of normalized input)
  TTL: expires_at (Unix epoch — DynamoDB auto-deletes expired items)
"""
import hashlib
import json
import logging
import re
import time
from decimal import Decimal
from typing import Optional

import boto3
from botocore.exceptions import ClientError

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import settings

logger = logging.getLogger(__name__)

# ─── Table Name ──────────────────────────────────────────────────────────────

CACHE_TABLE = settings.llm_cache_table if hasattr(settings, "llm_cache_table") else "SmartHome_LLMCache"


# ─── DynamoDB Resource ───────────────────────────────────────────────────────

_table = None


def _get_table():
    global _table
    if _table is None:
        kwargs = {"region_name": settings.aws_region}
        if settings.dynamodb_endpoint_url:
            kwargs["endpoint_url"] = settings.dynamodb_endpoint_url
            kwargs.update(aws_access_key_id="local", aws_secret_access_key="local")
        else:
            if settings.aws_access_key_id:
                kwargs["aws_access_key_id"] = settings.aws_access_key_id
                kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
        resource = boto3.resource("dynamodb", **kwargs)
        _table = resource.Table(CACHE_TABLE)
    return _table


def create_cache_table():
    """Create the LLM cache table if it doesn't exist. Call on startup."""
    kwargs = {"region_name": settings.aws_region}
    if settings.dynamodb_endpoint_url:
        kwargs["endpoint_url"] = settings.dynamodb_endpoint_url
        kwargs.update(aws_access_key_id="local", aws_secret_access_key="local")
    else:
        if settings.aws_access_key_id:
            kwargs["aws_access_key_id"] = settings.aws_access_key_id
            kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

    resource = boto3.resource("dynamodb", **kwargs)
    client = resource.meta.client

    try:
        existing = set(client.list_tables()["TableNames"])
        if CACHE_TABLE in existing:
            return
    except Exception:
        pass

    try:
        table = resource.create_table(
            TableName=CACHE_TABLE,
            KeySchema=[
                {"AttributeName": "cache_key", "KeyType": "HASH"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "cache_key", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        table.wait_until_exists()

        # Enable TTL on the expires_at attribute
        client.update_time_to_live(
            TableName=CACHE_TABLE,
            TimeToLiveSpecification={
                "Enabled": True,
                "AttributeName": "expires_at",
            },
        )
        logger.info(f"Created LLM cache table: {CACHE_TABLE} with TTL enabled")
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceInUseException":
            logger.error(f"Failed to create cache table: {e}")


# ─── Cache Operations ────────────────────────────────────────────────────────

class DynamoCache:
    """DynamoDB-backed LLM response cache with TTL auto-expiry."""

    def __init__(self, namespace: str, default_ttl: int = 300):
        """
        Args:
            namespace: Cache partition (e.g., "action_engine", "mood_analysis").
                       Prepended to keys to avoid collisions.
            default_ttl: Time-to-live in seconds before DynamoDB auto-deletes.
        """
        self.namespace = namespace
        self.default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[dict]:
        """Retrieve a cached response from DynamoDB. Returns None if missing/expired."""
        full_key = f"{self.namespace}#{key}"
        try:
            resp = _get_table().get_item(Key={"cache_key": full_key})
            item = resp.get("Item")
            if not item:
                self._misses += 1
                return None

            # Double-check TTL (DynamoDB TTL deletion is eventually consistent,
            # items may linger up to 48h after expiry)
            expires_at = int(item.get("expires_at", 0))
            if time.time() > expires_at:
                self._misses += 1
                return None

            # Deserialize the cached response
            value = json.loads(item["response_json"])
            self._hits += 1
            logger.debug(f"Cache HIT: {self.namespace} ({self.stats['hit_rate']})")
            return value

        except Exception as e:
            logger.warning(f"Cache GET failed ({self.namespace}): {e}")
            self._misses += 1
            return None

    def set(self, key: str, value: dict, ttl: Optional[int] = None):
        """Store an LLM response in DynamoDB with TTL."""
        full_key = f"{self.namespace}#{key}"
        ttl = ttl or self.default_ttl
        expires_at = int(time.time() + ttl)

        try:
            _get_table().put_item(
                Item={
                    "cache_key": full_key,
                    "namespace": self.namespace,
                    "response_json": json.dumps(value, default=str),
                    "expires_at": expires_at,
                    "created_at": int(time.time()),
                    "ttl_seconds": ttl,
                }
            )
        except Exception as e:
            logger.warning(f"Cache SET failed ({self.namespace}): {e}")

    def invalidate(self, key: str):
        """Delete a specific cache entry."""
        full_key = f"{self.namespace}#{key}"
        try:
            _get_table().delete_item(Key={"cache_key": full_key})
        except Exception as e:
            logger.warning(f"Cache INVALIDATE failed: {e}")

    def clear(self):
        """Clear all entries in this namespace. Scans and batch-deletes."""
        try:
            table = _get_table()
            resp = table.scan(
                FilterExpression="begins_with(cache_key, :ns)",
                ExpressionAttributeValues={":ns": f"{self.namespace}#"},
                ProjectionExpression="cache_key",
            )
            items = resp.get("Items", [])
            with table.batch_writer() as batch:
                for item in items:
                    batch.delete_item(Key={"cache_key": item["cache_key"]})
            self._hits = 0
            self._misses = 0
            logger.info(f"Cleared {len(items)} entries from {self.namespace} cache")
        except Exception as e:
            logger.warning(f"Cache CLEAR failed ({self.namespace}): {e}")

    @property
    def stats(self) -> dict:
        """Cache hit/miss statistics for this namespace."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        return {
            "namespace": self.namespace,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{hit_rate:.1f}%",
            "ttl_seconds": self.default_ttl,
        }


# ─── Context Normalization ───────────────────────────────────────────────────

def _normalize_context(context: str) -> str:
    """Normalize context string for consistent hashing.

    Removes minor variations that shouldn't produce a different LLM response:
    - Trailing whitespace
    - Minor float precision (0.934 → 0.9)
    """
    normalized = context.strip()
    normalized = re.sub(
        r"(\d+\.\d{2,})",
        lambda m: f"{float(m.group()):.1f}",
        normalized,
    )
    return normalized


def make_cache_key(prompt_prefix: str, context: str) -> str:
    """Generate a deterministic cache key from the prompt type + context.

    Args:
        prompt_prefix: Identifier for which LLM task (e.g., "action_engine", "mood_analysis")
        context: The user message / context being sent to the LLM
    """
    normalized = _normalize_context(context)
    content = f"{prompt_prefix}::{normalized}"
    return hashlib.sha256(content.encode()).hexdigest()[:32]


# ─── Singleton Cache Instances ───────────────────────────────────────────────

# Action Engine: device action decisions
# TTL 60s — behavior state changes frequently, identical signals within 1 min
# should return the same actions
action_cache = DynamoCache(namespace="action_engine", default_ttl=60)

# Mood Analysis: mood classification from text
# TTL 300s (5 min) — same sentence analyzed twice = same mood
mood_cache = DynamoCache(namespace="mood_analysis", default_ttl=300)

# Narrator: Alexa voice lines for context objects
# TTL 600s (10 min) — same anomaly context = similar narration
narrator_cache = DynamoCache(namespace="narrator", default_ttl=600)
