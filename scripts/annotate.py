#!/usr/bin/env python3
"""v3 定稿标注引擎：细红框 + 红底白字标签智能避让 + 细引线；不扩画布，允许轻微遮挡。

用法：python annotate.py --config spec.json

spec.json 结构：
{
  "frames_dir": "源帧目录",
  "out_dir": "输出目录",
  "images": [
    {
      "name": "输出文件名.png",
      "frame": "源帧文件名.png",
      "boxes": [ {"rect": [x1, y1, x2, y2], "label": "① 说明文字", "ev": "26:07"} ],   # ev=该标签在转写稿里的讲解时间戳，缺失会告警
      "notes": ["无框的整图说明（自动找全图最空处放置）"]
    }
  ]
}

要点（为什么这么做）：
- 标签落点按"分块像素方差"挑空白低信息区（分块取最大方差，防半空白区域蒙混）；
- 排序右侧优先，减少引线交叉；标签之间与红框本体禁止互压，图内内容允许轻微压住；
- 中文字体走多路径回退且加载后实测 CJK 渲染，杜绝静默降级成"豆腐块"。
- 红框过大 / 标签过长导致无空位时，**降级为压盖放置并打印 ⚠️ 告警**（不再崩溃）；
  看到告警就去缩小该图的红框或精简标签文字，不要放着不管。
- 任何异常都会带上出错的图片名与源帧名，几十张配置里可直接定位。
"""
import argparse
import hashlib
import json
import os

try:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
except ImportError as e:
    raise SystemExit(
        f"缺依赖（{e.name}）。本脚本须在 conda data_processing 环境运行：\n"
        "  source /opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh "
        "&& conda activate data_processing")

RED = (225, 30, 30)
PAD = 9


FONT_CANDS = ["/System/Library/Fonts/PingFang.ttc",
              "/System/Library/Fonts/Hiragino Sans GB.ttc",
              "/System/Library/Fonts/STHeiti Medium.ttc",
              "/System/Library/Fonts/Supplemental/Songti.ttc"]

# 私用区码点，任何字体都不会为它定义字形 → 渲染结果即该字体的 .notdef 形状
NOTDEF_PROBE = ""


def _glyph_sig(font, ch):
    """字符渲染结果的指纹。用于把真字形与 .notdef 区分开。"""
    try:
        return hashlib.md5(bytes(font.getmask(ch))).hexdigest()
    except Exception:
        return None


def has_glyph(font, ch):
    """该字体是否真的有这个字的字形。

    不能用 `getmask(ch).getbbox()` 判断——.notdef（方框带叉）本身就有 bbox，
    那种写法只能检出"整个字体加载失败"，检不出"个别字符缺字形"。
    2026-07-26 事故：Hiragino Sans GB 不含 Ø(U+00D8)，静默渲染成方框带叉进了成品。
    """
    if ch.isspace():
        return True
    sig = _glyph_sig(font, ch)
    return sig is not None and sig != _glyph_sig(font, NOTDEF_PROBE)


def load_font(sz):
    tried = []
    for p in FONT_CANDS:
        try:
            f = ImageFont.truetype(p, sz)
        except Exception as e:
            tried.append(f"{os.path.basename(p)}（打不开：{e}）")
            continue
        if has_glyph(f, "中"):
            return f
        tried.append(f"{os.path.basename(p)}（无中文字形）")
    raise RuntimeError("无可用中文字体，禁止静默降级。已试：" + "；".join(tried))


F = load_font(28)


def check_glyphs(spec):
    """渲染前对配置里所有标签逐字符体检，缺字形直接报错，不出带方框的成品。"""
    missing = {}
    for item in spec["images"]:
        for text in ([b.get("label", "") for b in item.get("boxes", [])]
                     + list(item.get("notes", []))):
            for ch in text:
                if not has_glyph(F, ch):
                    missing.setdefault(ch, set()).add(item.get("name", "<未命名>"))
    if missing:
        lines = [f"  {ch!r} (U+{ord(ch):04X}) —— 出现在：{', '.join(sorted(v))}"
                 for ch, v in missing.items()]
        raise RuntimeError(
            "当前字体缺以下字符的字形，渲染出来会是方框带叉，请换字符或换字体：\n"
            + "\n".join(lines))


def label_size(d, text):
    bb = d.textbbox((0, 0), text, font=F)
    return bb[2] - bb[0] + PAD * 2, bb[3] - bb[1] + PAD * 2


