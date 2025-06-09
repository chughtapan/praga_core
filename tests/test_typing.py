from datetime import datetime, timedelta

from praga_core.retriever_toolkit import RetrieverToolkit


class DemoToolkit(RetrieverToolkit):
    def __init__(self):
        super().__init__()


@DemoToolkit.tool(cache=True, ttl=timedelta(minutes=5))
def get_timestamp():
    return [{"id": "ts", "text": datetime.now().isoformat(), "metadata": {}}]


@DemoToolkit.tool(cache=False)
def get_greeting(name: str):
    return [{"id": "greet", "text": f"Hello, {name}!", "metadata": {"name": name}}]


def test_toolkit():
    tk = DemoToolkit()
    assert "get_timestamp" in tk._tools
    assert "get_greeting" in tk._tools
