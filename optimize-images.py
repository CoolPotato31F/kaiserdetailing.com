#!/usr/bin/env python3
"""
Kaiser's Detail Co. — Image Optimizer

Optimizes the website's images (before/after sliders, gallery, favicon, social
share image) for fast loading on the free-tier VM, where outbound bandwidth is
limited. It resizes oversized images to a sensible max width, strips metadata,
re-encodes at a good quality, and (optionally) also writes modern .webp copies.

WHY THESE SIZES?
The site displays images at these real sizes (from the CSS):
  • Before/after sliders (.ba-wrap): 100% width, 210px tall. A single card is
    ~280–540px wide on screen. At 2x (retina) that's up to ~1080px wide.
  • Gallery (.gal-item): 4:3 tiles; the wide spanning tiles render up to ~720px
    wide → ~1440px at 2x.
So a max width around 1600px keeps everything crisp on high-DPI screens while
shrinking typical phone photos (often 3000–4000px wide) by a large margin.
Smaller, role-specific caps are available via --profile.

USAGE
  python optimize_images.py                 # optimize ./static in place (with backups)
  python optimize_images.py --src ./photos --dst ./static
  python optimize_images.py --webp          # also emit .webp copies
  python optimize_images.py --max-width 1280
  python optimize_images.py --profile slider # tighter cap for slider-only images
  python optimize_images.py --dry-run        # report only, write nothing

By default the original files are backed up to ./static/_originals/ before being
overwritten, so nothing is lost.

Requires: Pillow  (pip install pillow)
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("Pillow is required. Install it with:  pip install pillow")


# Per-role width caps (longest edge for width). Used by --profile.
PROFILES = {
    "auto":    1600,   # safe default: crisp on retina for the largest tile
    "gallery": 1440,   # 4:3 gallery tiles at 2x
    "slider":  1100,   # before/after sliders at 2x
    "hero":    1920,   # if you add a full-bleed hero photo later
}

# Filenames that should NOT be resized/aggressively touched (icons / share image).
# favicon stays small & sharp; og-image must remain exactly 1200x630 for social.
SKIP_RESIZE = {"favicon.png"}
SOCIAL_FIXED = {"og-image.jpg": (1200, 630)}

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

# Encoding quality
JPEG_QUALITY = 82
WEBP_QUALITY = 80
PNG_OPTIMIZE = True


def human(n):
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}GB"


def is_photo_png(img):
    """Heuristic: a PNG that's really a photo (no transparency) is better as JPEG."""
    return img.mode in ("RGB", "L") or (img.mode == "RGBA" and not has_alpha(img))


def has_alpha(img):
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        alpha = img.convert("RGBA").getchannel("A")
        return alpha.getextrema()[0] < 255
    return False


