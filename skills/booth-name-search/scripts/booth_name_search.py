#!/usr/bin/env python3
"""
booth_name_search.py — BOOTH 商品名搜索整理术式
从文件名提取关键词，搜索 BOOTH，下载封面并整理本地文件。

用法:
  python booth_name_search.py <file1.zip> [file2.rar ...] [--base-dir G:/Lin_File/BOOTH]
"""
import argparse
import os
import re
import sys
import time
import struct
import ctypes
import gzip
import io
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image

try:
    from send2trash import send2trash
except Exception:
    send2trash = None

# ── 常量 ──────────────────────────────────────────────────────────
BOOTH_BASE = "https://booth.pm/ja"
SEARCH_URL = f"{BOOTH_BASE}/items"
ITEM_JSON  = f"{BOOTH_BASE}/items/{{id}}.json"
# BOOTH 类目 → 中文（覆盖付费商品常见类目；key 取自 JSON category.name）
CATEGORY_MAP = {
    # ── 3D / VRChat 头像系 ──
    "3Dアバター": "3D头像", "3D衣装・アクセサリー": "3D服饰",
    "3Dモデル": "3D模型", "3Dモデル（その他）": "3D模型（其他）",
    "3D装飾品": "3D饰品", "3D環境・ワールド": "3D环境",
    "3Dキャラクター": "3D角色", "3D小道具": "3D道具",
    "アバター": "头像", "アバターアイテム": "头像物品", "アバターギミック": "头像机关",
    "アクセサリ": "饰品", "アクセサリー": "饰品", "衣装・アクセサリー": "服饰饰品",
    "衣装": "服饰", "髪": "发型", "ヘアー": "发型", "ヘア": "发型",
    "バッジ": "徽章",
    "モーション": "动作", "ギミック": "机关", "リギング": "绑定",
    "テクスチャ": "贴图", "テクスチャ素材": "贴图素材", "シェーダー": "着色器",
    "エフェクト": "特效", "ツール": "工具", "ツール・プラグイン": "工具插件",
    "物理": "物理", "VR": "VR",
    "ソフトウェア": "软件", "3Dモーション・アニメーション": "3D动作",
    "3Dツール・システム": "3D工具", "3D衣装": "3D服饰",
    "3Dシェーダー・マテリアル": "3D着色器", "3Dテクスチャ": "3D贴图",
    "テクスチャ・素材": "贴图素材",
    # ── 音频 / 素材 / 视觉 ──
    "ﾓｼﾞｬｰﾙｱｲﾃﾑ": "AR物品", "音声": "语音", "効果音・SE": "音效",
    "BGM": "BGM", "素材": "素材", "イラスト": "插画", "漫画": "漫画",
    "小説": "小说", "ポスター": "海报", "その他": "其他",
    # ── 游戏 / VRChat 道具（付费重灾区）──
    "ゲーム": "游戏", "ゲーム関連商品": "游戏相关", "フリーゲーム": "免费游戏",
}
# 父级类目兜底（JSON category.parent.name）
CATEGORY_PARENT_MAP = {
    "3Dモデル": "3D模型", "ゲーム": "游戏", "アバター": "头像",
}


def classify(cat_name: str, cat_parent: str = "") -> str:
    """
    将 BOOTH 类目名映射为中文。
    优先精确匹配；缺失则退回父级类目；再缺失则保留日文原名（绝不臆造）。
    付费商品与免费商品走同一权威映射，不因价格改变归类。
    """
    if not cat_name:
        return "未分类"
    if cat_name in CATEGORY_MAP:
        return CATEGORY_MAP[cat_name]
    if cat_parent and cat_parent in CATEGORY_MAP:
        return CATEGORY_MAP[cat_parent]
    if cat_parent and cat_parent in CATEGORY_PARENT_MAP:
        return CATEGORY_PARENT_MAP[cat_parent]
    # 未知类目：保留原名并提示，绝不乱归类
    return cat_name
PROXY = os.environ.get("HTTPS_PROXY", "http://127.0.0.1:20122/")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en;q=0.9,zh-CN;q=0.8",
}

# ── 会话 ──────────────────────────────────────────────────────────
sess = requests.Session()
sess.headers.update(HEADERS)
if PROXY:
    sess.proxies = {"https": PROXY, "http": PROXY}

