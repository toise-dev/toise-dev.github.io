# toise-dev.github.io

Source of the [toise.dev](https://toise.dev) website.

Static HTML, no build step. Edit `index.html` directly.

Served via GitHub Pages, deployed automatically on push to `main`.

## Publishing a release post

1. Copy the latest post, e.g. `blog/v0.18.0/`, to `blog/vX.Y.Z/` and rewrite it.
   Keep the `<h1>` form "Announcing Toise X.Y.Z — title", the date in
   `<p class="meta">`, the `og:description`, and the Blog link in the header.
2. Run `python3 scripts/build-blog-index.py` from the repository root. It
   rebuilds the list in `blog/index.html` and adds the post to `sitemap.xml`.
3. Open a pull request against `main`.

The homepage Blog link points to `/blog/`, so it does not change per release.

See the main Toise project at
[github.com/toise-dev/toise](https://github.com/toise-dev/toise).

## License

Apache License 2.0. See [LICENSE](./LICENSE).
