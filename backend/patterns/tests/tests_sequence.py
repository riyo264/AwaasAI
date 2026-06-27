import json

from patterns.tests.sample_data_h003 import generate
from patterns.models.events import Event
from patterns.pattern_engine.sequence_based_2 import extract_sequence_patterns

sample_events = generate()

# Export events to JSON
with open("sample_data_h003.json", "w", encoding="utf-8") as f:
    json.dump(
        [event.model_dump(mode="json") for event in sample_events],
        f,
        indent=4,
        ensure_ascii=False,
    )

events = [
    Event(**event.model_dump())
    for event in sample_events
]

patterns = extract_sequence_patterns(
    "H003",
    events,
)

print("=" * 80)
print("Patterns Found:", len(patterns))
print()

for p in patterns:
    print("=" * 80)
    print(p.pattern_id)
    print(p.description)
    print(p.usual_time)
    print(p.occurrences)
    print(round(p.confidence, 3))
    print(p.steps)
    print()