# ── 查询清洗 ──────────────────────────────────────────────────────
def sanitize_query(filename: str) -> list[str]:
    """
    从文件名生成 BOOTH 搜索候选关键词。
    策略（主上妙招）：
      0. 下划线替换为空格（主上验证：SimpleJoinAlert_v100 / Chocolat_Real_skin — BOOTH 不认下划线）
      1. 去扩展名
      2. 去版本号：_v100, v2, 2.0, _v1.2 等
      3. 去中文备注（主上手加的描述性中文，与英文名分离）
      4. 去 VRChat 常见后缀词
    返回按优先级排序的候选列表（首个最可能命中）。
    """
    name = Path(filename).stem  # 去扩展名

    # 0. 下划线 → 空格（主上验证：SimpleJoinAlert_v100 / Chocolat_Real_skin — BOOTH 不认下划线）
    name = name.replace('_', ' ')

    # 去括号及内容  SimpleJoinAlert(1) → SimpleJoinAlert
    name = re.sub(r'[\(（\[【].*?[\)）\]】]', '', name)

    # 0.5 大写连写拆词（主上妙招：LunariaPaperFan → Lunaria Paper Fan 才能命中 7437723；
    # 类似：StarTiara_v1.0 → Star Tiara，SimpleJoinAlert → Simple Join Alert）
    # 连续 [a-z][A-Z] 边界插空格；保留原始名作为另一候选
    split_camel = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', name).strip()
    split_camel = re.sub(r'\s+', ' ', split_camel)

    candidates = []

    # 策略 1: 完整名（去括号后）
    c1 = name.strip()
    if c1:
        candidates.append(c1)

    # 策略 1.5: 拆词版（驼峰拆词，主上妙招；优先级低于原名，避免误改）
    if split_camel and split_camel != c1:
        candidates.append(split_camel)

    # 策略 2: 去版本号
    # 匹配: _v100, v2, 2.0, _v1.2.3, _v2024, Version2, Ver1.0 等
    c2 = re.sub(r'[_\-\s]?(?:v(?:er(?:sion)?)?\.?|version\s*)\d+(?:\.\d+)*[_\-\s]?', '', name, flags=re.I)
    c2 = re.sub(r'[_\-\s]\d+\.\d+(?:\.\d+)*$', '', c2)  # 尾部 2.0, 1.2.3
    c2 = c2.strip()
    if c2 and c2 not in candidates:
        candidates.append(c2)

    # 策略 3: 去版本号 + 去尾部中文
    # 分离：英文/日文主体 + 尾部连续中文（通常为主上备注）
    c3 = re.sub(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff].*$', '', c2).strip()
    if c3 and c3 not in candidates and len(c3) >= 3:
        candidates.append(c3)

    # 策略 4: 只取英文/数字主体（最长连续 ASCII 段）
    ascii_parts = re.findall(r'[A-Za-z][A-Za-z0-9_]{2,}', name)
    for part in sorted(ascii_parts, key=len, reverse=True):
        if part not in candidates and len(part) >= 4:
            candidates.append(part)

    # 策略 5: 去常见 VRChat 后缀词后
    vrc_stoppers = [
        'vrchat', 'vrc', 'unitypackage', 'package', 'prefab',
        'gimmick', 'shader', 'world', 'avatar',
        '玩家', '加入', '退出', '弹窗', '提示', '通知', '音效',
    ]
    c5 = c2
    for stop in vrc_stoppers:
        c5 = re.sub(rf'[_\-\s]?{re.escape(stop)}[_\-\s]?', ' ', c5, flags=re.I)
    c5 = re.sub(r'\s+', ' ', c5).strip()
    if c5 and c5 not in candidates and len(c5) >= 3:
        candidates.append(c5)

    # 去重保序
    seen = set()
    unique = []
    for c in candidates:
        key = c.lower()
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique if unique else [name]


# ── 搜索 BOOTH ───────────────────────────────────────────────────
def search_booth(query: str) -> list[dict]:
    """用 ?q= 搜索 BOOTH，返回匹配商品列表。"""
    url = f"{SEARCH_URL}?q={quote(query)}"
    try:
        r = sess.get(url, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"  搜索失败: {e}")
        return []

    html = r.text
    items = []

    # 解析 <li> 卡片中的 data-* 属性
    for m in re.finditer(r'data-product-id="(\d+)"', html):
        pid = m.group(1)
        start = max(0, m.start() - 300)
        end = min(len(html), m.end() + 4000)
        ctx = html[start:end]

        def attr(pattern, default=""):
            match = re.search(pattern, ctx)
            return unescape_html(match.group(1)) if match else default

        name     = attr(r'data-product-name="([^"]*)"')
        price    = attr(r'data-product-price="([^"]*)"')
        brand    = attr(r'data-product-brand="([^"]*)"')
        category = attr(r'data-product-category="([^"]*)"')

        # 店铺名
        shop_m = re.search(r'item-card__shop-name[^>]*>([^<]+)<', ctx)
        shop   = shop_m.group(1).strip() if shop_m else brand

        # 封面图（data-original 优先）
        thumb_m = re.search(r'data-original="(https://booth\.pximg\.net/[^"]*)"', ctx)
        thumb   = thumb_m.group(1) if thumb_m else ""

        # 分类名
        cat_name_m = re.search(r'item-card__category-anchor[^>]*>([^<]+)<', ctx)
        cat_name   = cat_name_m.group(1).strip() if cat_name_m else ""

        # 价格文本
        price_text_m = re.search(r'price[^>]*>([^<]*\d+[^<]*)<', ctx)
        price_text   = price_text_m.group(1).strip() if price_text_m else f"¥ {price}"

        items.append({
            "id": pid,
            "name": name,
            "price": int(price) if price.isdigit() else -1,
            "price_text": price_text,
            "brand": brand,
            "shop": shop,
            "category": category,
            "category_name": cat_name,
            "thumbnail": thumb,
        })

    return items


