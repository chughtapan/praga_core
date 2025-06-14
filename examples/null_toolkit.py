from datetime import datetime, timedelta, timezone
from typing import List, Optional

from praga_core.retriever_toolkit import RetrieverToolkit
from praga_core.types import Document, TextDocument


class NullToolkit(RetrieverToolkit):
    def __init__(self) -> None:
        super().__init__()

        # Register a state‑ful method (needs `self`)
        self.register_tool(
            method=self.echo,
            name="echo",
            cache=True,
            ttl=timedelta(minutes=30),
            paginate=False,
        )

    def get_document_by_id(self, document_id: str) -> Optional[Document]:
        """Get document by ID - example implementation returns None."""
        return None

    def echo(self, text: str) -> List[Document]:
        return [TextDocument(id="e", content=text)]

    # 1) A stateless utility tool – no cache, no pagination


@NullToolkit.tool()
def utc_time() -> List[Document]:
    now = datetime.now(tz=timezone.utc).isoformat()
    return [TextDocument(id="utc", content=now)]


if __name__ == "__main__":
    tk = NullToolkit()
    print("stateless:", tk.utc_time())
    print("stateful :", tk.echo("hello world"))
    print("speculate:", tk.speculate("what is the time?"))
