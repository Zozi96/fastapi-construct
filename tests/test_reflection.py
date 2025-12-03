"""Tests for dependency reflection and autowiring."""

import inspect
from collections.abc import Generator
from typing import Any

import pytest

from fastapi_construct import container
from fastapi_construct.exceptions import CaptiveDependencyError, InterfaceMismatchError
from fastapi_construct.reflection import autowire_callable, resolve_dependency_for_param


@pytest.fixture(autouse=True)
def clear_registry() -> Generator[None, Any, None]:
    """Clear the dependency registry before and after each test."""
    container.default_container._registry.clear()
    yield
    container.default_container._registry.clear()


class TestResolveDependencyForParam:
    """Tests for resolve_dependency_for_param function."""

    def test_resolve_dependency_returns_depends_for_scoped(self) -> None:
        """Test that scoped dependencies resolve to Depends with cache enabled."""

        class IService:
            pass

        class ServiceImpl:
            pass

        container.add_scoped(IService, ServiceImpl)

        dep = resolve_dependency_for_param(IService)

        # Should return a FastAPI Depends object
        assert hasattr(dep, "dependency")
        assert hasattr(dep, "use_cache")
        # Dependency is now a wrapper
        assert callable(dep.dependency)
        assert inspect.iscoroutinefunction(dep.dependency)
        assert dep.use_cache is True

    def test_resolve_dependency_transient_uses_no_cache(self) -> None:
        """Test that transient dependencies resolve to Depends without cache."""

        class IService:
            pass

        class ServiceImpl:
            pass

        container.add_transient(IService, ServiceImpl)

        dep = resolve_dependency_for_param(IService)

        assert hasattr(dep, "dependency")
        assert hasattr(dep, "use_cache")
        # Dependency is now a wrapper
        assert callable(dep.dependency)
        assert inspect.iscoroutinefunction(dep.dependency)
        assert dep.use_cache is False

    def test_resolve_dependency_singleton_uses_cache(self) -> None:
        """Test that singleton dependencies resolve to Depends with cache enabled."""

        class IService:
            pass

        class ServiceImpl:
            pass

        container.add_singleton(IService, ServiceImpl)

        dep = resolve_dependency_for_param(IService)

        assert hasattr(dep, "dependency")
        assert hasattr(dep, "use_cache")
        # Singleton uses internal caching/locking, so FastAPI cache is disabled
        assert dep.use_cache is False

    def test_resolve_dependency_unregistered_returns_annotation(self) -> None:
        """Test that unregistered types return the annotation as-is."""

        class IUnregistered:
            pass

        result = resolve_dependency_for_param(IUnregistered)

        # Should return the original annotation
        assert result is IUnregistered