def unescape_html(s: str) -> str:
    from html import unescape
    return unescape(s)


# ── 压缩包内水印识别（主上妙招）──────────────────────────────────
WATERMARK_PATTERNS = [
    r'https?://([\w-]+)\.booth\.pm/?',
    r'booth\.pm/[\w/]+/items/(\d+)',
    r'booth\.pm/items/(\d+)',
]


def detect_watermark_url_in_zip(filepath: str) -> str:
    """
    探查压缩包内是否含 BOOTH 店铺 URL 或商品 ID 链接。
    优先级：
      1. *.url 文件（Windows 快捷方式，常见为创作者工具链产物）
      2. *.txt / *.md / readme 等文本文件
      3. PNG/JPG 图片文件名 / 元数据（图片内容 OCR 需调用外部模型，本术式跳过）
    返回首个发现的 URL（若有），否则空字符串。
    """
    import zipfile
    fp = Path(filepath)
    if not fp.exists() or fp.suffix.lower() not in ('.zip',):
        return ""
    try:
        with zipfile.ZipFile(fp) as z:
            for n in z.namelist():
                ln = n.lower()
                if ln.endswith('.url') or ln.endswith('.txt') or 'readme' in ln or 'info' in ln:
                    try:
                        content = z.read(n).decode('utf-8', errors='replace')
                        for pat in WATERMARK_PATTERNS:
                            m = re.search(pat, content)
                            if m:
                                full = re.search(r'https?://[^\s"<>]+', content)
                                return full.group(0) if full else m.group(0)
                    except Exception:
                        continue
    except Exception:
        return ""
    return ""


def extract_shop_id_from_url(url: str) -> str:
    """从 BOOTH 店铺 URL 提取子域名（如 'no39'），供 list_shop_items 使用。"""
    m = re.search(r'https?://([\w-]+)\.booth\.pm', url)
    return m.group(1) if m else ""


def list_shop_items(shop_subdomain: str) -> list[dict]:
    """
    列取店铺全部商品（子域名为例 'no39'，对应 https://no39.booth.pm/items）。
    店铺根 `/` 通常有 Cloudflare 护盾，必须走 `/items?page=N` 翻页。
    """
    items = []
    for page in range(1, 6):  # 最多 5 页 60 件内
        try:
            r = sess.get(f"https://{shop_subdomain}.booth.pm/items?page={page}",
                         timeout=30)
            if r.status_code != 200:
                break
            ids = re.findall(r'data-product-id="(\d+)"', r.text)
            if not ids:
                break
            for pid in ids:
                d = fetch_item(pid)
                if d:
                    cat = d.get("category") or {}
                    items.append({
                        "id": pid,
                        "name": d.get("name", ""),
                        "price": _parse_price(d.get("price")),
                        "price_text": "",
                        "brand": "",
                        "shop": d.get("shop", {}).get("name", "") if isinstance(d.get("shop"), dict) else str(d.get("shop", "")),
                        "category": cat.get("name", ""),
                        "category_name": cat.get("name", ""),
                        "category_parent": (cat.get("parent") or {}).get("name", ""),
                        "thumbnail": _thumb_from_json(d),
                    })
            time.sleep(0.5)
        except Exception:
            break
    return items


# ── 结果评分 ──────────────────────────────────────────────────────
_json_cache: dict[str, str] = {}

def _canonical_name(item_id: str) -> str:
    """取 BOOTH JSON 规范名（含英文别名，卡片显示名多为日文）。带缓存。"""
    if item_id in _json_cache:
        return _json_cache[item_id]
    d = fetch_item(item_id)
    _json_cache[item_id] = (d or {}).get("name", "") or ""
    return _json_cache[item_id]

def _norm(s: str) -> str:
    """归一化：小写 + 去所有非字母数字（消空格/标点/中日假名噪声）。"""
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


