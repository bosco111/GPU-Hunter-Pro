#!/usr/bin/env python3
"""
GPU-Hunter-Pro — 多平台 GPU 自动扫描与租用脚本
支持平台: RunPod / PrimeIntellect / Vast / Clore
功能: 自动扫描 → 价格匹配 → 自动下单 → Telegram 通知
仅使用 Python 标准库, 无需安装额外依赖
"""

import argparse
import json
import os
import re
import ssl
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import textwrap
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ============================================================
# 常量 & 全局配置
# ============================================================

VERSION = "1.3.0"

# ============================================================
# ANSI 颜色系统
# ============================================================

class C:
    """ANSI 终端颜色"""
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    ITALIC  = "\033[3m"
    UNDER   = "\033[4m"
    BLINK   = "\033[5m"
    # 前景色
    BLACK   = "\033[30m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"
    # 亮色
    B_RED    = "\033[91m"
    B_GREEN  = "\033[92m"
    B_YELLOW = "\033[93m"
    B_BLUE   = "\033[94m"
    B_MAGENTA= "\033[95m"
    B_CYAN   = "\033[96m"
    B_WHITE  = "\033[97m"
    # 背景色
    BG_RED     = "\033[41m"
    BG_GREEN   = "\033[42m"
    BG_YELLOW  = "\033[43m"
    BG_BLUE    = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN    = "\033[46m"

    @staticmethod
    def disable():
        """禁用颜色 (非 TTY 环境)"""
        for attr in dir(C):
            if not attr.startswith("_") and isinstance(getattr(C, attr), str) and attr != "RESET":
                setattr(C, attr, "")
        C.RESET = ""

# 非终端环境自动禁用颜色
if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
    C.disable()

# ============================================================
# 终端显示宽度计算 (CJK 字符占 2 列, ANSI 转义码占 0 列)
# ============================================================

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")

def strip_ansi(s: str) -> str:
    """去除 ANSI 转义序列"""
    return _ANSI_RE.sub("", s)

def display_width(s: str) -> int:
    """计算字符串在终端中的显示宽度"""
    clean = strip_ansi(s)
    w = 0
    for ch in clean:
        eaw = unicodedata.east_asian_width(ch)
        if eaw in ("W", "F"):  # Wide / Fullwidth (CJK 等)
            w += 2
        else:
            w += 1
    return w

def pad_right(s: str, width: int) -> str:
    """按显示宽度右填充空格"""
    cur = display_width(s)
    if cur < width:
        return s + " " * (width - cur)
    return s

def pad_left(s: str, width: int) -> str:
    """按显示宽度左填充空格"""
    cur = display_width(s)
    if cur < width:
        return " " * (width - cur) + s
    return s

# 扫描动画帧
SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
_spinner_idx = 0

def next_spinner() -> str:
    global _spinner_idx
    s = SPINNER[_spinner_idx % len(SPINNER)]
    _spinner_idx += 1
    return s

def ui_box(title: str, width: int = 58) -> str:
    """生成彩色标题框"""
    inner = f" {title} "
    pad = width - len(inner) - 2
    left = pad // 2
    right = pad - left
    top = f"╭{'─' * left}{inner}{'─' * right}╮"
    bot = f"╰{'─' * (width - 2)}╯"
    return f"{C.B_CYAN}{top}{C.RESET}\n{C.B_CYAN}{bot}{C.RESET}"

def ui_section(icon: str, title: str) -> str:
    """章节标题"""
    return f"\n{C.B_YELLOW}  {icon} {title}{C.RESET}"

def ui_input(label: str, default: str = "") -> str:
    """彩色输入提示"""
    if default:
        prompt = f"  {C.DIM}│{C.RESET} {C.B_WHITE}{label}{C.RESET} {C.DIM}[{default}]{C.RESET}: "
    else:
        prompt = f"  {C.DIM}│{C.RESET} {C.B_WHITE}{label}{C.RESET}: "
    return input(prompt).strip()

def ui_hint(text: str):
    """灰色提示"""
    print(f"  {C.DIM}  {text}{C.RESET}")

def ui_ok(text: str):
    print(f"  {C.GREEN}✔ {text}{C.RESET}")

def ui_warn(text: str):
    print(f"  {C.YELLOW}⚠ {text}{C.RESET}")

def ui_err(text: str):
    print(f"  {C.B_RED}✘ {text}{C.RESET}")

def ui_divider(width: int = 58):
    print(f"  {C.DIM}{'─' * width}{C.RESET}")

def ui_kv(key: str, value: str, key_width: int = 14):
    """键值对显示"""
    k = key.ljust(key_width)
    print(f"  {C.DIM}│{C.RESET} {C.CYAN}{k}{C.RESET} {C.WHITE}{value}{C.RESET}")

def _make_banner() -> str:
    """生成正确对齐的彩色 Banner"""
    W = 56  # 框内内容宽度
    bc = C.B_CYAN
    r = C.RESET

    def border_line(ch_left, ch_mid, ch_right):
        return f"  {bc}{ch_left}{ch_mid * W}{ch_right}{r}"

    def content_line(inner_colored: str) -> str:
        """构建一行内容, 按显示宽度填充到 W 列后加右边框"""
        vis_w = display_width(inner_colored)
        pad = W - vis_w
        if pad < 0:
            pad = 0
        return f"  {bc}║{r}{inner_colored}{' ' * pad}{bc}║{r}"

    empty = content_line(" " * W)
    line1 = content_line(f"  {C.B_MAGENTA}⚡ GPU-Hunter-Pro{r}  {C.DIM}v{VERSION}{r}")
    line2 = content_line(
        f"  {C.B_BLUE}RunPod{r} {C.DIM}·{r} {C.B_GREEN}PrimeIntellect{r} {C.DIM}·{r} {C.B_YELLOW}Vast{r} {C.DIM}·{r} {C.B_RED}Clore{r}"
    )
    # 中文行: "自动扫描 → 价格匹配 → 自动下单 → Telegram 通知"
    # 每个中文字 = 2列, 需要精确计算
    cn_text = "自动扫描 → 价格匹配 → 自动下单 → Telegram 通知"
    line3 = content_line(f"  {C.WHITE}{cn_text}{r}")

    lines = [
        "",
        border_line("╔", "═", "╗"),
        empty,
        line1,
        empty,
        line2,
        empty,
        line3,
        empty,
        border_line("╚", "═", "╝"),
        "",
    ]
    return "\n".join(lines)

BANNER = _make_banner()

# API 基础 URL
RUNPOD_API_BASE   = "https://rest.runpod.io/v1"
PRIME_API_BASE    = "https://api.primeintellect.ai/api/v1"
VAST_API_BASE     = "https://console.vast.ai/api/v0"
CLORE_API_BASE    = "https://api.clore.ai/v1"

# 默认扫描间隔 (秒)
DEFAULT_INTERVAL  = 30
# 默认容器镜像
DEFAULT_IMAGE     = "pytorch/pytorch:2.12.1-cuda12.6-cudnn9-devel"
# 默认 Vast 模板 hash_id (官方示例模板)
DEFAULT_VAST_TEMPLATE_HASH = "4e17788f74f075dd9aab7d0d4427968f"
# 默认磁盘大小 (GB)
DEFAULT_DISK      = 50
# 默认 SSH 端口
DEFAULT_SSH_PORT  = "22/tcp"

# 创建无验证 SSL context (部分平台自签证书)
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


# ============================================================
# 工具函数
# ============================================================

def ts() -> str:
    """返回当前时间字符串"""
    return datetime.now().strftime("%H:%M:%S")


def log(msg: str, level: str = "INFO"):
    """带时间戳和颜色的日志"""
    t = f"{C.DIM}[{ts()}]{C.RESET}"
    if level == "ERROR":
        tag = f"{C.B_RED}[✘ ERROR]{C.RESET}"
    elif level == "WARN":
        tag = f"{C.YELLOW}[⚠ WARN ]{C.RESET}"
    elif level == "SUCCESS":
        tag = f"{C.B_GREEN}[✔ DONE ]{C.RESET}"
    elif level == "DRY":
        tag = f"{C.B_MAGENTA}[◈ DRY  ]{C.RESET}"
    else:
        tag = f"{C.B_BLUE}[● INFO ]{C.RESET}"
    print(f"{t} {tag} {msg}", flush=True)


