"""
Mood History — Stores every mood change to DynamoDB for the timeline view.

Table: SmartHome_MoodHistory
  PK: user_id (HASH)
  SK: timestamp ISO string (RANGE) — enables efficient time-ordered queries
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import boto3
from boto3.dynamodb.conditions import Key

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import settings

logger = logging.getLogger(__name__)

_table = None


def _get_table():
    global _table
    if _table is None:
        kwargs = {"region_name": settings.aws_region}
        if settings.dynamodb_endpoint_url:
            kwargs["endpoint_url"] = settings.dynamodb_endpoint_url
            kwargs.update(aws_access_key_id="local", aws_secret_access_key="local")
        else:
            kwargs["aws_access_key_id"] = settings.aws_access_key_id
            kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
        resource = boto3.resource("dynamodb", **kwargs)
        _table = resource.Table(settings.mood_history_table)
    return _table


def create_mood_history_table():
    """Create the mood history table if it doesn't exist."""
    kwargs = {"region_name": settings.aws_region}
    if settings.dynamodb_endpoint_url:
        kwargs["endpoint_url"] = settings.dynamodb_endpoint_url
        kwargs.update(aws_access_key_id="local", aws_secret_access_key="local")
    else:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

    resource = boto3.resource("dynamodb", **kwargs)
    client = resource.meta.client
    existing = set(client.list_tables()["TableNames"])

    if settings.mood_history_table not in existing:
        resource.create_table(
            TableName=settings.mood_history_table,
            KeySchema=[
                {"AttributeName": "user_id", "KeyType": "HASH"},
                {"AttributeName": "timestamp", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "timestamp", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        resource.Table(settings.mood_history_table).wait_until_exists()
        logger.info(f"Created table: {settings.mood_history_table}")


def store_mood_entry(
    user_id: str,
    mood: str,
    cognitive_load: str,
    confidence: float,
    trigger: str,
    source: str = "voice",
    alexa_response: str = "",
    actions: dict | None = None,
):
    """Store a mood change entry in DynamoDB."""
    now = datetime.now(timezone.utc)
    entry_id = str(uuid4())

    item = {
        "user_id": user_id,
        "timestamp": now.isoformat(),
        "entry_id": entry_id,
        "mood": mood,
        "cognitive_load": cognitive_load,
        "confidence": Decimal(str(round(confidence, 3))),
        "trigger": trigger,
        "source": source,
        "alexa_response": alexa_response,
    }
    if actions:
        # Convert floats to Decimal for DynamoDB
        item["actions"] = _to_dynamo_safe(actions)

    try:
        _get_table().put_item(Item=item)
        logger.info(f"Stored mood history: {user_id} → {mood} ({source})")
    except Exception as e:
        logger.error(f"Failed to store mood history: {e}")


def get_mood_history(user_id: str, limit: int = 50, since: str | None = None) -> list[dict]:
    """Retrieve mood history for a user, most recent first."""
    table = _get_table()

    key_cond = Key("user_id").eq(user_id)
    if since:
        key_cond = key_cond & Key("timestamp").gte(since)

    try:
        kwargs = {
            "KeyConditionExpression": key_cond,
            "ScanIndexForward": False,  # newest first
        }
        if limit:
            kwargs["Limit"] = limit

        resp = table.query(**kwargs)
        items = resp.get("Items", [])

        # Convert Decimal back to float for JSON serialization
        return [_from_dynamo(item) for item in items]
    except Exception as e:
        logger.error(f"Failed to read mood history: {e}")
        return []


def _to_dynamo_safe(obj):
    """Recursively convert floats to Decimal for DynamoDB."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_dynamo_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_dynamo_safe(i) for i in obj]
    return obj


def _from_dynamo(item: dict) -> dict:
    """Convert DynamoDB item back to JSON-friendly format."""
    result = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            result[k] = float(v)
        elif isinstance(v, dict):
            result[k] = _from_dynamo(v)
        else:
            result[k] = v
    return result
