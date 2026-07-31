# BOOTH Toolkit — BOOTH 素材全家桶（WorkBuddy Skill）

BOOTH（日本数字创作集市，VRChat 素材主产地）素材的 **下载 / 归档 / 按名搜索整理** 三件套，整合为一个 WorkBuddy 父技能，下属三个子技能各司其职。

> 仓库原名 `booth-free-collector`，现已升级为统一工具箱 `booth-toolkit`，仓库 URL 保持不变。

## 子技能一览

| 子技能 | 用途 | 入口 |
|--------|------|------|
| **booth-free-collector** | 给定整店 URL 或好友/群分享的散链，自动判定输入类型，爬取并下载 **免费（0 円）** 商品；输出分类目录 + 封面图标。 | `skills/booth-free-collector/` |
| **booth-archive-organizer** | 整理本地已有的 BOOTH 压缩包归档（文件名含 7 位商品 ID），按类目重命名归档到标准目录。 | `skills/booth-archive-organizer/` |
| **booth-name-search** | 仅有文件名、没有商品 ID 时，从文件名反搜 BOOTH 商品（去版本号/下划线→空格/`q=` 搜索/解析压缩包内水印店铺链接）。 | `skills/booth-name-search/` |

三者在本地统一输出 `G:\Lin_File\BOOTH\<类目中文>\<ID>_<标题>\` 结构（含 `cover.jpg` 封面与 Windows 文件夹大图标）。

## 安装（WorkBuddy）

将本仓库作为技能放入 WorkBuddy：

```bash
# 方式一：直接放入技能目录
git clone https://github.com/linnnnnnnnnnnnnnnnnnnnn/booth-free-collector.git
# 将仓库根目录（含 SKILL.md / skills/）软链或复制到：
#   ~/.workbuddy/skills/booth-toolkit/

# 方式二：Junction 链接（Windows，推荐，源目录统一管理在 G 盘）
New-Item -ItemType Junction -Path "$HOME/.workbuddy/skills/booth-toolkit" `
         -Target "G:\Lin_File\Documents\Skills\booth-toolkit"
```

放入后，WorkBuddy 会自动发现父技能与三个子技能，按触发词（如「下载免费鸡蛋」「booth归档」「按名字搜booth」）激活对应子技能。

## 隐私声明

本工具箱 **绝不** 包含任何登录凭据：

- 下载类子技能（booth-free-collector）所需的 BOOTH 登录 Cookie 由使用者本地自行填入，存于 `.booth_cookie.txt`，已被 `.gitignore` 屏蔽，**不会** 进入本仓库。
- 仓库 `.gitignore` 已屏蔽 `*_cookie.txt` / `*_session*` / `._booth_trash/` / `.env` 等敏感或临时文件。

## 许可

MIT —— 见根目录 `LICENSE`。
