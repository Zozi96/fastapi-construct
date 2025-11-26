import pytest

from fastapi_construct import Container, ServiceLifetime


def test_container_reset_clears_singletons():
    container = Container()

    class IService:
        pass

    class Service:
        pass

    container.register(IService, Service, ServiceLifetime.SINGLETON)

    instance1 = container.resolve(IService)
    instance2 = container.resolve(IService)
    assert instance1 is instance2

    container.reset()

    # After reset, registry is empty, so resolving should fail
    try:
        container.resolve(IService)
        pytest.fail("Should have raised DependencyNotFoundError")
    except Exception:
        pass

    # Re-register
    container.register(IService, Service, ServiceLifetime.SINGLETON)
    instance3 = container.resolve(IService)

    assert instance3 is not instance1


def test_container_isolation():
    container1 = Container()
    container2 = Container()

    class IService:
        pass

    class Service:
        pass

    container1.register(IService, Service, ServiceLifetime.SINGLETON)
    container2.register(IService, Service, ServiceLifetime.SINGLETON)

    instance1 = container1.resolve(IService)
    instance2 = container2.resolve(IService)

    assert instance1 is not instance2
