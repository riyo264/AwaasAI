"""Declarative DynamoDB table schemas + idempotent creation helper.

Table designs
=============

1. Events table  (``SmartHome_Events``)
   - Partition key : household_id      (groups all events for one home)
   - Sort key      : timestamp#event_id (ISO time + uuid -> sortable & unique)
   The composite sort key keeps events naturally ordered by time while
   remaining unique even when two events share a millisecond. Range queries
   like "events for H001 in the last 30 days" become a single efficient Query.

2. Household state table (``SmartHome_HouseholdState``)
   - Partition key : household_id      (exactly one item per home)
   A simple key-value document updated in place on every event.

3. Patterns table (``SmartHome_Patterns``)
   - Partition key : household_id
   - Sort key      : pattern_id
   Stores all learned patterns for a home; queried as a set by the context
   builder.

All tables use PAY_PER_REQUEST (on-demand) billing — ideal for spiky,
unpredictable hackathon / IoT traffic with zero capacity planning.
"""
from __future__ import annotations

from patterns.app.config import get_settings
from patterns.dynamodb.client import get_dynamodb_resource


def table_definitions() -> list[dict]:
    s = get_settings()
    return [
        {
            "TableName": s.events_table,
            "KeySchema": [
                {"AttributeName": "household_id", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            "AttributeDefinitions": [
                {"AttributeName": "household_id", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            "BillingMode": "PAY_PER_REQUEST",
        },
        {
            "TableName": s.state_table,
            "KeySchema": [
                {"AttributeName": "household_id", "KeyType": "HASH"},
            ],
            "AttributeDefinitions": [
                {"AttributeName": "household_id", "AttributeType": "S"},
            ],
            "BillingMode": "PAY_PER_REQUEST",
        },
        {
            "TableName": s.patterns_table,
            "KeySchema": [
                {"AttributeName": "household_id", "KeyType": "HASH"},
                {"AttributeName": "pattern_id", "KeyType": "RANGE"},
            ],
            "AttributeDefinitions": [
                {"AttributeName": "household_id", "AttributeType": "S"},
                {"AttributeName": "pattern_id", "AttributeType": "S"},
            ],
            "BillingMode": "PAY_PER_REQUEST",
        },
        {
            # Temporary occasion-driven adjustments (guests, festivals) that
            # overlay the learned patterns without mutating them.
            "TableName": s.adjustments_table,
            "KeySchema": [
                {"AttributeName": "household_id", "KeyType": "HASH"},
                {"AttributeName": "id", "KeyType": "RANGE"},
            ],
            "AttributeDefinitions": [
                {"AttributeName": "household_id", "AttributeType": "S"},
                {"AttributeName": "id", "AttributeType": "S"},
            ],
            "BillingMode": "PAY_PER_REQUEST",
        },
        {
            # User-declared home profile routines: manually entered schedules
            # (device + action + time) that seed the anomaly engine directly,
            # without requiring event history to be learned.
            "TableName": s.profiles_table,
            "KeySchema": [
                {"AttributeName": "household_id", "KeyType": "HASH"},
                {"AttributeName": "routine_id", "KeyType": "RANGE"},
            ],
            "AttributeDefinitions": [
                {"AttributeName": "household_id", "AttributeType": "S"},
                {"AttributeName": "routine_id", "AttributeType": "S"},
            ],
            "BillingMode": "PAY_PER_REQUEST",
        },
    ]


def create_tables() -> list[str]:
    """Create any missing tables. Safe to run repeatedly (idempotent)."""
    resource = get_dynamodb_resource()
    client = resource.meta.client
    existing = set(client.list_tables()["TableNames"])
    created: list[str] = []
    for definition in table_definitions():
        name = definition["TableName"]
        if name in existing:
            continue
        resource.create_table(**definition)
        resource.Table(name).wait_until_exists()
        created.append(name)
    return created
