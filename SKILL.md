---
name: booth-toolkit
description: |-
  Unified BOOTH toolkit for VRChat / XR creators. This parent skill bundles three
  sub-skills covering the full lifecycle of BOOTH assets: (1) booth-free-collector
  downloads a shop's free items or scattered share-links ("免费鸡蛋"/"免费鸡蛋" = free
  BOOTH goods in VRChat slang); (2) booth-archive-organizer tidies a local archive
  whose filename embeds a 7-digit BOOTH item id; (3) booth-name-search finds a BOOTH
  product by filename when no id is present (strips version/_underscores/Chinese notes,
  replaces underscores with spaces, searches via q=, and inspects in-zip cover watermarks
  to recover the shop). All three emit the same categorized folder layout with cover
  icons. Trigger words: 下载免费鸡蛋、booth下载、免费商品下载、VRChat免费素材、booth归档、
  下载booth店铺、免费鸡蛋、领鸡蛋、白嫖鸡蛋、下载散链、散的链接、朋友发的booth、booth整理、
  booth归档、整理booth压缩包、归档booth文件、整理这个booth包、booth文件归类、给这个压缩包重命名、
  按名字搜booth、搜booth商品名、整理vrc插件道具、找booth商品、按文件名搜索、拖入文件说明整理vrchat、
  booth按名搜索、整理vrc素材、整理着色器.
agent_created: true
---

# BOOTH Toolkit — BOOTH 素材全家桶

BOOTH（日本数字创作集市，VRChat 素材主产地）素材的**下载 / 归档 / 按名搜索整理**三件套。
以父技能形式整合，下属三个子技能各司其职，统一输出 `G:\Lin_File\BOOTH\类目中文\ID_标题\`
目录结构（含 `cover.jpg` 封面 + Windows 文件夹图标）。

## 统一 CLI（三合一入口）

三个子技能已合并为**单一脚本** `scripts/booth.py`（公共逻辑 `scripts/booth_common.py`）：

```bash
python scripts/booth.py download <店铺URL|散链> [--cookie ...] [--out DIR]   # 原 free-collector
python scripts/booth.py organize <本地包...> [--id ID] [--out DIR]           # 原 archive-organizer
python scripts/booth.py search   <本地文件...> [--id ID] [--base-dir DIR]    # 原 name-search
python scripts/booth.py audit    [--base DIR] [--dry-run]                    # 图标巡检
```

子技能 SKILL.md 保留（Agent 路由用），但用法统一指向 `booth.py <子命令>`。

## 子技能路由

| 子技能 | 何时使用 | 入口 |
|--------|---------|------|
| **booth-free-collector** | 给整店 URL 或散链，从网上爬取并下载**免费**商品（需登录 Cookie） | `booth.py download` |
| **booth-archive-organizer** | 本地已有的压缩包，文件名**含 7 位 BOOTH ID**，按 ID 取元数据整理（无需登录） | `booth.py organize` |
| **booth-name-search** | 本地压缩包**无 7 位 ID**、是商品名，按名字搜索 BOOTH 整理（含水印识图） | `booth.py search` |

### 决策树（快速判定走哪个子命令）

```
用户丢来一个文件 / 链接
├─ 是 BOOTH 店铺 URL 或商品散链（booth.pm/...）
│   └─► booth.py download              （从网上下载）
├─ 是本地压缩包，文件名含 7 位数字（如 跟随悬浮机-6504842等3个文件.rar）
│   └─► booth.py organize              （按 ID 取元数据整理）
└─ 是本地压缩包，无 ID，主上确认是 BOOTH 商品名（如 SimpleJoinAlert_v100.zip）
    └─► booth.py search                （按名字搜索 + 水印/UnityPackage 辅助识别）
```

## 关键共享知识（三子技能通用）

- **BOOTH 搜索端点**：`https://booth.pm/ja/items?q=词`（`?q=`，非 `?keyword=`——后者忽略关键词恒返 60 件固定列表；`/ja/search` 404）
- **公开元数据 API**：`https://booth.pm/ja/items/id.json`（免登录取标题/类目/封面 URL）
- **封面图 CDN**：`booth.pximg.net`（公开可达，整理类技能无需登录即可取封面）
- **分类汉化**：`booth_common.CATEGORY_MAP`（3Dテクスチャ→3D贴图、3D衣装→3D服饰、3Dモデル（その他）→3D模型（其他）、ポスター→海报 等）；未知类目保留日文原名不臆造
- **免费偏置禁忌**：整理「主上已有」文件（可能花钱）时，评分**不偏置免费**，否则会把付费商品错配到同名免费兄弟
- **文件名清洗**：去版本号 `_v100`/`v2`/`2.0`、去中文备注、去括号、**下划线→空格**（BOOTH 搜索不认下划线）、**驼峰拆词**（`LunariaPaperFan`→`Lunaria Paper Fan`）、**纯日文主体**（`メカ弾エフェクトVer_2.00`→只搜 `メカ弾エフェクト`）
- **压缩包水印识图**：搜索无果时读 `*.url`/`readme.txt` 提取店铺 URL（如封面图右下角 `https://no39.booth.pm/`），跳过店铺根 Cloudflare，直接走 `https://子域名.booth.pm/items?page=N` 翻页反查
- **UnityPackage 内部资源名是硬线索**：解包后**首段目录名 = 店铺名/作者名**（如 `Pirouette`→pipi18 店铺），内部 prefab/anim 名 = 商品主题；封面上的角色是**目标 avatar 不是配布店铺**，判断归属以内部资源名+店铺子域为准（详见 booth-name-search §8.3/8.4）
- **商品页下载文件名 = 终极锚点**：候选歧义时 WebFetch 商品页「免费下载」区实际文件名（如 3562410 → `メカ弾エフェクトVer_2.00.zip`），与本地文件前缀/版本号匹配，100% 确认（详见 booth-name-search §8.5）
- **隐私铁律**：任何登录 Cookie 仅存本机（`.booth_cookie.txt`），**绝不上传 GitHub**（仓库 .gitignore 已屏蔽）

