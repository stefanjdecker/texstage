# www.texstage.org

The project homepage: one static page (`index.html`, `styles.css`, `favicon.svg`) with no
build step and no external requests. Its screenshots and manual PDF are not copied here; `maintenance/build_site.py` takes them from `docs/` when it assembles the site.

## Preview

```sh
python maintenance/build_site.py
python -m http.server 8000 --directory _site
```

Then open http://localhost:8000. The script also checks every local link, image and anchor.
The demonstration video is not part of this repository: the page links to it on YouTube
(https://youtu.be/hPgWYiSEhYU), and its chapter links use `?t=` offsets in seconds. When
the video is recut, update the heading, the hero button and the chapter list together.

## Publishing on GitHub Pages

`.github/workflows/pages.yml` assembles the site and deploys it on every push to `main` that
changes the site or the media it uses. Once per repository:

1. **Settings → Pages → Build and deployment → Source:** GitHub Actions.
2. **Settings → Pages → Custom domain:** `www.texstage.org`, then **Enforce HTTPS** once the
   certificate is issued. With an Actions deployment, GitHub ignores a `CNAME` file, so the
   domain is set here only.
3. At the DNS provider of texstage.org:
   - `www` → `CNAME` → `stefanjdecker.github.io`
   - the apex `texstage.org` → `A` records `185.199.108.153`, `185.199.109.153`,
     `185.199.110.153`, `185.199.111.153` (optionally `AAAA` `2606:50c0:8000::153` to
     `2606:50c0:8003::153`), so that GitHub redirects it to `www`.
4. **Account settings → Pages → Verified domains:** verify texstage.org, so that no other
   GitHub account can claim it.

GitHub's [custom domain guide](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site)
has the details.
