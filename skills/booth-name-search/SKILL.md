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
故评分取 **JSON 规范名**（含英文别名）做归一化包含判定，多结果按规范名匹配度排序。

#### 4.1 单结果陷阱（血泪修正，务必遵守）
**曾经的写法「搜索只返回 1 个结果 → 直接采信」是错的。** BOOTH 的 `?q=` 会按标签/描述/店铺名做模糊召回，
关键词完全不沾边的商品也可能成为「唯一结果」，此时盲信必然张冠李戴。

一次批量重分类中该 bug 连造 **6 起误判**：

| 源文件 | 被误配到 | 实际应为 |
|---|---|---|
| `Moonpiercer.zip` | 7441550 Agent Owl（猫头鹰） | 待定，非 Agent Owl |
| `Éterna.zip` | 4986989 Bag（包） | 7475622 |
| `トミミの杖.zip` | 4236704 Face Gear | 7475262 |
| `Silent_Talk.zip` | 7747506 插画包 | 7436818 |
| `The_Smile.zip` | 911420 漫画 → 重试又误配 1917558 镜面球 | 仍待定 |
| （同批）| —— | —— |

**修正规则（已落入 `score_and_pick`）**：
```python
if not scored or scored[0][0] <= 0:
    if len(items) == 1:
        # 唯一结果也必须通过名称归一化包含校验
        if qn and (qn in _norm(_canonical_name(it["id"])) or qn in _norm(it["name"])):
            return items[0], False
        return None, False   # 名称不命中 → 判为未匹配，交人工/换关键词
    return None, False
```
即：**宁可返回「未匹配」交人工裁定，也绝不把不相干商品硬塞进库。**
误判的代价（错误封面 + 错误分类 + 源文件被改名打包）远高于漏判。

#### 4.2 启发式关键词兜底同样危险
重试逻辑里写 `any(w in name for w in ["smile","スマイル"])` 这类宽松兜底，
会把「ピンホール式ミラーボール」这种含误带词的商品捞进来。
**兜底匹配必须与主关键词做完整包含判定，不可用单词碎片 OR。**

#### 4.3 单结果「名称不命中」不是 100% 误判：必须再解 UnityPackage 验真
主上后续亲授纠正：

- `Moonpiercer.zip` 全局 `?q=Moonpiercer` 返回唯一结果 7441550「Agent Owl」，标题不命中曾被判误判；
- 主上解 zip → 解 `.unitypackage` → 导入 Unity 发现是「细剑」→ 搜索「Agent Owl」在 cybercritter 店铺锁定 7441550，
  内部 UnityPackage 资源名实为 Moonpiercer —— 结论：**唯一结果即使标题不匹配，也可能内部资源名才是真名**。

- `FREE無料-PoseAnimationMafuyu.zip` 外部文件名误导，实际 BOOTH 商品 5740973「Shapeshifter Clinic / Mafuyu FaceAnimation」；
- 解 UnityPackage 看到内部 `Shapeshifter Clinic` / `Mafuyu FaceAnimation` / `STAND.8.anim`，
  用「Shapeshifter Clinic」+「Mafuyu」做关键词交叉搜索，命中真身。

**修正（应升级入 `score_and_pick`）**：
```python
# 单结果 + 标题不命中 → 不立即判未匹配
# 进入「UnityPackage 内部线索」兜底：解压 zip → 解 .unitypackage (gzip)
#   → 提取 Unity 资源名（asset/prefab/mat/anim/unity 三段路径中的可读段）
#   → 与查询关键词做归一化包含校验
#   - 命中 → 采纳该唯一结果（即便标题不匹配）
#   - 不命中 → 返回 None，交人工裁定
```
**代价**：每次未命中搜索要解 zip + 解析 gzip 流，批量场景下慢。
**收益**：避免 Moonpiercer / Mafuyu 这类「标题是日文显示名 + 资源名才是英文真名」的盲点。

