from fastapi_construct.enums import ServiceLifetime


def test_service_lifetime_values():
    assert ServiceLifetime.TRANSIENT.value == "transient"
    assert ServiceLifetime.SCOPED.value == "scoped"
    assert ServiceLifetime.SINGLETON.value == "singleton"


def test_service_lifetime_members():
    members = set(ServiceLifetime)
    assert ServiceLifetime.TRANSIENT in members
    assert ServiceLifetime.SCOPED in members
    assert ServiceLifetime.SINGLETON in members
