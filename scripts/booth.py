#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
booth.py — BOOTH 技能统一 CLI（三合一）

将原 booth-free-collector / booth-archive-organizer / booth-name-search 三个独立脚本
合并为单一入口，子命令分发；公共逻辑在 booth_common.py。

用法：
    python booth.py download <店铺URL|子域名|散链> [--items ...] [--out DIR] [--cookie C] [--dry-run] [--limit N]
    python booth.py organize   <本地包...> [--id ID] [--out DIR] [--dry-run]
    python booth.py search     <本地文件...> [--base-dir DIR] [--id ID] [--keep] [--dry-run] [--auto] [--cookie-file F]
    python booth.py audit      [--base DIR] [--dry-run]
"""
import argparse
import os
import re
import shutil
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import booth_common as bc


# ══════════════════════════════════════════════════════════════════
# download — 原 booth-free-collector（整店爬取 / 散链下载免费商品）
# ══════════════════════════════════════════════════════════════════
def shop_subdomain(url_or_sub: str) -> str:
    m = re.search(r"https?://([^./]+)\.booth\.pm", url_or_sub)
    return m.group(1) if m else url_or_sub.strip().strip("/")


def parse_discrete(text: str) -> list:
    url_ids = re.findall(r'/items/(\d+)', text)
    bare = re.findall(r'(?<!\d)\d{5,}(?!\d)', text.replace(",", " "))
    ids = url_ids + [b for b in bare if b not in url_ids]
    return list(dict.fromkeys(ids))


def crawl_item_ids(sub: str, session: requests.Session) -> list:
    ids, seen, page = [], set(), 1
    while True:
        url = f"https://{sub}.booth.pm/items?page={page}"
        r = bc.retry_request("GET", url, session, headers=bc.UA, timeout=30)
        if not r or r.status_code != 200:
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


def free_downloads(item: dict) -> list:
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
    if not path.exists() or path.stat().st_size == 0:
        return False
    with open(path, "rb") as fh:
        return not looks_html(fh.read(256))


def download(url: str, dest: Path, session: requests.Session, check_html: bool = False):
    tmp = dest.with_suffix(dest.suffix + ".part")
    last_err = None
    for attempt in range(1, bc.MAX_RETRIES + 1):
        try:
            with session.get(url, headers=bc.UA, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_content(1 << 16):
                        fh.write(chunk)
            last_err = None
            break
        except (requests.ConnectionError, requests.Timeout,
                requests.exceptions.ChunkedEncodingError) as e:
            last_err = e
            if attempt < bc.MAX_RETRIES:
                time.sleep(attempt * 2)
    if last_err:
        # 分块 Range 续传兜底
        try:
            _ranged_download(url, tmp, session)
            last_err = None
        except Exception:
            pass
    if last_err:
        raise last_err
    if check_html:
        with open(tmp, "rb") as fh:
            if looks_html(fh.read(256)):
                tmp.unlink(missing_ok=True)
                raise RuntimeError("got BOOTH login page instead of file — supply --cookie (see SKILL.md)")
    tmp.replace(dest)


def _ranged_download(url: str, tmp: Path, session: requests.Session, chunk: int = 64 * 1024, max_retry: int = 6):
    """小分块 Range 下载，绕开代理对大流量的截断。"""
    size = 0
    if tmp.exists():
        size = tmp.stat().st_size
    while True:
        headers = {**bc.UA, "Range": f"bytes={size}-"}
        r = session.get(url, headers=headers, stream=True, timeout=60)
        if r.status_code == 416:  # Range not satisfiable → done
            break
        r.raise_for_status()
        with open(tmp, "ab") as fh:
            for block in r.iter_content(chunk):
                fh.write(block)
                size += len(block)
        if r.headers.get("Content-Length") and int(r.headers["Content-Length"]) < chunk:
            break


def cmd_download(args):
    discrete = []
    for blob in (args.items or []):
        discrete += parse_discrete(blob)
    if args.shop and parse_discrete(args.shop):
        discrete += parse_discrete(args.shop)
        args.shop = None
    discrete = list(dict.fromkeys(discrete))

    root = Path(args.out)
    session = bc.make_session(cookie=args.cookie, ua=args.ua)

    if discrete:
        mode, sub, ids = "items", "items", discrete
        print(f"== discrete items mode: {len(ids)} link(s) ==")
    elif args.shop:
        mode = "shop"
        sub = shop_subdomain(args.shop)
        print(f"== shop: {sub}.booth.pm ==")
        ids = crawl_item_ids(sub, session)
        print(f"found {len(ids)} items, checking free ones...")
    else:
        print("provide a shop URL/subdomain, or use --items with item links/IDs")
        return

    done, skipped, failures = 0, 0, []
    for n, item_id in enumerate(ids, 1):
        if args.limit and done >= args.limit:
            break
        try:
            item = bc.fetch_item(item_id, session)
        except Exception as e:
            print(f"[{n}/{len(ids)}] {item_id} fetch failed: {e}")
            continue
        if not item:
            continue
        files = free_downloads(item)
        if not files:
            continue
        title = item.get("name") or item_id
        if args.folder_by == "first-tag" and item.get("tags"):
            group = item["tags"][0].get("name", "その他")
        else:
            group = (item.get("category") or {}).get("name") or "その他"
        group = bc.CATEGORY_MAP.get(group, group)
        folder = root / bc.sanitize(group, 40) / f"{item_id}_{bc.sanitize(title)}"
        print(f"[{n}/{len(ids)}] FREE {item_id} | {group} | {title} ({len(files)} files)")
        if args.dry_run:
            done += 1
            continue
        folder.mkdir(parents=True, exist_ok=True)
        for url, fname in files:
            dest = folder / bc.sanitize(fname, 120)
            if valid_file(dest):
                skipped += 1
                continue
            print(f"    -> {fname}")
            try:
                download(url, dest, session, check_html=True)
            except Exception as e:
                print(f"    ! download failed: {e}")
                failures.append(f"{item_id} {fname}")
            time.sleep(0.6)
        images = item.get("images") or []
        cover = folder / "cover.jpg"
        if images and not cover.exists():
            try:
                bc.download_cover(images[0].get("original") or images[0].get("resized"), folder, session)
            except Exception as e:
                print(f"    ! cover failed: {e}")
        if cover.exists():
            bc.make_folder_icon(cover, folder)
        done += 1
        time.sleep(0.8)
    print(f"== done: {done} free items processed, {skipped} files already existed ==")
    if failures:
        print(f"== {len(failures)} downloads FAILED (likely login required, use --cookie): ==")
        for f in failures:
            print(f"   ! {f}")


# ══════════════════════════════════════════════════════════════════
# organize — 原 booth-archive-organizer（文件名含 ID → 按 ID 整理）
# ══════════════════════════════════════════════════════════════════
def extract_id(text: str) -> str:
    m = re.search(r"(?<!\d)(\d{7,})(?!\d)", text)
    return m.group(1) if m else ""


def organize_one(archive: Path, item_id: str, out_root: Path, dry_run: bool,
                 cookie: str = "") -> bool:
    session = bc.make_session(cookie=cookie) if cookie else bc.make_session()
    item = bc.fetch_item(item_id, session)
    if not item:
        print(f"! [{archive.name}] 无法获取商品 {item_id} 元数据")
        return False
    title = item.get("name") or item_id
    cat = (item.get("category") or {}).get("name") or "その他"
    group = bc.CATEGORY_MAP.get(cat, cat)
    folder_name = f"{item_id}_{bc.sanitize(title)}"
    folder = out_root / bc.sanitize(group, 40) / folder_name

    print(f"== 归档: {archive.name}")
    print(f"   ID={item_id} | 类目={group} | 标题={title}")
    print(f"   目标: {folder}")
    if item_id not in archive.stem and extract_id(archive.stem) != item_id:
        print(f"   (注意) 文件名中的 ID 与提供的 {item_id} 不一致，已按指定 ID 处理")
    if dry_run:
        print("   [dry-run] 不执行移动/下载")
        return True

    folder.mkdir(parents=True, exist_ok=True)
    # 主上规则：内部文件名保持**原文件名**（原名自带版本号），目录名用 ID_标题
    dest_arc = folder / bc.sanitize(archive.name, 120)
    if archive.resolve() != dest_arc.resolve():
        if dest_arc.exists():
            print(f"   ! 目标已存在同名校验文件，跳过移动: {dest_arc.name}")
        else:
            try:
                shutil.move(str(archive), str(dest_arc))
                print(f"   -> 已移入: {dest_arc.name}")
            except Exception:
                shutil.copy2(str(archive), str(dest_arc))
                print(f"   ~ 移动失败，已复制: {dest_arc.name} (原文件保留)")
    else:
        print(f"   (已在目标位置): {dest_arc.name}")

    images = item.get("images") or []
    cover = folder / "cover.jpg"
    if images and not cover.exists():
        try:
            curl = images[0].get("original") or images[0].get("resized")
            if curl:
                bc.download_cover(curl, folder, session)
                print(f"   -> 封面已下载: cover.jpg")
        except Exception as e:
            print(f"   ! 封面下载失败: {e}")
    if cover.exists():
        try:
            bc.make_folder_icon(cover, folder)
            print(f"   -> 文件夹图标已设置")
        except bc.IconContractError as e:
            print(f"   ! 图标契约失败: {e}")
    # 主上规则：商品页多免费版本全部补全
    try:
        n = backfill_free_files(folder, item_id, session, dry_run=False, cookie=cookie)
        if n:
            print(f"   ⚡ 免费版本补全: +{n} 个文件")
    except Exception as e:
        print(f"   ! 补全失败: {e}")
    return True


def cmd_organize(args):
    root = Path(args.out)
    ok = 0
    for path in args.archive:
        p = Path(path)
        if not p.is_file():
            print(f"! 找不到文件: {path}")
            continue
        item_id = args.id or extract_id(p.stem)
        if not item_id:
            print(f"! [{p.name}] 文件名中未找到 7 位数字 BOOTH ID，跳过（可用 --id 指定）")
            continue
        if organize_one(p, item_id, root, args.dry_run, cookie=args.cookie):
            ok += 1
    print(f"== 完成: {ok}/{len(args.archive)} 个归档处理成功 ==")


# ══════════════════════════════════════════════════════════════════
# search — 原 booth-name-search（无 ID 按名搜索 + UnityPackage 锚点）
# ══════════════════════════════════════════════════════════════════
def backfill_free_files(dest_dir: Path, item_id: str, session: requests.Session,
                        dry_run: bool = False, cookie: str = "") -> int:
    """商品页多免费版本补全：本地缺的免费文件全部下载补齐。

    主上规则（2026-08-03）：商品页有 2~3 个免费文件（如 3562410 的
    Ver_2.00.zip + Ver_1.01.zip），本地只有其中 1 个 → 其余全部补全。
    公开 JSON 的 variations[].downloadable 已含完整文件列表与 URL（免登录检测），
    但**实际下载需要登录 Cookie**（BOOTH 免费文件也要登录才能下载）。
    无 cookie 时仅报告缺失版本，不下载。
    """
    try:
        item = bc.fetch_item(item_id, session)
    except Exception as e:
        print(f"  ! 补全检查失败: {e}")
        return 0
    if not item:
        return 0
    files = free_downloads(item)
    if not files:
        return 0
    # 带 cookie 时重建带会话的 session（下载需登录）；无 cookie → 仅报告
    dl_session = None
    if cookie:
        dl_session = session or bc.make_session(cookie=cookie)
    added = 0
    missing = []
    for url, fname in files:
        dest = dest_dir / bc.sanitize(fname, 120)
        # 同版本不同后缀也算已存在（本地 Ver_2.00.unitypackage vs 远程 Ver_2.00.zip）
        local_ver = {bc.extract_version_tag(p.name) for p in dest_dir.iterdir() if p.is_file()}
        remote_ver = bc.extract_version_tag(fname)
        if remote_ver and remote_ver in local_ver:
            continue
        if dest.exists() and valid_file(dest):
            continue
        missing.append((url, fname))
    if not missing:
        return 0
    print(f"  ⚡ 商品页另有 {len(missing)} 个免费版本未在本地: {[f[1] for f in missing]}")
    if dry_run or not dl_session:
        if not dl_session:
            print("  (需 --cookie 才能下载；可用 `booth download` 带 cookie 补全)")
        return 0
    for url, fname in missing:
        print(f"    + 补全免费文件: {fname}")
        try:
            download(url, dest_dir / bc.sanitize(fname, 120), dl_session, check_html=True)
            added += 1
        except Exception as e:
            print(f"    ! 补全下载失败: {fname}: {e}")
        time.sleep(0.5)
    return added


def organize_file(src_path: str, item_info: dict, base_dir: str, move_mode: bool = True,
                  session: requests.Session | None = None, backfill: bool = True,
                  cookie: str = "") -> Path | None:
    src = Path(src_path)
    base = Path(base_dir)
    item_id = item_info["id"]
    title = bc.sanitize_filename(item_info["name"])
    cat_raw = item_info.get("category_name", "") or item_info.get("category", "")
    cat_cn = bc.classify(cat_raw, item_info.get("category_parent", ""))
    thumb = item_info.get("thumbnail", "")
    folder_name = f"{item_id}_{title}"
    cat_dir = base / cat_cn
    dest_dir = cat_dir / folder_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    # 主上规则：目录名 = ID_标题，但**内部文件名保持原文件名**（原名自带版本号）
    dest_file = dest_dir / bc.sanitize(src.name, 120)
    cover = dest_dir / "cover.jpg"

    # 幂等：已含原文件 + 有效封面，仅补图标
    if dest_file.exists() and cover.exists() and cover.stat().st_size > 1000:
        print(f"  已存在，仅补图标: {dest_dir}")
        bc.make_folder_icon(cover, dest_dir)
        return dest_dir

    if not dest_file.exists():
        if move_mode and src.exists():
            try:
                shutil.move(str(src), str(dest_file))
                print(f"  已移动: {dest_file.name}")
            except OSError:
                shutil.copy2(str(src), str(dest_file))
                print(f"  已复制(跨盘): {dest_file.name}")
        else:
            if src.exists():
                shutil.copy2(str(src), str(dest_file))
                print(f"  已复制: {dest_file.name}")

    if not (cover.exists() and cover.stat().st_size > 1000):
        cover = bc.download_cover(thumb, dest_dir)
    if cover:
        try:
            bc.make_folder_icon(cover, dest_dir)
        except bc.IconContractError as e:
            print(f"  ! 图标契约失败: {e}")
    print(f"  整理完成: {dest_dir}")

    # 主上规则：商品页多免费版本全部补全
    if backfill:
        n = backfill_free_files(dest_dir, item_id, session or bc.make_session(), cookie=cookie)
        if n:
            print(f"  ⚡ 免费版本补全: +{n} 个文件")
    return dest_dir


def process_file(filepath: str, base_dir: str, move_mode: bool = True,
                 auto: bool = False, force_id: str = "", session=None,
                 cookie: str = "") -> dict | None:
    fp = Path(filepath)
    if not fp.exists():
        print(f"文件不存在: {filepath}")
        return None
    print(f"\n{'='*60}")
    print(f"处理: {fp.name}")
    s = session or bc.make_session()

    if force_id:
        d = bc.fetch_item(force_id, s)
        if not d:
            print(f"  指定 ID {force_id} 获取失败")
            return None
        cat = d.get("category") or {}
        best_item = {
            "id": str(force_id), "name": d.get("name", ""),
            "price": bc._parse_price(d.get("price")), "price_text": "",
            "brand": "", "shop": d.get("shop", ""),
            "category": cat.get("name", ""), "category_name": cat.get("name", ""),
            "category_parent": (cat.get("parent") or {}).get("name", ""),
            "thumbnail": bc._thumb_from_json(d),
        }
        best_item = bc.refine_from_json(best_item, s)
        organize_file(filepath, best_item, base_dir, move_mode, session=s, cookie=cookie)
        return best_item

    candidates = bc.sanitize_query(fp.name)
    print(f"  搜索候选: {candidates}")

    # 1.5 水印识别兜底
    if not any(bc.search_booth(q, s) for q in candidates[:1]):
        watermark_url = bc.detect_watermark_url_in_zip(filepath)
        if watermark_url:
            print(f"  ⚡ 压缩包内发现水印 URL: {watermark_url}")
            shop_id = bc.extract_shop_id_from_url(watermark_url)
            if shop_id:
                print(f"  ⚡ 推断店铺: {shop_id}，尝试列出店内商品")
                shop_items = bc.list_shop_items(shop_id, s)
                if shop_items:
                    matched, ambiguous = bc.score_and_pick(candidates[0], shop_items, prefer_free=False,
                                                          source_zip_path=filepath, session=s)
                    if matched:
                        best_item = bc.refine_from_json(matched, s)
                        print(f"      通过水印店铺匹配: [{best_item['id']}] {best_item['name']}")
                        organize_file(filepath, best_item, base_dir, move_mode, session=s, cookie=cookie)
                        return best_item

    best_item = None
    ambig_fallback = None
    for i, q in enumerate(candidates):
        print(f"  [{i+1}] 搜索: {q}")
        results = bc.search_booth(q, s)
        print(f"      命中: {len(results)} 件")
        if results:
            picked, ambiguous = bc.score_and_pick(q, results, prefer_free=False,
                                                  source_zip_path=filepath, session=s)
            if picked:
                if ambiguous and not auto:
                    if not ambig_fallback:
                        ambig_fallback = (picked, results)
                    print(f"      ⚠ 歧义，暂存候选，继续尝试下一关键词...")
                    if i < len(candidates) - 1:
                        time.sleep(0.5)
                    continue
                best_item = bc.refine_from_json(picked, s)
                print(f"      选中: [{best_item['id']}] {best_item['name']}")
                print(f"            类目: {bc.classify(best_item.get('category_name',''), best_item.get('category_parent',''))} | 店铺: {best_item['shop']}")
                break
        if i < len(candidates) - 1:
            time.sleep(0.5)

    if not best_item and ambig_fallback:
        picked, results = ambig_fallback
        print(f"  ⚠ 所有候选均歧义，需主上确认。候选：")
        for it in results[:8]:
            print(f"    [{it['id']}] {it['name']} | {it['price_text']} | {it['shop']}")
        return {"_ambiguous": True, "candidates": results}
    if not best_item:
        print("  未找到匹配商品。")
        return None
    dest = organize_file(filepath, best_item, base_dir, move_mode, session=s, cookie=cookie)
    return best_item


def cmd_search(args):
    move_mode = not args.keep
    session = bc.make_session(cookie=args.cookie) if args.cookie else bc.make_session()
    results = []
    for fp in args.files:
        if args.dry_run:
            candidates = bc.sanitize_query(Path(fp).name)
            print(f"\n{'='*60}")
            print(f"Dry-run: {Path(fp).name}")
            print(f"  候选: {candidates}")
            for q in candidates:
                items = bc.search_booth(q, session)
                picked, ambiguous = bc.score_and_pick(q, items, prefer_free=False, session=session)
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
            info = process_file(fp, args.base_dir, move_mode=move_mode, auto=args.auto,
                                force_id=args.id, session=session, cookie=args.cookie)
            if info and not info.get("_ambiguous"):
                results.append(info)
    print(f"\n{'='*60}")
    print(f"汇总: {len(results)}/{len(args.files)} 件成功匹配")
    for r in results:
        print(f"  [{r['id']}] {r['name']} — {r.get('price_text','')}")


# ══════════════════════════════════════════════════════════════════
# audit — 原 audit_folder_icons.py（全库图标完整性巡检）
# ══════════════════════════════════════════════════════════════════
def _attr_str(p: Path) -> str:
    a = bc._get_attrs(p)
    s = []
    if a & 0x02:
        s.append('H')
    if a & 0x04:
        s.append('S')
    if a & 0x01:
        s.append('R')
    return ''.join(s) or '-'


def audit_one(d: Path, fix: bool):
    issues, actions = [], []
    ico = d / '.folder_icon.ico'
    ini = d / 'desktop.ini'
    cover = d / 'cover.jpg'
    has_icon_resource = False
    if ini.exists():
        txt = _read_ini(ini)
        has_icon_resource = 'IconResource=.folder_icon.ico' in txt
        if not has_icon_resource:
            issues.append('ini 缺 IconResource=.folder_icon.ico 字段')
    else:
        issues.append('ini 缺失')
    if not ico.exists():
        issues.append('ico 缺失')
    else:
        if ico.stat().st_size < 1024:
            issues.append(f'ico 过小（<1KB，实际 {ico.stat().st_size}B）')
    if ini.exists():
        if 'H' not in _attr_str(ini) or 'S' not in _attr_str(ini):
            issues.append(f'ini 属性 {_attr_str(ini)}（缺 H/S）')
    if ico.exists():
        if 'H' not in _attr_str(ico):
            issues.append(f'ico 属性 {_attr_str(ico)}（缺 H）')
    if 'R' not in _attr_str(d):
        issues.append(f'文件夹属性 {_attr_str(d)}（缺 R）')
    if fix and issues and cover.exists():
        actions.append('走 make_folder_icon 重写')
    elif fix and issues and not cover.exists():
        actions.append('缺 cover.jpg，需人工补')
    return issues, actions


def _read_ini(ini: Path) -> str:
    for enc in ('utf-16', 'utf-8', 'gbk'):
        try:
            return ini.read_text(encoding=enc, errors='ignore')
        except Exception:
            continue
    return ''


def fix_one(d: Path) -> str:
    cover = d / 'cover.jpg'
    if not cover.exists():
        return 'no-cover'
    try:
        bc.make_folder_icon(cover, d)
        return 'fixed'
    except Exception as e:
        return f"failed: {e}"


def cmd_audit(args):
    base = Path(args.base)
    if not base.is_dir():
        print(f"FATAL: {args.base} 不存在")
        return
    fix = not (args.dry_run or args.no_fix)
    total_dirs = issues_dirs = 0
    problem_dirs = []
    for cat_dir in sorted(base.iterdir()):
        if not cat_dir.is_dir():
            continue
        for d in sorted(cat_dir.iterdir()):
            if not d.is_dir():
                continue
            total_dirs += 1
            issues, suggested = audit_one(d, fix)
            if issues:
                issues_dirs += 1
                problem_dirs.append((d, issues, suggested))
    print(f"\n扫描 {total_dirs} 个商品目录")
    print(f"问题目录 {issues_dirs} 个")
    if not problem_dirs:
        print("✓ 全部通过")
        return
    for d, issues, suggested in problem_dirs[:50]:
        print(f"\n  {d.relative_to(base)}")
        for i in issues:
            print(f"    - {i}")
    if fix and not args.dry_run:
        ok = no_cover = failed = 0
        for d, issues, _ in problem_dirs:
            r = fix_one(d)
            if r == 'fixed':
                ok += 1
            elif r == 'no-cover':
                no_cover += 1
            else:
                failed += 1
                print(f"  {r}：{d.relative_to(base)}")
        print(f"\n修复完成：{ok} fixed / {no_cover} no-cover / {failed} failed")
        bc._notify_shell()


# ══════════════════════════════════════════════════════════════════
# CLI 主入口
# ══════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        prog="booth",
        description="BOOTH 素材统一管理：download(下载免费商品) / organize(按ID整理) / search(按名搜索) / audit(图标巡检)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # download
    p_dl = sub.add_parser("download", help="整店/散链下载免费商品（需 Cookie 拉文件）")
    p_dl.add_argument("shop", nargs="?", help="店铺 URL/子域名，或含 /items/<id> 的散链")
    p_dl.add_argument("--items", nargs="+", default=[], metavar="LINKS", help="散链链接/裸 ID")
    p_dl.add_argument("--out", default=r"G:\Lin_File\BOOTH")
    p_dl.add_argument("--dry-run", action="store_true")
    p_dl.add_argument("--limit", type=int, default=0)
    p_dl.add_argument("--folder-by", choices=["category", "first-tag"], default="category")
    p_dl.add_argument("--cookie", default="", help="BOOTH 登录 Cookie：原始串 / cookies.txt / 存串文件（会话 Cookie 名 _plaza_session_nktz7u）")
    p_dl.add_argument("--ua", default="")
    p_dl.set_defaults(func=cmd_download)

    # organize
    p_or = sub.add_parser("organize", help="本地压缩包（文件名含 7 位 ID）按 ID 整理归档")
    p_or.add_argument("archive", nargs="+", help="BOOTH archive file(s) (.rar/.zip/.7z/.unitypackage) with 7-digit id")
    p_or.add_argument("--out", default=r"G:\Lin_File\BOOTH")
    p_or.add_argument("--id", default="", help="force item id（文件名无 ID 时用）")
    p_or.add_argument("--dry-run", action="store_true")
    p_or.add_argument("--cookie", default="", help="BOOTH 登录 Cookie（用于补全商品页其他免费版本；无则仅报告缺失）")
    p_or.set_defaults(func=cmd_organize)

    # search
    p_se = sub.add_parser("search", help="本地文件（无 ID）按名搜索 BOOTH 后整理")
    p_se.add_argument("files", nargs="+", help="待整理的文件路径")
    p_se.add_argument("--base-dir", default="G:/Lin_File/BOOTH")
    p_se.add_argument("--dry-run", action="store_true")
    p_se.add_argument("--keep", action="store_true", help="复制而非移动")
    p_se.add_argument("--auto", action="store_true", help="歧义也强制选最佳")
    p_se.add_argument("--id", default="", help="强制指定 BOOTH 商品 ID（跳过搜索）")
    p_se.add_argument("--cookie-file", default="")
    p_se.add_argument("--cookie", default="", help="BOOTH 登录 Cookie（用于补全商品页其他免费版本；无则仅报告缺失）")
    p_se.set_defaults(func=cmd_search)

    # audit
    p_au = sub.add_parser("audit", help="全库文件夹图标三件套完整性巡检 + 自动修复")
    p_au.add_argument("--base", default=r"G:\Lin_File\BOOTH")
    p_au.add_argument("--dry-run", action="store_true")
    p_au.add_argument("--no-fix", action="store_true")
    p_au.set_defaults(func=cmd_audit)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
