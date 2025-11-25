import pytest

from fastapi_construct.container import Container
from fastapi_construct.exceptions import CircularDependencyError


class TestCircularDependency:
    """Tests for circular dependency detection."""

    def test_circular_dependency_raises_error(self):
        """Test that a simple A -> B -> A cycle raises CircularDependencyError."""
        container = Container()

        class IA:
            pass

        class IB:
            pass

        class A:
            def __init__(self, b: IB):
                self.b = b

        class B:
            def __init__(self, a: IA):
                self.a = a

        container.register(IA, A)
        container.register(IB, B)

        with pytest.raises(CircularDependencyError):
            container.resolve(IA)

    def test_self_dependency_raises_error(self):
        """Test that A -> A cycle raises CircularDependencyError."""
        container = Container()

        class IA:
            pass

        class A:
            def __init__(self, a: IA):
                self.a = a

        container.register(IA, A)

        with pytest.raises(CircularDependencyError):
            container.resolve(IA)
