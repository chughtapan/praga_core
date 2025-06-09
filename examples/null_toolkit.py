from datetime import datetime, timedelta, timezone
from typing import List

from praga_core.retriever_toolkit import RetrieverToolkit
from praga_core.types import Document


class NullToolkit(RetrieverToolkit):
    def __init__(self):
        super().__init__()

        # Register a state‑ful method (needs `self`)
        self.register_tool(
            method=self.echo,
            name="echo",
            cache=True,
            ttl=timedelta(minutes=30),
            paginate=False,
        )

    def echo(self, text: str) -> List[Document]:
        return [Document(id="e", content=text, metadata={})]

    # 1) A stateless utility tool – no cache, no pagination


@NullToolkit.tool()
def utc_time() -> List[Document]:
    now = datetime.now(tz=timezone.utc).isoformat()
    return [Document(id="utc", content=now, metadata={})]


if __name__ == "__main__":
    tk = NullToolkit()
    print("stateless:", tk.utc_time())
    print("stateful :", tk.echo("hello world"))
    print("speculate:", tk.speculate("what is the time?"))
