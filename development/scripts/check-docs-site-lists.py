"""Fail when a list on the built docs site rendered as text inside a paragraph or a quote.

The site's Markdown needs four spaces to nest a list, and a blank line between a paragraph and a
list after it. GitHub renders both without them, so a page can read right on GitHub and show its
steps as one paragraph on the site; the strict build passes either way. Run after the build:
    python3 development/scripts/check-docs-site-lists.py docs-site/site
"""

import re
import sys
from pathlib import Path

MARKER = re.compile(r"\n\s*(?:[-*] |\d+\. )")


def merged_lists(page: Path) -> list[str]:
    html = page.read_text()
    article = html[html.find("<article") : html.find("</article>")]
    article = re.sub(r"<pre.*?</pre>", "", article, flags=re.DOTALL)
    found = []
    for _, block in re.findall(r"<(p|blockquote)>(.*?)</\1>", article, re.DOTALL):
        text = re.sub(r"<[^>]+>", "", block)
        if MARKER.search(text):
            found.append(" ".join(text.split())[:100])
    return found


def main(site: str) -> int:
    failures = 0
    for page in sorted(Path(site).rglob("index.html")):
        for text in merged_lists(page):
            print(f"{page}: a list rendered as text: {text}")
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
