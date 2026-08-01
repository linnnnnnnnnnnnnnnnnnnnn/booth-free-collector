# -*- coding: utf-8 -*-
"""
BOOTH free item collector
Crawl a BOOTH shop, download all FREE (0 JPY) items, and organize them as:

    <out>/<category-or-tag folder>/<itemID>_<title>/
        - downloaded files (zip/psd/...)
        - cover.jpg              (first product image)
        - .folder_icon.ico       (hidden, generated from cover)
        - desktop.ini            (hidden+system, folder icon -> cover)

So in Windows Explorer "Large icons" view every item folder shows its cover.

Usage:
    python booth_free_dl.py <shop_url_or_subdomain> [--out DIR] [--dry-run] [--limit N]
    python booth_free_dl.py --items <item_link_or_id> [<item_link_or_id> ...]   # scattered/friend links

Example:
    python booth_free_dl.py https://atelier-kotone.booth.pm/ --out "G:/Lin_File/BOOTH"
    python booth_free_dl.py --items "https://atelier-kotone.booth.pm/items/6574952" "https://booth.pm/ja/items/6574953"
    python booth_free_dl.py "https://atelier-kotone.booth.pm/items/8103811"   # single link auto-detected

Notes:
- Only FREE variations are downloaded (variation price == 0 with download url).
  Paid items are never touched. Actual file download REQUIRES a login session cookie
  (without it BOOTH returns a login-page HTML disguised as the file).
- Idempotent: an item folder that already contains its files is skipped.
- Respects HTTP(S)_PROXY env vars automatically (requests default behavior).
"""
import argparse
import os
import platform
import re
import sys
import time
from pathlib import Path

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
INVALID = r'<>:"/\\|?*'
MAX_RETRIES = 3

# BOOTH category name -> Chinese folder name
# 注意：必须与 booth-name-search 的 CATEGORY_MAP 保持一致！
# 曾因 3D衣装 在此处映射为「3D服装」而在 name-search 映射为「3D服饰」，
# 导致同一类目分裂成两个目录。统一以 name-search 为准。
CATEGORY_MAP = {
    "3Dテクスチャ": "3D贴图",
    "3D衣装": "3D服饰",
    "3D装飾品": "3D饰品",
    "3Dモデル": "3D模型",
    "3Dモデル（その他）": "3D模型（其他）",
    "3Dキャラクター": "3D角色",
    "3D小道具": "3D道具",
    "3D環境・ワールド": "3D环境",
    "3Dモーション・アニメーション": "3D动作",
    "3Dツール・システム": "3D工具",
    "ポスター": "海报",
    "イラスト": "插画",
    "素材データ": "素材数据",
    "音楽": "音乐",
    "アバター": "虚拟形象",
    "アクセサリー": "配饰",
    "その他": "其他",
}
FILE_ATTRIBUTE_READONLY = 0x01
FILE_ATTRIBUTE_HIDDEN = 0x02
FILE_ATTRIBUTE_SYSTEM = 0x04


def log(msg):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("utf-8", "replace").decode("utf-8", "replace"), flush=True)