def http_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict] = None,
    data: Optional[Any] = None,
    timeout: int = 30,
) -> Tuple[int, Dict]:
    """
    通用 HTTP 请求, 返回 (status_code, json_body)
    """
    headers = headers or {}
    if data is not None and isinstance(data, (dict, list)):
        data = json.dumps(data).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        try:
            return e.code, json.loads(body) if body else {}
        except json.JSONDecodeError:
            return e.code, {"_raw": body}
    except Exception as e:
        log(f"HTTP 请求失败: {url} → {e}", "ERROR")
        return 0, {"_error": str(e)}


def send_telegram(bot_token: str, chat_id: str, text: str):
    """发送 Telegram 通知"""
    if not bot_token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        http_request(url, "POST", data=payload, timeout=10)
    except Exception:
        pass


def format_price(price: float) -> str:
    """格式化价格显示"""
    if price < 0.01:
        return f"${price:.4f}"
    return f"${price:.2f}"


# ============================================================
# 配置管理
# ============================================================

class Config:
    """全局配置"""

    def __init__(self):
        # API Keys
        self.runpod_key: str = ""
        self.prime_key: str = ""
        self.vast_key: str = ""
        self.clore_key: str = ""

        # 价格区间 (美元/小时/每张卡) — 按平台分组
        # 结构: {"runpod": {"rtx 4090": (0.20, 0.50), "h100": (1.00, 2.50)}, "vast": {...}}
        # 最低价为 0 表示不设下限
        self.price_ranges: Dict[str, Dict[str, Tuple[float, float]]] = {}

        # 通用价格区间 (每平台的默认, 匹配所有未单独设置的 GPU)
        # 结构: {"runpod": (0.0, 0.50), "vast": (0.0, 0.30)}
        self.default_price_range: Dict[str, Tuple[float, float]] = {}

        # Telegram
        self.telegram_bot_token: str = ""
        self.telegram_chat_id: str = ""

        # 扫描设置
        self.interval: int = DEFAULT_INTERVAL
        self.gpu_count_min: int = 1
        self.gpu_count_max: int = 8

        # 容器设置
        self.docker_image: str = DEFAULT_IMAGE
        self.disk_size: int = DEFAULT_DISK
        self.ssh_password: str = ""
        self.vast_template: str = DEFAULT_VAST_TEMPLATE_HASH

        # 运行模式
        self.dry_run: bool = False
        self.platforms: List[str] = ["runpod", "primeintellect", "vast", "clore"]

        # 代理
        self.proxy: str = ""

        # 已预订记录 (避免重复)
        self.booked: set = set()
        self.booked_lock = threading.Lock()


