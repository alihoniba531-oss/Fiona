import asyncio

from utils.background_tasks import create_background_task, shutdown_background_tasks


def test_background_task_exception_is_consumed_without_sensitive_text(capsys):
    async def scenario():
        async def fail():
            raise RuntimeError("private prompt contents")

        task = create_background_task(fail(), label="unit-test")
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0)

    asyncio.run(scenario())

    output = capsys.readouterr().out
    assert "task=unit-test failed type=RuntimeError" in output
    assert "private prompt contents" not in output


def test_shutdown_cancels_tracked_tasks():
    async def scenario():
        started = asyncio.Event()

        async def wait_forever():
            started.set()
            await asyncio.Event().wait()

        task = create_background_task(wait_forever(), label="shutdown-test")
        await started.wait()
        await shutdown_background_tasks()
        assert task.cancelled()

    asyncio.run(scenario())
