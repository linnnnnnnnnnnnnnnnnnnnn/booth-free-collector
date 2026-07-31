---
name: booth-name-search
description: |-
  Search BOOTH by sanitized filename to find the matching product, then organize
  the local file into the standard categorized folder layout with cover icon.
  Use when the user drops a zip/rar/7z whose filename does NOT contain a
  7-digit BOOTH item ID but IS a BOOTH product name (possibly with version
  numbers, Chinese annotations, or underscores). The skill cleans the filename
  (strips _v100, v2.0, Chinese notes, replaces underscores with spaces), searches
  BOOTH via q= parameter, matches the best result, fetches metadata and cover,
  and organizes the file like booth-archive-organizer. Also inspects zip
  contents for watermarks / .url files revealing the shop URL when global
  search fails. Trigger words: vrchat插件整理、按名字搜索booth、搜booth商品名、
  整理vrc插件道具、找booth商品、按文件名搜索、拖入文件说明整理vrchat、
  booth按名搜索、整理vrc素材、整理着色器.
  Differs from booth-archive-organizer: that one requires a 7-digit ID in the
  filename; this one searches by NAME when no ID is present.
agent_created: true
---

# BOOTH 商品名搜索整理术式

当压缩包文件名里 **没有 7 位 BOOTH ID**，但主上确认它是 BOOTH 商品时——
从文件名提取关键词，搜索 BOOTH 定位商品，下载封面并整理到标准目录。
当全局搜索无果时，从压缩包内水印 / .url 文件提取店铺 URL 反查。

## 何时使用

- 拖入的压缩包名如 `SimpleJoinAlert_v100.zip`、`JoinLeaveNotification玩家加入退出弹窗2.0.zip`
  ——无 7 位 ID，但主上说明「整理 vrchat vrc 相关插件 道具」
- 主上说「按名字搜 booth」「帮我找这个 booth 商品」
- 与 `booth-archive-organizer` 的边界：那个要求文件名含 7 位 ID；本术式靠 **名字搜索**

## 核心洞察（主上亲授妙招合集）

### 1. 搜索端点
BOOTH 商品搜索端点是 `https://booth.pm/ja/items?q=关键词`（注意是 `?q=` 不是 `?keyword=`）。
`?keyword=` 完全忽略关键词恒返 60 件固定列表；`/ja/search` 404 不可用。

### 2. 文件名清洗规则（搜索前必须执行）
主上验证的实测：

| 文件名 | 清洗后关键词 | 命中 |
|--------|------------|------|
| `SimpleJoinAlert_v100.zip` | `SimpleJoinAlert` | 6392372 免费 ✅ |
| `JoinLeaveNotification玩家加入退出弹窗2.0.zip` | `JoinLeaveNotification` | 6979951 免费 ✅ |
| `Chocolat_Real_skin_NO39.zip` | `Chocolat Real skin NO39` | 6466041 ¥2,800~ ✅ |

清洗策略（脚本 `sanitize_query()` 自动执行，按优先级生成多候选）：

1. **下划线 → 空格**（主上验证：BOOTH 不认下划线，空格才命中）
2. 去扩展名 `.zip/.rar/.7z`
3. 去括号内容 `(1)` `（副本）`
4. 去版本号：`_v100`, `v2`, `2.0`, `Ver1.0`, `Version2`
5. 去尾部连续中文（通常为主上备注）
6. 只取最长连续英文名段
7. 去 VRChat 常见后缀词（vrchat, vrc, unitypackage 等）

### 3. 压缩包内水印 / .url 文件识图（重要辅助）
当全局搜索无果时（如 `Chocolat_Real_skin_NO39` 因"Chocolat"过于宽泛），**检查压缩包内部**：
- `*.url` 文件（Windows 快捷方式，常含 `URL=https://...booth.pm/...`）
- `readme.txt` / `info.txt` / `credit.txt` 等文本
- PNG/JPG 封面图本身（如 `P1.png`）—— 通常右下角含**店铺 URL 水印**

**示例（Chocolat_Real_skin_NO39）**：
- 压缩包内 `lilToon - BOOTH.url` 指向 `https://booth.pm/ja/items/3087170`（lilToon 着色器，非皮肤本身）
- 压缩包内 `P1.png` 封面右下角水印 `https://no39.booth.pm/` → 推断店铺 `no39`
- 去该店铺子域名 `https://no39.booth.pm/items` 翻页列出全部商品 → 命中 [6466041]

**店铺根 `/` 通常有 Cloudflare 护盾**，必须走 `https://子域名.booth.pm/items?page=N` 翻页。

### 4. 评分机制（关键修正）
BOOTH 按别名/标签匹配，卡片 `data-product-name` 常为日文显示名，英文关键词并不出现其中。
故评分取 **JSON 规范名**（含英文别名）做归一化包含判定；单结果直接采信，多结果按规范名匹配度排序。

