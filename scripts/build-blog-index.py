#!/usr/bin/env python3
"""Rebuild the post list in blog/index.html and add missing posts to sitemap.xml.

Run from the repository root after adding blog/vX.Y.Z/index.html:

    python3 scripts/build-blog-index.py

Each post must carry an <h1> of the form "Announcing Toise X.Y.Z — title",
a <p class="meta"> containing its release date, and an og:description.
Python standard library only; the site itself stays static.
"""

import glob
import html
import re
import sys
from datetime import date

INDEX = "blog/index.html"
SITEMAP = "sitemap.xml"
LIST_RE = re.compile(r'(<ul class="posts">)(.*?)(\n        </ul>)', re.S)


def read_post(path):
    s = open(path, encoding="utf-8").read()
    version = path.split("/")[1][1:]
    h1 = re.search(r"<h1>([^<]*)</h1>", s)
    meta = re.search(r'<p class="meta">([^<]*)</p>', s)
    og = re.search(r'property="og:description"\s+content="([^"]*)"', s)
    if not (h1 and meta and og and " — " in h1.group(1)):
        sys.exit(f"{path}: missing <h1> with ' — ', <p class=\"meta\"> or og:description")
    released = re.search(r"\d{4}-\d{2}-\d{2}", meta.group(1))
    if not released:
        sys.exit(f"{path}: no date in <p class=\"meta\">")
    if 'href="/blog/"' not in s:
        print(f"warning: {path} has no Blog link back to /blog/", file=sys.stderr)
    return {
        "key": tuple(int(p) for p in version.split(".")),
        "version": version,
        "title": h1.group(1).split(" — ", 1)[1],
        "date": released.group(0),
        "summary": og.group(1),
    }


def render(posts):
    return "".join(
        f"""
          <li>
            <span class="when">{p['version']} · {p['date']}</span>
            <h2><a href="/blog/v{p['version']}/">Toise {p['version']} — {html.escape(p['title'], quote=False)}</a></h2>
            <p>{p['summary']}</p>
          </li>"""
        for p in posts
    )


def update_sitemap(posts):
    s = open(SITEMAP, encoding="utf-8").read()
    anchor = "  <url>\n    <loc>https://toise.dev/blog/</loc>"
    if anchor not in s:
        sys.exit(f"{SITEMAP}: no entry for https://toise.dev/blog/ to anchor new posts after")
    end = s.index("</url>\n", s.index(anchor)) + len("</url>\n")
    added = []
    for p in posts:
        loc = f"https://toise.dev/blog/v{p['version']}/"
        if loc in s:
            continue
        entry = f"""  <url>
    <loc>{loc}</loc>
    <lastmod>{date.today().isoformat()}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.5</priority>
  </url>
"""
        s = s[:end] + entry + s[end:]
        added.append(p["version"])
    open(SITEMAP, "w", encoding="utf-8").write(s)
    return added


def main():
    posts = sorted(
        (read_post(p) for p in glob.glob("blog/v*/index.html")),
        key=lambda p: p["key"],
        reverse=True,
    )
    s = open(INDEX, encoding="utf-8").read()
    if not LIST_RE.search(s):
        sys.exit(f'{INDEX}: no <ul class="posts"> block found')
    s = LIST_RE.sub(lambda m: m.group(1) + render(posts) + m.group(3), s, count=1)
    open(INDEX, "w", encoding="utf-8").write(s)
    added = update_sitemap(posts)
    print(f"{len(posts)} posts listed; sitemap additions: {', '.join(added) or 'none'}")


if __name__ == "__main__":
    main()
