#!/usr/bin/env python3
"""Copy and compress the site's binary assets (run once; the results are committed).

Sources live in the repository (docs/assets/readme, app/static) except two local-only files that the owner produced
(the promo video and the social preview), which are passed by their absolute path below. Needs Pillow; build.py does not.
"""
import shutil
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
MAIN = Path("/Users/chandery/PageTide")          # the main checkout holds the git-ignored .local/ files
OUT = HERE / "assets"
README = REPO / "docs" / "assets" / "readme"


def webp(src, dst, width, quality=80):
    im = Image.open(src).convert("RGB")
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    im.save(dst, "WEBP", quality=quality, method=6)


def main():
    OUT.mkdir(exist_ok=True)
    for lang in ("en", "zh"):
        for name in ("today", "reader-ask", "profile", "graph", "import", "weekly"):
            f = f"{lang}-{name}.png"
            shutil.copy2(README / f, OUT / f)
            webp(README / f, OUT / f.replace(".png", ".webp"), 1000)
    for lang in ("en", "zh"):
        webp(README / f"{lang}-today.png", OUT / f"{lang}-today-hero.webp", 1600, 84)
    webp(README / "cover.jpg", OUT / "cover.webp", 1280)
    shutil.copy2(README / "cover.jpg", OUT / "cover.jpg")
    shutil.copy2(MAIN / ".local/readme-video/pagetide-readme-cover-first.mp4", OUT / "pagetide-promo.mp4")
    shutil.copy2(MAIN / ".local/social/pagetide-social-preview.png", OUT / "og.png")
    shutil.copy2(REPO / "app/static/wordmark.png", OUT / "wordmark.png")
    shutil.copy2(REPO / "app/static/wordmark-dark.png", OUT / "wordmark-dark.png")
    icon = Image.open(README / "icon.png").convert("RGBA")
    icon.resize((180, 180), Image.LANCZOS).save(HERE / "apple-touch-icon.png")
    icon.resize((192, 192), Image.LANCZOS).save(HERE / "icon-192.png")
    icon.save(HERE / "icon-256.png")
    shutil.copy2(REPO / "app/static/favicon.png", HERE / "favicon.png")
    icon.save(HERE / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    icon.resize((96, 96), Image.LANCZOS).save(OUT / "icon.png")   # masthead (shown at 48 css px)


if __name__ == "__main__":
    main()
