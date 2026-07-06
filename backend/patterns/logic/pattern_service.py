"""Pattern service: run the deterministic engine and persist results.

Called by the in-process extraction scheduler and the
``POST /patterns/{id}/extract`` route. Reads the configured analysis window of
events, extracts patterns, and upserts them into the Patterns table.
"""
from __future__ import annotations

import json
from decimal import Decimal

from patterns.app.config import get_settings
from patterns.dynamodb.client import get_table
from patterns.models.patterns import BasePattern, pattern_from_item, pattern_to_item
from patterns.pattern_engine import extract_all
from patterns.logic import event_service


def _to_dynamo_safe(item: dict) -> dict:
    """DynamoDB rejects Python floats; round-trip through JSON to coerce every
    float into a Decimal while leaving ints/strings untouched."""
    return json.loads(json.dumps(item), parse_float=Decimal)


def extract_and_store(household_id: str) -> list[BasePattern]:
    settings = get_settings()
    events = event_service.get_recent_events(household_id, settings.analysis_window_days)
    patterns = extract_all(household_id, events)

    table = get_table(settings.patterns_table)
    with table.batch_writer() as batch:
        for pattern in patterns:
            item = pattern_to_item(pattern)
            item["household_id"] = household_id
            batch.put_item(Item=_to_dynamo_safe(item))
    return patterns


def get_patterns(household_id: str) -> list[BasePattern]:
    from boto3.dynamodb.conditions import Key
    from patterns.logic import profile_service

    table = get_table(get_settings().patterns_table)
    resp = table.query(KeyConditionExpression=Key("household_id").eq(household_id))
    items = resp.get("Items", [])
    while "LastEvaluatedKey" in resp:
        resp = table.query(
            KeyConditionExpression=Key("household_id").eq(household_id),
            ExclusiveStartKey=resp["LastEvaluatedKey"],
        )
        items.extend(resp.get("Items", []))

    learned = [pattern_from_item(i) for i in items]

    try:
        user_defined = profile_service.routines_as_patterns(household_id)
    except Exception:
        user_defined = []

    return learned + user_defined