#### 4.4 zip 文件名编码陷阱：UTF-8 声明 + Windows cp437 解码乱码
少数卖家（多为 Linux/macOS 工具链）打 BOOTH 包时 zip 文件名声明 `flag_bits=0x8`（UTF-8），
但 Windows 默认 cp437 解码时，非 ASCII 字符（如 `É` U+00C9）会显示为乱码（如 `╠ü`）。
Unity 导入 zip 时拿到乱码文件名（如 `E╠üterna Ribbon.unitypackage`），会判为非法 Package 拒绝导入。

**案例**：7475622「Éterna Ribbon -【キプフェル Kipfel】」zip 内 unitypackage 实际是 gzip 流（14593614 字节），
仅文件名编码异常，文件本身完整无损。

**修复路径（不归 BOOTH 错，是 BOOTH 商品本身的问题）**：
1. 用 7-Zip / WinRAR 解压（自动识别 UTF-8）
2. PowerShell `Expand-Archive -Encoding UTF8`
3. 联系卖家（`https://kipfel.booth.pm/`）重新打包

**整理术式侧**：归档正确（7475622 → 3D服饰），但建议在归档目录留 `_ISSUE_*.txt` 标注问题，
避免主上反复尝试 Unity 导入失败。

#### 4.5 分类目录图标失效（目录被移动/拷贝后）
现象：文件夹在资源管理器中显示**默认图标或过小图标**、封面不生效——即便 `desktop.ini` 和 `.folder_icon.ico` 文件都在。

根因：Windows 读取 `desktop.ini` 的**前提是文件带 Hidden+System 属性、文件夹带 ReadOnly 属性**；
目录被移动/拷贝后这些属性会被清掉，资源管理器便不再读 desktop.ini。

修复（批量巡检）：
```python
# desktop.ini / .folder_icon.ico → Hidden+System；文件夹 → ReadOnly
a = ctypes.windll.kernel32.GetFileAttributesW(p)
ctypes.windll.kernel32.SetFileAttributesW(p, a | 0x02 | 0x04)   # 文件
ctypes.windll.kernel32.SetFileAttributesW(p, a | 0x01)          # 文件夹
```
2026-08-01 主上 `G:\Lin_File\BOOTH` 全库 104 目录一次修复；根因是**别的 agent 运行下载脚本后移动目录**，
脚本幂等分支只判「文件存在」未补设属性（已修 `booth_free_dl.py`）。

#### 4.6 分类名必须与下载脚本一致（防目录分裂）
`booth_free_dl.py`（下载）与 `booth_name_search.py`（整理）的 `CATEGORY_MAP` 必须同源：
曾因下载脚本把 `3D衣装→3D服装`、`3D環境・ワールド→3D世界`，而整理脚本映射为 `3D服饰/3D环境`，
同一类目分裂成两个目录。统一规则（以本脚本为准）：
`3D衣装→3D服饰`、`3Dモデル→3D模型`、`3Dモデル（その他）→3D模型（其他）`、
`3D装飾品→3D饰品`、`3Dキャラクター→3D角色`、`3D小道具→3D道具`、`3D環境・ワールド→3D环境`。
若发现历史目录分裂（如 `3D服装` 与 `3D服饰` 并存），合并时移动商品目录并重设图标属性。

#### 4.7 ICO 宽幅条目陷阱（血泪修正）
现象：缩略图中图标**居中显示、外围大片空白**（如「256x154」居中在缩略图里）。

根因：cover.jpg 是宽幅矩形（1024x615 等）时，`PIL.Image.save('xxx.ico', sizes=[(256,256),...])`
**按原图比例生成 ICO 条目**（256x154），Windows 大图标视图按 ICO header 的 W×H 显示，
所以缩略图里只看到一个小矩形 + 大量空白。

修复：`make_folder_icon` 必须先粘贴到正方形画布再保存：
```python
img = Image.open(cover).convert("RGBA")
side = max(img.size)
canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))   # 透明背景
canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
canvas.save(ico_path, format="ICO", sizes=[(256,256), (128,128), (64,64), (48,48), (32,32), (16,16)])
```
之前 `booth_name_search.py` 的 `make_folder_icon` 漏了这步，导致宽幅 cover 的目录全部出现「居中小图」。
已全库扫描并重生成 7 个受影响目录（icon header 从 256x154 等变为 256x256）。