def region_std(gray, rect):
    x1, y1, x2, y2 = [int(v) for v in rect]
    r = gray[max(0, y1):y2, max(0, x1):x2]
    if r.size == 0:
        return 1e9
    bs, worst = 24, 0.0
    for yy in range(0, r.shape[0], bs):
        for xx in range(0, r.shape[1], bs):
            b = r[yy:yy + bs, xx:xx + bs]
            if b.size >= 64:
                worst = max(worst, float(b.std()))
    return worst


def overlaps(a, b, m=8):
    return not (a[2] + m < b[0] or b[2] + m < a[0] or a[3] + m < b[1] or b[3] + m < a[1])


def cheapest(gray, cands, lw, lh, W, H, cx0, cy0):
    """不考虑压盖，纯按代价挑一个位置——放不下时的兜底。"""
    best, best_cost = None, None
    for cx, cy, side in cands:
        cx = min(max(0, cx), W - lw)
        cy = min(max(0, cy), H - lh)
        rect = (cx, cy, cx + lw, cy + lh)
        cost = region_std(gray, rect) * 6 + \
            (abs((cx + lw / 2) - cx0) + abs((cy + lh / 2) - cy0)) * 0.5 + side * 60
        if best_cost is None or cost < best_cost:
            best, best_cost = rect, cost
    return best


def place(im, boxes, notes):
    """返回 (placed, warns)。找不到空位时降级为压盖放置并回报警告，不再返回 None。"""
    W, H = im.size
    gray = np.asarray(im.convert("L"), dtype=np.float32)
    d0 = ImageDraw.Draw(im)
    hard = [b["rect"] for b in boxes]
    placed, warns = [], []
    for b in boxes:
        x1, y1, x2, y2 = b["rect"]
        lw, lh = label_size(d0, b["label"])
        cands = []
        for gap in (16, 46, 90, 150, 220, 300):
            cands += [
                (x2 + gap, (y1 + y2) / 2 - lh / 2, 0), (x2 + gap, y1 - lh / 2, 0), (x2 + gap, y2 - lh / 2, 0),
                ((x1 + x2) / 2 - lw / 2, y1 - lh - gap, 1), (x1, y1 - lh - gap, 1), (x2 - lw, y1 - lh - gap, 1),
                ((x1 + x2) / 2 - lw / 2, y2 + gap, 2), (x1, y2 + gap, 2), (x2 - lw, y2 + gap, 2),
                (x1 - lw - gap, (y1 + y2) / 2 - lh / 2, 3),
            ]
        best, best_cost = None, None
        for cx, cy, side in cands:
            cx = min(max(0, cx), W - lw)
            cy = min(max(0, cy), H - lh)
            rect = (cx, cy, cx + lw, cy + lh)
            if any(overlaps(rect, h) for h in hard):
                continue
            s = region_std(gray, rect)
            dist = abs((cx + lw / 2) - (x1 + x2) / 2) + abs((cy + lh / 2) - (y1 + y2) / 2)
            cost = s * 6 + dist * 0.5 + side * 60
            if best_cost is None or cost < best_cost:
                best, best_cost = rect, cost
        if best is None:
            best = cheapest(gray, cands, lw, lh, W, H, (x1 + x2) / 2, (y1 + y2) / 2)
            warns.append(f"「{b['label']}」无空位，已压盖放置——红框可能画得太大")
        placed.append((best, b["rect"], b["label"]))
        hard.append(best)
    for text in notes:
        lw, lh = label_size(d0, text)
        best, best_cost = None, None
        for cy in range(8, H - lh - 8, 48):
            for cx in range(8, W - lw - 8, 64):
                rect = (cx, cy, cx + lw, cy + lh)
                if any(overlaps(rect, h) for h in hard):
                    continue
                cost = region_std(gray, rect) * 6 + cy * 0.12
                if best_cost is None or cost < best_cost:
                    best, best_cost = rect, cost
        if best is None:
            best = (8, 8, 8 + lw, 8 + lh)
            warns.append(f"整图说明「{text}」无空位，已压在左上角")
        placed.append((best, None, text))
        hard.append(best)
    return placed, warns


def leader_endpoints(rect, box):
    """标签 rect → 红框 box 的引线两端点；不需要画引线时返回 None。
    render 与排版 lint 共用，保证检查的就是实际画出来的那条线。"""
    rx1, ry1, rx2, ry2 = [int(v) for v in rect]
    lx = rx1 if rx1 > box[2] else rx2 if rx2 < box[0] else (rx1 + rx2) // 2
    ly = (ry1 + ry2) // 2 if (rx1 > box[2] or rx2 < box[0]) else (ry1 if ry1 > box[3] else ry2)
    bx = box[0] if lx <= box[0] else box[2] if lx >= box[2] else (box[0] + box[2]) // 2
    by = box[1] if ly <= box[1] else box[3] if ly >= box[3] else (box[1] + box[3]) // 2
    if abs(lx - bx) + abs(ly - by) <= 20:
        return None
    return (lx, ly), (bx, by)