def extract_unitypkg_resource_names(zip_path: str) -> set[str]:
    """
    提取 zip 内 .unitypackage 的可读资源名（asset/prefab/mat/anim/unity 等路径末段）。

    用法：当 BOOTH 搜索结果标题与查询词不匹配时（典型：标题日文 + 资源英文），
    改用本函数提取的内部资源名做二次校验。
    Unity .unitypackage 实质是 **gzip + tar** 存档：
    tar 里每条资源是一个 GUID 子目录（含 asset / asset.meta / pathname 三件套），
    而 **pathname 文件的内容** 才是真正的 Unity 资源路径（如 'Assets/Shapeshifter Clinic/...'）。
    本函数读取所有 pathname 文本，提取路径段作为资源名集合。

    参考：
      - 7678707 'FREE無料-PoseAnimationMafuyu' 误配，pathname 含 'Shapeshifter Clinic' / 'STAND.8.anim' →
        实际是 5740973
      - Moonpiercer.zip 标题 'Agent Owl'（7441550）不匹配，pathname 含 'Moonpiercer' → 实际是 7441550
    """
    import tarfile
    names: set[str] = set()
    if not zip_path or not os.path.isfile(zip_path):
        return names
    try:
        import zipfile
        with zipfile.ZipFile(zip_path) as z:
            for n in z.namelist():
                if not n.lower().endswith('.unitypackage'):
                    continue
                raw = z.read(n)
                with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as tf:
                    for member in tf.getmembers():
                        if not member.isfile():
                            continue
                        # 重点：pathname 文件是真正的 Unity 资源路径
                        if os.path.basename(member.name) == 'pathname':
                            try:
                                f = tf.extractfile(member)
                                if f is None:
                                    continue
                                txt = f.read().decode('utf-8', 'replace')
                                # pathname 通常是单行路径
                                for line in txt.splitlines():
                                    line = line.strip()
                                    if not line:
                                        continue
                                    # 全路径
                                    full = line.replace('\\', '/')
                                    # 拆段加入：目录段 + 末段（去扩展名）
                                    for seg in full.split('/'):
                                        if not seg or seg.startswith('.'):
                                            continue
                                        stem = seg.rsplit('.', 1)[0] if '.' in seg else seg
                                        if stem and len(stem) >= 2:
                                            names.add(stem)
                                        if len(seg) >= 2:
                                            names.add(seg)
                            except Exception:
                                continue
                        else:
                            # 兜底：取 tar 成员路径首段（GUID 通常作为目录名）
                            base = os.path.basename(member.name)
                            stem = base.rsplit('.', 1)[0] if '.' in base else base
                            if stem and len(stem) >= 2 and not base.startswith('._'):
                                names.add(stem)
    except Exception:
        pass
    return names


def score_and_pick(query: str, items: list[dict], prefer_free=False,
                   source_zip_path: str = "") -> tuple[dict | None, bool]:
    """
    从搜索结果中选最佳匹配。
    关键：BOOTH 按别名/标签匹配，卡片 data-product-name 常为日文显示名，
    英文关键词并不出现其中。故用 JSON 规范名（含英文别名）做归一化包含判定。
    单结果直接采信（BOOTH 已定位唯一匹配）；多结果按规范名匹配度排序。
    返回 (最佳商品, 是否歧义)。歧义=次优分差过小，或存在同名不同价的候选。

    source_zip_path: 当所有标题/规范名都不命中查询词、但搜索结果唯一时，
                    启用「UnityPackage 内部资源名」二次校验。
                    命中 → 采纳；不命中 → 仍判未匹配。
    """
    if not items:
        return None, False

    qn = _norm(query)
    scored = []
    for idx, it in enumerate(items):
        name_l = it["name"].lower()
        cn = _canonical_name(it["id"])
        s = 0
        # 卡片名归一化包含
        if qn and qn in _norm(name_l):
            s += 100
        # 规范名（JSON）归一化包含——覆盖「日文标题+英文别名」情形
        if qn and qn in _norm(cn):
            s += 100
        # 词级部分匹配（卡片名）
        for w in re.split(r'[_\-\s]+', query.lower()):
            if len(w) >= 3 and w in name_l:
                s += 20
        # BOOTH 相关度次序微加权（首位略优）
        s += max(0, 10 - idx * 2)
        if len(name_l) > len(query) * 5 and len(cn) > len(query) * 5:
            s -= 10
        scored.append((s, it))

    scored.sort(key=lambda x: x[0], reverse=True)

    # 无任何名称匹配：唯一结果也须名称命中，杜绝「唯一结果即采信」误判
    # （曾发生 Moonpiercer→Agent Owl、Silent_Talk→插画包、The_Smile→漫画 等 6 起张冠李戴）
    if not scored or scored[0][0] <= 0:
        if len(items) == 1:
            it = items[0]
            cn = _norm(_canonical_name(it["id"]))
            if qn and (qn in cn or qn in _norm(it["name"])):
                return items[0], False
            # 标题/规范名都不命中 → 启用「UnityPackage 内部资源名」二次校验
            if source_zip_path:
                res_names = extract_unitypkg_resource_names(source_zip_path)
                if res_names:
                    qn_norm = _norm(query)
                    for r in res_names:
                        rn = _norm(r)
                        # 查询词的「关键英文段」命中资源名（如 Moonpiercer → 'moonpiercer' 包含）
                        if qn_norm and (qn_norm in rn or rn in qn_norm):
                            return items[0], False
                        # 词级部分匹配（≥3 字符的英文词）
                        for w in re.split(r'[_\-\s]+', query.lower()):
                            if len(w) >= 3 and w in r.lower():
                                return items[0], False
            return None, False  # 单结果但名称不命中 → 视为未匹配，交人工/换关键词
        return None, False

    best_s = scored[0][0]
    ambiguous = False
    if len(scored) > 1 and (best_s - scored[1][0]) < 30:
        ambiguous = True
    # 同名（规范名归一化相同）不同价——付费 vs 免费兄弟，最易错配，必报
    best_cn = _norm(_canonical_name(scored[0][1]["id"]))
    best_price = scored[0][1]["price"]
    for s2, it2 in scored[1:]:
        if _norm(_canonical_name(it2["id"])) == best_cn and it2["price"] != best_price:
            ambiguous = True
    return scored[0][1], ambiguous


