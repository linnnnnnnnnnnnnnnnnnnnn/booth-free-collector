---
name: booth-free-collector
description: BOOTH 免费商品批量下载与归档。给定 BOOTH 店铺链接（如 https://xxx.booth.pm/）自动爬全店，或接收好友/群里分享的【零散商品链接】——脚本自动判定输入类型（整店 / 散链），筛选 0 円免费商品、下载全部免费文件，按「商品分类(文件夹)/商品ID_标题/」结构归档，每个商品文件夹内含 cover.jpg 封面并自动设置为 Windows 文件夹图标（大图标视图可直接预览）。触发词：booth、booth下载、免费商品下载、VRChat免费素材、booth归档、下载booth店铺、免费鸡蛋、下载鸡蛋、领鸡蛋、白嫖鸡蛋、下载散链、散的链接、朋友发的booth（"免费鸡蛋/蛋"是 VRChat 社区梗，指 BOOTH 上的免费商品/素材）。
group: 游戏与 XR
---

# BOOTH Free Collector — BOOTH 免费商品批量下载归档

> 黑话对照：VRChat 社区把 BOOTH 免费商品称为「鸡蛋 / 免费鸡蛋」（源自社区梗）。
> 「帮我下载免费鸡蛋」「领一下这家店的鸡蛋」「白嫖鸡蛋」= 下载该 BOOTH 店铺的全部免费商品并归档。

## 功能

给定一个 BOOTH 店铺 URL，自动完成：

1. 爬取店铺全部商品（`https://<sub>.booth.pm/items?page=N` 分页，正则提取 `/items/<id>`）
2. 逐个调用官方 JSON API `https://booth.pm/ja/items/<id>.json` 获取元数据
3. 筛选免费商品：`variations[].price == 0` 且 `downloadable` 含下载直链
4. 下载全部免费文件 + 第一张商品图为 `cover.jpg`（**文件下载必须登录**，见下）
5. 归档结构：`<输出根>/<商品分类中文名>/<商品ID>_<标题>/`（分类经 CATEGORY_MAP 汉化：3Dテクスチャ→3D贴图、3D衣装→3D服装、3D装飾品→3D饰品、ポスター→海报 等）
6. 用 Pillow 将封面转 `.folder_icon.ico`（隐藏）并写 `desktop.ini`（隐藏+系统）、文件夹加只读位 → Windows 资源管理器「大图标」视图直接显示封面

> 幂等性说明：重跑时通过**文件系统扫描**（`valid_file` 检查目标文件是否已存在且非伪装 HTML）跳过已下载项，无需任何额外清单文件。输出目录保持纯净——除商品内容文件与封面图标三件套（cover.jpg / .folder_icon.ico / desktop.ini）外，不写入任何副产物。

**下载健壮性**：优先单次流式下载（小文件极快）；若代理中途断流（如某些代理对单连接大文件传输设限，抛出 `IncompleteRead`），自动降级为**分块 Range 续传**（每片 64KB 独立短连接，逐片重试），绕开单连接限制。绝大多数情况下用户无感。

## 输入类型自动判定（核心特性）

脚本根据输入内容自动分流，无需用户指定模式：

| 输入形式 | 判定 | 行为 |
|---|---|---|
| `https://<sub>.booth.pm/` 或子域名 `atelier-kotone` | 整店 | 分页爬取全店商品 |
| `https://<sub>.booth.pm/items/6574952` 或 `https://booth.pm/ja/items/6574952` | 散链（单条） | 仅下载该商品 |
| `--items "链接1" "链接2"` 或 `--items "链接 裸ID 链接"` | 散链（多条） | 下载列出的每个商品 |
| 朋友/群里粘贴的一坨链接 + 裸 ID 混排 | 散链 | 正则抽取所有 `/items/<id>` 与 5 位以上裸 ID，逐个下载 |

判定逻辑见 `parse_discrete()`：先抽 `/items/<id>`，再补抽裸数字 ID（5 位以上），去重保序。

## 用法

```bash
# 按店铺整店下载
python scripts/booth_free_dl.py "https://atelier-kotone.booth.pm/" --out "./booth_downloads"

# 朋友/群里分享的零散链接（自动判定为散链模式）
python scripts/booth_free_dl.py --items \
  "https://atelier-kotone.booth.pm/items/6574952" \
  "https://booth.pm/ja/items/6574953" \
  "8103811"   # 裸 ID 也可

# 单条商品链接直接丢进去也行
python scripts/booth_free_dl.py "https://atelier-kotone.booth.pm/items/8103811"
```

