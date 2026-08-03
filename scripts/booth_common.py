#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
booth_common.py — BOOTH 技能共享层（三合一）

统一三子技能（free-collector 下载 / archive-organizer 按ID整理 / name-search 按名搜索）
的公共逻辑：CATEGORY_MAP + 分类汉化 + BOOTH 请求会话 + 封面下载 + 文件夹图标三件套
（含完整性契约）+ 文件名清洗（装饰 Unicode 过滤 + 驼峰拆词 + 纯日文主体搜索）。

用法（由 booth.py 子命令调用，不直接运行）。
"""
import os
import re
import sys
import io
import time
import ctypes
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
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
      "Accept-Language": "ja,en;q=0.9,zh-CN;q=0.8"}
PROXY = os.environ.get("HTTPS_PROXY", "http://127.0.0.1:20122/")
MAX_RETRIES = 3
INVALID = r'<>:"/\\|?*'

# ── BOOTH 类目 → 中文（统一 30+ 映射；key 取自 JSON category.name）──
CATEGORY_MAP = {
    # 3D / VRChat 头像系
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
    # 音频 / 素材 / 视觉
    "ﾓｼﾞｬｰﾙｱｲﾃﾑ": "AR物品", "音声": "语音", "効果音・SE": "音效",
    "BGM": "BGM", "素材": "素材", "イラスト": "插画", "漫画": "漫画",
    "小説": "小说", "ポスター": "海报", "その他": "其他",
    # 游戏 / VRChat 道具（付费重灾区）
    "ゲーム": "游戏", "ゲーム関連商品": "游戏相关", "フリーゲーム": "免费游戏",
    # 下载器补充（与 name-search 同源，防目录分裂）
    "3Dテクスチャ": "3D贴图", "3D衣装": "3D服饰", "3D装飾品": "3D饰品",
    "3Dモデル": "3D模型", "3Dキャラクター": "3D角色", "3D小道具": "3D道具",
    "3D環境・ワールド": "3D环境", "3Dモーション・アニメーション": "3D动作",
    "3Dツール・システム": "3D工具", "ポスター": "海报", "イラスト": "插画",
    "素材データ": "素材数据", "音楽": "音乐", "アバター": "虚拟形象",
    "アクセサリー": "配饰",
}
CATEGORY_PARENT_MAP = {"3Dモデル": "3D模型", "ゲーム": "游戏", "アバター": "头像"}


def classify(cat_name: str, cat_parent: str = "") -> str:
    """BOOTH 类目 → 中文。优先精确；退回父级；再退回保留日文原名（绝不臆造）。"""
    if not cat_name:
        return "未分类"
    if cat_name in CATEGORY_MAP:
        return CATEGORY_MAP[cat_name]
    if cat_parent and cat_parent in CATEGORY_MAP:
        return CATEGORY_MAP[cat_parent]
    if cat_parent and cat_parent in CATEGORY_PARENT_MAP:
        return CATEGORY_PARENT_MAP[cat_parent]
    return cat_name


# ── 请求会话 ──────────────────────────────────────────────────────
def make_session(cookie: str = "", ua: str = "") -> requests.Session:
    s = requests.Session()
    h = dict(UA)
    if ua:
        h["User-Agent"] = ua
    s.headers.update(h)
    if PROXY:
        s.proxies = {"https": PROXY, "http": PROXY}
    if cookie:
        load_cookie(s, cookie)
    return s


def retry_request(method: str, url: str, session: requests.Session, **kwargs):
    """transport 错误指数退避重试（ConnectionError/Timeout/ChunkedEncodingError）。
    HTTP 状态码留给调用方判断（404 页可优雅处理而非重试）。"""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return session.request(method, url, **kwargs)
        except (requests.ConnectionError, requests.Timeout,
                requests.exceptions.ChunkedEncodingError) as e:
            if attempt < MAX_RETRIES:
                time.sleep(attempt * 2)
            else:
                raise


def load_cookie(session: requests.Session, cookie_arg: str):
    """cookie_arg: 'k=v; k2=v2' 串 / Netscape cookies.txt 路径 / 存原始 Cookie 串的文本文件路径。
    会话 Cookie 真名 `_plaza_session_nktz7u`，建议连同 cf_clearance 一起。"""
    if not cookie_arg:
        return
    p = Path(cookie_arg)
    if p.is_file():
        text = p.read_text(encoding="utf-8", errors="ignore").strip()
        if any("\t" in line and not line.startswith("#") for line in text.splitlines()):
            loaded = 0
            for line in text.splitlines():
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) >= 7 and "booth" in parts[0]:
                    session.cookies.set(parts[5], parts[6], domain=parts[0])
                    loaded += 1
            if loaded > 0:
                return
        cookie_arg = text
    for pair in cookie_arg.split(";"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            session.cookies.set(k.strip(), v.strip(), domain=".booth.pm")


# ── 元数据 / 封面 ────────────────────────────────────────────────
def fetch_item(item_id: str, session: requests.Session | None = None) -> dict | None:
    s = session or make_session()
    try:
        r = retry_request("GET", ITEM_JSON.format(id=item_id), s,
                          headers={**UA, "Accept": "application/json"}, timeout=30)
        if r and r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def _parse_price(price_val) -> int:
    if isinstance(price_val, int):
        return price_val
    if isinstance(price_val, str):
        nums = re.sub(r'[^\d]', '', price_val)
        return int(nums) if nums else 0
    return -1


def _thumb_from_json(d: dict) -> str:
    imgs = d.get("images") or []
    if imgs and isinstance(imgs, list):
        first = imgs[0]
        if isinstance(first, dict):
            return first.get("original") or first.get("resized") or ""
    return ""


def refine_from_json(item: dict, session: requests.Session | None = None) -> dict:
    """用 JSON API 权威字段覆盖搜索卡片（洁净标题 + 精确类目 + 封面）。"""
    d = fetch_item(item["id"], session)
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


def download_cover(thumb_url: str, dest_dir: Path, session: requests.Session | None = None) -> Path | None:
    if not thumb_url:
        return None
    s = session or make_session()
    try:
        r = retry_request("GET", thumb_url, s,
                          headers={**UA, "Referer": "https://booth.pm/"}, timeout=60)
        if not r:
            return None
        r.raise_for_status()
        cover = dest_dir / "cover.jpg"
        cover.write_bytes(r.content)
        return cover
    except Exception as e:
        print(f"  封面下载失败: {e}")
        return None


# ── 文件名清洗 ───────────────────────────────────────────────────
def sanitize_filename(name: str) -> str:
    """移除 Windows 非法字符 + 装饰 Unicode（血泪坑：装饰 Unicode 目录名
    会被 Explorer 永久拒绝应用 desktop.ini）。保留 ASCII/中日韩/全角。"""
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    cleaned = []
    for ch in name:
        code = ord(ch)
        try:
            import unicodedata
            cat = unicodedata.category(ch)
        except Exception:
            cat = None
        if (0x1F300 <= code <= 0x1F9FF
                or 0x2000 <= code <= 0x27BF
                or 0x2B0 <= code <= 0x2FF
                or 0x2070 <= code <= 0x209F
                or cat in ('Me', 'Mn')
                or cat == 'Cn'):
            continue
        cleaned.append(ch)
    name = ''.join(cleaned)
    name = re.sub(r'\s+', ' ', name).strip('. ')
    return name[:80] if name else "unnamed"


def sanitize(name: str, max_len: int = 70) -> str:
    out = "".join(c for c in name if c not in INVALID and ord(c) >= 32)
    out = re.sub(r"\s+", " ", out).strip().rstrip(". ")
    if len(out) > max_len:
        out = out[:max_len].rstrip(". ")
    return out or "untitled"


def sanitize_query(filename: str) -> list[str]:
    """
    从文件名生成 BOOTH 搜索候选关键词（按优先级排序，首个最可能命中）。
    策略（主上妙招合集）：
      0. 下划线 → 空格（BOOTH 不认下划线）
      1. 去扩展名、去括号内容
      1.5 驼峰拆词：LunariaPaperFan → Lunaria Paper Fan（BOOTH 对驼峰不友好）
      1.6 **纯日文主体**：去尾部英文/版本号，只留日文段（メカ弾エフェクトVer_2.00 → メカ弾エフェクト）
      2. 去版本号：_v100 / v2 / 2.0 / Ver1.0
      3. 去尾部中文（主上备注）
      4. 只取最长连续 ASCII 段
      5. 去 VRChat 常见后缀词
    """
    name = Path(filename).stem
    name = name.replace('_', ' ')
    name = re.sub(r'[\(（\[【].*?[\)）\]】]', '', name)
    split_camel = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', name).strip()
    split_camel = re.sub(r'\s+', ' ', split_camel)

    # 纯日文主体：去尾部英文/数字/版本号，只留日文连续段
    ja_parts = re.findall(r'[\u3040-\u30ff\u4e00-\u9fff][\u3040-\u30ff\u4e00-\u9fff・ー]*', name)
    ja_body = "".join(ja_parts).strip() if ja_parts else ""

    candidates = []
    c1 = name.strip()
    if c1:
        candidates.append(c1)
    if split_camel and split_camel != c1:
        candidates.append(split_camel)
    if ja_body and ja_body != c1 and ja_body != split_camel and len(ja_body) >= 2:
        candidates.append(ja_body)  # 纯日文主体（主上：メカ弾エフェクトVer_2.00 → メカ弾エフェクト）

    c2 = re.sub(r'[_\-\s]?(?:v(?:er(?:sion)?)?\.?|version\s*)\d+(?:\.\d+)*[_\-\s]?', '', name, flags=re.I)
    c2 = re.sub(r'[_\-\s]\d+\.\d+(?:\.\d+)*$', '', c2)
    c2 = c2.strip()
    if c2 and c2 not in candidates:
        candidates.append(c2)

    c3 = re.sub(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff].*$', '', c2).strip()
    if c3 and c3 not in candidates and len(c3) >= 3:
        candidates.append(c3)

    ascii_parts = re.findall(r'[A-Za-z][A-Za-z0-9_]{2,}', name)
    for part in sorted(ascii_parts, key=len, reverse=True):
        if part not in candidates and len(part) >= 4:
            candidates.append(part)

    vrc_stoppers = ['vrchat', 'vrc', 'unitypackage', 'package', 'prefab',
                    'gimmick', 'shader', 'world', 'avatar',
                    '玩家', '加入', '退出', '弹窗', '提示', '通知', '音效']
    c5 = c2
    for stop in vrc_stoppers:
        c5 = re.sub(rf'[_\-\s]?{re.escape(stop)}[_\-\s]?', ' ', c5, flags=re.I)
    c5 = re.sub(r'\s+', ' ', c5).strip()
    if c5 and c5 not in candidates and len(c5) >= 3:
        candidates.append(c5)

    seen = set()
    unique = []
    for c in candidates:
        key = c.lower()
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique if unique else [name]


# ── Windows 文件夹图标（完整性契约）─────────────────────────────
class IconContractError(RuntimeError):
    """三件套不齐全时抛出（防 Hermes 类 agent 留半成品 desktop.ini 误导 Explorer）。"""


def set_attrs(path, attrs: int):
    if os.name != "nt":
        return
    ctypes.windll.kernel32.SetFileAttributesW(str(path), attrs)


def _get_attrs(path) -> int:
    """返回文件属性位（Windows）。失败返回 0。"""
    if os.name != "nt":
        return 0
    a = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    return a if a != 0xFFFFFFFF else 0


def _notify_shell():
    """触发 Windows Explorer 全 shell 刷新（图标缓存）。"""
    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SHChangeNotify(0x00008000, 0x0000, None, None)
    except Exception:
        pass


def set_hidden(path_str: str):
    """Hidden + System 同时设（2026-08-02 修正：之前只设 H 漏 S，
    导致 desktop.ini 属性不全、Explorer 拒读）。"""
    if os.name != "nt":
        return
    FILE_ATTRIBUTE_HIDDEN = 0x02
    FILE_ATTRIBUTE_SYSTEM = 0x04
    attrs = ctypes.windll.kernel32.GetFileAttributesW(path_str)
    if attrs != 0xFFFFFFFF:
        ctypes.windll.kernel32.SetFileAttributesW(path_str, attrs | FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM)


def _get_pidl_pair(folder_path: str):
    ole32 = ctypes.windll.ole32
    shell32 = ctypes.windll.shell32
    pidl = ctypes.c_void_p()
    shell32.SHParseDisplayName(folder_path, 0, None, ctypes.byref(ctypes.c_ulong()), ctypes.byref(pidl))
    return None, pidl


def _verify_icon_contract(ico_path, ini_path, folder_path):
    if not ico_path.exists():
        raise IconContractError(f"ico 缺失：{ico_path}")
    if ico_path.stat().st_size < 1024:
        raise IconContractError(f"ico 过小（<1KB）：{ico_path}")
    if not ini_path.exists():
        raise IconContractError(f"ini 缺失：{ini_path}")
    try:
        txt = ini_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        txt = ini_path.read_bytes().decode("utf-8", "replace")
    if "IconResource=.folder_icon.ico" not in txt:
        raise IconContractError(f"ini 缺 IconResource=.folder_icon.ico 字段：{ini_path}")
    a = ctypes.windll.kernel32.GetFileAttributesW(str(folder_path))
    if a == 0xFFFFFFFF or not (a & 0x01):
        ctypes.windll.kernel32.SetFileAttributesW(str(folder_path), a | 0x01)


def make_folder_icon(cover_path: Path, folder_path: Path):
    """cover.jpg → .folder_icon.ico + desktop.ini（三件套），含完整性契约。

    血泪坑（2026-08-01/02）：
      - 宽幅 cover 直接 save 会生成非正方形 ICO（256x154）→ 缩略图居中小图 → 先贴正方形画布
      - desktop.ini/ico 缺 H/S 属性 → Explorer 拒读 → 写完自检三件套
      - 写完不校验 → Hermes 类 agent 留残缺 desktop.ini → 自检 raise IconContractError
    """
    if not cover_path or not cover_path.exists():
        raise IconContractError(f"cover 缺失：{cover_path}")
    try:
        img = Image.open(cover_path).convert("RGBA")
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
            "IconResource=.folder_icon.ico,0\r\n"
            "IconIndex=0\r\n"
        )
        for p in (ico_path, ini_path):
            if p.exists():
                try:
                    ctypes.windll.kernel32.SetFileAttributesW(str(p), 0x80)
                except Exception:
                    pass
        canvas.save(str(ico_path), format="ICO", sizes=sizes)
        ini_path.write_text(ini_content, encoding="utf-8")
        set_hidden(str(ini_path))
        set_hidden(str(ico_path))
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(folder_path))
        ctypes.windll.kernel32.SetFileAttributesW(str(folder_path), attrs | 0x01)
        _verify_icon_contract(ico_path, ini_path, folder_path)
        # 通知 Explorer 刷新图标缓存
        try:
            _, pidl_item = _get_pidl_pair(str(folder_path))
            ctypes.windll.shell32.SHChangeNotify(0x00000008, 0x0000, pidl_item, None)
            ctypes.windll.ole32.CoTaskMemFree(pidl_item)
        except Exception:
            ctypes.windll.shell32.SHChangeNotify(0x00008000, 0x0000, None, None)
    except IconContractError:
        raise
    except Exception as e:
        ini = folder_path / "desktop.ini"
        if ini.exists():
            try:
                ctypes.windll.kernel32.SetFileAttributesW(str(ini), 0x80)
                ini.unlink()
            except Exception:
                pass
        raise IconContractError(f"图标设置失败（已清理残缺 desktop.ini）：{e}")


# ── 搜索 / 评分（按名搜索核心）──────────────────────────────────
def search_booth(query: str, session: requests.Session | None = None) -> list[dict]:
    """用 ?q= 搜索 BOOTH，返回匹配商品列表（data-* 卡片解析）。"""
    s = session or make_session()
    try:
        r = s.get(f"{SEARCH_URL}?q={quote(query)}", timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"  搜索失败: {e}")
        return []
    html = r.text
    items = []
    for m in re.finditer(r'data-product-id="(\d+)"', html):
        pid = m.group(1)
        start = max(0, m.start() - 300)
        end = min(len(html), m.end() + 4000)
        ctx = html[start:end]

        def attr(pattern, default=""):
            match = re.search(pattern, ctx)
            return unescape_html(match.group(1)) if match else default

        name = attr(r'data-product-name="([^"]*)"')
        price = attr(r'data-product-price="([^"]*)"')
        brand = attr(r'data-product-brand="([^"]*)"')
        category = attr(r'data-product-category="([^"]*)"')
        shop_m = re.search(r'item-card__shop-name[^>]*>([^<]+)<', ctx)
        shop = shop_m.group(1).strip() if shop_m else brand
        thumb_m = re.search(r'data-original="(https://booth\.pximg\.net/[^"]*)"', ctx)
        thumb = thumb_m.group(1) if thumb_m else ""
        cat_name_m = re.search(r'item-card__category-anchor[^>]*>([^<]+)<', ctx)
        cat_name = cat_name_m.group(1).strip() if cat_name_m else ""
        price_text_m = re.search(r'price[^>]*>([^<]*\d+[^<]*)<', ctx)
        price_text = price_text_m.group(1).strip() if price_text_m else f"¥ {price}"
        items.append({
            "id": pid, "name": name, "price": int(price) if price.isdigit() else -1,
            "price_text": price_text, "brand": brand, "shop": shop,
            "category": category, "category_name": cat_name, "thumbnail": thumb,
        })
    return items


def unescape_html(s: str) -> str:
    from html import unescape
    return unescape(s)


def _norm(s: str) -> str:
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


_json_cache: dict = {}


def _canonical_name(item_id: str, session=None) -> str:
    if item_id in _json_cache:
        return _json_cache[item_id]
    d = fetch_item(item_id, session)
    _json_cache[item_id] = (d or {}).get("name", "") or ""
    return _json_cache[item_id]


def extract_unitypkg_resource_names(zip_path: str) -> set[str]:
    """解 zip 内 .unitypackage（gzip+tar），读 pathname 文件内容提资源名。
    首段目录名通常是店铺名/作者名（硬锚点），prefab/anim 名是商品主题。"""
    import tarfile
    import zipfile
    names: set[str] = set()
    if not zip_path or not os.path.isfile(zip_path):
        return names
    try:
        with zipfile.ZipFile(zip_path) as z:
            for n in z.namelist():
                if not n.lower().endswith('.unitypackage'):
                    continue
                raw = z.read(n)
                with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as tf:
                    for member in tf.getmembers():
                        if not member.isfile():
                            continue
                        if os.path.basename(member.name) == 'pathname':
                            try:
                                f = tf.extractfile(member)
                                if f is None:
                                    continue
                                for line in f.read().decode('utf-8', 'replace').splitlines():
                                    for seg in line.replace('\\', '/').split('/'):
                                        if not seg or seg.startswith('.'):
                                            continue
                                        stem = seg.rsplit('.', 1)[0] if '.' in seg else seg
                                        if stem and len(stem) >= 2:
                                            names.add(stem)
                            except Exception:
                                continue
    except Exception:
        pass
    return names


def score_and_pick(query: str, items: list[dict], prefer_free=False,
                   source_zip_path: str = "", session=None) -> tuple[dict | None, bool]:
    """评分选最佳。单结果也必须名称命中（血泪坑）；标题不命中时解 UnityPackage 验真。"""
    if not items:
        return None, False
    qn = _norm(query)
    scored = []
    for idx, it in enumerate(items):
        name_l = it["name"].lower()
        cn = _canonical_name(it["id"], session)
        s = 0
        if qn and qn in _norm(name_l):
            s += 100
        if qn and qn in _norm(cn):
            s += 100
        for w in re.split(r'[_\-\s]+', query.lower()):
            if len(w) >= 3 and w in name_l:
                s += 20
        s += max(0, 10 - idx * 2)
        if len(name_l) > len(query) * 5 and len(cn) > len(query) * 5:
            s -= 10
        scored.append((s, it))
    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored or scored[0][0] <= 0:
        if len(items) == 1:
            it = items[0]
            cn = _norm(_canonical_name(it["id"], session))
            if qn and (qn in cn or qn in _norm(it["name"])):
                return items[0], False
            if source_zip_path:
                res_names = extract_unitypkg_resource_names(source_zip_path)
                if res_names:
                    qn_norm = _norm(query)
                    for r in res_names:
                        rn = _norm(r)
                        if qn_norm and (qn_norm in rn or rn in qn_norm):
                            return items[0], False
                        for w in re.split(r'[_\-\s]+', query.lower()):
                            if len(w) >= 3 and w in r.lower():
                                return items[0], False
            return None, False
        return None, False
    best_s = scored[0][0]
    ambiguous = False
    if len(scored) > 1 and (best_s - scored[1][0]) < 30:
        ambiguous = True
    best_cn = _norm(_canonical_name(scored[0][1]["id"], session))
    best_price = scored[0][1]["price"]
    for s2, it2 in scored[1:]:
        if _norm(_canonical_name(it2["id"], session)) == best_cn and it2["price"] != best_price:
            ambiguous = True
    return scored[0][1], ambiguous


# ── 压缩包水印识别 ─────────────────────────────────────────────
WATERMARK_PATTERNS = [
    r'https?://([\w-]+)\.booth\.pm/?',
    r'booth\.pm/[\w/]+/items/(\d+)',
    r'booth\.pm/items/(\d+)',
]


def detect_watermark_url_in_zip(filepath: str) -> str:
    """读 zip 内 .url/.txt/readme 找 BOOTH 店铺 URL 或商品 ID 链接。"""
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
    m = re.search(r'https?://([\w-]+)\.booth\.pm', url)
    return m.group(1) if m else ""


def list_shop_items(shop_subdomain: str, session=None) -> list[dict]:
    """店铺 `/items?page=N` 翻页列商品（店铺根有 Cloudflare 护盾，必须走 /items）。"""
    s = session or make_session()
    items = []
    for page in range(1, 6):
        try:
            r = s.get(f"https://{shop_subdomain}.booth.pm/items?page={page}", timeout=30)
            if r.status_code != 200:
                break
            ids = re.findall(r'data-product-id="(\d+)"', r.text)
            if not ids:
                break
            for pid in ids:
                d = fetch_item(pid, s)
                if not d:
                    continue
                cat = d.get("category") or {}
                items.append({
                    "id": pid, "name": d.get("name", ""),
                    "price": _parse_price(d.get("price")),
                    "price_text": "", "brand": "", "shop": (d.get("shop") or ""),
                    "category": cat.get("name", ""), "category_name": cat.get("name", ""),
                    "category_parent": (cat.get("parent") or {}).get("name", ""),
                    "thumbnail": _thumb_from_json(d),
                })
            time.sleep(0.5)
        except Exception:
            break
    return items
