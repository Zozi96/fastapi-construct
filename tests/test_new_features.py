import asyncio

from fastapi_construct import ServiceLifetime, container, injectable


# We define classes inside tests or re-register them to ensure they exist in the registry
# regardless of other tests clearing it.


def test_async_init():
    container.default_container.reset()

    @injectable(ServiceLifetime.SCOPED)
    class AsyncService:
        def __init__(self):
            self.initialized = False

        async def on_startup(self):
            await asyncio.sleep(0.01)
            self.initialized = True

    async def run_test():
        # Resolve using resolve_async
        service = await container.default_container.resolve_async(AsyncService)
        assert service.initialized is True

    asyncio.run(run_test())


def test_manual_scope():
    container.default_container.reset()

    @injectable(ServiceLifetime.SCOPED)
    class ScopedService:
        pass

    # Outside scope - should be transient-like (new instance every time)
    s1 = container.default_container.resolve(ScopedService)
    s2 = container.default_container.resolve(ScopedService)
    assert s1 is not s2

    # Inside scope
    with container.default_container.scope():
        s3 = container.default_container.resolve(ScopedService)
        s4 = container.default_container.resolve(ScopedService)
        assert s3 is s4
        assert s3 is not s1

        # Nested resolution
        s5 = container.default_container.resolve(ScopedService)
        assert s5 is s3

    # New scope
    with container.default_container.scope():
        s6 = container.default_container.resolve(ScopedService)
        assert s6 is not s3


if __name__ == "__main__":
    test_manual_scope()
    test_async_init()
