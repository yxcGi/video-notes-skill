# 六阶段流水线详细操作

以 B 站课程为主线写就；其它平台在①②两步替换对应工具，③以后完全通用。

## ① 获取

- B站/小红书/抖音：调 cn-video-downloader skill（脚本入口 `download.sh <URL> <输出目录>`）。
- **多 P 合集必须带 `?p=N`**，下载完核对产物文件名里的分 P 号与时长（下载器 v1.3.1 起支持分 P，仍要验证）。
- YouTube：`yt-dlp --merge-output-format mp4`。
- 输出到会话 scratchpad 的独立子目录（如 `p24/`），一集一目录。
- 分 P 元信息（标题/时长清单）：`https://api.bilibili.com/x/player/pagelist?bvid=<BV>`（带浏览器 UA）。

## ② 文字轨

优先级：平台人工字幕 > AI 字幕 > 音频转写。

- B站 AI 字幕：`opencli bilibili subtitle <BV> --page N -f json`（需桌面 Chrome + OpenCLI）。
- 兜底转写：ffmpeg 从已下载视频抽 16kHz 单声道 wav → `agent-reach transcribe`（需 Groq key，未配置时先问用户选云端注册还是本地 faster-whisper）。
- 把字幕转成紧凑时间轴文本（`[MM:SS] 文本` 每行），**通读全文**后产出 outline：
  - 章节划分（起止时间 + 主题 + 操作密集/讲解密集判定）；
  - 目标帧时间戳清单（对话框/设置面板/关键画面）；
  - 待帧核实的术语与数值清单（字幕口语转写常错）。
- **数值类目标帧一律排两个时间点**：讲师"念出数值"的时刻，和它 **+10~20s**。口述永远先于输入，只抽前者会拿到软件默认值或拖动中间值（已三次中招，详见 annotate-style.md 防呆第 2 条）。
- **主动找"总结回放"**：通读时留意「我们继续走这个工作流程 / 回顾一下 / 总结一下 / 这就是刚才那个流程」这类措辞，讲师多半正在放总结性课件（流程图、架构图）。这类帧不在按操作步骤列的 outline 里、场景检测也只当成普通切换，**必须手动补进目标帧清单**——系列课程里它天然交代了"本集在全局的位置"，价值高于任何一张操作截图（P21 的 SCDM 工作流程图即此例，靠补抽才撞见）。

## ③ 视觉轨

```bash
python scripts/extract_frames.py --video V.mp4 --out frames_scene --mode scene --threshold 0.04
python scripts/extract_frames.py --video V.mp4 --out frames_pts --mode points --points "149,490,1554.6"
python scripts/extract_frames.py --video V.mp4 --out frames_int --mode interval --interval 20   # 可选兜底
```

- 场景检测在"弹对话框"段会漏帧（画面变化小），outline 的定点补抽是必须项，不是可选项。
- 候选帧规模参考：60 min 录屏 ≈ 场景 300 张 + 定点 30 张。
- 粗筛：`python scripts/contact_sheet.py --dir frames_scene --out sheets/sheet.jpg`，读总览挑帧，再全分辨率精读入选帧。

## ④ 理解对齐

- 视频类型 → 组织轴：操作型按**步骤轴**（软件工作流程顺序）、理论型按**知识点轴**、问答型按 **Q&A 列表**（默认降级为要点摘要）。
- 逐段判定信息在画面还是在话里，定图文配比：操作密集段一步一图，讲解密集段一两张关键帧配长讲解。
- 界面文字（按钮名/参数值/文件名）以帧为准，反向校正转写稿术语；模糊口诀类表述（如"选第4项"）必须用帧确认具体指什么。

## ⑤ 制图

1. 精读入选帧，记录每张图的红框坐标（原图像素坐标）与标签文字；
2. 写 JSON 配置（结构见 annotate.py 文件头注释），标签文字规范见 annotate-style.md；
3. `python scripts/annotate.py --config spec.json`；
4. 按 annotate-style.md 的防呆清单核验；不合格改配置重跑（引擎快，返工便宜）。

图片命名：`<课程缩写>-pNN-<语义>.png`（如 `fluent-p24-inlet-y.png`），三个月后能看懂为准。

## ⑥ 落库校验

**Obsidian vault 会话**（默认）：

- 图片 → `raw/media/<课程目录>/`（一课程一子目录，防刷爆 media 根）；
- 笔记页 → 对应领域目录（Fluent 课程即 `wiki/learning/cfd/fluent/lesson/`），frontmatter 四硬字段齐全；
- 课程索引页勾进度、链新页；更新 `cfd/_index` 等领域索引与 `wiki/index.md`；
- `log.md` 置顶追加（含折叠检查）、`hot.md` 重写；
- 校验：笔记全部 `![[嵌图]]` 落盘存在、出链无死链。

**非 vault 会话**：询问输出目录，产出 `笔记.md + images/` 平铺结构，其余规范同上。

**完整性对账**（两种会话都做）：拿转写稿从头滚一遍，逐段自查"这段的操作/参数/坑进笔记了吗"，漏的补上。

## 收尾汇报模板

- 产出清单（笔记页路径、图片张数与 MB）；
- 校验结果（嵌图/链接/对账）；
- **本集卡点与优化建议**（自我优化机制的落点：新增 lessons + 1~3 个待拍板优化项）；
- 中间产物去留状态。
