#!/usr/bin/env python3
"""
Debug script v2: broader search for LinkedIn's hidden result count.
Dumps HTML to file so we can inspect it, and captures ALL network responses.
Run with Chrome closed.

Usage: python3 debug_search.py
"""

import re
import json
from browser import create_browser, close_browser

SEARCH_URL = (
    "https://www.linkedin.com/search/results/people/"
    "?keywords=product%20marketing%20manager"
    "&origin=FACETED_SEARCH"
    "&followerOf=%5B%22ACoAACVqxQABfV4w4zWyBJfdmQYyUxah1ZW--g8%22%5D"
)


def main():
    pw, context = create_browser(headless=False)
    captured_responses = []

    try:
        page = context.new_page()

        # Capture ALL responses (not just search/voyager)
        def handle_response(response):
            url = response.url
            if "linkedin.com" in url and response.status == 200:
                content_type = response.headers.get("content-type", "")
                if "json" in content_type or "graphql" in url or "voyager" in url:
                    try:
                        body = response.text()
                        captured_responses.append({"url": url, "body": body})
                    except Exception:
                        pass

        page.on("response", handle_response)

        print("Navigating to search URL...")
        page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=30000)
        print("Waiting for page to fully load...")
        page.wait_for_timeout(8000)

        # Scroll down to trigger any lazy loading
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(3000)

        # === NETWORK RESPONSES ===
        print(f"\nCaptured {len(captured_responses)} JSON responses")
        print("=" * 60)
        for i, resp in enumerate(captured_responses):
            body = resp["body"]
            # Look for ANY number > 100 near keywords that suggest a count
            has_count = bool(re.search(
                r'(?:total|count|result|paging|numFound|hits)',
                body, re.IGNORECASE
            ))
            if has_count:
                print(f"\n--- Response {i+1} ({len(body)} chars): {resp['url'][:100]} ---")
                # Find all number-bearing patterns
                for kw in ["total", "count", "result", "paging", "numFound", "hits"]:
                    for m in re.finditer(kw, body, re.IGNORECASE):
                        start = max(0, m.start() - 30)
                        end = min(len(body), m.end() + 60)
                        snippet = body[start:end].replace("\n", " ")
                        print(f"  ...{snippet}...")

        # === PAGE SOURCE: dump to file and search ===
        print("\n" + "=" * 60)
        print("Saving page source to data/debug_page_source.html")
        html = page.content()
        with open("data/debug_page_source.html", "w") as f:
            f.write(html)
        print(f"Saved {len(html)} chars")

        # Search for any number between 100 and 100000 near "result" keywords
        print("\nSearching HTML for large numbers near result-like keywords...")
        for m in re.finditer(r'(\d{3,6})', html):
            num = int(m.group(1))
            if 100 <= num <= 99999:
                start = max(0, m.start() - 60)
                end = min(len(html), m.end() + 60)
                context = html[start:end]
                # Only print if nearby text suggests it's a count
                if re.search(r'result|total|count|paging|search|found', context, re.IGNORECASE):
                    print(f"  [{num}] ...{context[:120]}...")

        # === VISIBLE TEXT ===
        print("\n" + "=" * 60)
        text = page.inner_text("body")
        visible_results = len(re.findall(r' • (?:1st|2nd|3rd\+?)', text))
        print(f"Visible results on page: {visible_results}")

        print("\nDONE.")

    finally:
        close_browser(pw, context)


if __name__ == "__main__":
    main()
