#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_folder_icons.py — BOOTH 全库图标三件套完整性巡检与修复

2026-08-02 主上反馈：Hermes 整理 8435322 时写出了残缺 desktop.ini（缺 IconResource 字段、
缺 .folder_icon.ico 文件）→ Explorer 不识别 → 文件夹显示默认黄色图标。
Skill 必须自带完整性契约，任意 agent 用本 Skill 整理都不应留半成品。

本工具对 G:\\Lin_File\\BOOTH\\ 下所有商品目录做 4 类巡检：
  1. desktop.ini 缺 IconResource=.folder_icon.ico 字段
  2. .folder_icon.ico 缺失或 < 1KB
  3. ICO 含非正方形条目（宽幅陷阱，导致缩略图居中小图）
  4. 属性不全（ini 缺 H+S、文件夹缺 R，Explorer 拒读 desktop.ini）

自动修复：能找到 cover.jpg 的就走 make_folder_icon 重写；找不到 cover 的标记需人工处理。

用法：
    python audit_folder_icons.py [--base G:\\Lin_File\\BOOTH] [--dry-run] [--no-fix]
"""
import argparse, os, sys, struct, ctypes
from pathlib import Path

FILE_ATTRIBUTE_HIDDEN  = 0x02
FILE_ATTRIBUTE_SYSTEM   = 0x04
FILE_ATTRIBUTE_READONLY = 0x01

def _attrs(p: Path) -> int:
    a = ctypes.windll.kernel32.GetFileAttributesW(str(p))
    return a if a != 0xFFFFFFFF else 0

def _attr_str(p: Path) -> str:
    a = _attrs(p)
    s = []
    if a & FILE_ATTRIBUTE_HIDDEN:  s.append('H')
    if a & FILE_ATTRIBUTE_SYSTEM:   s.append('S')
    if a & FILE_ATTRIBUTE_READONLY: s.append('R')
    return ''.join(s) or '-'

def _ico_sizes(p: Path) -> list[tuple[int,int]]:
    try:
        with open(p, 'rb') as f:
            hdr = f.read(6)
        if hdr[:4] != b'\x00\x00\x01\x00':
            return []
        n = struct.unpack('<H', hdr[4:6])[0]
        out = []
        for _ in range(n):
            e = f.read(16)
            w = e[0] or 256
            h = e[1] or 256
            out.append((w, h))
        return out
    except Exception:
        return []

def _read_ini(ini: Path) -> str:
    for enc in ('utf-16', 'utf-8', 'gbk'):
        try:
            return ini.read_text(encoding=enc, errors='ignore')
        except Exception:
            continue
    return ''

def audit_one(d: Path, fix: bool) -> tuple[list[str], list[str]]:
    """返回 (issues, actions)。"""
    issues, actions = [], []
    ico = d / '.folder_icon.ico'
    ini = d / 'desktop.ini'
    cover = d / 'cover.jpg'

    # 1. ini 缺 IconResource 字段
    has_icon_resource = False
    if ini.exists():
        txt = _read_ini(ini)
        has_icon_resource = 'IconResource=.folder_icon.ico' in txt
        if not has_icon_resource:
            issues.append('ini 缺 IconResource=.folder_icon.ico 字段')
    else:
        issues.append('ini 缺失')

    # 2. .folder_icon.ico 缺失或 < 1KB
    if not ico.exists():
        issues.append('ico 缺失')
    else:
        if ico.stat().st_size < 1024:
            issues.append(f'ico 过小（<1KB，实际 {ico.stat().st_size}B）')
        else:
            # 3. ICO 含非正方形条目（宽幅陷阱）
            sizes = _ico_sizes(ico)
            non_sq = [s for s in sizes if s[0] != s[1]]
            if non_sq:
                issues.append(f'ICO 含非正方形条目：{non_sq}')

    # 4. 属性
    if ini.exists():
        if 'H' not in _attr_str(ini) or 'S' not in _attr_str(ini):
            issues.append(f'ini 属性 {_attr_str(ini)}（缺 H/S）')
    if ico.exists():
        if 'H' not in _attr_str(ico):
            issues.append(f'ico 属性 {_attr_str(ico)}（缺 H）')
    if 'R' not in _attr_str(d):
        issues.append(f'文件夹属性 {_attr_str(d)}（缺 R）')

    # 自动修复
    if fix and issues and cover.exists():
        actions.append('走 make_folder_icon 重写')
    elif fix and issues and not cover.exists():
        actions.append('缺 cover.jpg，需人工补')

    return issues, actions

def fix_one(d: Path) -> str:
    """用 booth-name-search 的 make_folder_icon 重新写图标（最稳的版本）。
    找不到 cover 时跳过。返回 'fixed' / 'no-cover' / 'failed: <err>'"""
    # 优先用 booth-name-search 的 make_folder_icon（最完备，含 SHChangeNotify + 完整性自检）
    try:
        sys.path.insert(0, r'G:\Lin_File\Documents\Skills\booth-toolkit\skills\booth-name-search\scripts')
        from booth_name_search import make_folder_icon
    except Exception as e:
        return f"failed: 导入 booth_name_search 失败 {e}"

    cover = d / 'cover.jpg'
    if not cover.exists():
        return 'no-cover'

    # 强制 NORMAL 属性再覆盖
    for p in (d / '.folder_icon.ico', d / 'desktop.ini'):
        if p.exists():
            ctypes.windll.kernel32.SetFileAttributesW(str(p), 0x80)

    try:
        make_folder_icon(cover, d)
        return 'fixed'
    except Exception as e:
        return f"failed: {e}"

def main():
    ap = argparse.ArgumentParser(description='BOOTH 文件夹图标完整性巡检')
    ap.add_argument('--base', default=r'G:\Lin_File\BOOTH', help='BOOTH 根目录')
    ap.add_argument('--dry-run', action='store_true', help='只报告不修复')
    ap.add_argument('--no-fix', action='store_true', help='不自动修复，只报告')
    args = ap.parse_args()

    base = Path(args.base)
    if not base.is_dir():
        print(f"FATAL: {base} 不存在")
        sys.exit(1)

    fix = not (args.dry_run or args.no_fix)

    total_dirs = 0
    issues_dirs = 0
    problem_dirs: list[tuple[Path, list[str], list[str]]] = []

    # 遍历所有一级分类下的商品目录
    for cat_dir in sorted(base.iterdir()):
        if not cat_dir.is_dir():
            continue
        if cat_dir.name in ('_booth-restored', '_probe_imgs'):
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

    print(f"\n=== 问题目录 ===")
    for d, issues, suggested in problem_dirs[:50]:
        rel = d.relative_to(base)
        print(f"\n  {rel}")
        for i in issues:
            print(f"    - {i}")
        if suggested and not args.dry_run:
            print(f"    → 建议：{'; '.join(suggested)}")

    if len(problem_dirs) > 50:
        print(f"\n  ... 还有 {len(problem_dirs)-50} 个未显示")

    if fix and not args.dry_run:
        print(f"\n=== 开始修复 {issues_dirs} 个目录 ===")
        ok = 0
        no_cover = 0
        failed = 0
        for d, issues, _ in problem_dirs:
            r = fix_one(d)
            if r == 'fixed':
                ok += 1
            elif r == 'no-cover':
                no_cover += 1
                print(f"  SKIP（无 cover）：{d.relative_to(base)}")
            else:
                failed += 1
                print(f"  {r}：{d.relative_to(base)}")
        print(f"\n修复完成：{ok} fixed / {no_cover} no-cover / {failed} failed")

        # 全 shell SHChangeNotify
        ctypes.windll.shell32.SHChangeNotify(0x00008000, 0x0000, None, None)
        print("SHChangeNotify 全 shell 刷新已触发")

if __name__ == '__main__':
    main()