def seg_hits_rect(p, q, r, pad=2):
    """线段 pq 是否穿过矩形 r 内部（Liang-Barsky 裁剪判定）。"""
    (x1, y1), (x2, y2) = p, q
    xmin, ymin, xmax, ymax = r[0] + pad, r[1] + pad, r[2] - pad, r[3] - pad
    if xmin >= xmax or ymin >= ymax:
        return False
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p_, q_ in ((-dx, x1 - xmin), (dx, xmax - x1), (-dy, y1 - ymin), (dy, ymax - y1)):
        if p_ == 0:
            if q_ < 0:
                return False
        else:
            t = q_ / p_
            if p_ < 0:
                if t > t1:
                    return False
                t0 = max(t0, t)
            else:
                if t < t0:
                    return False
                t1 = min(t1, t)
    return t0 <= t1


def wide_chars(text):
    """全角等效字符数（CJK 记 1，其余两个记 1）。"""
    n = sum(2 if ord(c) > 0x2E7F else 1 for c in text)
    return (n + 1) // 2


def lint_item(item, placed, W):
    """渲染前后都不改变成品的静态排版检查，问题以告警返回。"""
    warns = []
    boxes = item.get("boxes", [])
    for b in boxes:
        if "ev" not in b:
            warns.append(f"标签「{b['label']}」缺讲解依据 ev 字段——确认讲师真讲过，否则下沉正文")
        if wide_chars(b["label"]) > 14:
            warns.append(f"标签「{b['label']}」超 14 全角字符——序数/口诀/推导下沉正文")
    for rect, box, text in placed:
        if box is None:                     # notes
            if (rect[2] - rect[0]) > W * 0.9:
                warns.append(f"整图说明「{text[:18]}…」渲染宽 {int(rect[2]-rect[0])}px 近乎横穿画布——压缩成一句")
            continue
        lead = leader_endpoints(rect, box)
        if not lead:
            continue
        for other in boxes:
            r = other["rect"]
            if list(r) == list(box):
                continue
            if seg_hits_rect(lead[0], lead[1], r):
                warns.append(f"引线穿框：指向 {list(box)} 的引线穿过了「{other['label']}」的红框——调整两框相对位置或改 notes")
    return warns


def render(im, boxes, placed):
    d = ImageDraw.Draw(im)
    for b in boxes:
        d.rectangle(b["rect"], outline=RED, width=3)
    for rect, box, text in placed:
        rx1, ry1, rx2, ry2 = [int(v) for v in rect]
        if box:
            lead = leader_endpoints(rect, box)
            if lead:
                (lx, ly), (bx, by) = lead
                d.line([(lx, ly), (bx, by)], fill=RED, width=2)
                d.ellipse([bx - 4, by - 4, bx + 4, by + 4], fill=RED)
        d.rounded_rectangle(rect, radius=5, fill=RED)
        d.text((rx1 + PAD, ry1 + PAD - 4), text, fill="white", font=F)
    return im


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    a = ap.parse_args()
    spec = json.load(open(a.config))
    check_glyphs(spec)          # 先体检字形，宁可不出图也不出方框带叉的成品
    os.makedirs(spec["out_dir"], exist_ok=True)
    all_warns = 0
    for item in spec["images"]:
        name = item.get("name", "<未命名>")
        try:
            im = Image.open(os.path.join(spec["frames_dir"], item["frame"])).convert("RGB")
            placed, warns = place(im, item.get("boxes", []), item.get("notes", []))
            warns += lint_item(item, placed, im.size[0])
            im = render(im, item.get("boxes", []), placed)
            im.save(os.path.join(spec["out_dir"], name))
        except Exception as e:  # 异常必须带上是哪张图，否则几十张配置里无从定位
            raise RuntimeError(f"{name}（源帧 {item.get('frame')}）渲染失败：{e}") from e
        for w in warns:
            print(f"⚠️ {name}: {w}")
            all_warns += 1
    total = sum(os.path.getsize(os.path.join(spec["out_dir"], f)) for f in os.listdir(spec["out_dir"]))
    print(f"{len(spec['images'])} 张 → {spec['out_dir']}（目录合计 {total/1048576:.1f} MB）"
          + (f"，{all_warns} 处告警" if all_warns else ""))