class TestAutowireCallable:
    """Tests for autowire_callable function."""

    def test_autowire_callable_sets_signature_defaults_to_depends(self) -> None:
        """Test that autowire_callable adds Depends defaults to registered parameters."""

        class IService:
            pass

        class ServiceImpl:
            pass

        container.add_scoped(IService, ServiceImpl)

        class TestClass:
            def __init__(self, value: int, svc: IService) -> None:
                self.svc = svc
                self.value = value

        autowire_callable(TestClass.__init__)
        sig = inspect.signature(TestClass.__init__)
        params = list(sig.parameters.values())

        # params: self, value, svc
        assert len(params) == 3

        svc_param = params[2]
        assert svc_param.name == "svc"
        assert svc_param.default is not inspect.Parameter.empty
        assert hasattr(svc_param.default, "dependency")
        # Dependency is now a wrapper
        assert callable(svc_param.default.dependency)

    def test_autowire_preserves_self_parameter(self) -> None:
        """Test that autowire_callable doesn't modify the self parameter."""

        class IService:
            pass

        class ServiceImpl:
            pass

        container.add_scoped(IService, ServiceImpl)

        class TestClass:
            def __init__(self, svc: IService) -> None:
                self.svc = svc

        autowire_callable(TestClass.__init__)
        sig = inspect.signature(TestClass.__init__)
        params = list(sig.parameters.values())

        # First parameter should still be self with no default
        self_param = params[0]
        assert self_param.name == "self"
        assert self_param.default is inspect.Parameter.empty

    def test_autowire_multiple_dependencies(self) -> None:
        """Test autowiring with multiple dependencies."""

        class IServiceA:
            pass

        class IServiceB:
            pass

        class IServiceC:
            pass

        class ServiceA:
            pass

        class ServiceB:
            pass

        class ServiceC:
            pass

        container.add_scoped(IServiceA, ServiceA)
        container.add_transient(IServiceB, ServiceB)
        container.add_singleton(IServiceC, ServiceC)

        class MultiDepClass:
            def __init__(self, a: IServiceA, b: IServiceB, c: IServiceC) -> None:
                self.a = a
                self.b = b
                self.c = c

        autowire_callable(MultiDepClass.__init__)
        sig = inspect.signature(MultiDepClass.__init__)
        params = list(sig.parameters.values())

        # All three service parameters should have Depends defaults
        assert len(params) == 4  # self + 3 services

        for param_name in ["a", "b", "c"]:
            param = next(p for p in params if p.name == param_name)
            assert param.default is not inspect.Parameter.empty
            assert hasattr(param.default, "dependency")

    def test_autowire_preserves_non_dependency_parameters(self) -> None:
        """Test that non-dependency parameters are preserved."""

        class IService:
            pass

        class ServiceImpl:
            pass

        container.add_scoped(IService, ServiceImpl)

        class MixedParams:
            def __init__(self, name: str, count: int, svc: IService) -> None:
                self.name = name
                self.count = count
                self.svc = svc

        autowire_callable(MixedParams.__init__)
        sig = inspect.signature(MixedParams.__init__)
        params = list(sig.parameters.values())

        # name and count should not have defaults (not registered)
        name_param = next(p for p in params if p.name == "name")
        count_param = next(p for p in params if p.name == "count")
        svc_param = next(p for p in params if p.name == "svc")

        assert name_param.default is inspect.Parameter.empty
        assert count_param.default is inspect.Parameter.empty
        assert svc_param.default is not inspect.Parameter.empty
        assert hasattr(svc_param.default, "dependency")

    def test_autowire_with_existing_defaults(self) -> None:
        """Test that autowire doesn't override existing parameter defaults."""

        class IService:
            pass

        class ServiceImpl:
            pass

        container.add_scoped(IService, ServiceImpl)

        class WithDefaults:
            def __init__(self, name: str = "default", count: int = 0) -> None:
                self.name = name
                self.count = count

        autowire_callable(WithDefaults.__init__)
        sig = inspect.signature(WithDefaults.__init__)
        params = list(sig.parameters.values())

        # Existing defaults should be preserved
        name_param = next(p for p in params if p.name == "name")
        count_param = next(p for p in params if p.name == "count")

        assert name_param.default == "default"
        assert count_param.default == 0

    def test_autowire_standalone_function(self) -> None:
        """Test autowiring a standalone function (not a method)."""

        class IService:
            pass

        class ServiceImpl:
            pass

        container.add_scoped(IService, ServiceImpl)

        def standalone_func(value: int, svc: IService) -> str:
            return f"value={value}"

        autowire_callable(standalone_func)
        sig = inspect.signature(standalone_func)
        params = list(sig.parameters.values())

        # svc should have Depends default
        svc_param = next(p for p in params if p.name == "svc")
        assert svc_param.default is not inspect.Parameter.empty
        assert hasattr(svc_param.default, "dependency")

    def test_autowire_respects_different_lifetimes(self) -> None:
        """Test that autowire correctly handles different service lifetimes."""

        class ITransient:
            pass

        class IScoped:
            pass

        class ISingleton:
            pass

        class TransientImpl:
            pass

        class ScopedImpl:
            pass

        class SingletonImpl:
            pass

        container.add_transient(ITransient, TransientImpl)
        container.add_scoped(IScoped, ScopedImpl)
        container.add_singleton(ISingleton, SingletonImpl)

        class MultiLifetime:
            def __init__(self, t: ITransient, s: IScoped, si: ISingleton) -> None:
                self.t = t
                self.s = s
                self.si = si

        autowire_callable(MultiLifetime.__init__)
        sig = inspect.signature(MultiLifetime.__init__)
        params = list(sig.parameters.values())

        t_param = next(p for p in params if p.name == "t")
        s_param = next(p for p in params if p.name == "s")
        si_param = next(p for p in params if p.name == "si")

        # All should have Depends, but with different use_cache settings
        assert t_param.default.use_cache is False  # Transient
        assert s_param.default.use_cache is True  # Scoped
        # Singleton uses a proxy with internal caching, so FastAPI cache is disabled
        assert si_param.default.use_cache is False


