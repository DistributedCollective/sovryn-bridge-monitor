import pytest

from bridge_monitor.business_logic.key_value_store import KeyValueStore


@pytest.fixture()
def key_value_service(dbsession) -> KeyValueStore:
    return KeyValueStore(dbsession=dbsession)


def test_get_or_create_value(key_value_service):
    value = key_value_service.get_or_create_value("foo", 123)
    assert value == 123
    value = key_value_service.get_or_create_value("foo", 4567890)
    assert value == 123
    value = key_value_service.get_or_create_value("bar", "bazz")
    assert value == "bazz"


def test_get_set_value(key_value_service):
    with pytest.raises(LookupError):
        key_value_service.get_value("example")
    key_value_service.set_value("example", "something")
    assert key_value_service.get_value("example") == "something"
    key_value_service.set_value("example", {"a": 1})
    assert key_value_service.get_value("example") == {"a": 1}
