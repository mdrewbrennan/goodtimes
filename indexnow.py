"""Tell IndexNow (Bing and the search engines that share its index) which pages changed.

The daily refresh runs this right after it asks Netlify to rebuild: python3 indexnow.py https://example.com
It waits until the live sitemap shows a build newer than when it started, then submits every URL in it.
It does nothing while the live site asks search engines to stay away (PREVIEW in build.py).

Standard library only.
"""

import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlsplit

from build import INDEXNOW_KEY

WAIT_MINUTES = 15


def get(url):
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode()


def main():
    site = sys.argv[1].rstrip("/")
    started = datetime.now(timezone.utc)
    deadline = time.monotonic() + WAIT_MINUTES * 60
    while True:
        sitemap = get(f"{site}/sitemap.xml?t={int(time.time())}")
        built = [datetime.fromisoformat(m) for m in re.findall(r"<lastmod>(.*?)</lastmod>", sitemap)]
        if built and max(built) >= started:
            break
        if time.monotonic() > deadline:
            sys.exit(f"The new build wasn't live after {WAIT_MINUTES} minutes; not pinging IndexNow.")
        time.sleep(30)

    if re.search(r"^Disallow: /\s*$", get(f"{site}/robots.txt"), re.M):
        print("The site is still a preview (robots.txt blocks crawlers), so there's nothing to submit.")
        return

    urls = re.findall(r"<loc>(.*?)</loc>", sitemap)
    body = json.dumps({"host": urlsplit(site).hostname, "key": INDEXNOW_KEY,
                       "keyLocation": f"{site}/{INDEXNOW_KEY}.txt", "urlList": urls}).encode()
    req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        print(f"IndexNow accepted {len(urls)} URLs (HTTP {resp.status}).")


if __name__ == "__main__":
    main()
