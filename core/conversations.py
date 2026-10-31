from collections import OrderedDict
from threading import RLock


class ConversationStore:
    """Bounded process-local histories, keyed by authenticated identity."""

    def __init__(self, capacity=256, max_messages=20):
        self.capacity = capacity
        self.max_messages = max_messages
        self._items = OrderedDict()
        self.lock = RLock()

    def history(self, user_id, session_id):
        with self.lock:
            return list(self._items.get((user_id, session_id), []))

    def append(self, user_id, session_id, question, response):
        key = (user_id, session_id)
        with self.lock:
            turns = self._items.pop(key, [])
            turns += [{"role": "user", "content": question}, {"role": "assistant", "content": response}]
            self._items[key] = turns[-self.max_messages:]
            while len(self._items) > self.capacity:
                self._items.popitem(last=False)

    def reset(self, user_id, session_id):
        with self.lock:
            self._items.pop((user_id, session_id), None)


def require_scope(user_id, session_id):
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("A positive authenticated user ID is required")
    if session_id != f"user_{user_id}_default":
        raise ValueError("Session does not belong to authenticated user")
