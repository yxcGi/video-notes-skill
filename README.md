# video-notes

一个 [Claude Code](https://claude.com/claude-code) skill：把教学 / 操作类视频完整复现成**标注截图 + 书面讲解**的图文笔记。

目标是「看笔记 ≈ 看视频」——操作零遗漏、参数零遗漏、可独立复现。适用于 B 站课程逐集笔记、软件实操教程、录屏演示。

流水线在一门 Fluent / SpaceClaim 课程上经多集人工验收迭代定型，目前处理过 32~67 分钟的单集，单集产出 20~26 张标注图 + 350~520 行笔记。

---

## 它做什么

给定一个视频（或 B 站分 P 链接），产出：

- 一批**关键帧截图**，每张带细红框 + 红底白字标签 + 细引线，标注讲师讲到的界面元素与参数；
- 一篇按视频类型组织的**书面笔记**（操作型按步骤轴、理论型按知识点轴、问答型按 Q&A 列表），每个操作、每个参数值、每个讲师强调的坑都落进正文。

标注样式是定稿的 v3：标签自动落到画面空白区、不扩画布、允许轻微遮挡换取排版整齐。

---

## 六阶段流水线

| 阶段 | 做什么 |
|---|---|
| ① 获取 | 下载单集视频（多 P 必须核对分 P 号与时长） |
| ② 文字轨 | 平台人工字幕 > AI 字幕 > 音频转写；产出带时间轴转写稿，通读后搭章节骨架 + 目标帧时间戳清单 |
| ③ 视觉轨 | 三模式抽帧（场景检测打底 / 按清单定点补抽 / 固定间隔兜底），拼总览粗筛后精读入选帧 |
| ④ 理解对齐 | 判定视频类型定组织轴；转写稿与帧按时间戳对齐；**界面文字是术语基准**，用帧校正字幕错词 |
| ⑤ 制图 | 标定红框坐标 → 写 JSON 配置 → 渲染 → 按防呆清单核验 |
| ⑥ 落库校验 | 写笔记页 + 图片入库 + 索引更新 + 完整性对账 + 链接与嵌图校验 |

细节见 [`references/pipeline.md`](references/pipeline.md)。

---

## 目录结构

```
video-notes/
├── SKILL.md                      # skill 入口：作用范围、六阶段概览、质量红线
├── references/
│   ├── pipeline.md               # 六阶段详细操作
│   ├── annotate-style.md         # v3 标注样式规范 + 渲染前防呆清单
│   └── lessons.md                # 卡点日志（append-only，开工前先扫一遍）
└── scripts/
    ├── extract_frames.py         # 抽帧：场景检测 / 定点 / 固定间隔
    ├── contact_sheet.py          # 候选帧拼总览图，供粗筛
    └── annotate.py               # v3 标注渲染引擎
```

---

## 脚本用法

依赖：`ffmpeg`、Python 3 + `Pillow`、`numpy`。

```bash
# 抽帧（三种模式）
python scripts/extract_frames.py --video V.mp4 --out frames_scene --mode scene    --threshold 0.04
python scripts/extract_frames.py --video V.mp4 --out frames_pts   --mode points   --points "149,490,1554.6"
python scripts/extract_frames.py --video V.mp4 --out frames_int   --mode interval --interval 20

# 候选帧拼总览（读图粗筛用）
python scripts/contact_sheet.py --dir frames_scene --out sheets/sheet.jpg

# 渲染标注
python scripts/annotate.py --config spec.json
```

`spec.json` 结构：

```json
{
  "frames_dir": "源帧目录",
  "out_dir": "输出目录",
  "images": [
    {
      "name": "输出文件名.png",
      "frame": "源帧文件名.png",
      "boxes": [ {"rect": [x1, y1, x2, y2], "label": "① 说明文字"} ],
      "notes": ["无框的整图说明（自动落到全图最空处）"]
    }
  ]
}
```

### 引擎的两个设计要点

- **中文字体不静默降级**：多路径回退链 + 渲染前对所有标签**逐字符**做字形体检。判定不能用 `getmask(ch).getbbox()`——`.notdef`（方框带叉）本身就有 bbox，那只能检出「整个字体加载失败」，检不出「个别字符缺字形」。改用私用区码点 `U+E000` 的渲染指纹做 md5 比对。命中缺字形直接报错，宁可不出图也不出带方框的成品。
- **放不下时降级而非崩溃**：红框过大 / 标签过长导致找不到空位时，降级为压盖放置并打印告警，异常信息带上出错的图名与源帧名。

---

## 质量红线

这些每一条都有真实翻车史，写在 `SKILL.md` 里：

- 图片全程保持**原始分辨率**，任何环节不缩放成品；
- **高信息密度图不拼图**，拆单图各配讲解；
- 对话框 / 弹窗类、以及标签引用了图内数值的关键帧，渲染后必须**全分辨率逐张核验**「红框-内容一致性」——定点抽帧既会撞 UI 过渡瞬间，也会抽到输入框里的拖动中间值而非讲师键入的目标值，缩略总览一律查不出来；
- **只标讲师讲过的**：每条标签所指的对象必须能在转写稿里找到对应讲解。界面里存在但视频只字未提的东西一律不标——红框会被读者默认为「讲师强调过的要点」，标了等于凭空捏造重点；
- **序号链只放同一条主线**：并列项、旁例、备选做法必须用无序号标签区分，否则 ①②③ 会被读成先后顺序；
- 讲解**零遗漏但书面语重构**，不逐字转录口语；
- **不罗列字幕转写错误**：AI 字幕认错词是既定前提，笔记直接用正确写法行文。唯一例外是讲师口述与界面文字确实不一致（跟着操作会找不到按钮），这种要保留提示。

---

## 自我优化机制

这个 skill 的核心设计是**越用越准**，靠三层闭环：

1. **卡点即记**——同一步骤失败重试 ≥2 次 / 用户指出成品缺陷 / 遇到新平台或新 UI，当场把「日期 + 场景 + 现象 + 处置」追加进 `references/lessons.md`；
2. **每集微复盘**——单集收尾时列出新增 lessons，并提 1~3 个具体可选的优化项由用户拍板；
3. **教训泛化入本体**——某条 lesson 反复出现或明显可泛化时，提议修改 SKILL.md / references / scripts 本体，获准后修改并更新 CHANGELOG。

`lessons.md` 里已积累 25 条，其中约一半已泛化进本体（条目末尾标 `✅ 已入本体 vX.Y`）。变更历史见 [`CHANGELOG.md`](CHANGELOG.md)。

---

## 安装

放进 Claude Code 的 skills 目录即可：

```bash
git clone https://github.com/yxcGi/video-notes-skill.git ~/.claude/skills/video-notes
```

skill 默认只能用户手动 `/video-notes` 调用（`disable-model-invocation: true`）。若希望在某个项目内自动触发，可在该项目的 `.claude/skills/` 下放一个同名薄壳，用 frontmatter 的 `description` 描述触发条件，正文指向本 skill。

---

## 说明

- 版本管理从 v1.7 起，此前 v1.0~v1.6 的演进只有 CHANGELOG 记录，没有代码快照。
- 产出的笔记仅供个人学习使用；本仓库只含流水线本身，不含任何课程内容或笔记成品。

## License

[MIT](LICENSE)
