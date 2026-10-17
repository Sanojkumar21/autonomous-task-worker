"""Render a run's screenshots into an animated GIF with step captions.

    python scripts/make_gif.py                 # latest run under runs/
    python scripts/make_gif.py runs/<run_id>   # a specific run
    python scripts/make_gif.py <run_dir> --out docs/demo.gif --fps 0.8
"""
import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent


def latest_run():
    runs = sorted((p for p in (ROOT / "runs").rglob("run.json")), key=lambda p: p.stat().st_mtime)
    if not runs:
        sys.exit("no runs found")
    return runs[-1].parent


def caption(step):
    args = json.dumps(step["action"]["args"], ensure_ascii=False)
    text = f"step {step['index']}  {step['action']['tool']} {args}"
    return text[:110] + (" …" if len(text) > 110 else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", nargs="?")
    ap.add_argument("--out", default=str(ROOT / "docs" / "demo.gif"))
    ap.add_argument("--fps", type=float, default=0.7)
    ap.add_argument("--width", type=int, default=900)
    args = ap.parse_args()
    run_dir = Path(args.run_dir) if args.run_dir else latest_run()
    run = json.loads((run_dir / "run.json").read_text())
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    except OSError:
        font = bold = ImageFont.load_default()
    frames = []
    for step in run["steps"]:
        shot = step.get("screenshot")
        if not shot or not Path(shot).exists():
            continue
        img = Image.open(shot).convert("RGB")
        ratio = args.width / img.width
        img = img.resize((args.width, int(img.height * ratio)))
        canvas = Image.new("RGB", (img.width, img.height + 92), "white")
        canvas.paste(img, (0, 92))
        d = ImageDraw.Draw(canvas)
        d.text((12, 8), run["request"][:95], fill="#1d2330", font=bold)
        d.text((12, 36), caption(step), fill="#243b6b", font=font)
        res = step.get("result", "").replace("\n", " ")
        d.text((12, 60), ("→ " + res)[:120], fill="#0b5" if "refused" not in res else "#b3261e", font=font)
        frames.append(canvas)
    if not frames:
        sys.exit("no screenshots in this run")
    # hold the last frame longer so the outcome is readable
    frames += [frames[-1]] * 3
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=int(1000 / args.fps), loop=0, optimize=True)
    print(f"wrote {out} ({len(frames)} frames, {out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