def interactive_setup(cfg: Config):
    """交互式配置向导 (美化版)"""
    # 清屏
    os.system("clear" if os.name != "nt" else "cls")
    print(BANNER)
    print(f"  {C.B_WHITE}配置向导{C.RESET}  {C.DIM}— 按 Enter 跳过可选项{C.RESET}")
    print()

    # ════════ Step 1: 选择平台 & API Keys ════════
    print(ui_section("🔑", "Step 1/5 — 选择平台 & API Keys"))
    ui_hint("也可通过环境变量提前设置 (RUNPOD_API_KEY 等)")
    print()

    # 平台菜单
    platform_menu = [
        ("runpod",         "RunPod",          C.B_BLUE,   "https://console.runpod.io"),
        ("primeintellect", "PrimeIntellect",   C.B_GREEN,  "https://app.primeintellect.ai"),
        ("vast",           "Vast",             C.B_YELLOW, "https://console.vast.ai"),
        ("clore",          "Clore",            C.B_RED,    "https://clore.ai"),
    ]
    env_keys = {
        "runpod": "RUNPOD_API_KEY",
        "primeintellect": "PRIME_API_KEY",
        "vast": "VAST_API_KEY",
        "clore": "CLORE_API_KEY",
    }

    # 显示编号菜单
    for i, (pid, pname, pc, purl) in enumerate(platform_menu, 1):
        print(f"  {C.DIM}│{C.RESET}")
        print(f"  {C.DIM}│{C.RESET}  {C.B_WHITE}{i}.{C.RESET} {pc}{pname}{C.RESET}  {C.DIM}{purl}{C.RESET}")
    print(f"  {C.DIM}│{C.RESET}")
    print()

    # 选择平台
    while True:
        sel = input(f"  {C.DIM}│{C.RESET} {C.B_WHITE}选择平台{C.RESET} (输入编号, 逗号分隔, 如 1,2,3): ").strip()
        if not sel:
            ui_err("请至少选择一个平台!")
            continue

        try:
            chosen = [int(x.strip()) for x in sel.split(",") if x.strip()]
        except ValueError:
            ui_warn("输入无效, 请用数字和逗号 (如 1,2,3)")
            continue

        if not all(1 <= n <= len(platform_menu) for n in chosen):
            ui_warn(f"编号范围 1~{len(platform_menu)}, 请重新输入")
            continue

        break

    # 去重并排序
    chosen = sorted(set(chosen))
    print()

    # 逐个输入 API Key
    cfg.platforms = []
    platform_colors = {}
    for idx in chosen:
        pid, pname, pc, purl = platform_menu[idx - 1]
        platform_colors[pid] = pc

        # 先检查环境变量
        env_val = os.environ.get(env_keys[pid], "")
        if env_val:
            ui_ok(f"{pc}{pname}{C.RESET} {C.DIM}→ 已从环境变量 {env_keys[pid]} 读取{C.RESET}")
            key = env_val
        else:
            key = input(f"  {C.DIM}│{C.RESET} {pc}{pname}{C.RESET} API Key: ").strip()
            if not key:
                ui_warn(f"跳过 {pname} (未输入 Key)")
                continue
            ui_ok(f"{pname} {C.DIM}→ {key[:8]}...{C.RESET}")

        # 存入 config
        if pid == "runpod":
            cfg.runpod_key = key
        elif pid == "primeintellect":
            cfg.prime_key = key
        elif pid == "vast":
            cfg.vast_key = key
        elif pid == "clore":
            cfg.clore_key = key
        cfg.platforms.append(pid)

    if not cfg.platforms:
        print()
        ui_err("至少需要一个平台的 API Key!")
        sys.exit(1)

    colored_platforms = " ".join(f"{platform_colors[p]}● {p}{C.RESET}" for p in cfg.platforms)
    print(f"\n  {C.GREEN}✔ 已启用:{C.RESET} {colored_platforms}")

    # ════════ Step 2: 价格区间 (按平台) ════════
    print(ui_section("💰", "Step 2/5 — 价格区间 (美元/小时/每卡)"))
    ui_hint("为每个已选平台分别设置 GPU 价格区间")
    ui_hint("输入 GPU 型号 → 最低价 → 最高价, 空行结束该平台")
    ui_hint("常用: RTX 4090, RTX 5090, A100, H100, L40S, A10, RTX 3090 ...")
    ui_hint(f"输入 {C.B_WHITE}*{C.RESET}{C.DIM} 表示通用区间, 最低价填 0 表示不设下限{C.RESET}")
    print()

    # 平台显示名 & 颜色
    _pname_map = {
        "runpod": ("RunPod", C.B_BLUE),
        "primeintellect": ("PrimeIntellect", C.B_GREEN),
        "vast": ("Vast", C.B_YELLOW),
        "clore": ("Clore", C.B_RED),
    }

    any_price_set = False
    for plat in cfg.platforms:
        pname, pc = _pname_map.get(plat, (plat, C.WHITE))
        print(f"  {C.DIM}┌{C.RESET} {pc}{C.BOLD}{pname}{C.RESET} {C.DIM}的价格区间{C.RESET}")

        cfg.price_ranges[plat] = {}
        gpu_count_added = 0

        while True:
            gpu = ui_input(f"{pc}{pname}{C.RESET} — {C.B_WHITE}GPU 型号{C.RESET} (或 * 或空行跳过)")
            if not gpu:
                break

            p_min_str = ui_input(f"  {C.GREEN}最低价{C.RESET} ($/hr/卡, 0=不限)")
            p_max_str = ui_input(f"  {C.RED}最高价{C.RESET} ($/hr/卡)")
            try:
                p_min = float(p_min_str) if p_min_str else 0.0
                p_max = float(p_max_str)
            except ValueError:
                ui_warn("价格无效, 跳过")
                continue
            if p_max <= 0:
                ui_warn("最高价必须 > 0, 跳过")
                continue
            if p_min > p_max:
                p_min, p_max = p_max, p_min
                ui_warn(f"自动修正: 最低={p_min}, 最高={p_max}")

            lo = format_price(p_min) if p_min > 0 else "$0"
            hi = format_price(p_max)

            if gpu == "*":
                cfg.default_price_range[plat] = (p_min, p_max)
                ui_ok(f"{pname} 通用区间: {C.GREEN}{lo}{C.RESET} ~ {C.RED}{hi}{C.RESET}/hr/卡")
            else:
                cfg.price_ranges[plat][gpu.lower()] = (p_min, p_max)
                ui_ok(f"{pname} — {gpu}: {C.GREEN}{lo}{C.RESET} ~ {C.RED}{hi}{C.RESET}/hr/卡")
            gpu_count_added += 1
            any_price_set = True

        if gpu_count_added == 0:
            ui_warn(f"{pname} 未设置价格区间")
        else:
            ui_ok(f"{pname} 共设置 {gpu_count_added} 条价格区间")
        print(f"  {C.DIM}└{C.RESET}")
        print()

    if not any_price_set:
        print()
        ui_err("至少需要设置一个价格区间!")
        sys.exit(1)

    # ════════ Step 3: 容器设置 ════════
    print(ui_section("🐳", "Step 3/5 — 容器设置"))
    ui_hint("按 Enter 使用默认值")
    print()

    img = ui_input("Docker 镜像", DEFAULT_IMAGE)
    if img:
        cfg.docker_image = img

    # Vast 模板选择 (仅当选择了 Vast 时显示)
    if "vast" in cfg.platforms:
        print(f"\n  {C.DIM}│{C.RESET} {C.B_YELLOW}Vast 模板设置{C.RESET}")
        ui_hint("Vast 推荐使用 template_hash_id 创建实例 (更稳定)")
        ui_hint("可在 Vast 控制台模板页面复制 hash_id")
        ui_hint(f"默认模板 hash: {DEFAULT_VAST_TEMPLATE_HASH}")
        ui_hint("留空使用默认模板, 输入 0 不使用模板 (改用 Docker 镜像)")
        print()

        tpl_input = ui_input("Vast template_hash_id", DEFAULT_VAST_TEMPLATE_HASH)
        if tpl_input == "0":
            cfg.vast_template = ""
            ui_ok("将使用 Docker 镜像 (非模板)")
        elif tpl_input:
            cfg.vast_template = tpl_input
            ui_ok(f"Vast 模板: {C.B_YELLOW}{cfg.vast_template}{C.RESET}")
        else:
            cfg.vast_template = DEFAULT_VAST_TEMPLATE_HASH
            ui_ok(f"使用默认模板: {C.B_YELLOW}{DEFAULT_VAST_TEMPLATE_HASH}{C.RESET}")
        print()

    disk = ui_input("磁盘大小 (GB)", str(DEFAULT_DISK))
    if disk:
        try:
            cfg.disk_size = int(disk)
        except ValueError:
            pass

    pwd = ui_input("SSH 密码 (留空自动生成)")
    cfg.ssh_password = pwd or _gen_password()
    ui_ok(f"SSH 密码已设置 {C.DIM}({len(cfg.ssh_password)}位){C.RESET}")

    # ════════ Step 4: Telegram ════════
    print(ui_section("📡", "Step 4/5 — Telegram 通知 (可选)"))
    ui_hint("配置后, 预订成功时会推送通知")
    print()

    cfg.telegram_bot_token = ui_input("Bot Token") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    cfg.telegram_chat_id = ui_input("Chat ID") or os.environ.get("TELEGRAM_CHAT_ID", "")
    if cfg.telegram_bot_token and cfg.telegram_chat_id:
        ui_ok("Telegram 通知已配置")
    else:
        ui_hint("跳过 Telegram 通知")

    # ════════ Step 5: 扫描设置 ════════
    print(ui_section("🔍", "Step 5/5 — 扫描设置"))
    print()

    ival = ui_input("扫描间隔 (秒)", str(DEFAULT_INTERVAL))
    if ival:
        try:
            cfg.interval = max(5, int(ival))
        except ValueError:
            pass

    gmin = ui_input("最少 GPU 数量", "1")
    if gmin:
        try:
            cfg.gpu_count_min = max(1, int(gmin))
        except ValueError:
            pass

    gmax = ui_input("最多 GPU 数量", "8")
    if gmax:
        try:
            cfg.gpu_count_max = max(cfg.gpu_count_min, int(gmax))
        except ValueError:
            pass

    print()
    dr = ui_input(f"启用 {C.B_MAGENTA}Dry-Run{C.RESET} 模式? (只查询不下单) [y/N]")
    cfg.dry_run = dr.lower() in ("y", "yes")

    # ════════ 配置摘要 ════════
    print()
    ui_divider(58)
    print(f"  {C.B_WHITE}📋 配置摘要{C.RESET}")
    ui_divider(58)

    colored_platforms = " ".join(f"{platform_colors[p]}● {p}{C.RESET}" for p in cfg.platforms)
    print(f"  {C.DIM}│{C.RESET} {C.CYAN}平台{C.RESET}        {colored_platforms}")
    print(f"  {C.DIM}│{C.RESET} {C.CYAN}价格区间{C.RESET}")
    for plat in cfg.platforms:
        pname, pc = _pname_map.get(plat, (plat, C.WHITE))
        plat_ranges = cfg.price_ranges.get(plat, {})
        plat_default = cfg.default_price_range.get(plat)
        if plat_ranges or plat_default:
            print(f"  {C.DIM}│{C.RESET}   {pc}{pname}{C.RESET}:")
            for gpu, (pmin, pmax) in plat_ranges.items():
                lo = format_price(pmin) if pmin > 0 else "$0"
                print(f"  {C.DIM}│{C.RESET}     {C.WHITE}{gpu}{C.RESET}: {C.GREEN}{lo}{C.RESET} ~ {C.RED}{format_price(pmax)}{C.RESET}/hr/卡")
            if plat_default and plat_default[1] > 0:
                lo = format_price(plat_default[0]) if plat_default[0] > 0 else "$0"
                print(f"  {C.DIM}│{C.RESET}     {C.WHITE}* 通用{C.RESET}: {C.GREEN}{lo}{C.RESET} ~ {C.RED}{format_price(plat_default[1])}{C.RESET}/hr/卡")

    print(f"  {C.DIM}│{C.RESET} {C.CYAN}GPU 数量{C.RESET}    {C.WHITE}{cfg.gpu_count_min}x ~ {cfg.gpu_count_max}x{C.RESET}")
    img_short = cfg.docker_image.split("/")[-1] if "/" in cfg.docker_image else cfg.docker_image
    print(f"  {C.DIM}│{C.RESET} {C.CYAN}Docker{C.RESET}      {C.DIM}{img_short}{C.RESET}")
    print(f"  {C.DIM}│{C.RESET} {C.CYAN}磁盘{C.RESET}        {C.WHITE}{cfg.disk_size} GB{C.RESET}")
    print(f"  {C.DIM}│{C.RESET} {C.CYAN}扫描间隔{C.RESET}    {C.WHITE}{cfg.interval}s{C.RESET}")

    dry_label = f"{C.B_MAGENTA}是 (只查询){C.RESET}" if cfg.dry_run else f"{C.WHITE}否 (自动下单){C.RESET}"
    print(f"  {C.DIM}│{C.RESET} {C.CYAN}Dry-Run{C.RESET}     {dry_label}")

    tg_label = f"{C.GREEN}已配置{C.RESET}" if cfg.telegram_bot_token else f"{C.DIM}未配置{C.RESET}"
    print(f"  {C.DIM}│{C.RESET} {C.CYAN}Telegram{C.RESET}    {tg_label}")
    ui_divider(58)

    print()
    confirm = input(f"  {C.B_GREEN}▶ 确认启动?{C.RESET} [Y/n]: ").strip().lower()
    if confirm == "n":
        ui_warn("已取消")
        sys.exit(0)


