from patterns.tests.sample_data_h003 import generate
from patterns.models.events import Event
from patterns.pattern_engine.duration2 import extract_duration_patterns

sample_events = generate()

events = [
    Event(**event.model_dump())
    for event in sample_events
]

patterns = extract_duration_patterns(
    "H003",
    events,
)

print("=" * 80)
print("Patterns Found:", len(patterns))

for p in patterns:
    print("=" * 80)
    print(p.pattern_id)
    print(p)