#!/usr/bin/env python3
"""缩略总览表：把一个目录的图片拼成带文件名标签的网格图，一次读图完成粗筛/自检。

用法：python contact_sheet.py --dir 图片目录 --out sheet.jpg [--cols 4] [--width 470] [--per-sheet 30]

`--width` 是**单张缩略图**宽度，画布宽 = width × cols（给 2400 会得到 9600 px 画布）。
输出目录不存在会自动创建。
排图顺序为**自然排序**（文件名里的数字段按数值比大小），所以 p152.0s 排在 p1510.0s 前面；
用字典序会让时间戳在总览里来回跳，找某个时刻的帧很费眼。

两个用途：
- 候选帧粗筛：几百张候选帧先看总览，挑出要精读的少数帧，省 token；
- 成品自检：全部成品一屏过，查标注错位、字体豆腐块、帧内容错误。
⚠️ 总览缩略图看不出小红框级别的错位（material-db 事故的教训）——对话框/弹窗类关键图仍须全分辨率单独核验。
"""
import argparse
import os
import re

from PIL import Image, ImageDraw, ImageFont


def natural_key(name):
    """自然排序键：连续数字段按数值比较，其余按小写字符串比较。

    re.split 保证奇数位恒为数字段、偶数位恒为非数字段，两个键的同一位置类型必然一致，
    不会出现 int 与 str 相比的 TypeError。
    """
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def load_font(sz):
    for p in ["/System/Library/Fonts/PingFang.ttc",
              "/System/Library/Fonts/Hiragino Sans GB.ttc"]:
        try:
            f = ImageFont.truetype(p, sz)
            if f.getmask("中").getbbox():
                return f
        except Exception:
            pass
    raise RuntimeError("无可用中文字体")


def build_sheet(files, src, out, cols, tw, font):
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    tiles = []
    for name in files:
        im = Image.open(os.path.join(src, name))
        th = int(im.height * tw / im.width)
        tiles.append((im.resize((tw, th)), os.path.splitext(name)[0], th))
    rows = (len(tiles) + cols - 1) // cols
    row_h = [max(t[2] for t in tiles[r * cols:(r + 1) * cols]) + 26 for r in range(rows)]
    sheet = Image.new("RGB", (cols * tw, sum(row_h)), "black")
    d = ImageDraw.Draw(sheet)
    y = 0
    for r in range(rows):
        for c, (im, name, th) in enumerate(tiles[r * cols:(r + 1) * cols]):
            sheet.paste(im, (c * tw, y + 26))
            d.text((c * tw + 4, y + 2), name, fill="yellow", font=font)
        y += row_h[r]
    sheet.save(out, quality=80)
    print(f"{out}: {len(files)} 张, 画布 {sheet.size[0]}x{sheet.size[1]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--width", type=int, default=470,
                    help="单张缩略图宽度（不是画布宽度！画布宽 = width × cols）")
    ap.add_argument("--per-sheet", type=int, default=30, help="超出则拆多张 _00/_01 …")
    a = ap.parse_args()
    font = load_font(20)
    exts = (".jpg", ".jpeg", ".png")
    files = sorted((f for f in os.listdir(a.dir) if f.lower().endswith(exts)),
                   key=natural_key)
    if not files:
        raise SystemExit("目录里没有图片")
    if len(files) <= a.per_sheet:
        build_sheet(files, a.dir, a.out, a.cols, a.width, font)
    else:
        base, ext = os.path.splitext(a.out)
        for i in range(0, len(files), a.per_sheet):
            build_sheet(files[i:i + a.per_sheet], a.dir,
                        f"{base}_{i // a.per_sheet:02d}{ext}", a.cols, a.width, font)