参数：
- `shop`：店铺 URL 或子域名（`atelier-kotone` 等价于完整 URL）；若值含 `/items/<id>` 则自动转散链模式
- `--items`：零散商品链接/ID（可传多个，空格分隔；或一条字符串内逗号/换行分隔；好友分享的链接贴这里）
- `--out`：输出根目录，默认 `./booth_downloads`
- `--cookie`：**必需**（下载文件时）。三种形式：原始 Cookie 串 / Netscape cookies.txt 路径 / 存有原始 Cookie 串的文本文件路径。**会话 Cookie 真名是 `_plaza_session_nktz7u`**（不是 _plaz_session），建议直接从浏览器 F12 → Network 复制整条 Cookie 头（连同 `cf_clearance` 一起）
- `--ua`：**通常无需指定**。实测 `downloadables` 下载端点只校验有效会话 cookie（`_plaza_session_nktz7u`），默认 UA 即可正常下载；仅当遇到 Cloudflare 挑战页（如店铺根 `/`）时才需与浏览器 UA 一致。保留作可选保险。
- `--dry-run`：只列出将下载的免费商品，不写盘（**新店铺建议先 dry-run 给用户确认**）
- `--limit N`：最多处理 N 个免费商品
- `--folder-by category|first-tag`：分组文件夹用商品分类中文名（默认）还是第一个 tag

## 依赖

- Python 3.10+（需 `requests`、`pillow` 库）
- 网络代理：requests 自动读取 `HTTPS_PROXY` 环境变量（直连 booth.pm 可能 SSL 握手失败，建议配置代理）

## 关键经验 / 注意事项

- **⚠️ 下载必须登录**：`booth.pm/downloadables/<id>` 未登录时返回 200 但内容是**登录页 HTML**（伪装成 zip/png 的假文件）！脚本已内置魔数校验（looks_html/valid_file）：下载后检测到 HTML 即报错并删除；重跑时假文件会被自动识别并重下。**没有 --cookie 时绝不要以为下载成功了**。
- **免费判定以 variation 为准**：`item['price']` 是字符串（如 `"¥ 0"`），可靠做法是遍历 `variations[].price == 0`。同一商品可能免费+付费变体并存，只下免费部分。
- **限时免费**（标题含「〇/〇まで無料」）也会被正常识别（当前价格为 0 即下载）。
- 下载直链形如 `https://booth.pm/downloadables/<id>?variation_id=<vid>`，登录后 302 到签名 URL。**付费商品无此字段，绝不会误下**。
- 商品 JSON API 与商品图（booth.pximg.net）无需登录。
- R-18 店铺需要 `adult=t` cookie，当前脚本未处理；遇到时在 session 上加 cookie。
- 文件夹图标机制：`desktop.ini`（UTF-16 编码）+ `IconResource=.folder_icon.ico,0` + 文件夹 ReadOnly 属性缺一不可；图标不即时刷新属 Explorer 缓存正常现象（重开窗口或稍等即可）。
- **⚠️ 目录被移动/拷贝后图标失效（血泪坑）**：`desktop.ini` / `.folder_icon.ico` / 文件夹的 Hidden / System / ReadOnly 属性在**移动或拷贝目录后会被清掉**，Windows 资源管理器不再读取 desktop.ini → 封面消失（表现为文件夹显示默认图标、或图标过小）。修复脚本 `make_folder_icon` 的幂等分支**必须重新补设属性**（文件在 ≠ 属性在）：
  ```python
  if ico.exists() and ini.exists():
      set_attrs(ico, FILE_ATTRIBUTE_HIDDEN)
      set_attrs(ini, FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM)
      set_attrs(folder, FILE_ATTRIBUTE_READONLY)
      return
  ```
  批量修复存量库：遍历所有含 desktop.ini 的目录，给 desktop.ini / .folder_icon.ico 补 `Hidden+System`，给文件夹补 `ReadOnly`（2026-08 主上库内 104 目录一次修复）。
- **⚠️ 分类映射必须与 booth-name-search 保持一致**：本脚本曾把 `3D衣装` 映射为 `3D服装`、`3D環境・ワールド` 映射为 `3D世界`，而整理技能映射为 `3D服饰` / `3D环境`，导致**同一类目分裂成两个目录**（3D服装 与 3D服饰 并存）。已统一以 name-search 为准，且补 `3Dモデル（その他）→3D模型（其他）`、`3Dキャラクター→3D角色`、`3D小道具→3D道具`。改映射后要把旧分类目录合并（移动商品目录 + 重设图标属性）。
- 请求间隔 0.6~0.8s，礼貌爬取，勿并发轰炸 booth.pm。
- **代理瞬断**：本地代理（HTTPS_PROXY env）偶发 ProxyError 导致个别文件失败——直接**再跑一遍**即可，幂等重跑只补失败文件（末尾有 FAILED 清单）。
- 实际文件下载 302 到 `s6.booth.pm`（S3 签名 URL，180 秒时效），Cookie 只在第一跳 booth.pm 需要。
- 本技能**只新增文件，绝不删除/移动已有文件**。
- 控制台若出现日文乱码，用 `PYTHONIOENCODING=utf-8` 运行。

## 输出结构示例

```
<输出根目录>/
├── 3D饰品\
│   └── 7603673_【FREE】あったかニット帽🧶\
│       ├── ニット帽_v1.1.zip
│       ├── cover.jpg
│       ├── .folder_icon.ico   (隐藏)
│       └── desktop.ini        (隐藏+系统)
├── 3D贴图\
├── 3D服装\
└── 海报\
```

> 输出根目录仅含分类文件夹，不写入任何 manifest / 日志等副产物。