# ── 获取商品 JSON 元数据 ──────────────────────────────────────────
def fetch_item(item_id: str) -> dict | None:
    url = ITEM_JSON.format(id=item_id)
    try:
        r = sess.get(url, timeout=30)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def _parse_price(price_val) -> int:
    """Parse BOOTH price field (can be int or string like '¥ 100')."""
    if isinstance(price_val, int):
        return price_val
    if isinstance(price_val, str):
        nums = re.sub(r'[^\d]', '', price_val)
        return int(nums) if nums else 0
    return -1


def _thumb_from_json(d: dict) -> str:
    """从 JSON 响应中提取封面图 URL。"""
    imgs = d.get("images") or []
    if imgs and isinstance(imgs, list):
        first = imgs[0]
        if isinstance(first, dict):
            return first.get("original") or first.get("resized") or ""
    return ""


def refine_from_json(item: dict) -> dict:
    """用 JSON API 的权威字段覆盖搜索卡片（洁净标题 + 精确类目）。"""
    d = fetch_item(item["id"])
    if not d:
        return item
    cat = d.get("category") or {}
    cat_name = cat.get("name", "") or item.get("category_name", "")
    cat_parent = (cat.get("parent") or {}).get("name", "")
    return {
        "id": item["id"],
        "name": d.get("name") or item["name"],
        "price": _parse_price(d.get("price")) if d.get("price") is not None else item.get("price", -1),
        "price_text": item.get("price_text", ""),
        "brand": item.get("brand", ""),
        "shop": d.get("shop") or item.get("shop", ""),
        "category": cat_name,
        "category_name": cat_name,
        "category_parent": cat_parent,
        "thumbnail": item.get("thumbnail", "") or _thumb_from_json(d),
    }


# ── 下载封面 ─────────────────────────────────────────────────────
def download_cover(thumb_url: str, dest_dir: Path) -> Path | None:
    """下载封面到 dest_dir/cover.jpg"""
    if not thumb_url:
        return None
    try:
        r = sess.get(thumb_url, timeout=30)
        r.raise_for_status()
        cover = dest_dir / "cover.jpg"
        cover.write_bytes(r.content)
        return cover
    except Exception as e:
        print(f"  封面下载失败: {e}")
        return None


# ── Windows 文件夹图标 ──────────────────────────────────────────
def set_hidden(path_str: str):
    """用 ctypes 设置文件/文件夹的隐藏属性（兼容 Python < 3.14）。"""
    FILE_ATTRIBUTE_HIDDEN = 0x02
    attrs = ctypes.windll.kernel32.GetFileAttributesW(path_str)
    if attrs != 0xFFFFFFFF:
        ctypes.windll.kernel32.SetFileAttributesW(path_str, attrs | FILE_ATTRIBUTE_HIDDEN)


def make_folder_icon(cover_path: Path, folder_path: Path):
    """将 cover.jpg 转为 .folder_icon.ico 并设置 desktop.ini（可覆盖旧文件）。

    关键：cover 原图若是宽幅矩形（如 1024x615），PIL.Image.save(..., sizes=[...])
    会按**原图比例**生成多尺寸 ICO 条目（如 256x154），Windows 大图标视图按 ICO header
    的 W×H 显示，于是缩略图变成「居中小图、外围大片空白」。
    修复：先 paste 到 side x side 的透明画布，所有 ICO 条目才会是正方形。
    """
    if not cover_path or not cover_path.exists():
        return
    try:
        img = Image.open(cover_path).convert("RGBA")
        # 正方形画布（边长取较长边，透明背景，cover 居中粘贴）
        side = max(img.size)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
        sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
        ico_path = folder_path / ".folder_icon.ico"
        ini_path = folder_path / "desktop.ini"
        ini_content = (
            "[ViewState]\r\n"
            "FolderType=Generic\r\n"
            "[.ShellClassInfo]\r\n"
            f"IconResource=.folder_icon.ico,0\r\n"
            "IconIndex=0\r\n"
        )
        # 先清除旧隐藏/系统属性，确保可覆盖写入
        for p in (ico_path, ini_path):
            if p.exists():
                try:
                    ctypes.windll.kernel32.SetFileAttributesW(str(p), 0x80)  # NORMAL，清除其余位
                except Exception:
                    pass
        canvas.save(str(ico_path), format="ICO", sizes=sizes)
        ini_path.write_text(ini_content, encoding="utf-8")
        set_hidden(str(ini_path))
        set_hidden(str(ico_path))

        # 设置文件夹 ReadOnly（触发 Windows 读取 desktop.ini）
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(folder_path))
        ctypes.windll.kernel32.SetFileAttributesW(str(folder_path), attrs | 0x01)

        # 通知 Explorer 重新读取 desktop.ini / 图标缓存
        # SHCNE_UPDATEITEM(0x08) | SHCNE_ATTRIBUTES(0x02)：要求刷新本目录属性/图标
        # SHCNF_IDLIST(0x0)：用 PIDL（指向具体目录）
        # 之前 2026-08-01 主上反馈：含特殊 Unicode（⌖ ݁˚）的目录名 + 移动目录后，
        # Explorer 偶尔缓存旧图标不刷新。SHChangeNotify 强制重读。
        try:
            pidl_parent, pidl_item = _get_pidl_pair(str(folder_path))
            SHCNE_UPDATEITEM = 0x00000008
            SHCNF_IDLIST = 0x0000
            ctypes.windll.shell32.SHChangeNotify(
                SHCNE_UPDATEITEM | SHCNF_IDLIST, 0,
                pidl_item, None
            )
            ctypes.windll.ole32.CoTaskMemFree(pidl_item)
        except Exception:
            # PIDL 失败时退化为全 shell 刷新
            ctypes.windll.shell32.SHChangeNotify(0x00008000, 0x0000, None, None)
    except Exception as e:
        print(f"  图标设置失败: {e}")