**判定哪些目录受影响**：读 `.folder_icon.ico` 的 ICO header，
若任一条目 `width != height`（如 256x154），就需要重生成。

#### 4.8 Explorer 永久拒绝应用 desktop.ini（装饰 Unicode 目录名）
现象：cover.jpg / .folder_icon.ico / desktop.ini / 属性全部正确，但 Explorer **仍然**显示默认文件夹图标。
已尝试：SHChangeNotify（PIDL + 全 shell）、`ie4uinit.exe -show`、重启资源管理器——**均无效**。

根因：目录名含装饰 Unicode 时（`❥` U+2765、`⁺` U+207A、`⌖` U+2316、`˚` U+02DA、
`🌕` U+1F315、`💗` U+1F497、`！！` U+FF01 范围内的部分符号），
Windows 资源管理器**永久**不读该目录的 desktop.ini（缓存失效，IE4UInit 刷不出来）。
2026-08-01 主上亲身验证：ie4uinit.exe -show + 重启资源管理器后依旧显示默认文件夹图标。

**唯一修复**：从源头清理目录名——`sanitize_filename` 必须过滤装饰 Unicode 区块：
```python
# 剔除（保留 ASCII / 中日韩 / 全角 FF00-FFEF）
- 0x1F300-0x1F9FF  # emoji 区块
- 0x2000-0x27BF    # General Punctuation + Misc Technical + Dingbats + Symbols
- 0x2B0-0x2FF      # Spacing Modifier Letters（含 ˚）
- 0x2070-0x209F    # Superscripts and Subscripts（含 ⁺）
- combining marks (Mn/Me) + 未定义 (Cn)
```
示例：BOOTH 原标题「！！SALE~8.31 ！！ 💗【FREE無料】Mafuyu100Type❥動くまばたきFace&PoseAnimations ⌖ ݁˚」
→ 清洗后「！！SALE~8.31 ！！ 【FREE無料】Mafuyu100Type動くまばたきFace&PoseAnimations」
→ Explorer 立即显示封面。

已修复 5740973 / 7100790 两个历史目录（重命名 + 重生成图标）。

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

### 7. 套装 / 多角色变体：合并为单一文件夹 + 子文件名线索 + 店铺子域无 `data-product-id`

**主上亲授案例（UmikoLab ハロウィンネイル）**：拖入 7 个 `UmikoLab_HWNail<角色>.zip`
（Hakuu / ICHIGO / Nevry / Retinia / SharlenSenri / Shinano / TinmeshiTei），主上明言
「一套美甲、多人多角色适配，统合放入一个文件夹就好」。经解析，这是 BOOTH 商品
**【9アバター対応】ハロウィンネイル**（编号 **7437926**，うみこLab = UmikoLab 店铺，¥100）。

该案例沉淀出三条此前未覆盖的术式要点：

#### 7.1 套装 / 多角色变体 → 合并为「一个」文件夹（绝不每变体一个）
- 当主上说明「一套 X、多角色适配、统合放一个文件夹」时，**全部变体 zip 归入同一目录**，
  而非按变体拆成 N 个 `ID_标题` 文件夹。
- 目录名取**套装层面的 BOOTH 商品编号 + 套装总称**（如 `7437926_【9アバター対応】ハロウィンネイル`），
  封面与文件夹图标照常设置一次即可。
- 变体 zip 可保留各自文件名（如 `UmikoLab_HWNailHakuu.zip`），无需逐个改名。

#### 7.2 压缩包内子文件名是搜索线索
- 全局 `?q=` 搜不到时（如本例 `?q=UmikoLab HWNail` 0 命中，`?q=Halloween Nail` 60 件但都是别家），
  **打开变体 zip 看内部 unitypackage / 资源文件名**：本例内部均为 `HalloweenNail<角色>`，
  直指「Halloween Nail」套装主题。
- 子文件名 + 主上给的店铺/作者线索（UmikoLab）共同收敛搜索空间。

#### 7.3 店铺子域翻页：无 `data-product-id`，需解析 `/ja/items/<id>` 链接
- 本例店铺 `umikolab.booth.pm/items` **无 Cloudflare 护盾**（HTTP 200），但 HTML 结构异于全局搜索：
  **不含 `data-product-id` 属性**，商品以 `/ja/items/<id>` 链接形式渲染。
