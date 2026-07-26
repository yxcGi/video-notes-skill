#!/usr/bin/env python3
"""抽帧工具：场景检测 / 定点列表 / 固定间隔 三模式。

用法：
  python extract_frames.py --video V.mp4 --out DIR --mode scene   [--threshold 0.04]
  python extract_frames.py --video V.mp4 --out DIR --mode points  --points "149,490,1554.6"
  python extract_frames.py --video V.mp4 --out DIR --mode interval --interval 20

场景模式产物按时间戳命名（tMMmSSs.jpg）；定点模式命名 pSECs.png（保留小数）。
⚠️ 定点抽帧可能撞上 UI 过渡瞬间（对话框刚弹出/翻页中），关键帧务必人工核验，必要时 ±0.5~2s 微调。
"""
import argparse
import os
import re
import subprocess
import sys


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def scene(video, out, thr, quality):
    os.makedirs(out, exist_ok=True)
    log = os.path.join(out, "_scene_log.txt")
    cmd = ["ffmpeg", "-hide_banner", "-i", video,
           "-vf", f"select='gt(scene,{thr})',showinfo", "-vsync", "vfr",
           "-q:v", str(quality), os.path.join(out, "s_%04d.jpg")]
    with open(log, "w") as f:
        subprocess.run(cmd, stderr=f, check=True)
    times = re.findall(r"pts_time:([0-9.]+)", open(log).read())
    files = sorted(f for f in os.listdir(out) if f.startswith("s_"))
    if len(times) != len(files):
        sys.exit(f"时间戳数({len(times)})与帧数({len(files)})不符，检查 {log}")
    for f, t in zip(files, times):
        t = float(t)
        os.rename(os.path.join(out, f),
                  os.path.join(out, f"t{int(t//60):02d}m{int(t%60):02d}s.jpg"))
    print(f"场景帧 {len(files)} 张 → {out}")


def points(video, out, pts, quality):
    os.makedirs(out, exist_ok=True)
    for sec in pts:
        dst = os.path.join(out, f"p{sec}s.png")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                        "-ss", str(sec), "-i", video, "-frames:v", "1",
                        "-q:v", str(quality), dst], check=True)
    print(f"定点帧 {len(pts)} 张 → {out}")


def interval(video, out, sec, quality):
    os.makedirs(out, exist_ok=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", video,
                    "-vf", f"fps=1/{sec}", "-q:v", str(quality),
                    os.path.join(out, "i_%04d.jpg")], check=True)
    n = len([f for f in os.listdir(out) if f.startswith("i_")])
    print(f"间隔帧 {n} 张（每 {sec}s）→ {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", required=True, choices=["scene", "points", "interval"])
    ap.add_argument("--threshold", type=float, default=0.04)
    ap.add_argument("--points", default="")
    ap.add_argument("--interval", type=float, default=20)
    ap.add_argument("--quality", type=int, default=2, help="ffmpeg -q:v，1 最高")
    a = ap.parse_args()
    if a.mode == "scene":
        scene(a.video, a.out, a.threshold, a.quality)
    elif a.mode == "points":
        pts = [float(x) for x in a.points.split(",") if x.strip()]
        if not pts:
            sys.exit("--points 不能为空")
        points(a.video, a.out, pts, a.quality)
    else:
        interval(a.video, a.out, a.interval, a.quality)