def retry_request(method, url, session, **kwargs):
    """Send a request with exponential-backoff retry on *transport* errors only
    (ConnectionError / Timeout / ChunkedEncodingError from proxy blips).
    HTTP status is left to the caller (so e.g. a 404 page can be handled
    gracefully instead of being retried/raised here)."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.request(method, url, **kwargs)
            return r
        except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError) as e:
            if attempt < MAX_RETRIES:
                wait = attempt * 2
                log(f"    ! 请求失败 (attempt {attempt}/{MAX_RETRIES}), {wait}s 后重试: {e}")
                time.sleep(wait)
            else:
                raise


def sanitize(name: str, max_len: int = 70) -> str:
    out = "".join(c for c in name if c not in INVALID and ord(c) >= 32)
    out = re.sub(r"\s+", " ", out).strip().rstrip(". ")
    if len(out) > max_len:
        out = out[:max_len].rstrip(". ")
    return out or "untitled"


def shop_subdomain(url_or_sub: str) -> str:
    m = re.search(r"https?://([^./]+)\.booth\.pm", url_or_sub)
    return m.group(1) if m else url_or_sub.strip().strip("/")


def parse_discrete(text: str) -> list:
    """Extract BOOTH item ids from a blob of links/ids (friends' shared links).

    Handles:
      - full item urls: https://<sub>.booth.pm/items/6574952
      - ja urls:        https://booth.pm/ja/items/6574952
      - bare ids:       6574952 6574953  (fallback, 5+ digits)
    Returns a de-duplicated, order-preserving id list.
    """
    url_ids = re.findall(r'/items/(\d+)', text)
    # (?<!\d)...(?!\d): full-id match; \\b fails when a CJK char sits next to the
    # digits (Python Unicode \\b treats CJK as word char, breaking the boundary).
    bare = re.findall(r'(?<!\d)\d{5,}(?!\d)', text.replace(",", " "))
    ids = url_ids + [b for b in bare if b not in url_ids]
    return list(dict.fromkeys(ids))


def crawl_item_ids(sub: str, session: requests.Session) -> list:
    """Walk shop pages, collect unique item ids in display order."""
    ids, seen, page = [], set(), 1
    while True:
        # NOTE: shop root "/" is behind a Cloudflare challenge; "/items" is not.
        url = f"https://{sub}.booth.pm/items?page={page}"
        r = retry_request("GET", url, session, headers=UA, timeout=30)
        if r.status_code != 200:
            break
        found = re.findall(r'href="https?://[^"]*/items/(\d+)"', r.text) or re.findall(r'/items/(\d+)', r.text)
        new = [i for i in dict.fromkeys(found) if i not in seen]
        if not new:
            break
        for i in new:
            seen.add(i)
            ids.append(i)
        page += 1
        time.sleep(0.8)
    return ids


def fetch_item(item_id: str, session: requests.Session) -> dict:
    r = retry_request("GET", f"https://booth.pm/ja/items/{item_id}.json", session,
                      headers={**UA, "Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    return r.json()


def free_downloads(item: dict) -> list:
    """Return [(url, filename)] for all free downloadable files."""
    out = []
    for v in item.get("variations") or []:
        if (v.get("price") or 0) != 0:
            continue
        dl = v.get("downloadable") or {}
        for group in ("no_musics", "musics"):
            for f in dl.get(group) or []:
                if f.get("url"):
                    out.append((f["url"], f.get("name") or f"file_{len(out)}"))
    return out


def looks_html(head: bytes) -> bool:
    s = head[:256].lstrip().lower()
    return s.startswith(b"<!doctype") or s.startswith(b"<html")


def valid_file(path: Path) -> bool:
    """True if file exists, non-empty, and is NOT a disguised HTML (login) page."""
    if not path.exists() or path.stat().st_size == 0:
        return False
    with open(path, "rb") as fh:
        return not looks_html(fh.read(256))


def download(url: str, dest: Path, session: requests.Session, check_html: bool = False):
    tmp = dest.with_suffix(dest.suffix + ".part")
    last_err = None
    # 1) fast path: single streamed GET (works for small files; proven in practice)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with session.get(url, headers=UA, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_content(1 << 16):
                        fh.write(chunk)
            last_err = None
            break
        except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError) as e:
            last_err = e
            if attempt < MAX_RETRIES:
                wait = attempt * 2
                log(f"    ! 下载失败 (attempt {attempt}/{MAX_RETRIES}), {wait}s 后重试: {e}")
                time.sleep(wait)
    # 2) fallback: chunked Range download (survives proxies that cut large streams)
    if last_err:
        try:
            log("    ~ 流式下载中断，切换为分块续传模式")
            _ranged_download(url, tmp, session)
            last_err = None
        except Exception as e:  # noqa: BLE001 - any ranged failure keeps original symptom
            last_err = e
    if last_err:
        raise last_err
    if check_html:
        with open(tmp, "rb") as fh:
            if looks_html(fh.read(256)):
                tmp.unlink(missing_ok=True)
                raise RuntimeError("got BOOTH login page instead of file — supply --cookie (see SKILL.md)")
    tmp.replace(dest)


def _ranged_download(url: str, tmp: Path, session: requests.Session,
                     chunk: int = 64 * 1024, max_retry: int = 6):
    """Download via HTTP Range in small chunks.

    Some proxies silently cut a single large response (e.g. after ~90KB),
    which makes a normal streamed GET fail with IncompleteRead on big files.
    Splitting into small ranged chunks — each its own short-lived connection —
    gets around that. We re-issue the ORIGINAL url per chunk so the signed S3
    URL is always fresh (BOOTH's downloadables redirect to a time-limited
    s6.booth.pm URL; re-resolving each time keeps it valid).
    """
    with session.get(url, headers={**UA, "Range": "bytes=0-0"}, stream=True,
                     timeout=60, allow_redirects=True) as r:
        r.raise_for_status()
        cr = r.headers.get("Content-Range", "")
        if "/" not in cr:
            raise RuntimeError(f"server does not support Range (no Content-Range): {cr!r}")
        total = int(cr.rsplit("/", 1)[-1])
    if total == 0:
        open(tmp, "wb").close()  # empty file, nothing to fetch
        return
    done = 0
    with open(tmp, "wb") as fh:
        while done < total:
            end = min(done + chunk - 1, total - 1)
            ok = False
            for att in range(1, max_retry + 1):
                try:
                    with session.get(url, headers={**UA, "Range": f"bytes={done}-{end}"},
                                     stream=True, timeout=120, allow_redirects=True) as r:
                        r.raise_for_status()
                        for c in r.iter_content(1 << 16):
                            fh.write(c)
                    ok = True
                    break
                except (requests.ConnectionError, requests.Timeout,
                        requests.exceptions.ChunkedEncodingError) as e:
                    if att < max_retry:
                        time.sleep(1)
                    else:
                        raise RuntimeError(f"chunk {done}-{end} failed: {e}")
            if not ok:
                raise RuntimeError(f"chunk {done}-{end} failed after {max_retry} retries")
            done = end + 1
    log(f"    ~ 分块续传完成 ({total} bytes)")



def load_cookie(session: requests.Session, cookie_arg: str):
    """cookie_arg: 'k=v; k2=v2' string, OR path to Netscape cookies.txt,
    OR path to a plain text file whose content is the raw 'k=v; k2=v2' string."""
    if not cookie_arg:
        return
    p = Path(cookie_arg)
    if p.is_file():
        text = p.read_text(encoding="utf-8", errors="ignore").strip()
        # Netscape cookies.txt: 7 tab-separated fields, first line starts with domain
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
        cookie_arg = text  # raw cookie header string in a file
    for pair in cookie_arg.split(";"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            session.cookies.set(k.strip(), v.strip(), domain=".booth.pm")


def set_attrs(path: Path, attrs: int):
    if platform.system() != "Windows":
        return
    import ctypes
    ctypes.windll.kernel32.SetFileAttributesW(str(path), attrs)


def make_folder_icon(folder: Path, cover: Path):
    """cover image -> .ico + desktop.ini so Explorer large-icon view shows it."""
    if platform.system() != "Windows":
        return
    try:
        from PIL import Image
    except ImportError:
        log("  ! Pillow missing, skip icon"); return
    ico = folder / ".folder_icon.ico"
    ini = folder / "desktop.ini"
    # 幂等但必须校验属性：文件在 ≠ 属性在。目录被移动/拷贝后
    # Hidden/System/ReadOnly 属性会丢失，Explorer 不再读 desktop.ini → 封面消失。
    if ico.exists() and ini.exists():
        set_attrs(ico, FILE_ATTRIBUTE_HIDDEN)
        set_attrs(ini, FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM)
        set_attrs(folder, FILE_ATTRIBUTE_READONLY)  # tells Explorer folder is customized
        return
    if ico.exists():
        set_attrs(ico, 0x80)  # clear hidden attr, or PIL can't overwrite
    try:
        img = Image.open(cover).convert("RGBA")
        side = max(img.size)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
        canvas.save(ico, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32)])
    except Exception as e:
        log(f"  ! icon convert failed: {e}"); return
    if ini.exists():
        set_attrs(ini, 0x80)  # normal, allow overwrite
    ini.write_text("[.ShellClassInfo]\r\nIconResource=.folder_icon.ico,0\r\nConfirmFileOp=0\r\n", encoding="utf-16")
    set_attrs(ico, FILE_ATTRIBUTE_HIDDEN)
    set_attrs(ini, FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM)
    set_attrs(folder, FILE_ATTRIBUTE_READONLY)  # tells Explorer folder is customized


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("shop", nargs="?",
                    help="shop URL/subdomain (crawl whole shop) OR a single item link. "
                         "If it contains /items/<id>, discrete mode is auto-selected.")
    ap.add_argument("--items", nargs="+", default=[], metavar="LINKS",
                    help="discrete item link(s)/ID(s) from friends/groups. "
                         "Multiple values separated by spaces, or one string with comma/newline separated ids.")
    ap.add_argument("--out", default=r"G:\Lin_File\BOOTH")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--folder-by", choices=["category", "first-tag"], default="category",
                    help="group folder: item category (default) or first tag")
    ap.add_argument("--cookie", default="",
                    help="BOOTH login cookie: raw 'k=v; k2=v2' string / cookies.txt / raw-string file "
                         "(REQUIRED for actual file downloads; without it BOOTH returns a login page). "
                         "Session cookie name is '_plaza_session_nktz7u'; include 'cf_clearance' too.")
    ap.add_argument("--ua", default="",
                    help="override User-Agent (MUST match the browser that produced cf_clearance)")
    args = ap.parse_args()
    if args.ua:
        UA["User-Agent"] = args.ua

    # ---- input resolution: auto-judge shop vs discrete items ----
    discrete = []
    for blob in args.items:
        discrete += parse_discrete(blob)
    if args.shop and parse_discrete(args.shop):
        discrete += parse_discrete(args.shop)
        args.shop = None  # not a shop crawl
    discrete = list(dict.fromkeys(discrete))

    root = Path(args.out)
    session = requests.Session()
    load_cookie(session, args.cookie)

    if discrete:
        mode, sub, ids = "items", "items", discrete
        log(f"== discrete items mode: {len(ids)} link(s) ==")
    elif args.shop:
        mode = "shop"
        sub = shop_subdomain(args.shop)
        log(f"== shop: {sub}.booth.pm ==")
        ids = crawl_item_ids(sub, session)
        log(f"found {len(ids)} items, checking free ones...")
    else:
        ap.error("provide a shop URL/subdomain, or use --items with item links/IDs")

    done, skipped, failures = 0, 0, []
    for n, item_id in enumerate(ids, 1):
        if args.limit and done >= args.limit:
            break
        try:
            item = fetch_item(item_id, session)
        except Exception as e:
            log(f"[{n}/{len(ids)}] {item_id} fetch failed: {e}")
            continue
        files = free_downloads(item)
        if not files:
            continue  # paid item
        title = item.get("name") or item_id
        if args.folder_by == "first-tag" and item.get("tags"):
            group = item["tags"][0].get("name", "その他")
        else:
            group = (item.get("category") or {}).get("name") or "その他"
        group = CATEGORY_MAP.get(group, group)
        folder = root / sanitize(group, 40) / f"{item_id}_{sanitize(title)}"
        log(f"[{n}/{len(ids)}] FREE {item_id} | {group} | {title} ({len(files)} files)")
        if args.dry_run:
            done += 1
            continue

        folder.mkdir(parents=True, exist_ok=True)
        # downloads (skip existing VALID files; re-download disguised HTML fakes)
        for url, fname in files:
            dest = folder / sanitize(fname, 120)
            if valid_file(dest):
                skipped += 1
                continue
            log(f"    -> {fname}")
            try:
                download(url, dest, session, check_html=True)
            except Exception as e:
                log(f"    ! download failed: {e}")
                failures.append(f"{item_id} {fname}")
            time.sleep(0.6)
        # cover + icon
        images = item.get("images") or []
        cover = folder / "cover.jpg"
        if images and not cover.exists():
            try:
                download(images[0].get("original") or images[0].get("resized"), cover, session)
            except Exception as e:
                log(f"    ! cover failed: {e}")
        if cover.exists():
            make_folder_icon(folder, cover)
        done += 1
        time.sleep(0.8)

    log(f"== done: {done} free items processed, {skipped} files already existed ==")
    if failures:
        log(f"== {len(failures)} downloads FAILED (likely login required, use --cookie): ==")
        for f in failures:
            log(f"   ! {f}")


if __name__ == "__main__":
    sys.exit(main())