- 解析法门（与第 3 节「走子域名翻页」互补，但此处不能靠 `data-product-id`）：
  1. 抓取 `https://<子域名>.booth.pm/items?page=N`（可多页）
  2. 正则提取所有 `/ja/items/(\d+)` 链接 → 得到候选商品 ID 列表
  3. **逐一对 `https://booth.pm/ja/items/<id>.json` 取规范名**，用套装关键词
     （本例 `ネイル` / `nail` / `ハロウィン`）命中正确编号
  4. 命中后按 7.1 合并目录 + 封面 + 图标
- 注意：店铺页 HTML 片段常含日文商品名（如 `【9アバター対応】ハロウィンネイル(¥ 100)`），
  可先肉眼核对片段，再发 JSON 请求确认 ID 与封面 URL。

> 该案例为**手动统合术式**（脚本当前不自动做多文件套装合并）：先按主上指令把变体 zip
> 聚到临时文件夹，再用 `fetch_item()` + `download_cover()` + `make_folder_icon()` 补全编号与封面。

### 8. 双层文件名线索：拆词 + 解 UnityPackage

主上亲授的两条关键搜索技巧（解决了 `LunariaPaperFan.zip` / `FREE無料-PoseAnimationMafuyu.zip` 两个误归档）：

#### 8.1 大写连写拆词
**主上原话**：`LunariaPaperFan.zip` 去掉 `.zip` 得 `LunariaPaperFan`，三个大写单词之间加空格 → `Lunaria Paper Fan`，
就能正确找到原主（BOOTH 7437723「FREE Lunaria Paper Fan (PC/Quest)」，Lunaria Ayaren 店铺）。

**原理**：BOOTH 搜索对驼峰命名极其不友好，「LunariaPaperFan」整体作为关键词几乎搜不到原主，
但「Lunaria Paper Fan」会被切成 3 个词，全文索引命中所有出现位置。
类似场景：`SimpleJoinAlert_v100` → `Simple Join Alert`，`StarTiara_v1.0` → `Star Tiara`。

**已实现**：`sanitize_query()` 策略 1.5 加了驼峰拆词：
```python
# 驼峰拆词（CamelCase → spaced words）
split_camel = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', name).strip()
# 作为次优候选（保留原名优先级），类似 LunariaPaperFan → Lunaria Paper Fan
```

#### 8.2 解 UnityPackage 看内部资源名（深度线索）
**主上原话**：希望学会把 unitypack 包解开看里面东西去搜索。

**示例（7678707 真身 5740973）**：
- 外部文件名 `FREE無料-PoseAnimationMafuyu.unitypackage` 误导，「Pose Animation Mafuyu」搜不到原主；
- 解 UnityPackage（zip 内 .unitypackage = gzip 流）：
  ```
  Shapeshifter Clinic/
    [Mafuyu] FaceAnimation/
      (FREE$ 無料) Mafuyu/
        STAND.8.anim        ← 关键资源名
        ...
  ```
- 搜「Shapeshifter Clinic」+「Mafuyu」→ 命中 5740973「動くまばたき Face & Pose Animations」。

**实现要点**（已提议加入 score_and_pick）：
```python
import gzip, io
def extract_unitypkg_resource_names(zip_path: str) -> set[str]:
    """提取 zip 内 .unitypackage 的可读资源名（asset/prefab/mat/anim/unity 路径段）。"""
    names = set()
    with zipfile.ZipFile(zip_path) as z:
        for n in z.namelist():
            if n.lower().endswith('.unitypackage'):
                try:
                    with gzip.open(io.BytesIO(z.read(n))) as g:
                        for raw in g.read().decode('utf-8', 'replace').split('\x00'):
                            if raw and not raw.startswith('._') and len(raw) > 3:
                                # 取路径末段（如 ".../asset.mat"）
                                last = raw.rsplit('/', 1)[-1]
                                if '.' in last:
                                    stem = last.rsplit('.', 1)[0]
                                    if stem: names.add(stem)
                except Exception: pass
    return names
```