def _get_pidl_pair(folder_path: str):
    """取文件夹 PIDL（用于 SHChangeNotify 精准刷新）。"""
    ole32 = ctypes.windll.ole32
    shell32 = ctypes.windll.shell32
    pidl = ctypes.c_void_p()
    shell32.SHParseDisplayName(folder_path, 0, None, ctypes.byref(ctypes.c_ulong()), ctypes.byref(pidl))
    return None, pidl


# ── 整理文件 ─────────────────────────────────────────────────────
def organize_file(src_path: str, item_info: dict, base_dir: str, move_mode: bool = True) -> Path | None:
    """
    将源文件整理到 base_dir/<分类>/<ID>_<标题>/ 内。
    move_mode=True（默认）：移动文件，源处不留尸体；已整理则源文件移入回收站。
    move_mode=False（--keep）：复制，源文件保留。
    返回目标文件夹路径。
    """
    src = Path(src_path)
    base = Path(base_dir)

    item_id = item_info["id"]
    title   = sanitize_filename(item_info["name"])
    cat_raw = item_info.get("category_name", "") or item_info.get("category", "")
    cat_cn  = classify(cat_raw, item_info.get("category_parent", ""))
    thumb   = item_info.get("thumbnail", "")

    # 目标文件夹
    folder_name = f"{item_id}_{title}"
    dest_dir = base / cat_cn / folder_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    # 源文件清理（移动模式下，避免重复时残留尸体）
    def clean_source_if_move():
        if not move_mode:
            return
        if not src.exists():
            return  # 源已不在（前次已移走或本就缺失），无需处理
        s_src = os.path.normcase(os.path.abspath(str(src)))
        s_dst = os.path.normcase(os.path.abspath(str(dest_file)))
        if s_src == s_dst:
            return
        if send2trash:
            try:
                send2trash(str(src))
                print(f"  源文件已移入回收站（整理副本已就位）: {src.name}")
                return
            except Exception as e:
                print(f"  警告: 源文件清理失败仍留存 {src.name} ({e})")
        else:
            print(f"  警告: 未安装 send2trash，源文件未清理: {src.name}")

    # 若已存在同 item_id 的文件夹（标题可能因规范名变更而不同），复用之，避免重复
    cat_dir = base / cat_cn
    existing = None
    if cat_dir.exists():
        for d in cat_dir.iterdir():
            if d.is_dir() and d.name.startswith(f"{item_id}_"):
                existing = d
                break
    dest_dir = existing if existing else (cat_dir / folder_name)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # 幂等：已含重命名包 + 有效封面，仅补图标
    dest_file = dest_dir / f"{folder_name}{src.suffix}"
    cover = dest_dir / "cover.jpg"
    if dest_file.exists() and cover.exists() and cover.stat().st_size > 1000:
        print(f"  已存在，仅补图标: {dest_dir}")
        make_folder_icon(cover, dest_dir)
        clean_source_if_move()
        return dest_dir

    # 移动 / 复制文件
    if not dest_file.exists():
        import shutil
        if move_mode and src.exists():
            shutil.move(str(src), str(dest_file))
            print(f"  已移动: {dest_file}")
        else:
            if src.exists():
                shutil.copy2(str(src), str(dest_file))
                print(f"  已复制: {dest_file}")
            else:
                print(f"  警告: 源文件不存在，跳过: {src_path}")

    # 下载封面
    if not (cover.exists() and cover.stat().st_size > 1000):
        cover = download_cover(thumb, dest_dir)

    # 设置图标
    if cover:
        make_folder_icon(cover, dest_dir)

    print(f"  整理完成: {dest_dir}")
    return dest_dir