def _gen_password(length: int = 16) -> str:
    import secrets
    import string
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


# ============================================================
# 价格匹配逻辑
# ============================================================

def match_price(cfg: Config, platform: str, gpu_name: str, price_per_gpu: float, gpu_count: int) -> bool:
    """
    判断该 offer 是否满足价格区间 (按平台查找)
    platform: 平台标识 (如 "runpod", "vast")
    gpu_name: GPU 型号名称 (如 "NVIDIA GeForce RTX 4090")
    price_per_gpu: 每卡每小时价格
    gpu_count: 卡数
    返回 True 当价格落在该平台的 [min_price, max_price] 区间内
    """
    if gpu_count < cfg.gpu_count_min or gpu_count > cfg.gpu_count_max:
        return False

    # 提取简短型号名用于匹配
    gpu_lower = gpu_name.lower()
    short_names = _extract_gpu_short_name(gpu_lower)

    # 先查该平台精确匹配
    plat_ranges = cfg.price_ranges.get(platform, {})
    price_range = None
    for sn in short_names:
        if sn in plat_ranges:
            price_range = plat_ranges[sn]
            break

    # 再查该平台的通用区间
    if price_range is None:
        dr = cfg.default_price_range.get(platform)
        if dr and dr[1] > 0:
            price_range = dr

    if price_range is None:
        return False

    p_min, p_max = price_range

    # 检查区间: 价格 >= 最低价 且 <= 最高价
    if p_min > 0 and price_per_gpu < p_min:
        return False
    if p_max > 0 and price_per_gpu > p_max:
        return False

    # 至少要有上限
    if p_max <= 0:
        return False

    return True


def _extract_gpu_short_name(gpu_lower: str) -> List[str]:
    """从完整 GPU 名称提取可能的短名"""
    names = [gpu_lower]
    # 去掉 "nvidia " 前缀
    if gpu_lower.startswith("nvidia "):
        names.append(gpu_lower[7:])
    # 去掉 "geforce " 前缀
    if "geforce " in gpu_lower:
        names.append(gpu_lower.replace("geforce ", ""))
    # 常见映射
    mappings = {
        "rtx 4090": ["rtx 4090", "4090"],
        "rtx 5090": ["rtx 5090", "5090"],
        "rtx 3090": ["rtx 3090", "3090"],
        "rtx a6000": ["rtx a6000", "a6000"],
        "rtx a5000": ["rtx a5000", "a5000"],
        "a100": ["a100"],
        "h100": ["h100"],
        "l40s": ["l40s"],
        "l40": ["l40"],
        "a10": ["a10"],
        "a40": ["a40"],
        "t4": ["t4"],
        "v100": ["v100"],
        "h200": ["h200"],
        "b200": ["b200"],
        "gb200": ["gb200"],
    }
    for key, vals in mappings.items():
        if key in gpu_lower:
            names.extend(vals)
    return list(set(names))


def is_booked(cfg: Config, platform: str, offer_id: str) -> bool:
    key = f"{platform}:{offer_id}"
    with cfg.booked_lock:
        return key in cfg.booked


def mark_booked(cfg: Config, platform: str, offer_id: str):
    key = f"{platform}:{offer_id}"
    with cfg.booked_lock:
        cfg.booked.add(key)


# ============================================================
# RunPod 扫描器
# ============================================================

def scan_runpod(cfg: Config, results: List, stop_event: threading.Event):
    """RunPod 平台扫描线程"""
    log("[RunPod] 扫描线程启动")
    headers = {
        "Authorization": f"Bearer {cfg.runpod_key}",
        "Content-Type": "application/json",
    }

    while not stop_event.is_set():
        try:
            _scan_runpod_once(cfg, headers, results)
        except Exception as e:
            log(f"[RunPod] 扫描异常: {e}", "ERROR")
        stop_event.wait(cfg.interval)

    log("[RunPod] 扫描线程结束")


def _scan_runpod_once(cfg: Config, headers: Dict, results: List):
    """RunPod 单次扫描"""
    # RunPod 没有直接的 "marketplace search" API
    # 我们通过创建 pod 请求来查看可用性和价格
    # 或者通过 GET /pods 查看当前 pod 信息
    # 实际上 RunPod 的 GPU 可用性和价格通过创建 pod 时的响应获取
    # 我们用一种 "询价" 方式: 尝试创建 pod 但不确认 (dry-run)

    # 方法: 用 GET /gpuTypes 或类似端点 (RunPod 内部 API)
    # 根据文档, RunPod 使用 POST /pods 创建, 价格从 machine 信息获取

    # 尝试获取 GPU 类型列表
    # RunPod 未公开 GPU 列表 API, 但我们可以尝试已知型号
    known_gpus = [
        "NVIDIA GeForce RTX 4090",
        "NVIDIA GeForce RTX 5090",
        "NVIDIA GeForce RTX 3090",
        "NVIDIA A100-SXM4-80GB",
        "NVIDIA A100-SXM4-40GB",
        "NVIDIA A100-PCIE-80GB",
        "NVIDIA H100",
        "NVIDIA H100 80GB HBM3",
        "NVIDIA H200",
        "NVIDIA L40S",
        "NVIDIA L40",
        "NVIDIA L4",
        "NVIDIA A10",
        "NVIDIA A40",
        "NVIDIA RTX A6000",
        "NVIDIA RTX A5000",
        "NVIDIA RTX A4000",
        "NVIDIA GeForce RTX 3080",
        "NVIDIA GeForce RTX 3070",
        "NVIDIA T4",
        "NVIDIA V100",
        "NVIDIA B200",
        "NVIDIA GB200",
    ]

    for gpu_type in known_gpus:
        for gpu_count in range(cfg.gpu_count_min, cfg.gpu_count_max + 1):
            # 构建 pod 查询/创建请求来获取价格
            pod_body = {
                "gpuTypeIds": [gpu_type],
                "gpuCount": gpu_count,
                "imageName": cfg.docker_image,
                "containerDiskInGb": cfg.disk_size,
                "volumeInGb": 0,
                "ports": DEFAULT_SSH_PORT,
                "cloudType": "SECURE",
                "computeType": "GPU",
                "supportPublicIp": True,
            }

            status, resp = http_request(
                f"{RUNPOD_API_BASE}/pods",
                "POST",
                headers=headers,
                data=pod_body,
                timeout=15,
            )

            if status in (200, 201) and resp.get("costPerHr"):
                total_price = resp.get("costPerHr", 0)
                price_per_gpu = total_price / gpu_count if gpu_count > 0 else total_price
                offer_id = resp.get("id", f"runpod-{gpu_type}-{gpu_count}")

                matched = match_price(cfg, "runpod", gpu_type, price_per_gpu, gpu_count)

                if matched:
                    offer = {
                        "platform": "RunPod",
                        "gpu_name": gpu_type,
                        "gpu_count": gpu_count,
                        "price_total": total_price,
                        "price_per_gpu": price_per_gpu,
                        "offer_id": offer_id,
                        "raw": resp,
                    }
                    results.append(offer)

                    log(
                        f"[RunPod] {gpu_type} x{gpu_count} = "
                        f"{format_price(total_price)}/hr ({format_price(price_per_gpu)}/卡) ✓"
                    )

                if matched and not cfg.dry_run and not is_booked(cfg, "runpod", offer_id):
                    # Pod 已经创建成功了 (POST 就是创建)
                    mark_booked(cfg, "runpod", offer_id)
                    _notify_booking(cfg, offer, resp)
                    log(f"[RunPod] 已预订: {gpu_type} x{gpu_count}", "SUCCESS")

                elif matched and cfg.dry_run:
                    # Dry-run: 删除刚创建的 pod
                    pod_id = resp.get("id")
                    if pod_id:
                        http_request(
                            f"{RUNPOD_API_BASE}/pods/{pod_id}",
                            "DELETE",
                            headers=headers,
                            timeout=10,
                        )
                    log(f"[RunPod] [Dry-Run] 匹配但已取消创建", "DRY")

            elif status == 400:
                # GPU 不可用或参数错误, 继续
                pass
            elif status == 401:
                log("[RunPod] API Key 无效!", "ERROR")
                return

            # 避免触发限流
            time.sleep(0.3)


