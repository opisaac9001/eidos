from collections import defaultdict
from typing import Callable, Dict, List

class EventBus:
    _instance = None

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)

    @classmethod
    def instance(cls):
        if not cls._instance:
            cls._instance = EventBus()
        return cls._instance

    def subscribe(self, event_type: str, handler: Callable):
        self._subscribers[event_type].append(handler)

    def publish(self, event_type: str, data: dict):
        for handler in self._subscribers.get(event_type, []):
            handler(data)
