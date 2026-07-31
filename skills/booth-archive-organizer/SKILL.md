---
name: booth-archive-organizer
description: |-
  Organize a locally-existing BOOTH archive (.rar/.zip/.7z) into the same
  categorized folder layout that booth-free-collector produces by downloading.
  This skill should be used when the user drops, pastes, or references a local
  compressed file whose name embeds a 7-digit BOOTH item id (e.g.
  "跟随悬浮机-6504842等3个文件.rar") and wants it tidied: extract the id,
  fetch title/category/cover from booth.pm, rename the archive to
  "id_标题", create "类目 id_标题/" folder, move the archive
  in, download cover.jpg, and set the Windows folder cover-icon. Trigger words:
  booth整理、booth归档、整理booth压缩包、归档booth文件、整理这个booth包、booth文件归类、
  给这个压缩包重命名、这种文件拖给你(booth)、booth rar整理. Differs from
  booth-free-collector: that one DOWNLOADS free items from the web; this one
  ORGANIZES an archive the user already has on disk (no login needed — metadata
  and cover come from public endpoints).
agent_created: true
---

# BOOTH 归档整理术式

把**主上磁盘上已有的 BOOTH 压缩包**（朋友发的、自己下的、安装残留里翻出来的）整理成
和 `booth-free-collector` 下载后一致的目录结构：

```
G:\Lin_File\BOOTH\
└── 类目中文tag\
    └── 7位ID_标题\
        ├── 7位ID_标题.ext   ← 原压缩包，已重命名并移入
        ├── cover.jpg              ← 商品首图（booth.pximg.net，公开无需登录）
        ├── .folder_icon.ico       (隐藏)
        └── desktop.ini            (隐藏+系统)
```

Windows 资源管理器「大图标」视图即可直接预览封面，与下载术式完全同源结构。

## 何时使用

- 用户**拖入 / 粘贴 / 提到**一个本地压缩包（`.rar` / `.zip` / `.7z`），其文件名里含 7 位数字
  （BOOTH 商品 ID）。典型：「`跟随悬浮机-6504842等3个文件.rar`」
- 用户说「帮我整理这个 booth 包」「归档一下这个 booth 文件」「给这个压缩包重命名归类」之类
- 与 `booth-free-collector` 的边界：**那个是「从网上抓取免费商品」；本术式是「整理你已有的本地包」**。
  整理**不需要 BOOTH 登录 Cookie**——标题/类目来自公开 JSON API，封面来自公开 CDN `booth.pximg.net`。

## 工作流程

1. **提取 ID**：从文件名取第一个 7+ 位数字（`\b\d{7,}\b`）。也可用 `--id` 强制指定。
2. **取元数据**：`GET https://booth.pm/ja/items/id.json`（公开，无需登录）
   - `name` → 标题；`category.name` → 经 `CATEGORY_MAP` 汉化（与下载术式同一张表）
   - `images[0].original/resized` → 封面 URL
3. **命名与建文件夹**：
   - 新压缩包名 = `id_sanitize(标题).原后缀`
   - 目标文件夹 = `out默认G:\Lin_File\BOOTH/类目中文tag/id_标题/`
4. **移动 + 重命名**：`shutil.move` 把原包移入目标文件夹（同盘为瞬时改名；跨盘则复制并保留原文件）。
5. **封面 + 图标**：下载 `cover.jpg`（pximg 公开 CDN），Pillow 转 `.folder_icon.ico` + 写
   `desktop.ini` + 文件夹加只读位 → 大图标直显封面。
6. **幂等**：目标文件夹已含重命名包 + 有效 `cover.jpg` 时，仅补齐缺失的封面/图标，不重复移动。

## 用法

```bash
# 单个归档（最常用：用户直接把文件丢进来）
python scripts/organize_booth_archive.py "G:/圣域/安装残留/11_待定_其他/已判定/跟随悬浮机-6504842等3个文件.rar"

# 多个一起
python scripts/organize_booth_archive.py "a.rar" "b.zip" --out "G:/Lin_File/BOOTH"

# 文件名里没有 ID / 想强制指定
python scripts/organize_booth_archive.py "weird_name.rar" --id 6504842

# 先看会做什么、不动文件
python scripts/organize_booth_archive.py "xxx.rar" --dry-run
```

依赖：`requests`、`Pillow`（均已装于默认 venv）。网络走 `HTTPS_PROXY` 环境变量。

> 隐私：本术式不读取、不要求任何 BOOTH 登录 Cookie（整理只需公开元数据与公开封面 CDN）。
> 若将来需要把压缩包内的免费文件也按下载术式补封面，则另走 `booth-free-collector`。