# ============================================================
# PrimeIntellect 扫描器
# ============================================================

def scan_primeintellect(cfg: Config, results: List, stop_event: threading.Event):
    """PrimeIntellect 平台扫描线程"""
    log("[PrimeIntellect] 扫描线程启动")
    headers = {
        "Authorization": f"Bearer {cfg.prime_key}",
        "Content-Type": "application/json",
    }

    while not stop_event.is_set():
        try:
            _scan_prime_once(cfg, headers, results)
        except Exception as e:
            log(f"[PrimeIntellect] 扫描异常: {e}", "ERROR")
        stop_event.wait(cfg.interval)

    log("[PrimeIntellect] 扫描线程结束")


def _scan_prime_once(cfg: Config, headers: Dict, results: List):
    """PrimeIntellect 单次扫描"""
    # 1. 获取 GPU 可用性和价格摘要
    status, resp = http_request(
        f"{PRIME_API_BASE}/availability/gpu-summary",
        "GET",
        headers=headers,
        timeout=15,
    )

    if status == 401:
        log("[PrimeIntellect] API Key 无效!", "ERROR")
        return
    if status != 200:
        log(f"[PrimeIntellect] 查询失败: HTTP {status}", "WARN")
        return

    # 解析响应 — 格式可能是 {gpu_type: {onDemand, spot, ...}}
    gpu_data = {}
    if isinstance(resp, dict):
        # 尝试多种可能的响应结构
        if "gpus" in resp:
            gpu_data = resp["gpus"]
        elif "data" in resp:
            gpu_data = resp["data"]
        elif "items" in resp:
            gpu_data = resp["items"]
        else:
            # 直接是 GPU 数据
            gpu_data = resp

    for gpu_name, info in gpu_data.items():
        if not isinstance(info, dict):
            continue

        # 提取价格信息
        price_on_demand = info.get("onDemand", info.get("on_demand", info.get("price", 0)))
        price_spot = info.get("spotPrice", info.get("spot", info.get("spot_price", 0)))
        price_community = info.get("communityPrice", info.get("community", 0))

        # 取最低价
        prices = [p for p in [price_on_demand, price_spot, price_community] if isinstance(p, (int, float)) and p > 0]
        if not prices:
            continue

        best_price = min(prices)
        price_type = "spot" if best_price == price_spot else ("community" if best_price == price_community else "on-demand")

        # GPU 数量 (PrimeIntellect 通常是单卡或固定配置)
        available_count = info.get("availableCount", info.get("count", info.get("instances", 1)))
        if isinstance(available_count, (int, float)):
            available_count = int(available_count)
        else:
            available_count = 1

        for gpu_count in range(cfg.gpu_count_min, min(cfg.gpu_count_max, available_count) + 1):
            total_price = best_price * gpu_count
            offer_id = f"prime-{gpu_name}-{gpu_count}-{price_type}"

            matched = match_price(cfg, "primeintellect", gpu_name, best_price, gpu_count)

            if matched:
                offer = {
                    "platform": "PrimeIntellect",
                    "gpu_name": gpu_name,
                    "gpu_count": gpu_count,
                    "price_total": total_price,
                    "price_per_gpu": best_price,
                    "price_type": price_type,
                    "offer_id": offer_id,
                    "raw": info,
                }
                results.append(offer)

                log(
                    f"[PrimeIntellect] {gpu_name} x{gpu_count} = "
                    f"{format_price(total_price)}/hr ({format_price(best_price)}/卡, {price_type}) ✓"
                )

                if not is_booked(cfg, "primeintellect", offer_id):
                    if cfg.dry_run:
                        log(f"[PrimeIntellect] [Dry-Run] 匹配但不自动下单", "DRY")
                    else:
                        # 尝试创建实例
                        booked = _book_primeintellect(cfg, headers, gpu_name, gpu_count, info)
                        if booked:
                            mark_booked(cfg, "primeintellect", offer_id)
                            _notify_booking(cfg, offer, {})


def _book_primeintellect(cfg: Config, headers: Dict, gpu_name: str, gpu_count: int, gpu_info: Dict) -> bool:
    """尝试在 PrimeIntellect 预订实例"""
    # 尝试多个可能的创建端点
    create_endpoints = [
        f"{PRIME_API_BASE}/compute/instances",
        f"{PRIME_API_BASE}/instances",
        f"{PRIME_API_BASE}/compute/clusters",
    ]

    payload = {
        "gpuType": gpu_name,
        "gpu_type": gpu_name,
        "gpuCount": gpu_count,
        "gpu_count": gpu_count,
        "image": cfg.docker_image,
        "diskSize": cfg.disk_size,
    }

    for endpoint in create_endpoints:
        status, resp = http_request(endpoint, "POST", headers=headers, data=payload, timeout=15)
        if status in (200, 201):
            log(f"[PrimeIntellect] 预订成功: {gpu_name} x{gpu_count}", "SUCCESS")
            return True
        elif status == 404:
            continue  # 尝试下一个端点
        elif status == 400:
            log(f"[PrimeIntellect] 预订失败(参数错误): {resp}", "WARN")
            return False

    log(f"[PrimeIntellect] 无法找到有效的创建端点", "WARN")
    return False


# ============================================================
# Vast 扫描器
# ============================================================

