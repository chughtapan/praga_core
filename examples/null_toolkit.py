from datetime import datetime, timedelta, timezone

from praga_core.retriever_toolkit import RetrieverToolkit


class NullToolkit(RetrieverToolkit):
    def __init__(self):
        super().__init__()

        # Register a state‑ful method (needs `self`)
        self._register_tool(
            method=self.echo,
            name="echo",
            cache=True,
            ttl=timedelta(minutes=30),
            paginate=False,
        )

    def echo(self, text: str):
        return [{"id": "e", "text": text, "metadata": {}}]

    # 1) A stateless utility tool – no cache, no pagination


@NullToolkit.tool()
def utc_time():
    now = datetime.now(tz=timezone.utc).isoformat()
    return [{"id": "utc", "text": now, "metadata": {}}]


if __name__ == "__main__":
    tk = NullToolkit()
    print("stateless:", tk.utc_time())
    print("stateful :", tk.echo("hello world"))
    print("speculate:", tk.speculate("what is the time?"))
