"""The one way the backend builds an OpenSearch client (issue 715). The app, bootstrap and every job
command line call `build_client`, so how JAVV signs in and checks TLS cannot drift between them;
`test_opensearch_client.py` fails on an `AsyncOpenSearch(` anywhere else in `backend/src`.

- **No login unless a username is set.** `("", "")` would still send `Authorization: Basic Og==`,
  which a secured store answers with a 401 that points nowhere useful.
- **`ssl_show_warn=False`.** With verification off, opensearch-py warns once per connection through
  `warnings`, outside the log pipeline. `warn_about_transport` says it once, structured and counted.
"""

from urllib.parse import urlsplit

import structlog
from opensearchpy import AsyncOpenSearch

from backend.core.metrics import CONFIG_WARNINGS
from backend.core.settings import Settings

log = structlog.get_logger()


def build_client(settings: Settings) -> AsyncOpenSearch:
    username = settings.opensearch_username
    password = settings.opensearch_password.get_secret_value()
    return AsyncOpenSearch(
        hosts=[settings.opensearch_url],
        timeout=settings.request_timeout,
        http_auth=(username, password) if username else None,
        verify_certs=settings.opensearch_verify_certs,
        ca_certs=settings.opensearch_ca_bundle.strip() or None,
        ssl_show_warn=False,
    )


def warn_about_transport(settings: Settings) -> None:
    """Start-up warnings for a connection weaker than it looks; each is one line and one count."""
    scheme = urlsplit(settings.opensearch_url).scheme
    if scheme == "https" and not settings.opensearch_verify_certs:
        log.warning("opensearch certificates not checked", setting="JAVV_OPENSEARCH_VERIFY_CERTS")
        CONFIG_WARNINGS.labels("JAVV_OPENSEARCH_VERIFY_CERTS").inc()
    if scheme == "http" and settings.opensearch_username:
        log.warning("opensearch password sent over plain http", setting="JAVV_OPENSEARCH_URL")
        CONFIG_WARNINGS.labels("JAVV_OPENSEARCH_URL").inc()