def scan_vast(cfg: Config, results: List, stop_event: threading.Event):
    """Vast 平台扫描线程"""
    log("[Vast] 扫描线程启动")
    headers = {
        "Authorization": f"Bearer {cfg.vast_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    while not stop_event.is_set():
        try:
            _scan_vast_once(cfg, headers, results)
        except Exception as e:
            log(f"[Vast] 扫描异常: {e}", "ERROR")
        stop_event.wait(cfg.interval)

    log("[Vast] 扫描线程结束")


def _scan_vast_once(cfg: Config, headers: Dict, results: List):
    """Vast 单次扫描"""
    # Vast 搜索 API: POST /bundles/
    # 按已知 GPU 型号逐个查询, 合并结果
    vast_gpu_names = [
        "RTX 4090", "RTX 5090", "RTX 3090", "RTX 3080", "RTX 3070",
        "A100-SXM4-80GB", "A100-SXM4-40GB", "A100-PCIE-80GB", "A100",
        "H100", "H100 80GB HBM3", "H200",
        "L40S", "L40", "L4",
        "A10", "A40", "T4", "V100",
        "RTX A6000", "RTX A5000", "RTX A4000",
        "B200", "GB200",
    ]

    all_offers = []
    for gpu in vast_gpu_names:
        query = {
            "gpu_name": {"in": [gpu]},
            "rentable": {"eq": True},
        }

        status, resp = http_request(
            f"{VAST_API_BASE}/bundles/",
            "POST",
            headers=headers,
            data=query,
            timeout=20,
        )

        if status == 401:
            log("[Vast] API Key 无效!", "ERROR")
            return
        if status != 200:
            continue  # 该型号无结果, 跳过

        offers_raw = resp.get("offers", [])
        if isinstance(offers_raw, list):
            all_offers.extend(offers_raw)

        # 避免限流
        time.sleep(0.2)

    log(f"[Vast] 共获取到 {len(all_offers)} 条 offer")

    matched_count = 0
    for offer in all_offers:
        if not isinstance(offer, dict):
            continue

        gpu_name = offer.get("gpu_name", offer.get("gpu_display", "Unknown GPU"))
        gpu_count = offer.get("num_gpus", offer.get("gpu_count", 1))
        total_price = offer.get("dph_total", offer.get("hourly_price", 0))
        offer_id = str(offer.get("id", offer.get("machine_id", "")))

        if not offer_id or total_price <= 0:
            continue

        try:
            gpu_count = int(gpu_count)
            total_price = float(total_price)
        except (ValueError, TypeError):
            continue

        price_per_gpu = total_price / gpu_count if gpu_count > 0 else total_price

        matched = match_price(cfg, "vast", gpu_name, price_per_gpu, gpu_count)
        if matched:
            matched_count += 1
            result = {
                "platform": "Vast",
                "gpu_name": gpu_name,
                "gpu_count": gpu_count,
                "price_total": total_price,
                "price_per_gpu": price_per_gpu,
                "offer_id": offer_id,
                "raw": offer,
            }
            results.append(result)

            log(
                f"[Vast] {gpu_name} x{gpu_count} = "
                f"{format_price(total_price)}/hr ({format_price(price_per_gpu)}/卡) ✓"
            )

            if not is_booked(cfg, "vast", offer_id):
                if cfg.dry_run:
                    log(f"[Vast] [Dry-Run] 匹配但不自动下单", "DRY")
                else:
                    booked = _book_vast(cfg, headers, offer_id, offer)
                    if booked:
                        mark_booked(cfg, "vast", offer_id)
                        _notify_booking(cfg, result, offer)

    if matched_count == 0:
        log(f"[Vast] {len(all_offers)} 条 offer 均不在价格区间内")


def _book_vast(cfg: Config, headers: Dict, offer_id: str, offer: Dict) -> bool:
    """在 Vast 上租用机器"""
    # PUT /asks/{id}/ 预订
    payload = {
        "disk": cfg.disk_size,
        "env": {},
        "label": f"gpu-hunter-pro-{offer_id}",
        "onstart": "",
    }

    # 优先使用 Vast 模板, 否则用 Docker 镜像
    if cfg.vast_template:
        payload["template_hash_id"] = cfg.vast_template
        log(f"[Vast] 使用模板: {cfg.vast_template}")
    else:
        payload["image"] = cfg.docker_image
        log(f"[Vast] 使用镜像: {cfg.docker_image}")

    # 添加 SSH 密码
    if cfg.ssh_password:
        payload["env"]["JUPYTER_PWD"] = cfg.ssh_password

    status, resp = http_request(
        f"{VAST_API_BASE}/asks/{offer_id}/",
        "PUT",
        headers=headers,
        data=payload,
        timeout=15,
    )

    if status in (200, 201):
        log(f"[Vast] 预订成功: offer {offer_id}", "SUCCESS")
        return True
    else:
        log(f"[Vast] 预订失败: HTTP {status} — {resp}", "WARN")
        return False


# ============================================================
# Clore 扫描器
# ============================================================

def scan_clore(cfg: Config, results: List, stop_event: threading.Event):
    """Clore 平台扫描线程"""
    log("[Clore] 扫描线程启动")

    while not stop_event.is_set():
        try:
            _scan_clore_once(cfg, results)
        except Exception as e:
            log(f"[Clore] 扫描异常: {e}", "ERROR")
        stop_event.wait(cfg.interval)

    log("[Clore] 扫描线程结束")


def _scan_clore_once(cfg: Config, results: List):
    """Clore 单次扫描"""
    headers = {
        "Authorization": f"Bearer {cfg.clore_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # 获取可用服务器列表
    status, resp = http_request(
        f"{CLORE_API_BASE}/marketplace/servers",
        "GET",
        headers=headers,
        timeout=20,
    )

    if status == 401:
        log("[Clore] API Key 无效!", "ERROR")
        return
    if status != 200:
        log(f"[Clore] 查询失败: HTTP {status}", "WARN")
        return

    servers = resp.get("servers", resp.get("data", []))
    if not isinstance(servers, list):
        # 尝试其他结构
        servers = resp.get("items", [])
    if not isinstance(servers, list):
        servers = [resp] if isinstance(resp, dict) and "gpu" in resp else []

    log(f"[Clore] 获取到 {len(servers)} 台服务器")

    for server in servers:
        if not isinstance(server, dict):
            continue

        # 解析 GPU 信息
        gpu_info = server.get("gpu", server.get("gpu_info", {}))
        if isinstance(gpu_info, dict):
            gpu_name = gpu_info.get("name", gpu_info.get("model", "Unknown GPU"))
            gpu_count = gpu_info.get("count", gpu_info.get("num", 1))
        elif isinstance(gpu_info, str):
            gpu_name = gpu_info
            gpu_count = server.get("gpu_count", server.get("num_gpus", 1))
        else:
            gpu_name = "Unknown GPU"
            gpu_count = 1

        # 解析价格
        pricing = server.get("pricing", server.get("price", {}))
        if isinstance(pricing, dict):
            total_price = pricing.get("hourly", pricing.get("per_hour", pricing.get("dph_total", 0)))
        elif isinstance(pricing, (int, float)):
            total_price = pricing
        else:
            total_price = 0

        server_id = str(server.get("id", server.get("server_id", "")))
        if not server_id or total_price <= 0:
            continue

        try:
            gpu_count = int(gpu_count)
            total_price = float(total_price)
        except (ValueError, TypeError):
            continue

        price_per_gpu = total_price / gpu_count if gpu_count > 0 else total_price
        is_rented = server.get("rented", server.get("is_rented", False))

        if is_rented:
            continue

        matched = match_price(cfg, "clore", gpu_name, price_per_gpu, gpu_count)
        if matched:
            result = {
                "platform": "Clore",
                "gpu_name": gpu_name,
                "gpu_count": gpu_count,
                "price_total": total_price,
                "price_per_gpu": price_per_gpu,
                "offer_id": server_id,
                "raw": server,
            }
            results.append(result)

            log(
                f"[Clore] {gpu_name} x{gpu_count} = "
                f"{format_price(total_price)}/hr ({format_price(price_per_gpu)}/卡) ✓"
            )

            if not is_booked(cfg, "clore", server_id):
                if cfg.dry_run:
                    log(f"[Clore] [Dry-Run] 匹配但不自动下单", "DRY")
                else:
                    booked = _book_clore(cfg, headers, server_id, server)
                    if booked:
                        mark_booked(cfg, "clore", server_id)
                        _notify_booking(cfg, result, server)


def _book_clore(cfg: Config, headers: Dict, server_id: str, server: Dict) -> bool:
    """在 Clore 上租用服务器"""
    payload = {
        "renting_server": server_id,
        "image": cfg.docker_image,
        "currency": "USD",
        "ports": ["22/tcp"],
    }

    status, resp = http_request(
        f"{CLORE_API_BASE}/create_order",
        "POST",
        headers=headers,
        data=payload,
        timeout=15,
    )

    if status in (200, 201):
        code = resp.get("code", resp.get("status", ""))
        if code in ("ok", "success", 200, 201) or "success" in str(resp).lower():
            log(f"[Clore] 预订成功: server {server_id}", "SUCCESS")
            return True

    log(f"[Clore] 预订失败: HTTP {status} — {resp}", "WARN")
    return False


# ============================================================
# 通知
# ============================================================

def _notify_booking(cfg: Config, offer: Dict, raw_resp: Dict):
    """发送预订成功通知"""
    platform = offer["platform"]
    gpu_name = offer["gpu_name"]
    gpu_count = offer["gpu_count"]
    total = offer["price_total"]
    per_gpu = offer["price_per_gpu"]

    text = (
        f"<b>🎉 GPU 预订成功!</b>\n\n"
        f"<b>平台:</b> {platform}\n"
        f"<b>GPU:</b> {gpu_name} x{gpu_count}\n"
        f"<b>总价:</b> {format_price(total)}/hr\n"
        f"<b>单价:</b> {format_price(per_gpu)}/hr/卡\n"
    )

    # 提取连接信息
    if raw_resp:
        ip = raw_resp.get("publicIp", raw_resp.get("public_ip", raw_resp.get("ip", "")))
        ssh_port = ""
        port_mappings = raw_resp.get("portMappings", raw_resp.get("port_mappings", {}))
        if isinstance(port_mappings, dict):
            ssh_port = port_mappings.get("22", port_mappings.get("22/tcp", ""))

        if ip and ssh_port:
            text += f"\n<b>SSH:</b> ssh root@{ip} -p {ssh_port}"
        elif ip:
            text += f"\n<b>IP:</b> {ip}"

        password = raw_resp.get("password", cfg.ssh_password)
        if password:
            text += f"\n<b>密码:</b> <code>{password}</code>"

    text += f"\n\n<i>GPU-Hunter-Pro v{VERSION}</i>"

    log(f"发送 Telegram 通知: {platform} {gpu_name} x{gpu_count}")
    send_telegram(cfg.telegram_bot_token, cfg.telegram_chat_id, text)


# ============================================================
# 主循环 — 结果展示
# ============================================================

def display_results(cfg: Config, results: List):
    """终端展示扫描结果 (彩色表格, 正确对齐)"""
    results_sorted = sorted(results, key=lambda x: x.get("price_per_gpu", 999))

    # 平台颜色映射
    pcolors = {
        "RunPod": C.B_BLUE,
        "PrimeIntellect": C.B_GREEN,
        "Vast": C.B_YELLOW,
        "Clore": C.B_RED,
    }
    # 平台显示名 → 内部 ID
    _plat_id = {
        "RunPod": "runpod",
        "PrimeIntellect": "primeintellect",
        "Vast": "vast",
        "Clore": "clore",
    }

    # 列宽定义 (显示宽度)
    COL_P = 16   # 平台
    COL_G = 28   # GPU 型号
    COL_N = 5    # 数量
    COL_U = 10   # 单价
    COL_T = 10   # 总价
    COL_S = 8    # 状态
    TOTAL_W = COL_P + COL_G + COL_N + COL_U + COL_T + COL_S + 7  # 7 = 空格和边框

    if not results_sorted:
        sp = next_spinner()
        print(f"\n  {C.DIM}{sp} 扫描中, 等待结果...{C.RESET}\n")
        return

    matched_count = sum(1 for r in results_sorted if match_price(cfg, _plat_id.get(r["platform"], ""), r["gpu_name"], r["price_per_gpu"], r["gpu_count"]))

    bdr = C.DIM
    r = C.RESET

    # 表头
    print()
    print(f"  {bdr}╭{'─' * TOTAL_W}╮{r}")
    hdr = f"  {bdr}│{r} "
    hdr += pad_right(f"{C.B_WHITE}平台{r}", COL_P) + " "
    hdr += pad_right(f"{C.B_WHITE}GPU 型号{r}", COL_G) + " "
    hdr += pad_left(f"{C.B_WHITE}数量{r}", COL_N) + " "
    hdr += pad_left(f"{C.B_WHITE}单价/hr{r}", COL_U) + " "
    hdr += pad_left(f"{C.B_WHITE}总价/hr{r}", COL_T) + " "
    hdr += pad_right(f"{C.B_WHITE}状态{r}", COL_S)
    hdr += f" {bdr}│{r}"
    print(hdr)
    print(f"  {bdr}├{'─' * TOTAL_W}┤{r}")

    shown = 0
    for item in results_sorted[:50]:
        platform = item["platform"]
        gpu_name = item["gpu_name"]
        gpu_count = item["gpu_count"]
        price_total = item["price_total"]
        price_per_gpu = item["price_per_gpu"]

        # 截断 GPU 名称 (按显示宽度)
        if display_width(gpu_name) > COL_G - 2:
            while display_width(gpu_name) > COL_G - 4:
                gpu_name = gpu_name[:-1]
            gpu_name += ".."

        matched = match_price(cfg, _plat_id.get(platform, ""), item["gpu_name"], price_per_gpu, gpu_count)
        pc = pcolors.get(platform, C.WHITE)

        if matched:
            status_str = f"{C.B_GREEN}✔ 匹配{r}"
            dim = ""
        else:
            status_str = f"{C.DIM}  --{r}"
            dim = C.DIM

        # 构建行: 用 pad_right/pad_left 按显示宽度填充
        row = f"  {bdr}│{r} "
        row += pad_right(f"{pc}{platform}{r}", COL_P) + " "
        row += pad_right(f"{dim}{gpu_name}{r}", COL_G) + " "
        row += pad_left(f"{dim}{gpu_count}x{r}", COL_N) + " "
        row += pad_left(f"{dim}{format_price(price_per_gpu)}{r}", COL_U) + " "
        row += pad_left(f"{dim}{format_price(price_total)}{r}", COL_T) + " "
        row += pad_right(status_str, COL_S)
        row += f" {bdr}│{r}"
        print(row)
        shown += 1

    print(f"  {bdr}╰{'─' * TOTAL_W}╯{r}")

    # 统计行
    booked_count = len(cfg.booked)
    stats = f"  {bdr}│{r} 共 {C.B_WHITE}{len(results_sorted)}{r} 条"
    stats += f" · 匹配 {C.B_GREEN}{matched_count}{r}"
    if booked_count:
        stats += f" · 已预订 {C.B_CYAN}{booked_count}{r} 台"
    stats += f" {bdr}│{r}"
    print(stats)
    print()


# ============================================================
# 命令行参数解析
# ============================================================

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="GPU-Hunter-Pro: 多平台 GPU 自动扫描与租用",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            示例:
              # 交互模式 (推荐, 逐步填写价格区间)
              python3 gpu_hunter_pro.py

              # 非交互模式 (设置价格区间)
              python3 gpu_hunter_pro.py --no-prompt \\
                --runpod-key "KEY" --vast-key "KEY" \\
                --price-4090 0.50 --price-4090-min 0.15 \\
                --price-5090 0.80 --price-5090-min 0.25

              # Dry-Run 测试
              python3 gpu_hunter_pro.py --dry-run --once \\
                --runpod-key "KEY" --price-4090 0.50

            环境变量:
              RUNPOD_API_KEY       RunPod API Key
              PRIME_API_KEY        PrimeIntellect API Key
              VAST_API_KEY         Vast API Key
              CLORE_API_KEY        Clore API Key
              TELEGRAM_BOT_TOKEN   Telegram Bot Token
              TELEGRAM_CHAT_ID     Telegram Chat ID
        """),
    )

    # 运行模式
    p.add_argument("--no-prompt", action="store_true", help="非交互模式, 从参数/环境变量读取配置")
    p.add_argument("--dry-run", action="store_true", help="只查询不下单")
    p.add_argument("--once", action="store_true", help="只扫描一轮后退出")

    # API Keys
    p.add_argument("--runpod-key", default="", help="RunPod API Key")
    p.add_argument("--prime-key", default="", help="PrimeIntellect API Key")
    p.add_argument("--vast-key", default="", help="Vast API Key")
    p.add_argument("--clore-key", default="", help="Clore API Key")

    # 价格区间 (便捷参数 — 每个 GPU 支持 min/max)
    p.add_argument("--price-4090", type=float, default=0, help="RTX 4090 最高价格 ($/hr/卡)")
    p.add_argument("--price-4090-min", type=float, default=0, help="RTX 4090 最低价格 ($/hr/卡, 默认0=不限)")
    p.add_argument("--price-5090", type=float, default=0, help="RTX 5090 最高价格 ($/hr/卡)")
    p.add_argument("--price-5090-min", type=float, default=0, help="RTX 5090 最低价格 ($/hr/卡)")
    p.add_argument("--price-3090", type=float, default=0, help="RTX 3090 最高价格 ($/hr/卡)")
    p.add_argument("--price-3090-min", type=float, default=0, help="RTX 3090 最低价格 ($/hr/卡)")
    p.add_argument("--price-a100", type=float, default=0, help="A100 最高价格 ($/hr/卡)")
    p.add_argument("--price-a100-min", type=float, default=0, help="A100 最低价格 ($/hr/卡)")
    p.add_argument("--price-h100", type=float, default=0, help="H100 最高价格 ($/hr/卡)")
    p.add_argument("--price-h100-min", type=float, default=0, help="H100 最低价格 ($/hr/卡)")
    p.add_argument("--price-l40s", type=float, default=0, help="L40S 最高价格 ($/hr/卡)")
    p.add_argument("--price-l40s-min", type=float, default=0, help="L40S 最低价格 ($/hr/卡)")
    p.add_argument("--price-default", type=float, default=0, help="通用最高价格 (匹配所有未单独设置的 GPU)")
    p.add_argument("--price-default-min", type=float, default=0, help="通用最低价格")

    # 扫描设置
    p.add_argument("--interval", type=int, default=DEFAULT_INTERVAL, help=f"扫描间隔秒数 (默认 {DEFAULT_INTERVAL})")
    p.add_argument("--gpu-min", type=int, default=1, help="最少 GPU 数量")
    p.add_argument("--gpu-max", type=int, default=8, help="最多 GPU 数量")

    # 容器设置
    p.add_argument("--image", default=DEFAULT_IMAGE, help=f"Docker 镜像 (默认 {DEFAULT_IMAGE})")
    p.add_argument("--disk", type=int, default=DEFAULT_DISK, help=f"磁盘大小 GB (默认 {DEFAULT_DISK})")
    p.add_argument("--ssh-password", default="", help="SSH 密码 (留空自动生成)")

    # Telegram
    p.add_argument("--telegram-bot-token", default="", help="Telegram Bot Token")
    p.add_argument("--telegram-chat-id", default="", help="Telegram Chat ID")

    # 平台控制
    p.add_argument("--only", default="", help="只扫描指定平台 (逗号分隔: runpod,vast)")

    return p


def config_from_args(args) -> Config:
    """从命令行参数构建配置"""
    cfg = Config()

    # API Keys (参数优先, 环境变量兜底)
    cfg.runpod_key = args.runpod_key or os.environ.get("RUNPOD_API_KEY", "")
    cfg.prime_key = args.prime_key or os.environ.get("PRIME_API_KEY", "")
    cfg.vast_key = args.vast_key or os.environ.get("VAST_API_KEY", "")
    cfg.clore_key = args.clore_key or os.environ.get("CLORE_API_KEY", "")

    # 平台过滤 (先确定平台, 再分配价格)
    if args.only:
        cfg.platforms = [p.strip().lower() for p in args.only.split(",")]
    else:
        cfg.platforms = []
        if cfg.runpod_key:
            cfg.platforms.append("runpod")
        if cfg.prime_key:
            cfg.platforms.append("primeintellect")
        if cfg.vast_key:
            cfg.platforms.append("vast")
        if cfg.clore_key:
            cfg.platforms.append("clore")

    # 价格区间 (从命令行参数构建 — CLI 模式价格应用到所有已选平台)
    _price_map = {
        "rtx 4090": (args.price_4090_min, args.price_4090),
        "4090":     (args.price_4090_min, args.price_4090),
        "rtx 5090": (args.price_5090_min, args.price_5090),
        "5090":     (args.price_5090_min, args.price_5090),
        "rtx 3090": (args.price_3090_min, args.price_3090),
        "3090":     (args.price_3090_min, args.price_3090),
        "a100":     (args.price_a100_min, args.price_a100),
        "h100":     (args.price_h100_min, args.price_h100),
        "l40s":     (args.price_l40s_min, args.price_l40s),
    }
    for plat in cfg.platforms:
        cfg.price_ranges[plat] = {}
        for gpu_key, (pmin, pmax) in _price_map.items():
            if pmax > 0:
                cfg.price_ranges[plat][gpu_key] = (pmin, pmax)

        if args.price_default > 0:
            cfg.default_price_range[plat] = (args.price_default_min, args.price_default)

    # 扫描设置
    cfg.interval = args.interval
    cfg.gpu_count_min = args.gpu_min
    cfg.gpu_count_max = args.gpu_max
    cfg.docker_image = args.image
    cfg.disk_size = args.disk
    cfg.ssh_password = args.ssh_password or _gen_password()
    cfg.dry_run = args.dry_run

    # Telegram
    cfg.telegram_bot_token = args.telegram_bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    cfg.telegram_chat_id = args.telegram_chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")

    return cfg


# ============================================================
# 主入口
# ============================================================

def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.no_prompt:
        cfg = config_from_args(args)
        if not cfg.platforms:
            print("[ERROR] 至少需要一个平台的 API Key!")
            parser.print_help()
            sys.exit(1)
        # 检查是否有任何价格区间
        has_prices = any(cfg.price_ranges.get(p) for p in cfg.platforms) or any(cfg.default_price_range.get(p) for p in cfg.platforms)
        if not has_prices:
            print("[ERROR] 至少需要设置一个价格区间!")
            parser.print_help()
            sys.exit(1)
    else:
        cfg = Config()
        interactive_setup(cfg)

    print(BANNER)
    # 平台名称映射
    _pn = {"runpod": "RunPod", "primeintellect": "PrimeIntellect", "vast": "Vast", "clore": "Clore"}
    # 彩色平台列表
    _pc = {"runpod": C.B_BLUE, "primeintellect": C.B_GREEN, "vast": C.B_YELLOW, "clore": C.B_RED}
    colored = " ".join(f"{_pc.get(p, C.WHITE)}● {p}{C.RESET}" for p in cfg.platforms)
    log(f"已启用: {colored}")

    # 显示价格区间 (按平台)
    for plat in cfg.platforms:
        pname = _pn.get(plat, plat)
        pc = _pc.get(plat, C.WHITE)
        plat_ranges = cfg.price_ranges.get(plat, {})
        plat_default = cfg.default_price_range.get(plat)
        parts = []
        for gpu, (pmin, pmax) in plat_ranges.items():
            lo = format_price(pmin) if pmin > 0 else "$0"
            parts.append(f"{C.WHITE}{gpu}{C.RESET} {C.GREEN}{lo}{C.RESET}~{C.RED}{format_price(pmax)}{C.RESET}")
        if plat_default and plat_default[1] > 0:
            lo = format_price(plat_default[0]) if plat_default[0] > 0 else "$0"
            parts.append(f"{C.WHITE}*通用{C.RESET} {C.GREEN}{lo}{C.RESET}~{C.RED}{format_price(plat_default[1])}{C.RESET}")
        if parts:
            log(f"{pc}{pname}{C.RESET} 价格: {' | '.join(parts)}")
    log(f"扫描间隔: {C.WHITE}{cfg.interval}s{C.RESET} | GPU: {C.WHITE}{cfg.gpu_count_min}x~{cfg.gpu_count_max}x{C.RESET}")
    if cfg.dry_run:
        log("Dry-Run 模式: 只查询不下单", "DRY")

    # 发送启动通知
    if cfg.telegram_bot_token and cfg.telegram_chat_id:
        send_telegram(
            cfg.telegram_bot_token,
            cfg.telegram_chat_id,
            f"<b>🚀 GPU-Hunter-Pro 启动</b>\n"
            f"平台: {', '.join(cfg.platforms)}\n"
            f"模式: {'Dry-Run' if cfg.dry_run else '自动下单'}\n"
            f"间隔: {cfg.interval}s",
        )

    # 结果收集列表
    results: List[Dict] = []
    results_lock = threading.Lock()

    # 停止事件
    stop_event = threading.Event()

    # 启动扫描线程
    threads: List[threading.Thread] = []
    scanner_map = {
        "runpod": scan_runpod,
        "primeintellect": scan_primeintellect,
        "vast": scan_vast,
        "clore": scan_clore,
    }

    for platform in cfg.platforms:
        scanner = scanner_map.get(platform)
        if scanner:
            t = threading.Thread(
                target=scanner,
                args=(cfg, results, stop_event),
                daemon=True,
                name=f"scanner-{platform}",
            )
            t.start()
            threads.append(t)
            log(f"已启动 {platform} 扫描线程")

    if not threads:
        log("没有可用的扫描线程, 退出", "ERROR")
        sys.exit(1)

    # 主循环 — 展示结果
    try:
        round_count = 0
        while not stop_event.is_set():
            time.sleep(cfg.interval)

            # 展示当前轮次结果
            with results_lock:
                display_results(cfg, list(results))

            round_count += 1

            # --once 模式
            if args.once:
                log("单轮模式, 扫描完成, 退出")
                break

    except KeyboardInterrupt:
        log("\n收到中断信号, 正在停止...")
    finally:
        stop_event.set()
        for t in threads:
            t.join(timeout=5)
        log("所有扫描线程已停止")

        # 最终摘要
        if cfg.booked:
            log(f"本次共预订 {len(cfg.booked)} 台机器", "SUCCESS")

        log("GPU-Hunter-Pro 已退出")


if __name__ == "__main__":
    main()