## 防错速查（血泪案例总结）

| 症状 | 根因 | 修复 |
|------|------|------|
| 封面显示默认文件夹图标 | desktop.ini/ico 缺 Hidden+System、文件夹缺 ReadOnly（移动/拷贝丢失） | 批量补属性（见 name-search §4.5） |
| 封面图标「居中小图」外留白 | cover 是宽幅矩形，PIL 按原图比例生成 ICO 条目（256x154） | 正方形画布 paste 后保存（§4.7） |
| 图标仍不显示（属性全对） | 目录名含装饰 Unicode（`❥⁺⌖˚🌕💗`），Explorer 永久不读 desktop.ini | `sanitize_filename` 过滤装饰 Unicode + **重启电脑**（§4.8） |
| 商品被误配张冠李戴 | 单结果盲信 / 标题相似但实为别家 | 名称归一化必须命中 + 解 UnityPackage 校验（§4.1/§4.3/§8.3） |
| 同题材商品分不清（ear and tail 等） | 只凭标题关键词相似归档 | 内部资源名首段目录=店铺名，交叉验证（§8.3） |
| zip 导入 Unity 失败 | zip 声明 UTF-8 但 Windows cp437 解码乱码（`É`→`╠ü`） | 7-Zip 重解压 / `Expand-Archive -Encoding UTF8`（§4.4） |
| 目录分裂成两套（3D服装 vs 3D服饰） | 脚本间 CATEGORY_MAP 不一致 | 统一到 `booth_common.CATEGORY_MAP`（§4.6） |
| **新**：Hermes 等 agent 整理后图标仍显示默认文件夹 | agent 写残缺 desktop.ini（缺 IconResource 字段）或漏 .folder_icon.ico | **完整性契约**（`make_folder_icon` 写完必自检三件套 + IconResource 字段）+ `booth.py audit` 全库巡检修复 |
| **新**：日文+英文+版本号混合名搜不到 | BOOTH 索引对混合串匹配差 | 只搜纯日文主体段（§8.5） |
| **新**：整理后文件名版本号丢失（Ver_2.00 → 纯标题） | `organize_file` 用标题生成文件名 | **内部文件名保持原文件名**（§8.6）；目录名才用 ID_标题 |
| **新**：商品页多免费版本本地只有 1 个 | 整理后未检查其他免费版本 | `backfill_free_files` 自动补全（公开 JSON 检测 + `--cookie` 下载，§8.7） |

> 各「§」指 `skills/booth-name-search/SKILL.md` 对应章节。

---

## 完整性契约（强制规则）

**任何 agent 用本 Skill 整理商品目录后，必须满足三件套齐全**：
1. `cover.jpg`（商品首图）
2. `.folder_icon.ico`（≥1KB，含 256×256 正方形条目）
3. `desktop.ini`（**必须**含 `IconResource=.folder_icon.ico,0` 字段）+ Hidden+System 属性

`make_folder_icon()` 内置完整性自检：写完立刻读回 ini 校验 `IconResource` 字段，
任一缺失即 raise `IconContractError` 并清理已写的 ini，**不留半成品**。

**自检工具**：`python scripts/booth.py audit [--dry-run]`

- 扫描 `<base>/` 下所有商品目录，4 类问题：① ini 缺 IconResource ② ico 缺失/过小
  ③ ICO 含非正方形条目（宽幅陷阱）④ 属性不全（ini 缺 H/S、文件夹缺 R）
- 默认自动修复（有 cover 的就走 `make_folder_icon` 重写）
- 任何 agent（Hermes / WorkBuddy / 自定义）整理后**应主动跑一次 audit**

## 输出目录结构（三子技能同构）

```
G:\Lin_File\BOOTH\
└── 类目中文tag\
    └── ID_标题\
        ├── ID_标题.ext   原文件（下载/移动/复制）
        ├── cover.jpg           商品首图
        ├── .folder_icon.ico    (隐藏)
        └── desktop.ini         (隐藏+系统)
```

## 非 BOOTH 商品处理

部分 VRC 素材不在 BOOTH 上（如 Poiyomi Toon 着色器走 GitHub 分发）。
booth-name-search 判定「所有搜索 + 水印探测均无果」时保留源文件不整理，
由主上确认来源平台后手动归入 `G:\Lin_File\BOOTH\着色器\` 等对应分类。

## 依赖

`requests`、`Pillow`（装于默认 venv）。网络走 `HTTPS_PROXY` 环境变量。
脚本均自包含于各自 `skills/子技能名/scripts/` 目录，互不依赖。