def optimize_one(path: Path, dst_dir: Path, max_width: int,
                 make_webp: bool, to_jpeg_when_opaque: bool, dry_run: bool,
                 backup_dir: Path):
    name = path.name
    orig_size = path.stat().st_size

    try:
        img = Image.open(path)
        img = ImageOps.exif_transpose(img)  # honor camera rotation, then drop EXIF
    except Exception as e:
        print(f"  ! skip {name}: cannot open ({e})")
        return 0, 0

    w, h = img.size
    note = []

    # Decide target size
    if name in SOCIAL_FIXED:
        target = SOCIAL_FIXED[name]
        img_resized = ImageOps.fit(img, target, Image.LANCZOS)
        note.append(f"social {target[0]}x{target[1]}")
        out_w, out_h = target
    elif name in SKIP_RESIZE:
        img_resized = img
        out_w, out_h = w, h
        note.append("icon (no resize)")
    elif w > max_width:
        ratio = max_width / w
        out_w, out_h = max_width, round(h * ratio)
        img_resized = img.resize((out_w, out_h), Image.LANCZOS)
        note.append(f"{w}x{h} -> {out_w}x{out_h}")
    else:
        img_resized = img
        out_w, out_h = w, h
        note.append(f"{w}x{h} (already small)")

    # Choose output format
    ext = path.suffix.lower()
    opaque = not has_alpha(img_resized)
    out_path = dst_dir / name
    save_kwargs = {}

    if name in SOCIAL_FIXED or ext in (".jpg", ".jpeg"):
        fmt = "JPEG"
        out_path = dst_dir / (path.stem + (".jpg" if name not in SOCIAL_FIXED else path.suffix))
        img_to_save = img_resized.convert("RGB")
        save_kwargs = dict(quality=JPEG_QUALITY, optimize=True, progressive=True)
    elif ext == ".png" and to_jpeg_when_opaque and opaque and name not in SKIP_RESIZE:
        # Photo-style PNG with no transparency -> JPEG is far smaller.
        # NOTE: this changes the extension, so we DON'T do it by default
        # (the site references .png). Only active with --png-to-jpeg.
        fmt = "JPEG"
        out_path = dst_dir / (path.stem + ".jpg")
        img_to_save = img_resized.convert("RGB")
        save_kwargs = dict(quality=JPEG_QUALITY, optimize=True, progressive=True)
        note.append("PNG->JPEG")
    elif ext == ".png":
        fmt = "PNG"
        img_to_save = img_resized
        save_kwargs = dict(optimize=PNG_OPTIMIZE)
    elif ext == ".webp":
        fmt = "WEBP"
        img_to_save = img_resized
        save_kwargs = dict(quality=WEBP_QUALITY, method=6)
    else:
        print(f"  ! skip {name}: unsupported {ext}")
        return 0, 0

    if dry_run:
        print(f"  · {name}: {', '.join(note)}  [{fmt}]  (dry-run, not written)")
        return orig_size, orig_size

    # Back up original before overwriting (only when writing into same dir/name)
    if out_path.resolve() == path.resolve():
        backup_dir.mkdir(parents=True, exist_ok=True)
        if not (backup_dir / name).exists():
            shutil.copy2(path, backup_dir / name)

    img_to_save.save(out_path, fmt, **save_kwargs)
    new_size = out_path.stat().st_size

    # If we changed extension (e.g. PNG->JPEG), remove the stale original copy in dst
    if out_path.resolve() != path.resolve() and path.parent == dst_dir:
        backup_dir.mkdir(parents=True, exist_ok=True)
        if not (backup_dir / name).exists():
            shutil.copy2(path, backup_dir / name)
        path.unlink()

    # Optional .webp companion (does not replace the original-format file)
    webp_size = 0
    if make_webp and fmt != "WEBP":
        webp_path = dst_dir / (out_path.stem + ".webp")
        img_resized.save(webp_path, "WEBP", quality=WEBP_QUALITY, method=6)
        webp_size = webp_path.stat().st_size

    saved = orig_size - new_size
    pct = (saved / orig_size * 100) if orig_size else 0
    extra = f" (+{human(webp_size)} .webp)" if webp_size else ""
    arrow = f"{human(orig_size)} -> {human(new_size)}"
    print(f"  ✓ {name}: {', '.join(note)}  {arrow}  ({pct:+.0f}%){extra}")
    return orig_size, new_size


def main():
    ap = argparse.ArgumentParser(description="Optimize Kaiser's Detail Co. site images.")
    ap.add_argument("--src", default="static", help="Folder with source images (default: static)")
    ap.add_argument("--dst", default=None, help="Output folder (default: same as --src, in place)")
    ap.add_argument("--profile", choices=PROFILES.keys(), default="auto",
                    help="Width cap profile (default: auto=1600px)")
    ap.add_argument("--max-width", type=int, default=None,
                    help="Override max width in pixels (beats --profile)")
    ap.add_argument("--webp", action="store_true", help="Also write .webp copies")
    ap.add_argument("--png-to-jpeg", action="store_true",
                    help="Convert opaque (non-transparent) PNG photos to JPEG "
                         "(smaller, but changes file extensions — update HTML if used)")
    ap.add_argument("--dry-run", action="store_true", help="Report only; write nothing")
    args = ap.parse_args()

    src = Path(args.src)
    dst = Path(args.dst) if args.dst else src
    if not src.is_dir():
        sys.exit(f"Source folder not found: {src}")
    dst.mkdir(parents=True, exist_ok=True)
    backup_dir = dst / "_originals"

    max_width = args.max_width if args.max_width else PROFILES[args.profile]

    images = sorted(
        p for p in src.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS and p.parent.name != "_originals"
    )
    if not images:
        print(f"No images found in {src}/. "
              f"Drop your .png/.jpg files there and re-run.")
        return

    print(f"Optimizing {len(images)} image(s) in '{src}' "
          f"(max width {max_width}px, profile '{args.profile}')"
          + (" [DRY RUN]" if args.dry_run else ""))
    print(f"Originals backed up to: {backup_dir}/\n")

    total_before = total_after = 0
    for p in images:
        b, a = optimize_one(
            p, dst, max_width, args.webp,
            to_jpeg_when_opaque=args.png_to_jpeg,
            dry_run=args.dry_run, backup_dir=backup_dir,
        )
        total_before += b
        total_after += a

    print()
    if total_before:
        saved = total_before - total_after
        pct = saved / total_before * 100
        print(f"TOTAL: {human(total_before)} -> {human(total_after)}  "
              f"(saved {human(saved)}, {pct:.0f}% smaller)")
    if not args.dry_run:
        print(f"\nDone. If results look wrong, restore from {backup_dir}/")


if __name__ == "__main__":
    main()