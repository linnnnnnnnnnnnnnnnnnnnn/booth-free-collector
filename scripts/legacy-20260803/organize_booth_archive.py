# -*- coding: utf-8 -*-
"""
BOOTH archive organizer
When the user drops / pastes a local BOOTH archive (.rar/.zip/.7z) whose file
name embeds a 7-digit BOOTH item ID, organize it into:

    <out>/<category-zh tag>/<itemID>_<title>/
        - <itemID>_<title>.<ext>   (the renamed archive, moved in)
        (or, if the archive is a multi-item bundle, keep its original name)
        - cover.jpg                 (first product image, from booth.pximg.net)
        - .folder_icon.ico          (hidden, generated from cover)
        - desktop.ini               (hidden+system, folder icon -> cover)

So in Windows Explorer "Large icons" view every item folder shows its cover,
identical layout to what booth-free-collector produces by downloading.

Usage:
    python organize_booth_archive.py "G:/path/跟随悬浮机-6504842等3个文件.rar"
    python organize_booth_archive.py "a.rar" "b.zip" --out "G:/Lin_File/BOOTH"
    python organize_booth_archive.py "weird_name.rar" --id 6504842   # force id

Notes:
- Metadata (title/category/cover URL) comes from the PUBLIC BOOTH JSON API
  (https://booth.pm/ja/items/<id>.json) — no login needed for organizing.
- Cover images live on booth.pximg.net (public CDN), also no login needed.
- Idempotent: if the target folder already exists with the renamed archive and
  a valid cover.jpg, the archive is left in place and only missing cover/icon
  are filled in.
- Respects HTTP(S)_PROXY env vars automatically (requests default behavior).
"""
import argparse
import os
import platform
import re
import shutil
import sys
import time
from pathlib import Path

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
INVALID = r'<>:"/\\|?*'
MAX_RETRIES = 3

