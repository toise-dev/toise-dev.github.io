#!/usr/bin/env python3
"""Check the static site for common problems."""

import os
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

SELF_HOSTS = ("https://toise.dev/", "http://toise.dev/")


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.hrefs = []
        self.srcs = []
        self.title = ""
        self.viewport = False
        self.h1_count = 0
        self.h1_texts = []
        self._in_title = False
        self._title_parts = []
        self._in_h1 = False
        self._h1_parts = []

    def _handle_tag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))

        if tag == "title":
            self._in_title = True
            self._title_parts = []
        elif tag == "h1":
            self.h1_count += 1
            self._in_h1 = True
            self._h1_parts = []

        if tag == "meta" and attrs.get("name") == "viewport":
            self.viewport = True

        href = attrs.get("href")
        if href is not None:
            self.hrefs.append(href)

        src = attrs.get("src")
        if src is not None:
            self.srcs.append(src)

    def handle_starttag(self, tag, attrs):
        self._handle_tag(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self._handle_tag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
            self.title = "".join(self._title_parts).strip()
        elif tag == "h1":
            self._in_h1 = False
            self.h1_texts.append("".join(self._h1_parts).strip())

    def handle_data(self, data):
        if self._in_title:
            self._title_parts.append(data)
        if self._in_h1:
            self._h1_parts.append(data)


def find_html_files(root):
    pages = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "docs" and not d.startswith(".")]
        for filename in filenames:
            if filename.endswith(".html"):
                pages.append(os.path.join(dirpath, filename))
    return sorted(pages)


def relative_path(path, root):
    return os.path.relpath(path, root).replace(os.sep, "/")


def parse_file(path):
    with open(path, encoding="utf-8") as f:
        source = f.read()
    parser = PageParser()
    parser.feed(source)
    parser.close()
    return parser, source


def is_absolute_exception(tag, attrs):
    if tag == "link":
        rel = attrs.get("rel", "")
        return "canonical" in rel.lower().split()
    if tag == "meta":
        return attrs.get("property") == "og:url"
    return False


def check_internal_link(root, value, rel, out):
    path = value.split("?", 1)[0].split("#", 1)[0]
    if not path:
        return

    if path.startswith("/docs/"):
        rest = path[len("/docs/") :]
        first = rest.split("/", 1)[0] if rest else ""
        target = os.path.join(root, "docs", first) if first else os.path.join(root, "docs")
        if os.path.isdir(target):
            return
        out.add((rel, f"broken link: {path}"))
        return

    target = os.path.join(root, path.lstrip("/"))
    if path.endswith("/"):
        if os.path.isdir(target) and os.path.isfile(os.path.join(target, "index.html")):
            return
        out.add((rel, f"broken link: {path}"))
        return

    if os.path.isfile(target):
        return
    if os.path.isdir(target):
        out.add((rel, f"link to directory without trailing slash: {path}"))
        return
    out.add((rel, f"broken link: {path}"))


def is_blog_post(rel):
    parts = rel.split("/")
    return len(parts) == 3 and parts[0] == "blog" and parts[1].startswith("v") and parts[2] == "index.html"


def check_blog_post(rel, version, parser, source, out):
    expected_prefix = f"Announcing Toise {version} — "
    h1_ok = parser.h1_count == 1 and parser.h1_texts and parser.h1_texts[0].startswith(expected_prefix)
    if not h1_ok:
        title = ""
        if parser.h1_texts:
            first = parser.h1_texts[0]
            if " — " in first:
                title = first.split(" — ", 1)[1]
            else:
                title = first
        out.add((rel, f'h1 must read "Announcing Toise {version} — {title}"'))

    meta_match = re.search(r'<p class="meta">(.*?)</p>', source, re.S)
    if not (meta_match and re.search(r"\d{4}-\d{2}-\d{2}", meta_match.group(1))):
        out.add((rel, "meta line has no date"))

    og_ok = False
    for tag, attrs in parser.tags:
        if tag == "meta" and attrs.get("property") == "og:description":
            if attrs.get("content", "").strip():
                og_ok = True
            break
    if not og_ok:
        out.add((rel, "missing og:description"))

    canonical = f"https://toise.dev/blog/v{version}/"
    canonical_ok = False
    for tag, attrs in parser.tags:
        if tag == "link" and "canonical" in (attrs.get("rel", "").lower().split()):
            if attrs.get("href") == canonical:
                canonical_ok = True
            break
    if not canonical_ok:
        out.add((rel, f"canonical must be {canonical}"))

    if "/blog/" not in parser.hrefs:
        out.add((rel, "no link back to /blog/"))


def check_page_from_parser(rel, root, parser, source):
    problems = set()

    if not parser.title:
        problems.add((rel, "missing <title>"))
    if not parser.viewport:
        problems.add((rel, "missing viewport meta"))

    for tag, attrs in parser.tags:
        for attr_name in ("href", "src"):
            value = attrs.get(attr_name)
            if value is None:
                continue
            if value.startswith(SELF_HOSTS):
                if not is_absolute_exception(tag, attrs):
                    problems.add((rel, f"absolute self-link: {value}"))
            elif value.startswith("/") and not value.startswith("//"):
                check_internal_link(root, value, rel, problems)

    if is_blog_post(rel):
        version = rel.split("/")[1][1:]
        check_blog_post(rel, version, parser, source, problems)

    return problems


def find_post_versions(root):
    blog_dir = os.path.join(root, "blog")
    if not os.path.isdir(blog_dir):
        return []
    versions = []
    for name in os.listdir(blog_dir):
        if name.startswith("v") and name != "v":
            if os.path.isdir(os.path.join(blog_dir, name)):
                versions.append(name[1:])
    return sorted(versions)


def read_sitemap_locs(root):
    path = os.path.join(root, "sitemap.xml")
    if not os.path.exists(path):
        return set(), None

    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError) as exc:
        return None, f"not well-formed: {exc}"

    locs = set()
    for elem in tree.iter():
        if elem.tag.rsplit("}", 1)[-1] == "loc":
            if elem.text and elem.text.strip():
                locs.add(elem.text.strip())
    return locs, None


def check_rule4(root, page_info, problems):
    versions = find_post_versions(root)

    locs, parse_error = read_sitemap_locs(root)
    if parse_error:
        problems.add(("sitemap.xml", parse_error))
        return

    blog_index = page_info.get("blog/index.html")
    blog_hrefs = set(blog_index.hrefs) if blog_index else set()

    for version in versions:
        loc = f"https://toise.dev/blog/v{version}/"
        href = f"/blog/v{version}/"
        if loc not in locs:
            problems.add(("sitemap.xml", f"post missing from sitemap: v{version}"))
        if href not in blog_hrefs:
            problems.add(("blog/index.html", f"post missing from blog index: v{version}"))


def check(root):
    root = os.fspath(root)
    pages = find_html_files(root)
    problems = set()
    page_info = {}

    for path in pages:
        rel = relative_path(path, root)
        try:
            parser, source = parse_file(path)
        except (OSError, UnicodeDecodeError) as exc:
            problems.add((rel, f"unreadable: {exc}"))
            continue
        page_info[rel] = parser
        problems.update(check_page_from_parser(rel, root, parser, source))

    check_rule4(root, page_info, problems)
    return ["{}: {}".format(file, message) for file, message in sorted(problems)]


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    root = os.fspath(argv[0]) if argv else os.getcwd()
    page_count = len(find_html_files(root))
    problems = check(root)

    if problems:
        for line in problems:
            print(line)
        return 1

    print(f"ok: {page_count} pages checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
