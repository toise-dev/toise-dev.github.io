import contextlib
import importlib.util
import io
import os
import sys
import tempfile
import unittest

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)

SPEC = importlib.util.spec_from_file_location(
    "check_site", os.path.join(SCRIPTS_DIR, "check-site.py")
)
check_site = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_site)


class CheckSiteTests(unittest.TestCase):
    def write(self, root, relpath, content):
        path = os.path.join(root, relpath)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def minimal_page(self, body="", head=""):
        return (
            '<!doctype html><html><head><title>page</title>'
            '<meta name="viewport" content="width=device-width">'
            f"{head}</head><body>{body}</body></html>"
        )

    def valid_post(self, version="0.1.0", title="x"):
        return f"""<!doctype html>
<html>
<head>
<title>Toise {version}</title>
<meta name="viewport" content="width=device-width">
<meta property="og:description" content="summary">
<link rel="canonical" href="https://toise.dev/blog/v{version}/">
</head>
<body>
<h1>Announcing Toise {version} — {title}</h1>
<p class="meta">2024-01-01</p>
<a href="/blog/">Blog</a>
<a href="/">Home</a>
</body>
</html>"""

    def sitemap_with_posts(self, root, versions):
        locs = "".join(
            f"<url><loc>https://toise.dev/blog/v{v}/</loc></url>" for v in versions
        )
        self.write(
            root,
            "sitemap.xml",
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{locs}\n</urlset>\n",
        )

    def blog_index_with_posts(self, root, versions):
        links = "".join(f'<a href="/blog/v{v}/">post</a>' for v in versions)
        self.write(root, "blog/index.html", self.minimal_page(body=links))

    def build_clean_site(self, root):
        self.write(
            root,
            "index.html",
            self.minimal_page(body='<a href="/docs/0.1.0/">docs</a> <a href="/blog/">Blog</a>'),
        )
        self.blog_index_with_posts(root, ["0.1.0"])
        self.write(root, "blog/v0.1.0/index.html", self.valid_post("0.1.0", "x"))
        self.write(root, "docs/0.1.0/index.html", "<!doctype html><title>doc</title>")
        self.sitemap_with_posts(root, ["0.1.0"])

    def test_clean_site_reports_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            self.build_clean_site(root)
            self.assertEqual([], check_site.check(root))

    def test_broken_link(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(
                root,
                "index.html",
                self.minimal_page(body='<a href="/missing/">bad</a>'),
            )
            self.assertEqual(
                ["index.html: broken link: /missing/"],
                check_site.check(root),
            )

    def test_directory_without_slash(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(
                root,
                "index.html",
                self.minimal_page(body='<a href="/blog">bad</a>'),
            )
            self.write(root, "blog/index.html", self.minimal_page())
            self.assertEqual(
                ["index.html: link to directory without trailing slash: /blog"],
                check_site.check(root),
            )

    def test_docs_link_checks_first_segment_only(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(
                root,
                "index.html",
                self.minimal_page(body='<a href="/docs/0.1.0/deep/page/">x</a>'),
            )
            self.write(root, "docs/0.1.0/index.html", "<!doctype html><title>doc</title>")
            self.assertEqual([], check_site.check(root))

            self.write(
                root,
                "index.html",
                self.minimal_page(body='<a href="/docs/9.9.9/">x</a>'),
            )
            self.assertEqual(
                ["index.html: broken link: /docs/9.9.9/"],
                check_site.check(root),
            )

    def test_absolute_self_link(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(
                root,
                "index.html",
                self.minimal_page(
                    body='<a href="https://toise.dev/blog/">bad</a>',
                    head='<link rel="canonical" href="https://toise.dev/">',
                ),
            )
            self.assertEqual(
                ["index.html: absolute self-link: https://toise.dev/blog/"],
                check_site.check(root),
            )

    def test_post_metadata(self):
        cases = [
            (
                "h1",
                lambda p: p.replace(
                    "<h1>Announcing Toise 0.1.0 — x</h1>",
                    "<h1>Announcing Toise 0.2.0 — x</h1>",
                ),
                'blog/v0.1.0/index.html: h1 must read "Announcing Toise 0.1.0 — x"',
            ),
            (
                "meta",
                lambda p: p.replace(
                    '<p class="meta">2024-01-01</p>',
                    '<p class="meta">no date</p>',
                ),
                "blog/v0.1.0/index.html: meta line has no date",
            ),
            (
                "noblog",
                lambda p: p.replace('<a href="/blog/">Blog</a>\n', ""),
                "blog/v0.1.0/index.html: no link back to /blog/",
            ),
        ]

        for name, transform, expected in cases:
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as root:
                    self.write(root, "index.html", self.minimal_page())
                    self.blog_index_with_posts(root, ["0.1.0"])
                    self.sitemap_with_posts(root, ["0.1.0"])
                    self.write(
                        root,
                        "blog/v0.1.0/index.html",
                        transform(self.valid_post("0.1.0", "x")),
                    )
                    self.assertEqual([expected], check_site.check(root))

    def test_sitemap_and_index(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root, "index.html", self.minimal_page())
            self.write(root, "blog/index.html", self.minimal_page())
            self.write(root, "blog/v0.1.0/index.html", self.valid_post("0.1.0", "x"))
            self.write(
                root,
                "sitemap.xml",
                '<?xml version="1.0"?>'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>',
            )

            self.assertEqual(
                [
                    "blog/index.html: post missing from blog index: v0.1.0",
                    "sitemap.xml: post missing from sitemap: v0.1.0",
                ],
                check_site.check(root),
            )

    def test_malformed_sitemap(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root, "sitemap.xml", "<urlset><url>")
            self.write(root, "index.html", self.minimal_page())
            problems = check_site.check(root)
            self.assertEqual(1, len(problems))
            self.assertTrue(problems[0].startswith("sitemap.xml: not well-formed"))

    def test_exit_code(self):
        with tempfile.TemporaryDirectory() as root:
            self.build_clean_site(root)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = check_site.main([root])
            self.assertEqual(0, rc)
            self.assertTrue(buf.getvalue().strip().startswith("ok: "))
            self.assertIn("pages checked", buf.getvalue())

        with tempfile.TemporaryDirectory() as root:
            self.write(
                root,
                "index.html",
                self.minimal_page(body='<a href="/missing/">bad</a>'),
            )
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = check_site.main([root])
            self.assertEqual(1, rc)
            self.assertIn("broken link: /missing/", buf.getvalue())

    def test_head_metadata(self):
        cases = [
            ("og", '<meta property="og:description" content="summary">', "", "missing og:description"),
            ("canonical", '<link rel="canonical" href="https://toise.dev/blog/v0.1.0/">', "", "canonical must be https://toise.dev/blog/v0.1.0/"),
            ("title", "<title>Toise 0.1.0</title>", "", "missing <title>"),
            ("viewport", '<meta name="viewport" content="width=device-width">', "", "missing viewport meta"),
        ]
        for name, old, new, expected in cases:
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as root:
                    self.write(root, "index.html", self.minimal_page())
                    self.blog_index_with_posts(root, ["0.1.0"])
                    self.sitemap_with_posts(root, ["0.1.0"])
                    post = self.valid_post("0.1.0", "x")
                    self.assertIn(old, post)
                    self.write(root, "blog/v0.1.0/index.html", post.replace(old, new))
                    self.assertEqual([f"blog/v0.1.0/index.html: {expected}"], check_site.check(root))

    def test_unreadable_page_is_reported(self):
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "index.html"), "wb") as f:
                f.write(b"<title>x</title>\xff\xfe")
            problems = check_site.check(root)
            self.assertEqual(1, len(problems))
            self.assertTrue(problems[0].startswith("index.html: unreadable:"))

    def test_hidden_and_docs_dirs_are_skipped(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root, "docs/x/index.html", '<a href="/missing/">')
            self.write(root, ".cache/page.html", '<a href="/missing/">')
            self.assertEqual([], check_site.check(root))


if __name__ == "__main__":
    unittest.main()
