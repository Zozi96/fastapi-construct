from fastapi_construct import ServiceLifetime, container, injectable


def test_self_binding_default():
    """Test @injectable() without arguments (self-binding, default scoped)."""

    @injectable()
    class MyService:
        pass

    cfg = container.get_dependency_config(MyService)
    assert cfg is not None
    assert cfg.lifetime == ServiceLifetime.SCOPED
    assert cfg.provider is MyService

    instance = container.default_container.resolve(MyService)
    assert isinstance(instance, MyService)


def test_self_binding_singleton():
    """Test @injectable(ServiceLifetime.SINGLETON)."""

    @injectable(ServiceLifetime.SINGLETON)
    class MySingleton:
        pass

    cfg = container.get_dependency_config(MySingleton)
    assert cfg is not None
    assert cfg.lifetime == ServiceLifetime.SINGLETON

    instance1 = container.default_container.resolve(MySingleton)
    instance2 = container.default_container.resolve(MySingleton)
    assert instance1 is instance2


def test_interface_binding_backward_compatibility():
    """Test @injectable(Interface) still works."""

    class IService:
        pass

    @injectable(IService)
    class ServiceImpl(IService):
        pass

    cfg = container.get_dependency_config(IService)
    assert cfg is not None
    assert cfg.provider is ServiceImpl


def test_interface_binding_with_lifetime():
    """Test @injectable(Interface, lifetime) still works."""

    class IService:
        pass

    @injectable(IService, lifetime=ServiceLifetime.TRANSIENT)
    class ServiceImpl(IService):
        pass

    cfg = container.get_dependency_config(IService)
    assert cfg is not None
    assert cfg.lifetime == ServiceLifetime.TRANSIENT
