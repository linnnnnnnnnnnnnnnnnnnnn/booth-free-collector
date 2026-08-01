# BOOTH Toolkit · BOOTH 素材统一管理套件

> 一个 GitHub 仓库装齐 BOOTH 素材的「下载 / 归档 / 按名搜索」三件套，输出结构同构，
> 任何遵循 Agent Skills 规范（`SKILL.md` + `scripts/`）的 AI Agent 都能加载使用。

BOOTH（日本数字创作集市，VRChat / VSeeFace / Live2D 等创作者主产地）上分散的免费与付费素材——
按「分类(中文) / 商品ID_标题 /」的结构统一归档，每个商品目录自动配上 Windows 文件夹封面图标。

---

## 子技能分工

| 子技能 | 何时使用 | 入口 |
|--------|---------|------|
| **booth-free-collector** | 给整店 URL 或散链，**从网上爬取并下载**免费商品（需登录 Cookie） | `skills/booth-free-collector/` |
| **booth-archive-organizer** | 本地压缩包**文件名含 7 位 BOOTH ID**，按 ID 取元数据整理（无需登录） | `skills/booth-archive-organizer/` |
| **booth-name-search** | 本地压缩包**无 ID、只有商品名**，按名字搜索 BOOTH 整理（含水印识别 + UnityPackage 内部资源名兜底） | `skills/booth-name-search/` |

### 决策树

```
用户丢来一个文件 / 链接
├─ 是 BOOTH 店铺 URL 或商品散链（booth.pm/...）
│   └─► booth-free-collector        （从网上下载）
├─ 是本地压缩包，文件名含 7 位数字 ID（如「跟随悬浮机-6504842.zip」）
│   └─► booth-archive-organizer     （按 ID 取元数据整理）
└─ 是本地压缩包，无 ID，主上确认是 BOOTH 商品名（如 SimpleJoinAlert_v100.zip）
    └─► booth-name-search           （按名字搜索 + UnityPackage 资源名锚点）
```

---

## 一键自学（推荐 · 给 Agent 自己学）

**最快的接入方式**：不用手动 clone / 建链接——直接把下面这段话**连同本仓库链接**丢给任意 AI Agent，
它会自己 clone 仓库、读 SKILL.md、装依赖、验证结构，然后就能开始干活：

```text
学习此技能：BOOTH Toolkit（booth-toolkit）— BOOTH 素材统一管理套件

来源：https://github.com/linnnnnnnnnnnnnnnnnnnnn/booth-free-collector

请按以下步骤自学并进入可用状态：
1. clone 该仓库到你的 skills 目录（或临时目录，之后由你决定链接方式）
2. 读根目录 SKILL.md 和 README.md，理解父技能与三个子技能的分工
   （booth-free-collector 下载 / booth-archive-organizer 按ID整理 / booth-name-search 按名搜索）
3. 为 scripts/ 安装依赖：pip install requests pillow（若无 venv 则先建）
4. 跑一遍 --help 或 --dry-run 验证脚本可执行
5. 向我确认「已学会，可以开始处理 BOOTH 素材任务」，等待指令
```

> 说明：脚本依赖 `requests` + `Pillow`；网络走 `HTTPS_PROXY` 环境变量；
> 下载类操作需要 BOOTH 登录 Cookie（仅本地使用，见下方隐私声明）。
> Agent 若无法直接 clone（无网络/无 git），可退回「安装」一节的软链/Junction 方式。

---

## 安装（Agent Skills 标准做法）

任何遵循以下规范的 Agent 都能直接加载：

- **父技能**：识别仓库根的 `SKILL.md`，按文件树的子目录加载 `skills/<name>/SKILL.md`
- **脚本执行**：`python scripts/<name>.py <args>`，依赖 `requests` + `Pillow`

