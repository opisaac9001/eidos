# eidos_agent/features/firmament/core/event_types.py

THOUGHT_TRIGGER = "thought.trigger"
WORLD_EVENT = "world.random"
MOOD_UPDATED = "ethos.mood_update"
SCHEDULE_BLOCK_STARTED = "chronos.schedule_started"
SCHEDULE_BLOCK_ENDED = "chronos.schedule_ended"
IMPULSE = "subconscious.impulse"
SLEEP_REQUESTED = "availability.request_sleep"
NPC_DIALOGUE = "npc.say"

# Event published when a new NPC has been improvised and registered
NEW_NPC_IMPROVISED = "firmament.npc.improvised.new"

# Event published by ChronosAdapter when ChronosEngine updates its schedule
FIRMAMENT_SCHEDULE_RELOAD_REQUESTED = "firmament.schedule_reload_requested"