def sanitize_filename(name: str) -> str:
    """移除文件名中不允许的字符 + 装饰 Unicode。

    主上 2026-08-01 反馈：目录名含 `❥ ⁺ ⌖ ˚ ！！ 💗 🌕` 等装饰 Unicode 时，
    Windows 资源管理器**永久拒绝**为该目录应用 desktop.ini（ie4uinit.exe -show、
    SHChangeNotify、重启资源管理器均无效）。故必须从源头清洗装饰 Unicode。
    保留：ASCII（含常见括号/标点）、中日韩（CJK / Hiragana / Katakana）、
    半角假名、半角数字货币等。
    """
    # 1. 去掉 Windows 非法字符
    name = re.sub(r'[<>:"/\\|?*]', '', name)

    # 2. 去掉装饰 Unicode 区块（血泪坑：导致 Explorer 永久不读 desktop.ini）
    cleaned = []
    for ch in name:
        code = ord(ch)
        cat = None
        try:
            import unicodedata
            cat = unicodedata.category(ch)
        except Exception:
            cat = None

        # 显式剔除：emoji 区块 / 装饰符号块 / 拼音声调
        # 注：保留 U+FF00-U+FFEF（全角，如 ！！【】）和 U+4E00-U+9FFF + Hiragana/Katakana
        if (0x1F300 <= code <= 0x1F9FF   # emoji 区块
            or 0x2000 <= code <= 0x27BF   # General Punctuation / Misc Technical / Dingbats / Symbols（含 ⌖ ❥ ⁺ 💗 🌕 ˚）
            or 0x2B0  <= code <= 0x2FF    # Spacing Modifier Letters（含 ˚ ˇ ˆ）
            or 0x2070 <= code <= 0x209F   # Superscripts and Subscripts（含 ⁺ ⁰ ⁵）
            or cat in ('Me', 'Mn')         # combining marks（拼音声调等）
            or cat == 'Cn'                 # 未定义 / 私有保留
        ):
            continue
        cleaned.append(ch)
    name = ''.join(cleaned)

    # 3. 折叠重复空格；去首尾空白 / 点
    name = re.sub(r'\s+', ' ', name).strip('. ')

    # 4. 截断 + 兜底
    return name[:80] if name else "unnamed"


# ── 检查更新 ─────────────────────────────────────────────────────
def check_and_update(item_info: dict, existing_dir: Path | None, cookie: str = "") -> bool:
    """
    如果商品免费且现有目录中的文件版本较旧，下载新版。
    需要 cookie 才能实际下载（免费商品需登录）。
    """
    if not cookie:
        print("  未提供 cookie，跳过自动更新下载。")
        return False
    if item_info["price"] != 0:
        print("  非免费商品，跳过更新。")
        return False

    # 获取下载链接等详细信息（需登录）
    # 此部分复用 booth-free-collector 的下载逻辑
    print("  自动更新需要 cookie — 请使用 booth-free-collector 技能下载。")
    return False


