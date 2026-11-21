from penshot.neopen.task.workflow_registry import WorkflowRegistry


def test_workflow_registry_reuses_cached_instance():
    registry = WorkflowRegistry(max_cache_size=2)
    workflow = object()

    registry.put("cfg-a", workflow)

    assert registry.get("cfg-a") is workflow
    assert registry.keys() == ["cfg-a"]


def test_workflow_registry_evicts_oldest_entry():
    registry = WorkflowRegistry(max_cache_size=2)

    registry.put("cfg-a", "workflow-a")
    registry.put("cfg-b", "workflow-b")
    registry.put("cfg-c", "workflow-c")

    assert registry.get("cfg-a") is None
    assert registry.get("cfg-b") == "workflow-b"
    assert registry.get("cfg-c") == "workflow-c"


class _ClosableWorkflow:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_workflow_registry_closes_evicted_workflow():
    registry = WorkflowRegistry(max_cache_size=2)
    first, second, third = _ClosableWorkflow(), _ClosableWorkflow(), _ClosableWorkflow()

    registry.put("a", first)
    registry.put("b", second)
    registry.put("c", third)

    assert first.closed
    assert not second.closed
    assert not third.closed


def test_workflow_registry_pop_and_clear_close_workflow():
    registry = WorkflowRegistry(max_cache_size=10)
    first, second = _ClosableWorkflow(), _ClosableWorkflow()

    registry.put("a", first)
    registry.put("b", second)

    registry.pop("a")
    assert first.closed
    assert not second.closed

    registry.clear(close_workflows=True)
    assert second.closed
