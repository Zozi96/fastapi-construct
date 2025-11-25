import pytest

from fastapi_construct.container import Container
from fastapi_construct.exceptions import DependencyNotFoundError, DependencyRegistrationError


class TestContainerClass:
    """Tests for the Container class."""

    def test_container_isolation(self):
        """Test that different containers are isolated."""
        container1 = Container()
        container2 = Container()

        class IService:
            pass

        class Service1:
            pass

        class Service2:
            pass

        container1.register(IService, Service1)
        container2.register(IService, Service2)

        cfg1 = container1.get_config(IService)
        cfg2 = container2.get_config(IService)

        assert cfg1.provider is Service1
        assert cfg2.provider is Service2

    def test_register_invalid_provider_raises_error(self):
        """Test that registering a non-callable provider raises an error."""
        container = Container()

        class IService:
            pass

        with pytest.raises(DependencyRegistrationError):
            container.register(IService, "not callable")  # type: ignore

    def test_resolve_raises_error_if_not_found(self):
        """Test that resolve raises DependencyNotFoundError if not found."""
        container = Container()

        class IService:
            pass

        with pytest.raises(DependencyNotFoundError):
            container.resolve(IService)

    def test_resolve_returns_instance(self):
        """Test that resolve returns an instance of the dependency."""
        container = Container()

        class IService:
            pass

        class Service:
            pass

        container.register(IService, Service)
        instance = container.resolve(IService)
        assert isinstance(instance, Service)
