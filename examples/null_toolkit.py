from datetime import datetime, timedelta, timezone
from typing import List, Optional

from praga_core.agents import RetrieverToolkit
from praga_core.types import Page, PageURI, TextPage


class NullToolkit(RetrieverToolkit):
    def __init__(self, root: str = "null") -> None:
        super().__init__()
        self.root = root

        # Register a state-ful method (needs `self`)
        self.register_tool(
            method=self.echo,
            name="echo",
            cache=True,
            ttl=timedelta(minutes=30),
            paginate=False,
        )

    def get_page_by_uri(self, uri: PageURI) -> Optional[Page]:
        """Get page by URI - example implementation returns None."""
        return None

    def echo(self, text: str) -> List[Page]:
        uri = PageURI(root=self.root, type="echo", id="e1", version=1)
        return [TextPage(uri=uri, content=text)]

    # 1) A stateless utility tool – no cache, no pagination
    @staticmethod
    def utc_time() -> List[Page]:
        now = datetime.now(tz=timezone.utc).isoformat()
        uri = PageURI(root="null", type="time", id="utc", version=1)
        return [TextPage(uri=uri, content=now)]


if __name__ == "__main__":
    tk = NullToolkit()
    print("stateless:", tk.utc_time())
    print("stateful :", tk.echo("hello world"))
    # Note: speculate is no longer part of the base toolkit