**搜索策略升级**：单结果 + 标题不命中时，先调用 `extract_unitypkg_resource_names()`，
再用查询关键词去匹配内部资源名（做归一化包含判定）；命中则采纳。

#### 8.3 UnityPackage 内部资源名的「首段目录 = 店铺名 / 作者名」（硬锚点）
**主上第三次纠错（6585620 → 5928702）**：

- 目录 `6585620_Crystal Earandtail（耳・猫尻尾・狐尻尾・九尾の4つセット）` 曾被归档到 3D饰品，
  cover 显示 PIROUETTE_C 女角色 + "EAR AND TAIL / Thx 1st anniv"，zip 内 UnityPackage 资源名
  `1st earandtail / Pirouette / earandtail1-3.prefab`。
- 我第一次判断「cover 和 zip 是同一个商品」——**错**。cover 上的 PIROUETTE_C 女角色是**目标 avatar**
  （配饰要戴在哪个 avatar 上），不是配布店铺本身。
- 真身是 **5928702「Thx 1st ear and tail 【VRChat】」**（店铺 **Pirouette** = pipi18），
  因为 UnityPackage 内部资源名的**首段目录 `Pirouette` 就是店铺名**——这是最硬的搜索锚点；
  而 6585620 是另一家（tubomishop）的同题材商品，封面风格相似但**不是同一件**。

**规则**：
1. 解 UnityPackage 后，**首段目录名（如 `Pirouette`、`Shapeshifter Clinic`）优先当作店铺名/作者名**，
   直接搜 `https://booth.pm/ja/items?q=<首段名>` 或去 `https://<子域>.booth.pm/items` 翻页反查。
2. **封面上的角色/场景 ≠ 配布店铺**——那是展示用的目标 avatar。判断商品归属
   **以内部资源名 + 店铺子域为准**，不凭封面角色猜。
3. 相似题材商品（ear and tail、nails、hair 等）多家都有，**必须用内部资源名交叉验证**，
   不能凭「标题关键词相似」直接归档。

#### 8.4 校验流程：解包三层（压缩包 → UnityPackage → 资源名/店铺名）
对一个无 ID 的本地包，真身校验的推荐顺序：
```
1. 文件名清洗 → ?q= 搜索 → 评分（§4）
2. 若命中唯一/高分 → 解 zip 内部 .url / readme / 水印（§3）
3. 仍不确定 → 解 .unitypackage 看资源名：
   - 首段目录 = 店铺名/作者名（§8.3）→ 搜索该店铺
   - 内部 prefab/anim 名 = 商品主题（§8.2）→ 交叉验证
4. 全部交叉命中一致 → 归档；任一环节矛盾 → 上报主上人工裁定
```
**血泪总结**：凡「标题相似但内部资源名指向别家」的，一律以**内部资源名 + 店铺**为准。

### 9. 已下架 / 非 BOOTH 商品的归宿

部分商品虽然在 BOOTH 店铺页可查（`https://<店铺>.booth.pm/`）但**单件商品已下架**（`is_end_of_sale: true`），
无法定位确切 ID；或商品本来就不在 BOOTH（如 Gumroad / Patreon 分发）。

**处理规则**：
- 不强求 ID，归档到 `G:\Lin_File\BOOTH\已下架商品\`，目录命名 `<店铺>_<商品名>(疑似下架)`，
  留 `_NOTE.txt` 说明来源店铺与状态。
- 主上后续如拿到确切 ID，可再用 `process_file(..., force_id=...)` 重新整理。

**案例**：
- `The_Smile.zip` → `已下架商品/EXEERON_Project_E.G.O笑顔(疑似下架)_The_Smile/_NOTE.txt`
  记录来源 `https://gardenia601.booth.pm/`、状态「BOOTH 商品疑似下架」。

## 工作流程

0. **套装 / 多角色识别（前置）**：若主上明言「一套 X、多角色适配、统合放一个文件夹」，
   先定位全部变体 zip 聚入同一临时目录，按 **第 7 节** 处理（合并为单一 `ID_标题` 文件夹 + 一次封面/图标），
   **不**走单文件逐件整理。
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