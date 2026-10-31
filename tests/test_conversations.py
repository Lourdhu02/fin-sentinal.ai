import pytest

from core.conversations import ConversationStore, require_scope


def test_histories_and_reset_are_user_scoped():
    store = ConversationStore()
    store.append(1, "a", "private", "secret")
    store.append(2, "b", "other", "answer")
    assert store.history(2, "a") == []
    store.reset(2, "b")
    assert store.history(1, "a")[0]["content"] == "private"


def test_cross_user_session_rejected():
    with pytest.raises(ValueError):
        require_scope(1, "user_2_default")


def test_histories_are_bounded():
    store = ConversationStore(capacity=1, max_messages=2)
    store.append(1, "a", "q", "a")
    store.append(2, "b", "q", "a")
    assert store.history(1, "a") == []