### 5. 同名歧义 + 付费精准
枪械类道具等热门品类可能有多个同名商品。**默认不偏置免费**——拖入的文件是主上「已有」的商品（可能花钱购买），
偏置免费会把付费商品错配到同名免费兄弟。付费与免费走同一权威分类映射，**绝不因价格改变归类**。

**分类权威源**：BOOTH JSON 的 `category.name`（父级 `category.parent.name` 兜底），不再依赖搜索卡片名。
类目表已扩充至 VRChat/游戏付费重灾区（软件/3D动作/3D工具/3D服饰/3D着色器/3D贴图/贴图素材 等）；
未知类目保留日文原名并提示，绝不臆造。

当存在多个强候选（次优分差过小，或同名不同价）时，脚本列出候选并**跳过自动整理**，
由主上用 `--id 商品ID` 确认正确那件后重跑。

### 6. 非 BOOTH 商品处理
部分主上认可的 VRC 素材**不在 BOOTH 上**（如 Poiyomi Toon 着色器通过 GitHub 分发）。
脚本判定「所有搜索候选 + 水印探测均无果」时，**保留源文件不整理**，由主上告知来源平台后**手动归入对应分类文件夹**。
例如 `poi_Toon_*.zip` → 主上指定放入 `G:\Lin_File\BOOTH\着色器\`。

## 工作流程

1. **提取候选关键词**：`sanitize_query(filename)` → 多个候选查询
2. **尝试压缩包内水印识别**（首次搜索空结果时触发）：
   - 读 `*.url` / `*.txt` / readme / info 文件 → 提取 `https://*.booth.pm/...` 链接
   - 推断店铺子域名 → 翻页列出店内全部商品
3. **搜索 BOOTH**：依次用候选查询 GET `https://booth.pm/ja/items?q=候选`
4. **解析结果**：从 HTML 卡片提取 `data-product-id` / `data-product-name` / `data-product-price` / 封面 URL
5. **评分选最佳**：取 JSON 规范名做归一化包含判定，单结果采信，多结果按匹配度排序（不偏免费）
6. **获取元数据**：`GET https://booth.pm/ja/items/ID.json`（公开 JSON API，规范名 + 权威类目 + 封面 URL）
7. **整理文件**（默认**移动**，源处不留尸体；`--keep` 改复制）：
   - 重命名 → `ID_标题.ext`，按 `item_id` 复用既有文件夹（标题变更不新建重复目录）
   - 建文件夹 → `G:\Lin_File\BOOTH\分类中文\ID_标题\`
   - 下载封面 → `cover.jpg`（booth.pximg.net 公开 CDN）
   - 设图标 → `.folder_icon.ico` + `desktop.ini`（写入前清旧隐藏属性，可覆盖）
8. **若全部无果**：上报主上，告知「不在 BOOTH」并保留源文件

## 用法

```bash
# 单个文件（最常用：用户直接把文件丢进来）——默认移动整理，源处不留尸体
python scripts/booth_name_search.py "G:/圣域/安装残留/SimpleJoinAlert_v100.zip"

# 多个文件一起
python scripts/booth_name_search.py "a.zip" "b.rar" --base-dir "G:/Lin_File/BOOTH"

# 先看搜索结果，不动文件
python scripts/booth_name_search.py "xxx.zip" --dry-run

# 歧义时由主上确认正确商品后，用 --id 强制指定重跑
python scripts/booth_name_search.py "xxx.zip" --id 6979951

# 歧义也强制自动选最佳（不询问）
python scripts/booth_name_search.py "xxx.zip" --auto

# 复制而非移动（保留源文件）
python scripts/booth_name_search.py "xxx.zip" --keep

# 提供 cookie 以支持自动更新下载
python scripts/booth_name_search.py "xxx.zip" --cookie-file .booth_cookie.txt
```

依赖：`requests`、`Pillow`（均已装于默认 venv）。网络走 `HTTPS_PROXY` 环境变量。

## 输出目录结构

```
G:\Lin_File\BOOTH\
└── 类目中文tag\
    └── ID_标题\
        ├── ID_标题.ext   ← 原压缩包，已重命名并移入（默认移动；--keep 复制）
        ├── cover.jpg            ← 商品首图
        ├── .folder_icon.ico     (隐藏)
        └── desktop.ini          (隐藏+系统)
```

与 `booth-free-collector` 和 `booth-archive-organizer` 输出完全同构。

## 与其他 BOOTH 技能的关系

| 技能 | 触发条件 | 核心操作 |
|------|---------|---------|
| `booth-free-collector` | 整店 URL 或散链 | 从网上爬取 + 下载免费商品 |
| `booth-archive-organizer` | 文件名含 7 位 ID | 按 ID 取元数据，整理本地包 |
| **`booth-name-search`** | 文件名无 ID，是商品名 | 按名字搜索 + 水印辅助识别 BOOTH，匹配后整理 |