```bash
git clone https://github.com/linnnnnnnnnnnnnnnnnnnnn/booth-free-collector.git
cd booth-free-collector
# 把整个仓库（含 SKILL.md + skills/）放到你的 Agent 能发现的 skills 目录
# 不同 Agent 的位置不同，例如：
#   - WorkBuddy : ~/.workbuddy/skills/booth-toolkit/ （Junction 或复制均可）
#   - Claude Code: .claude/skills/booth-toolkit/
#   - 自定义 Agent: <YOUR_AGENT_HOME>/skills/booth-toolkit/
ln -s "$(pwd)" /path/to/your-agent/skills/booth-toolkit    # 类 Unix 软链
# 或 mklink /D C:\path\to\your-agent\skills\booth-toolkit "$(pwd)"   # Windows Junction
```

依赖安装：
```bash
python -m venv .venv
.venv\Scripts\activate    # Windows；或 source .venv/bin/activate
pip install requests pillow
# 走网络代理：set HTTPS_PROXY=http://127.0.0.1:20122/（或 export HTTPS_PROXY=...）
```

加载后，父技能 `booth-toolkit` 会被自动识别（含描述、触发词），三个子技能按决策树路由触发。

---

## 输出结构（三子技能同构）

```
<用户指定输出根>\
└── <分类中文>\
    └── <ID_标题>\
        ├── <ID_标题>.zip   ← 原压缩包（移动 / 复制 / 下载）
        ├── cover.jpg            ← BOOTH 商品首图
        ├── .folder_icon.ico     (隐藏)
        └── desktop.ini          (隐藏+系统)
```

Windows 资源管理器「大图标」视图自动显示封面，无需手动配置。

---

## 防错快查（血泪案例汇总）

| 症状 | 根因 | 修复 |
|------|------|------|
| 封面显示默认文件夹图标 | desktop.ini/ico 缺 Hidden+System、文件夹缺 ReadOnly | 全库属性巡检（name-search §4.5） |
| 封面图标「居中小图」外留白 | cover 是宽幅矩形，PIL 按原图比例生成 ICO | 正方形画布 paste 后保存（§4.7） |
| 图标仍不显示（属性全对） | 目录名含装饰 Unicode（`❥⁺⌖˚`），Explorer 永久拒读 | `sanitize_filename` 过滤装饰 Unicode + **重启电脑**（§4.8） |
| 商品被误配张冠李戴 | 单结果盲信 / 标题相似但实为别家 | 名称归一化必须命中 + 解 UnityPackage 校验（§4.1/§4.3/§8.3） |
| 同题材商品分不清 | 只凭标题关键词相似归档 | 内部资源名首段目录=店铺名，交叉验证（§8.3） |
| zip 导入 Unity 失败 | zip UTF-8 标志 + Windows cp437 解码乱码（`É`→`╠ü`） | 7-Zip 重解压 / `Expand-Archive -Encoding UTF8`（§4.4） |

详细分析与完整防护规则见 `skills/booth-name-search/SKILL.md` 对应章节。

---

## 隐私声明（必读）

**本仓库不包含任何人的 BOOTH 登录 Cookie。**

- 下载类技能（booth-free-collector）需要 BOOTH 登录 Cookie 才能拉文件，**用户自行**从浏览器复制并通过 `--cookie` 参数传入
- Cookie 仅本地、当次运行使用；`.gitignore` 已屏蔽 `.booth_cookie.txt` / `*_cookie.txt` / `*_session*` / `._booth_trash` / `.env`
- 不收集、不上传、不共享任何用户数据

---

## 触发词（用于 AI Agent 路由）

- **父技能** `booth-toolkit`：下载免费鸡蛋、booth 下载、免费商品下载、VRChat 免费素材、booth 归档、整理 booth 压缩包、booth 整理、按名字搜 booth、booth 整理
- `booth-free-collector`：booth 整店下载、下载散链、领鸡蛋、白嫖鸡蛋、朋友发的 booth
- `booth-archive-organizer`：整理这个 booth 包、归档 booth 文件、按 ID 整理 booth
- `booth-name-search`：按名搜索 booth、整理 vrc 插件道具、找 booth 商品、整理着色器

---

## 贡献与反馈

- 仓库：https://github.com/linnnnnnnnnnnnnnnnnnnnn/booth-free-collector
- Issue / PR 都欢迎，但请勿提交任何 Cookie / Session / 个人配置

---

## License

MIT