class TestAutowireEdgeCases:
    """Tests for edge cases in autowiring."""

    def test_autowire_no_parameters(self) -> None:
        """Test autowiring a callable with no parameters."""

        def no_params() -> str:
            return "hello"

        # Should not raise an error
        autowire_callable(no_params)
        sig = inspect.signature(no_params)
        assert len(sig.parameters) == 0

    def test_autowire_only_self_parameter(self) -> None:
        """Test autowiring a method with only self parameter."""

        class SimpleClass:
            def __init__(self) -> None:
                pass

        autowire_callable(SimpleClass.__init__)
        sig = inspect.signature(SimpleClass.__init__)
        params = list(sig.parameters.values())

        assert len(params) == 1
        assert params[0].name == "self"

    def test_autowire_unannotated_parameters_ignored(self) -> None:
        """Test that parameters without type annotations are ignored."""

        class IService:
            pass

        class ServiceImpl:
            pass

        container.add_scoped(IService, ServiceImpl)

        class TestClass:
            # Put unannotated param first to avoid Python signature ordering issues
            def __init__(self, unannotated, annotated: IService) -> None:  # type: ignore
                pass

        autowire_callable(TestClass.__init__)
        sig = inspect.signature(TestClass.__init__)
        params = list(sig.parameters.values())

        # Skip self parameter
        unannotated_param = params[1]
        annotated_param = params[2]

        assert unannotated_param.default is inspect.Parameter.empty
        assert annotated_param.default is not inspect.Parameter.empty

    def test_autowire_raises_error_for_implementation_injection(self) -> None:
        """Test that injecting an implementation instead of interface raises a helpful InterfaceMismatchError."""

        class IService:
            pass

        class ServiceImpl:
            pass

        container.add_scoped(IService, ServiceImpl)

        class WrongInjection:
            def __init__(self, svc: ServiceImpl) -> None:
                self.svc = svc

        # Should raise InterfaceMismatchError with specific message
        with pytest.raises(InterfaceMismatchError) as exc_info:
            autowire_callable(WrongInjection.__init__)

        error_msg = str(exc_info.value)
        assert "WrongInjection.__init__" in error_msg
        assert "Parameter 'svc' with type 'ServiceImpl'" in error_msg
        assert "registered as 'IService'" in error_msg
        assert "Change the type annotation" in error_msg

    def test_autowire_raises_error_for_scoped_in_singleton(self) -> None:
        """Test that injecting a Scoped dependency into a Singleton raises CaptiveDependencyError."""

        class IScoped:
            pass

        class ScopedImpl:
            pass

        class SingletonService:
            def __init__(self, scoped: IScoped) -> None:
                self.scoped = scoped

        container.add_scoped(IScoped, ScopedImpl)
        # We don't register SingletonService yet because we want to test autowire_callable directly first
        # or simulate what @injectable(ServiceLifetime.SINGLETON) does.

        # Should raise CaptiveDependencyError
        with pytest.raises(CaptiveDependencyError) as exc_info:
            autowire_callable(SingletonService.__init__, owner_lifetime=container.ServiceLifetime.SINGLETON)

        assert "Cannot inject Scoped dependency" in str(exc_info.value)
        assert "into Singleton service" in str(exc_info.value)
