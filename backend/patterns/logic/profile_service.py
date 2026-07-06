"""Home profile service: CRUD for user-declared routines.

User routines are stored in the HomeProfiles DynamoDB table (PK: household_id,
SK: routine_id) and converted to synthetic TimePattern / DurationPattern objects
with confidence=1.0.  The pattern_service.get_patterns() call merges these with
the learned patterns so the anomaly engine and context builder see both sources
without any further changes.
"""
from __future__ import annotations

import json
from decimal import Decimal

from patterns.app.config import get_settings
from patterns.dynamodb.client import get_table
from patterns.models.patterns import BasePattern, DurationPattern, TimePattern
from patterns.models.profile import UserRoutine, UserRoutineCreate


def _dynamo_safe(item: dict) -> dict:
    return json.loads(json.dumps(item, default=str), parse_float=Decimal)


def create_routine(household_id: str, body: UserRoutineCreate) -> UserRoutine:
    routine = UserRoutine(household_id=household_id, **body.model_dump())
    table = get_table(get_settings().profiles_table)
    table.put_item(Item=_dynamo_safe(routine.model_dump(mode="json")))
    return routine


def list_routines(household_id: str) -> list[UserRoutine]:
    from boto3.dynamodb.conditions import Key

    table = get_table(get_settings().profiles_table)
    resp = table.query(KeyConditionExpression=Key("household_id").eq(household_id))
    items = resp.get("Items", [])
    while "LastEvaluatedKey" in resp:
        resp = table.query(
            KeyConditionExpression=Key("household_id").eq(household_id),
            ExclusiveStartKey=resp["LastEvaluatedKey"],
        )
        items.extend(resp.get("Items", []))
    return [UserRoutine(**i) for i in items]


def delete_routine(household_id: str, routine_id: str) -> None:
    table = get_table(get_settings().profiles_table)
    table.delete_item(Key={"household_id": household_id, "routine_id": routine_id})


def routines_as_patterns(household_id: str) -> list[BasePattern]:
    """Convert every user routine into synthetic patterns for the anomaly engine."""
    patterns: list[BasePattern] = []
    for r in list_routines(household_id):
        patterns.append(
            TimePattern(
                pattern_id=f"USER#{r.routine_id}#TIME",
                household_id=household_id,
                confidence=1.0,
                occurrences=0,
                device=r.device_id,
                action=r.action.value,
                usual_time=r.usual_time,
                window_minutes=r.window_minutes,
            )
        )
        if r.duration_minutes:
            patterns.append(
                DurationPattern(
                    pattern_id=f"USER#{r.routine_id}#DUR",
                    household_id=household_id,
                    confidence=1.0,
                    occurrences=0,
                    device=r.device_id,
                    usual_duration_minutes=r.duration_minutes,
                    stddev_minutes=0.0,
                    usual_start_time=r.usual_time,
                )
            )
    return patterns
