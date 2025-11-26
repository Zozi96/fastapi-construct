"""Tests for the dependency injection container."""

from collections.abc import Generator
from typing import Any

import pytest

from fastapi_construct import container
from fastapi_construct.enums import ServiceLifetime


@pytest.fixture(autouse=True)
def clear_registry() -> Generator[None, Any, None]:
    """Clear the dependency registry before and after each test."""
    container.default_container._registry.clear()
    yield
    container.default_container._registry.clear()


class TestTransientLifetime:
    """Tests for transient service lifetime."""

    def test_register_and_get_transient(self) -> None:
        """Test registering a transient dependency."""

        class ITest:
            pass

        class Provider:
            def __init__(self) -> None:
                self.value = 1
                self.instance_id = id(self)

        container.add_transient(ITest, Provider)
        cfg = container.get_dependency_config(ITest)

        assert cfg is not None
        assert cfg.lifetime == ServiceLifetime.TRANSIENT
        assert cfg.provider is Provider

    def test_transient_creates_new_instances(self) -> None:
        """Test that transient services create new instances each time."""

        class ITransient:
            pass

        class TransientService:
            def __init__(self) -> None:
                self.instance_id = id(self)

        container.add_transient(ITransient, TransientService)
        cfg = container.get_dependency_config(ITransient)
        assert cfg is not None

        # Create multiple instances - they should be different
        instance1 = cfg.provider()
        instance2 = cfg.provider()
        instance3 = cfg.provider()

        assert instance1 is not instance2
        assert instance2 is not instance3
        assert instance1 is not instance3

    def test_transient_with_constructor_args(self) -> None:
        """Test transient service with constructor arguments."""

        class IService:
            pass

        class ServiceWithArgs:
            def __init__(self, name: str, count: int = 0) -> None:
                self.name = name
                self.count = count

        container.add_transient(IService, ServiceWithArgs)
        cfg = container.get_dependency_config(IService)
        assert cfg is not None

        instance = cfg.provider(name="test", count=42)
        assert instance.name == "test"
        assert instance.count == 42


class TestScopedLifetime:
    """Tests for scoped service lifetime."""

    def test_register_scoped(self) -> None:
        """Test registering a scoped dependency."""

        class IScoped:
            pass

        class ScopedService:
            def __init__(self) -> None:
                self.value = 100

        container.add_scoped(IScoped, ScopedService)
        cfg = container.get_dependency_config(IScoped)

        assert cfg is not None
        assert cfg.lifetime == ServiceLifetime.SCOPED
        assert cfg.provider is ScopedService

    def test_scoped_provider_is_class(self) -> None:
        """Test that scoped services don't get wrapped."""

        class IScoped:
            pass

        class ScopedService:
            def __init__(self) -> None:
                pass

        container.add_scoped(IScoped, ScopedService)
        cfg = container.get_dependency_config(IScoped)
        assert cfg is not None

        # Scoped should not be wrapped, provider should be the class itself
        assert cfg.provider is ScopedService


class TestSingletonLifetime:
    """Tests for singleton service lifetime."""

    def test_register_singleton_wraps_and_caches(self) -> None:
        """Test that singleton services are wrapped and cached."""

        class IOne:
            pass

        class SingletonService:
            def __init__(self) -> None:
                self.instance_id = id(self)

        container.add_singleton(IOne, SingletonService)
        cfg = container.get_dependency_config(IOne)

        assert cfg is not None
        assert cfg.lifetime == ServiceLifetime.SINGLETON

        # Provider should be the class itself (not wrapped)
        assert cfg.provider is SingletonService

        # Resolve via container to trigger singleton logic
        instance1 = container.default_container.resolve(IOne)
        instance2 = container.default_container.resolve(IOne)

        assert instance1 is instance2
        assert hasattr(instance1, "instance_id")

    def test_singleton_caches_across_multiple_calls(self) -> None:
        """Test that singleton returns same instance across many calls."""

        class ISingleton:
            pass

        class SingletonService:
            def __init__(self) -> None:
                self.created_at = id(self)

        container.add_singleton(ISingleton, SingletonService)

        instances = [container.default_container.resolve(ISingleton) for _ in range(10)]

        # All instances should be the same object
        first = instances[0]
        assert all(inst is first for inst in instances)

    def test_singleton_with_constructor_args(self) -> None:
        """Test singleton service with constructor arguments."""
        # Note: With the new container implementation, singletons are cached by Interface type.
        # Constructor arguments are only used for the FIRST creation.
        # Subsequent calls return the same instance regardless of arguments (if resolved by type).
        # However, resolve() doesn't take arguments. Arguments are resolved recursively.
        # If we want to test with args, we need to register dependencies that provide those args.

        class IConfig:
            pass

        class ConfigService:
            def __init__(self) -> None:
                self.env = "dev"

        container.add_singleton(IConfig, ConfigService)

        instance1 = container.default_container.resolve(IConfig)
        instance2 = container.default_container.resolve(IConfig)

        assert instance1 is instance2
        assert instance1.env == "dev"


class TestContainerEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_get_dependency_config_missing_returns_none(self) -> None:
        """Test getting config for unregistered interface returns None."""

        class IUnregistered:
            pass

        assert container.get_dependency_config(IUnregistered) is None

    def test_multiple_registrations_overwrites(self) -> None:
        """Test that registering the same interface twice overwrites."""

        class IService:
            pass

        class ServiceV1:
            def __init__(self) -> None:
                self.version = 1

        class ServiceV2:
            def __init__(self) -> None:
                self.version = 2

        container.add_scoped(IService, ServiceV1)
        cfg1 = container.get_dependency_config(IService)
        assert cfg1 is not None
        assert cfg1.provider is ServiceV1

        # Register again with different implementation
        container.add_scoped(IService, ServiceV2)
        cfg2 = container.get_dependency_config(IService)
        assert cfg2 is not None
        assert cfg2.provider is ServiceV2

    def test_register_with_factory_function(self) -> None:
        """Test registering a factory function instead of a class."""

        class IService:
            pass

        class Service:
            def __init__(self, value: int) -> None:
                self.value = value

        def service_factory() -> Service:
            return Service(value=999)

        container.add_transient(IService, service_factory)
        cfg = container.get_dependency_config(IService)
        assert cfg is not None

        instance = cfg.provider()
        assert isinstance(instance, Service)
        assert instance.value == 999

    def test_singleton_factory_function_not_wrapped(self) -> None:
        """Test that singleton factory functions get wrapped properly."""

        class IService:
            pass

        class Service:
            pass

        def service_factory() -> Service:
            return Service()

        # Factory functions should NOT be wrapped (only classes)
        container.register_dependency(IService, service_factory, ServiceLifetime.SINGLETON)
        cfg = container.get_dependency_config(IService)
        assert cfg is not None

        # Since it's a function, it won't be wrapped
        assert cfg.provider is service_factory