# BOOTH category name -> Chinese folder name (mirrors booth-free-collector)
CATEGORY_MAP = {
    "3Dテクスチャ": "3D贴图",
    "3D衣装": "3D服装",
    "3D装飾品": "3D饰品",
    "3Dモデル": "3D模型",
    "3Dキャラクター": "3D角色",
    "3D小道具": "3D道具",
    "3D環境・ワールド": "3D世界",
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


def sanitize(name: str, max_len: int = 70) -> str:
    out = "".join(c for c in name if c not in INVALID and ord(c) >= 32)
    out = re.sub(r"\s+", " ", out).strip().rstrip(". ")
    if len(out) > max_len:
        out = out[:max_len].rstrip(". ")
    return out or "untitled"


def extract_id(text: str) -> str:
    """First 7+ digit BOOTH item id found in the text (file name).

    Uses look-around for non-digit neighbours instead of \\b, because Python's
    Unicode \\b treats CJK chars (e.g. the 等 right after an id) as word chars,
    which would break a plain \\b\\d{7,}\\b boundary.
    """
    m = re.search(r"(?<!\d)(\d{7,})(?!\d)", text)
    return m.group(1) if m else ""


def fetch_item(item_id: str, session: requests.Session) -> dict:
    r = session.get(f"https://booth.pm/ja/items/{item_id}.json",
                    headers={**UA, "Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    return r.json()


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
        log("  ! Pillow missing, skip icon")
        return
    ico = folder / ".folder_icon.ico"
    ini = folder / "desktop.ini"
    if ico.exists() and ini.exists():
        return  # already customized (idempotent)
    if ico.exists():
        set_attrs(ico, 0x80)  # clear hidden attr, or PIL can't overwrite
    try:
        img = Image.open(cover).convert("RGBA")
        side = max(img.size)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
        canvas.save(ico, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32)])
    except Exception as e:
        log(f"  ! icon convert failed: {e}")
        return
    if ini.exists():
        set_attrs(ini, 0x80)
    ini.write_text("[.ShellClassInfo]\r\nIconResource=.folder_icon.ico,0\r\nConfirmFileOp=0\r\n", encoding="utf-16")
    set_attrs(ico, FILE_ATTRIBUTE_HIDDEN)
    set_attrs(ini, FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM)
    set_attrs(folder, FILE_ATTRIBUTE_READONLY)


def download_cover(url: str, dest: Path, session: requests.Session):
    """Small public image (booth.pximg.net). Simple streamed GET w/ retry."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with session.get(url, headers={**UA, "Referer": "https://booth.pm/"},
                             stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_content(1 << 16):
                        fh.write(chunk)
            last_err = None
            break
        except (requests.ConnectionError, requests.Timeout,
                requests.exceptions.ChunkedEncodingError) as e:
            last_err = e
            if attempt < MAX_RETRIES:
                time.sleep(attempt * 2)
    if last_err:
        raise last_err
    tmp.replace(dest)


def organize_one(archive: Path, item_id: str, out_root: Path, dry_run: bool):
    session = requests.Session()
    try:
        item = fetch_item(item_id, session)
    except Exception as e:
        log(f"! [{archive.name}] 无法获取商品 {item_id} 元数据: {e}")
        return False

    title = item.get("name") or item_id
    cat = (item.get("category") or {}).get("name") or "その他"
    group = CATEGORY_MAP.get(cat, cat)
    folder_name = f"{item_id}_{sanitize(title)}"
    new_arc_name = f"{folder_name}{archive.suffix}"
    folder = out_root / sanitize(group, 40) / folder_name

    log(f"== 归档: {archive.name}")
    log(f"   ID={item_id} | 类目={group} | 标题={title}")
    log(f"   目标: {folder}")

    if item_id not in archive.stem and extract_id(archive.stem) != item_id:
        log(f"   (注意) 文件名中的 ID 与提供的 {item_id} 不一致，已按指定 ID 处理")

    if dry_run:
        log("   [dry-run] 不执行移动/下载")
        return True

    folder.mkdir(parents=True, exist_ok=True)
    dest_arc = folder / new_arc_name

    # move archive in (same drive = instant rename; cross-device = copy)
    if archive.resolve() != dest_arc.resolve():
        if dest_arc.exists():
            log(f"   ! 目标已存在同名校验文件，跳过移动: {dest_arc.name}")
        else:
            try:
                shutil.move(str(archive), str(dest_arc))
                log(f"   -> 已重命名并移入: {new_arc_name}")
            except Exception as e:
                # fallback: copy then leave original
                shutil.copy2(str(archive), str(dest_arc))
                log(f"   ~ 移动失败，已复制: {new_arc_name} (原文件保留): {e}")
    else:
        log(f"   (已在目标位置): {new_arc_name}")

    # cover
    images = item.get("images") or []
    cover = folder / "cover.jpg"
    if images and not cover.exists():
        try:
            curl = images[0].get("original") or images[0].get("resized")
            if curl:
                download_cover(curl, cover, session)
                log(f"   -> 封面已下载: cover.jpg")
        except Exception as e:
            log(f"   ! 封面下载失败: {e}")
    if cover.exists():
        make_folder_icon(folder, cover)
        log(f"   -> 文件夹图标已设置")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("archive", nargs="+", help="BOOTH archive file(s) (.rar/.zip/.7z) with a 7-digit item id in the name")
    ap.add_argument("--out", default=r"G:\Lin_File\BOOTH")
    ap.add_argument("--id", default="", help="force the BOOTH item id (else auto-extracted from file name)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = Path(args.out)
    ok = 0
    for path in args.archive:
        p = Path(path)
        if not p.is_file():
            log(f"! 找不到文件: {path}")
            continue
        item_id = args.id or extract_id(p.stem)
        if not item_id:
            log(f"! [{p.name}] 文件名中未找到 7 位数字 BOOTH ID，跳过（可用 --id 指定）")
            continue
        if organize_one(p, item_id, root, args.dry_run):
            ok += 1
    log(f"== 完成: {ok}/{len(args.archive)} 个归档处理成功 ==")


if __name__ == "__main__":
    sys.exit(main())
