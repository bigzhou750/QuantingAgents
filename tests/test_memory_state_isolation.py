import pytest

from app.services.memory_state_manager import MemoryStateManager


@pytest.mark.asyncio
async def test_in_memory_task_lookup_requires_matching_owner():
    manager = MemoryStateManager()
    await manager.create_task("task-a", "user-a", "000001")
    await manager.create_task("task-b", "user-b", "000002")

    assert await manager.get_user_task_dict("user-a", "task-a")
    assert await manager.get_user_task_dict("user-a", "task-b") is None
    assert await manager.delete_user_task("user-a", "task-b") is False
    assert await manager.get_user_task_dict("user-b", "task-b")


@pytest.mark.asyncio
async def test_in_memory_operations_fail_closed_without_scope():
    manager = MemoryStateManager()
    await manager.create_task("task-a", "user-a", "000001")

    with pytest.raises(RuntimeError, match="scope"):
        await manager.get_task_dict("task-a")
    with pytest.raises(RuntimeError, match="scope"):
        await manager.list_all_tasks()
    with pytest.raises(RuntimeError, match="scope"):
        await manager.get_statistics()
    with pytest.raises(RuntimeError, match="scope"):
        await manager.remove_task("task-a")
