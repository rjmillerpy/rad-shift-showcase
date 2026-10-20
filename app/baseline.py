"""The public edition (app/plugins.py): what runs when no private package is installed.

- no extra routers (the admin console is private);
- generators: the RSS adapter, and no web scraper;
- Chronicle: the plain prompt;
- Amble: the demo town's bindings.
"""

from app.amble.content.constants import DEMO_BINDINGS_PATH
from app.chronicle.prompt import PlainPrompt
from app.generators.platforms.rss import RssAdapter
from app.plugins import PUBLIC, Edition

EDITION = Edition(
    name=PUBLIC,
    routers=(),
    platform_adapters=(RssAdapter(),),
    web_scraper=None,
    chronicle_prompt=PlainPrompt(),
    amble_bindings_path=DEMO_BINDINGS_PATH,
)