# ── 主流程 ────────────────────────────────────────────────────────
def process_file(filepath: str, base_dir: str, cookie: str = "",
                 move_mode: bool = True, auto: bool = False,
                 force_id: str = "") -> dict | None:
    """处理单个文件：搜索 → 匹配 → 整理。返回商品信息或 None。
    force_id: 跳过搜索，直接整理该 BOOTH 商品（歧义时由主上指定）。
    auto: 歧义时也强制选最佳（不等待确认）。"""
    fp = Path(filepath)
    if not fp.exists():
        print(f"文件不存在: {filepath}")
        return None

    print(f"\n{'='*60}")
    print(f"处理: {fp.name}")

    # 强制指定商品 ID（歧义确认后）
    if force_id:
        d = fetch_item(force_id)
        if not d:
            print(f"  指定 ID {force_id} 获取失败")
            return None
        cat = d.get("category") or {}
        best_item = {
            "id": str(force_id),
            "name": d.get("name", ""),
            "price": _parse_price(d.get("price")),
            "price_text": "",
            "brand": "",
            "shop": d.get("shop", ""),
            "category": cat.get("name", ""),
            "category_name": cat.get("name", ""),
            "category_parent": (cat.get("parent") or {}).get("name", ""),
            "thumbnail": "",
        }
        best_item = refine_from_json(best := best_item)
        organize_file(filepath, best_item, base_dir, move_mode)
        return best_item

    # 1. 生成搜索候选
    candidates = sanitize_query(fp.name)
    print(f"  搜索候选: {candidates}")

    # 1.5 若搜索无果，尝试压缩包内封面水印识别（主上妙招）
    if not any(search_booth(q) for q in candidates[:1]):
        watermark_url = detect_watermark_url_in_zip(filepath)
        if watermark_url:
            print(f"  ⚡ 压缩包内发现水印 URL: {watermark_url}")
            shop_id = extract_shop_id_from_url(watermark_url)
            if shop_id:
                print(f"  ⚡ 推断店铺: {shop_id}，尝试列出店内商品")
                shop_items = list_shop_items(shop_id)
                if shop_items:
                    results = shop_items
                    # 尝试用文件名去匹配
                    matched, ambiguous = score_and_pick(candidates[0], results, prefer_free=False, source_zip_path=filepath)
                    if matched:
                        best_item = refine_from_json(matched)
                        print(f"      通过水印店铺匹配: [{best_item['id']}] {best_item['name']}")
                        print(f"            类目: {classify(best_item.get('category_name',''), best_item.get('category_parent',''))} | 店铺: {best_item['shop']}")
                        organize_file(filepath, best_item, base_dir, move_mode)
                        return best_item

    # 2. 逐候选搜索
    best_item = None
    ambig_fallback = None  # 歧义时的最佳候选（试完所有候选仍无清晰匹配时上报）
    for i, q in enumerate(candidates):
        print(f"  [{i+1}] 搜索: {q}")
        results = search_booth(q)
        print(f"      命中: {len(results)} 件")

        if results:
            picked, ambiguous = score_and_pick(q, results, prefer_free=False, source_zip_path=filepath)
            if picked:
                if ambiguous and not auto:
                    # 歧义：保存为兜底，继续试下一候选（更短/更干净的候选可能消歧）
                    if not ambig_fallback:
                        ambig_fallback = (picked, results)
                    print(f"      ⚠ 歧义，暂存候选，继续尝试下一关键词...")
                    if i < len(candidates) - 1:
                        time.sleep(0.5)
                    continue
                best_item = refine_from_json(picked)
                print(f"      选中: [{best_item['id']}] {best_item['name']}")
                print(f"            类目: {classify(best_item.get('category_name',''), best_item.get('category_parent',''))} | 店铺: {best_item['shop']}")
                break

        # 避免请求过快
        if i < len(candidates) - 1:
            time.sleep(0.5)

    # 所有候选都歧义 → 上报
    if not best_item and ambig_fallback:
        picked, results = ambig_fallback
        print(f"  ⚠ 所有候选均歧义，需主上确认。候选：")
        for it in results[:8]:
            print(f"    [{it['id']}] {it['name']} | {it['price_text']} | {it['shop']}")
        return {"_ambiguous": True, "candidates": results}

    if not best_item:
        print("  未找到匹配商品。")
        return None

    # 3. 整理文件（移动式）
    dest = organize_file(filepath, best_item, base_dir, move_mode)

    # 4. 检查更新（若免费且提供 cookie）
    if best_item["price"] == 0 and cookie:
        check_and_update(best_item, dest, cookie)

    return best_item


# ── CLI ───────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="BOOTH 商品名搜索整理")
    parser.add_argument("files", nargs="+", help="待整理的文件路径")
    parser.add_argument("--base-dir", default="G:/Lin_File/BOOTH",
                        help="输出根目录 (默认 G:/Lin_File/BOOTH)")
    parser.add_argument("--cookie-file", default="",
                        help="Cookie 文件路径（用于自动更新下载）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只搜索不整理")
    parser.add_argument("--keep", action="store_true",
                        help="复制而非移动（默认移动，源处不留尸体）")
    parser.add_argument("--auto", action="store_true",
                        help="歧义时也强制选最佳（不等待确认）")
    parser.add_argument("--id", default="",
                        help="强制指定 BOOTH 商品 ID（跳过搜索，用于歧义确认）")
    args = parser.parse_args()

    cookie = ""
    if args.cookie_file and os.path.exists(args.cookie_file):
        cookie = Path(args.cookie_file).read_text(encoding="utf-8").strip()

    move_mode = not args.keep

    results = []
    for fp in args.files:
        if args.dry_run:
            fp_path = Path(fp)
            candidates = sanitize_query(fp_path.name)
            print(f"\n{'='*60}")
            print(f"Dry-run: {fp_path.name}")
            print(f"  候选: {candidates}")
            for q in candidates:
                items = search_booth(q)
                picked, ambiguous = score_and_pick(q, items, prefer_free=False)
                if picked:
                    tag = " ⚠歧义" if ambiguous else ""
                    print(f"  搜索 '{q}' → [{picked['id']}] {picked['name']} ({picked['price_text']}){tag}")
                    if ambiguous:
                        for it in items[:6]:
                            print(f"      · [{it['id']}] {it['name']} | {it['price_text']}")
                    results.append(picked)
                    break
                time.sleep(0.3)
        else:
            info = process_file(fp, args.base_dir, cookie,
                                move_mode=move_mode, auto=args.auto,
                                force_id=args.id)
            if info and not info.get("_ambiguous"):
                results.append(info)

    # 输出汇总
    print(f"\n{'='*60}")
    print(f"汇总: {len(results)}/{len(args.files)} 件成功匹配")
    for r in results:
        print(f"  [{r['id']}] {r['name']} — {r.get('price_text','')}")


if __name__ == "__main__":
    main()
