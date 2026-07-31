# BOOTH Free Collector · BOOTH 免费商品批量下载归档

自动爬取 BOOTH 店铺的 **0 円免费商品**（或下载好友/群里分享的零散免费商品链接），
按「商品分类(中文)/商品ID_标题/」结构归档，并为每个商品文件夹生成 Windows 大图标封面预览。

> VRChat 社区黑话：BOOTH 免费商品 = **「鸡蛋 / 免费鸡蛋」**。
> 「帮我下载免费鸡蛋」== 下载这家店的免费商品。

---

## ⚠️ 隐私声明（必读）

**本仓库不包含任何人的登录 Cookie。**

BOOTH 的免费文件下载 **必须登录**（不登录会返回伪装成 zip/png 的登录页 HTML）。
因此运行脚本时，你需要 **自己** 从浏览器复制 BOOTH 的登录 Cookie，通过 `--cookie` 参数传入：

```bash
python scripts/booth_free_dl.py "https://xxx.booth.pm/" --cookie "你的cookie串"
```

Cookie 只在你本地、本次运行中使用，**不要**提交到任何仓库或发给他人。
仓库已通过 `.gitignore` 屏蔽 `.booth_cookie.txt` / `*_cookie.txt` / `*_session*`，杜绝误提交。

---

## 安装

```bash
git clone https://github.com/linnnnnnnnnnnnnnnnnnnnnn/booth-free-collector.git
cd booth-free-collector

python -m venv .venv
.venv\Scripts\activate        # Windows
pip install requests pillow

# 脚本在 scripts/ 目录下，运行需加路径前缀
# python scripts/booth_free_dl.py ...
```

> 代理：脚本使用 `requests`，会自动读取 `HTTPS_PROXY` 环境变量。
> 直连 `booth.pm` 可能 SSL 握手失败，请保留网络代理。

---

## 用法

### 1. 按店铺整店下载

```bash
python scripts/booth_free_dl.py "https://atelier-kotone.booth.pm/" --out "G:/Lin_File/BOOTH"
```

### 2. 好友 / 群里分享的零散链接（自动判定为「散链模式」）

```bash
python scripts/booth_free_dl.py --items \
  "https://atelier-kotone.booth.pm/items/6574952" \
  "https://booth.pm/ja/items/6574953" \
  "8103811"        # 裸 ID 也行
```

### 3. 单条商品链接直接丢进去

```bash
python scripts/booth_free_dl.py "https://atelier-kotone.booth.pm/items/8103811"
```

脚本根据输入 **自动判定** 整店 / 散链，无需手动指定模式。

### 参数

| 参数 | 说明 |
|---|---|
| `shop` | 店铺 URL / 子域名；若含 `/items/<id>` 则自动转散链模式 |
| `--items` | 零散商品链接/ID（可传多个，空格分隔；或一条字符串内逗号/换行分隔） |
| `--out` | 输出根目录，默认 `./booth_downloads`（当前目录下） |
| `--cookie` | **必需**（下载文件时）。原始 `k=v; k2=v2` 串 / cookies.txt / 存串的文本文件。会话 Cookie 真名是 `_plaza_session_nktz7u`，建议连同 `cf_clearance` 一起复制 |
| `--ua` | 通常无需指定；实测下载仅需有效会话 Cookie，默认 UA 即可（仅 Cloudflare 挑战页需与浏览器一致） |
| `--dry-run` | 只列出将下载的免费商品，不写盘（新源建议先 dry-run 确认） |
| `--limit N` | 最多处理 N 个免费商品 |
| `--folder-by` | `category`（默认，按分类中文名）或 `first-tag`（按第一个标签）分组 |

---

## 如何获取你的 Cookie

1. 浏览器登录 BOOTH（https://booth.pm ）
2. 打开任意商品页 → F12 → Network（网络）标签
3. 刷新页面，点任意一个请求 → 复制 **Request Headers** 里的 `Cookie:` 整行
4. 连同 `_plaza_session_nktz7u` 与 `cf_clearance` 一起传给 `--cookie`

> 注意：`cf_clearance` 由 Cloudflare 签发、与 UA 绑定。换浏览器/UA 需重新获取。

---

## 输出结构

```
G:\Lin_File\BOOTH\
├── 3D饰品\
│   └── 7603673_【FREE】あったかニット帽🧶\
│       ├── ニット帽_v1.1.zip
│       ├── cover.jpg
│       ├── .folder_icon.ico   (隐藏)
│       └── desktop.ini        (隐藏+系统)
├── 海报\
└── 3D贴图\
```

每个商品文件夹含 `cover.jpg` 并自动设为 Windows 文件夹图标，
资源管理器「大图标」视图可直接预览封面。

> 输出目录保持纯净：除商品内容文件与封面图标三件套（cover.jpg / .folder_icon.ico / desktop.ini）外，不写入任何清单/日志副产物。重跑时通过文件系统扫描跳过已下载项（幂等）。

---

## 分类汉化表

| BOOTH 分类 | 中文文件夹 |
|---|---|
| 3Dテクスチャ | 3D贴图 |
| 3D衣装 | 3D服装 |
| 3D装飾品 | 3D饰品 |
| 3Dモデル | 3D模型 |
| 3Dキャラクター | 3D角色 |
| 3D小道具 | 3D道具 |
| 3D環境・ワールド | 3D世界 |
| 3Dモーション・アニメーション | 3D动作 |
| 3Dツール・システム | 3D工具 |
| ポスター | 海报 |
| イラスト | 插画 |
| 素材データ | 素材数据 |
| 音楽 | 音乐 |
| アバター | 虚拟形象 |
| アクセサリー | 配饰 |
| その他 | 其他 |

---

## 注意事项

- **不登录 = 假文件**：未登录下载会得到「登录页 HTML 伪装成的 zip/png」。脚本内置魔数校验，检测到 HTML 即报错删除；重跑时假文件会被自动识别并重下。
- **免费判定以 variation 为准**：`variations[].price == 0` 才下，付费商品绝不会误下。
- **礼貌爬取**：请求间隔 0.6~0.8s，勿并发轰炸 booth.pm。
- **代理瞬断**：个别文件失败直接再跑一遍（幂等重跑只补失败项）。
- 仅新增文件，绝不删除/移动已有文件。

---

## License

[MIT](LICENSE)
