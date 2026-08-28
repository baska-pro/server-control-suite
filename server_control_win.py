#!/usr/bin/env python3
from __future__ import annotations
"""
╔══════════════════════════════════════════════════════════════════╗
║      WINDOWS CONTROL — Remote Management Suite v5.0            ║
║  Telegram Bot + Web Dashboard | Single File | Python 3.10+      ║
╠══════════════════════════════════════════════════════════════════╣
║  Jalankan sekali: python server_control_win.py                       ║
║  Setup tersimpan dan startup otomatis melalui Task Scheduler.   ║
║  Proses background berjalan tanpa CMD/terminal.                  ║
╠══════════════════════════════════════════════════════════════════╣
║  Windows v5.0:                                                   ║
║    • Live Chart.js dashboard (no meta-refresh)                   ║
║    • Network monitor (interfaces, ports, connections)            ║
║    • Windows Services manager (start/stop/restart)               ║
║    • Event Viewer (System, Application, Security, Defender)      ║
║    • File editor (Ctrl+S, Tab indent, syntax-aware)              ║
║    • Alert system (CPU/RAM/Disk threshold → Telegram notify)     ║
║    • History ring-buffer (5-min chart: CPU / RAM / Net)          ║
║    • Web terminal: persistent CWD + command history              ║
║    • 20 terminal shortcuts                                       ║
║    • Sortable / filterable process tables                        ║
║    • Proper Restart (distinct from Run) everywhere               ║
╠══════════════════════════════════════════════════════════════════╣
║  Windows Defender Firewall dan shortcut dibuat otomatis.        ║
╚══════════════════════════════════════════════════════════════════╝
"""

# ─────────────────────────────────────────────────────────────────
# 0. AUTO-INSTALL DEPENDENCIES
# ─────────────────────────────────────────────────────────────────
import sys, subprocess, importlib

REQUIRED = {
    "telegram": "python-telegram-bot[job-queue]>=21,<23",
    "psutil":   "psutil>=5.9",
    "flask":    "flask>=3,<4",
    "humanize": "humanize>=4",
    "requests": "requests>=2.31",
    "waitress": "waitress>=3,<4",
    "send2trash": "Send2Trash>=1.8",
}

def _install(pkg_import: str, pkg_pip: str):
    try:
        importlib.import_module(pkg_import)
    except ImportError:
        if sys.stdout:
            print(f"[AUTO-INSTALL] Installing {pkg_pip} ...")
        cmd = [sys.executable, "-m", "pip", "install",
               "--disable-pip-version-check", "--quiet", "--upgrade", pkg_pip]
        try:
            subprocess.check_call(cmd, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError:
            try:
                subprocess.check_call([sys.executable, "-m", "ensurepip", "--upgrade"],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
                subprocess.check_call(cmd, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError:
                subprocess.check_call(cmd + ["--user"], stdout=subprocess.DEVNULL,
                                      stderr=subprocess.STDOUT)
        if sys.stdout:
            print(f"[AUTO-INSTALL] {pkg_pip} ✓")

for _imp, _pip in REQUIRED.items():
    _install(_imp, _pip)

# ─────────────────────────────────────────────────────────────────
# 1. IMPORTS
# ─────────────────────────────────────────────────────────────────
import os, re, time, json, html, shutil, hashlib, logging, datetime
import platform, threading, socket, traceback, asyncio, secrets, tempfile
import ctypes, getpass, shlex, signal, uuid, webbrowser, base64
from pathlib   import Path
from functools import wraps
from collections import deque
from urllib.parse import urlparse, quote as urlquote
from logging.handlers import RotatingFileHandler

import psutil, humanize, requests
from waitress import serve as waitress_serve
from send2trash import send2trash

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputFile, BotCommand,
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)
from telegram.constants import ParseMode

from flask import (
    Flask, request, redirect, session,
    jsonify, send_file, abort,
)

# ─────────────────────────────────────────────────────────────────
# 2. CONFIGURATION
# ─────────────────────────────────────────────────────────────────
IS_WINDOWS = os.name == "nt"
VERSION = "5.0.0"
APP_NAME = "Windows Control Suite"
TASK_NAME = "Windows Control Suite"
APP_BASE = Path(os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or Path.home())
APP_DIR = APP_BASE / "WindowsControlSuite"
APP_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = APP_DIR / "config.json"
TASKS_FILE = APP_DIR / "managed_tasks.json"
INSTALLED_SCRIPT = APP_DIR / "server_control.py"
LOG_FILE = APP_DIR / "server_control.log"
NOHUP_LOG_DIR = APP_DIR / "script_logs"
NOHUP_LOG_DIR.mkdir(parents=True, exist_ok=True)

def _read_json(path: Path, default):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, type(default)) else default
    except Exception:
        return default

def _write_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    if IS_WINDOWS:
        try:
            subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r",
                            f"{getpass.getuser()}:(R,W)"], capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception:
            pass

CONFIG = _read_json(CONFIG_FILE, {})

def _cfg(name: str, env_name: str, default):
    raw = os.getenv(env_name)
    return raw if raw not in (None, "") else CONFIG.get(name, default)

TOKEN = str(_cfg("telegram_token", "TOKEN_SERVER_CONTROL", "")).strip()
try:
    OWNER_ID = int(_cfg("admin_id", "ADMIN_ID", 0) or 0)
except (TypeError, ValueError):
    OWNER_ID = 0
try:
    WEB_PORT = int(_cfg("web_port", "DASH_PORT", 8080) or 8080)
except (TypeError, ValueError):
    WEB_PORT = 8080
WEB_HOST = str(_cfg("web_host", "DASH_HOST", "0.0.0.0"))
SECRET_KEY = str(_cfg("secret_key", "DASH_SECRET", "") or secrets.token_hex(32))
DASH_TOKEN = str(_cfg("dash_token", "DASH_TOKEN", "") or secrets.token_urlsafe(12))
CURRENT_USER = os.getenv("USERNAME") or getpass.getuser()
CURRENT_UID = -1

_script_roots = [Path(__file__).resolve().parent, Path.home()]
for _folder in ("Desktop", "Documents", "Downloads"):
    _candidate = Path.home() / _folder
    if _candidate.exists():
        _script_roots.append(_candidate)
SCRIPT_SEARCH_PATHS = list(dict.fromkeys(_script_roots))
SYSTEM_PREFIXES = [
    str(Path(os.environ.get("WINDIR", r"C:\Windows"))).lower(),
    str(Path(os.environ.get("ProgramFiles", r"C:\Program Files"))).lower(),
    str(Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))).lower(),
]
for _tool_dir in (
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Docker" / "Docker" / "resources" / "bin",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "cmd",
):
    if _tool_dir.exists() and str(_tool_dir).lower() not in os.environ.get("PATH", "").lower():
        os.environ["PATH"] = str(_tool_dir) + os.pathsep + os.environ.get("PATH", "")

# Alert thresholds (env-configurable)
ALERT_CPU_THRESH = int(_cfg("alert_cpu", "ALERT_CPU", 90))
ALERT_RAM_THRESH = int(_cfg("alert_ram", "ALERT_RAM", 90))
ALERT_DISK_THRESH = int(_cfg("alert_disk", "ALERT_DISK", 95))
ALERT_COOLDOWN = int(_cfg("alert_cooldown", "ALERT_CD", 600))
ALERTS_ENABLED    = True
ALERT_LAST: dict  = {"cpu": 0.0, "ram": 0.0, "disk": 0.0}

def save_runtime_config() -> None:
    CONFIG.update({
        "telegram_token": TOKEN, "admin_id": OWNER_ID,
        "web_port": WEB_PORT, "web_host": WEB_HOST,
        "secret_key": SECRET_KEY, "dash_token": DASH_TOKEN,
        "alert_cpu": ALERT_CPU_THRESH, "alert_ram": ALERT_RAM_THRESH,
        "alert_disk": ALERT_DISK_THRESH, "alert_cooldown": ALERT_COOLDOWN,
        "version": VERSION,
    })
    _write_json(CONFIG_FILE, CONFIG)

# History ring-buffer  (60 pts × 5 s = 5 min)
HIST_MAXLEN = 60
HISTORY: dict = {
    "cpu":    deque(maxlen=HIST_MAXLEN),
    "ram":    deque(maxlen=HIST_MAXLEN),
    "net_s":  deque(maxlen=HIST_MAXLEN),
    "net_r":  deque(maxlen=HIST_MAXLEN),
    "labels": deque(maxlen=HIST_MAXLEN),
}

PROC_REG: dict = {}       # nohup process registry
PATH_TOKENS: dict[str, str] = {}
_BOT_APP       = None     # Telegram Application instance
_BOT_LOOP      = None     # Event loop reference for alert_monitor

# ─────────────────────────────────────────────────────────────────
# 3. LOGGING
# ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024,
                            backupCount=5, encoding="utf-8"),
    ] + ([logging.StreamHandler(sys.stdout)] if sys.stdout else []),
)
log = logging.getLogger("SC")

# ─────────────────────────────────────────────────────────────────
# 4. HELPERS
# ─────────────────────────────────────────────────────────────────

def owner_only(func):
    @wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE, *a, **kw):
        user = (update.effective_user
                or (update.callback_query.from_user if update.callback_query else None))
        uid  = user.id if user else 0
        if uid != OWNER_ID:
            log.warning(f"Unauthorized uid={uid}")
            if update.message:
                await update.message.reply_text("⛔ Akses ditolak.")
            elif update.callback_query:
                await update.callback_query.answer("⛔ Akses ditolak.", show_alert=True)
            return
        return await func(update, ctx, *a, **kw)
    return wrapper

def safe_exec(cmd: str, cwd: str = None, timeout: int = 30) -> str:
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            cwd=cwd or str(Path.home()), timeout=timeout,
            encoding="utf-8", errors="replace",
            creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0)
                           if IS_WINDOWS else 0),
        )
        out = (r.stdout or "") + (r.stderr or "")
        return out.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"⏱ Timeout setelah {timeout}s"
    except Exception as e:
        return f"❌ Error: {e}"

def powershell(script: str, timeout: int = 30) -> str:
    """Run PowerShell non-interactively without opening a visible window."""
    exe = shutil.which("powershell.exe") or shutil.which("pwsh.exe") or "powershell.exe"
    try:
        r = subprocess.run(
            [exe, "-NoLogo", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = (r.stdout or "") + (r.stderr or "")
        return out.strip() or ("OK" if r.returncode == 0 else f"Exit code {r.returncode}")
    except subprocess.TimeoutExpired:
        return f"⏱ Timeout setelah {timeout}s"
    except Exception as exc:
        return f"❌ PowerShell error: {exc}"

def is_admin() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def request_elevation() -> bool:
    """Show the standard UAC prompt once so all Windows controls can work."""
    if not IS_WINDOWS or is_admin():
        return True
    try:
        params = subprocess.list2cmdline([str(Path(__file__).resolve()),
                                         *[a for a in sys.argv[1:] if a != "--no-elevate"]])
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, str(Path(__file__).resolve().parent), 1)
        return result > 32
    except Exception:
        return False

def _hidden_kwargs() -> dict:
    return {"creationflags": (getattr(subprocess, "CREATE_NO_WINDOW", 0) |
                              getattr(subprocess, "DETACHED_PROCESS", 0))} if IS_WINDOWS else {}

def kill_process_tree(pid: int) -> bool:
    if pid == os.getpid(): return False
    try:
        parent   = psutil.Process(pid)
        children = parent.children(recursive=True)
        for child in children:
            try: child.kill()
            except psutil.NoSuchProcess: pass
        try: parent.kill()
        except psutil.NoSuchProcess: pass
        psutil.wait_procs(children + [parent], timeout=3)
        return True
    except psutil.NoSuchProcess:
        return True
    except Exception as e:
        log.error(f"Kill tree error pid={pid}: {e}")
        return False

def fmt_bytes(n: int) -> str:
    return humanize.naturalsize(n, binary=True)

def fmt_time(sec: float) -> str:
    return str(datetime.timedelta(seconds=int(sec)))

def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]; s.close(); return ip
    except Exception:
        return "127.0.0.1"

def paginate(items: list, page: int, per_page: int = 20):
    total = len(items)
    pages = max(1, (total + per_page - 1) // per_page)
    page  = max(0, min(page, pages - 1))
    return items[page * per_page:(page + 1) * per_page], page, pages

def kb(rows: list) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(rows)

def btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data)

def is_proc_alive(pid: int) -> bool:
    try:
        p = psutil.Process(pid)
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False

def trunc(s: str, n: int = 32) -> str:
    return s if len(s) <= n else s[:n - 1] + "…"

def path_token(path: str | Path) -> str:
    value = str(Path(path))
    token = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:20]
    PATH_TOKENS[token] = value
    return token

def token_path(token: str) -> str:
    value = PATH_TOKENS.get(token)
    if not value:
        raise ValueError("Referensi file kedaluwarsa. Buka ulang daftar script.")
    return value

def h(s: str) -> str:
    """HTML-escape a string."""
    return html.escape(str(s))

def tail_file(path: Path | str, lines: int = 100) -> str:
    try:
        p = Path(path)
        with p.open("r", encoding="utf-8", errors="replace") as handle:
            return "".join(deque(handle, maxlen=max(1, lines))).rstrip() or "(log kosong)"
    except FileNotFoundError:
        return "(log belum ada)"
    except Exception as exc:
        return f"❌ Gagal membaca log: {exc}"

def first_run_setup() -> bool:
    """One-time console wizard. Background starts never prompt for secrets."""
    global TOKEN, OWNER_ID, WEB_PORT, DASH_TOKEN, SECRET_KEY
    force = "--setup" in sys.argv
    if TOKEN and OWNER_ID and not force:
        save_runtime_config()
        return True
    if "--background" in sys.argv or not sys.stdin or not sys.stdin.isatty():
        return False
    print("\n" + "=" * 68)
    print(" WINDOWS CONTROL SUITE v5 - SETUP PERTAMA")
    print(" Konfigurasi disimpan di:", CONFIG_FILE)
    print("=" * 68)
    if force:
        TOKEN = ""
        OWNER_ID = 0
    while not TOKEN:
        TOKEN = input("Token bot Telegram dari @BotFather: ").strip()
        if not re.fullmatch(r"\d{6,15}:[A-Za-z0-9_-]{20,}", TOKEN):
            print("Format token tampak tidak valid. Silakan periksa kembali.")
            TOKEN = ""
            continue
        try:
            check = requests.get(f"https://api.telegram.org/bot{TOKEN}/getMe", timeout=15)
            payload = check.json()
            if check.status_code == 200 and payload.get("ok"):
                print(f"✅ Bot terverifikasi: @{payload.get('result', {}).get('username', '-')}")
            elif check.status_code in (400, 401, 404):
                print("❌ Token ditolak oleh Telegram. Masukkan token yang benar.")
                TOKEN = ""
        except Exception:
            print("⚠️ Internet tidak tersedia; token akan diverifikasi saat bot mulai.")
    while not OWNER_ID:
        raw = input("Telegram Admin/Owner ID (angka): ").strip()
        try:
            OWNER_ID = int(raw)
            if OWNER_ID <= 0:
                raise ValueError
        except ValueError:
            OWNER_ID = 0
            print("Admin ID harus berupa angka positif.")
    raw_port = input(f"Port dashboard [{WEB_PORT}]: ").strip()
    if raw_port:
        try:
            port = int(raw_port)
            if not 1 <= port <= 65535:
                raise ValueError
            WEB_PORT = port
        except ValueError:
            print(f"Port tidak valid; tetap menggunakan {WEB_PORT}.")
    save_runtime_config()
    print(f"\nToken login dashboard: {DASH_TOKEN}")
    return True

def pythonw_path() -> Path:
    exe = Path(sys.executable).resolve()
    if IS_WINDOWS:
        pyw = exe.with_name("pythonw.exe")
        if pyw.exists():
            return pyw
    return exe

def ensure_installed_copy() -> Path:
    """Keep a stable copy outside Downloads/Desktop for Task Scheduler."""
    source = Path(__file__).resolve()
    try:
        if source != INSTALLED_SCRIPT and (
                not INSTALLED_SCRIPT.exists() or
                hashlib.sha256(source.read_bytes()).digest() !=
                hashlib.sha256(INSTALLED_SCRIPT.read_bytes()).digest()):
            shutil.copy2(source, INSTALLED_SCRIPT)
    except Exception as exc:
        log.warning("Tidak dapat memperbarui installed copy: %s", exc)
        return source
    return INSTALLED_SCRIPT if INSTALLED_SCRIPT.exists() else source

def scheduled_task_status() -> dict:
    if not IS_WINDOWS:
        return {"installed": False, "status": "unsupported", "detail": "Windows required"}
    try:
        r = subprocess.run(["schtasks.exe", "/Query", "/TN", TASK_NAME, "/FO", "LIST", "/V"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        text_out = (r.stdout or "") + (r.stderr or "")
        status = "Ready"
        for line in text_out.splitlines():
            if line.lower().startswith(("status:", "scheduled task state:")):
                status = line.split(":", 1)[-1].strip()
                break
        return {"installed": r.returncode == 0, "status": status,
                "detail": text_out[-1200:]}
    except Exception as exc:
        return {"installed": False, "status": "error", "detail": str(exc)}

def install_startup_task(script_path: Path) -> tuple[bool, str]:
    """Install an ONLOGON task with restart-on-failure and no console window."""
    if not IS_WINDOWS:
        return False, "Script ini ditujukan untuk Windows 10/11."
    task_user = safe_exec("whoami", timeout=5).splitlines()[0].strip()
    if "\\" not in task_user or task_user.startswith("❌"):
        task_user = f"{os.environ.get('USERDOMAIN', platform.node())}\\{CURRENT_USER}"
    command = str(pythonw_path())
    arguments = f'"{script_path}" --background'
    level = "HighestAvailable" if is_admin() else "LeastPrivilege"
    xml = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>{APP_NAME} - bot Telegram dan dashboard Windows.</Description></RegistrationInfo>
  <Triggers><LogonTrigger><Enabled>true</Enabled><UserId>{h(task_user)}</UserId></LogonTrigger></Triggers>
  <Principals><Principal id="Author"><UserId>{h(task_user)}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>{level}</RunLevel></Principal></Principals>
  <Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><AllowHardTerminate>true</AllowHardTerminate><StartWhenAvailable>true</StartWhenAvailable><RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable><IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings><AllowStartOnDemand>true</AllowStartOnDemand><Enabled>true</Enabled><Hidden>true</Hidden><ExecutionTimeLimit>PT0S</ExecutionTimeLimit><Priority>7</Priority><RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure></Settings>
  <Actions Context="Author"><Exec><Command>{h(command)}</Command><Arguments>{h(arguments)}</Arguments><WorkingDirectory>{h(str(script_path.parent))}</WorkingDirectory></Exec></Actions>
</Task>'''
    temp_xml = Path(tempfile.gettempdir()) / f"windows-control-{uuid.uuid4().hex}.xml"
    try:
        temp_xml.write_text(xml, encoding="utf-16")
        r = subprocess.run(["schtasks.exe", "/Create", "/TN", TASK_NAME,
                            "/XML", str(temp_xml), "/F"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        return r.returncode == 0, out or "Task Scheduler berhasil dipasang."
    except Exception as exc:
        return False, str(exc)
    finally:
        try:
            temp_xml.unlink(missing_ok=True)
        except Exception:
            pass

def create_dashboard_shortcuts(port: int) -> None:
    """Create reliable Start Menu/Desktop .url shortcuts without COM modules."""
    if not IS_WINDOWS:
        return
    url_text = ("[InternetShortcut]\nURL=http://127.0.0.1:%d/\n"
                "IconFile=%%SystemRoot%%\\System32\\SHELL32.dll\nIconIndex=220\n" % port)
    targets = [Path.home() / "Desktop" / "Windows Control Dashboard.url"]
    appdata = os.getenv("APPDATA")
    if appdata:
        targets.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" /
                       "Programs" / "Windows Control Dashboard.url")
    for target in targets:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(url_text, encoding="utf-8")
        except Exception as exc:
            log.debug("Shortcut gagal %s: %s", target, exc)

def ensure_firewall_rule(port: int) -> tuple[bool, str]:
    """Add only this application's inbound rule; never alter unrelated rules."""
    if not IS_WINDOWS:
        return False, "Windows required"
    if not is_admin():
        return False, "Jalankan setup sebagai Administrator untuk akses LAN/firewall."
    rule = f"{APP_NAME} Dashboard {port}"
    subprocess.run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={rule}"],
                   capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    r = subprocess.run(["netsh", "advfirewall", "firewall", "add", "rule",
                        f"name={rule}", "dir=in", "action=allow", "protocol=TCP",
                        f"localport={port}", "profile=private"], capture_output=True,
                       text=True, encoding="utf-8", errors="replace",
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.returncode == 0, ((r.stdout or "") + (r.stderr or "")).strip()

_INSTANCE_MUTEX = None
def acquire_single_instance() -> bool:
    global _INSTANCE_MUTEX
    if not IS_WINDOWS:
        return True
    _INSTANCE_MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False,
                                                          "Local\\WindowsControlSuite-v5")
    return ctypes.windll.kernel32.GetLastError() != 183

def launch_hidden(script_path: Path | None = None) -> bool:
    try:
        target = script_path or (INSTALLED_SCRIPT if INSTALLED_SCRIPT.exists()
                                 else Path(__file__).resolve())
        subprocess.Popen([str(pythonw_path()), str(target), "--background"],
                         cwd=str(target.parent), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         **_hidden_kwargs())
        return True
    except Exception as exc:
        log.error("Gagal menjalankan background: %s", exc)
        return False

def _delayed_restart() -> None:
    """Let the HTTP/Telegram response finish, then replace this process."""
    time.sleep(0.8)
    target = ensure_installed_copy()
    if IS_WINDOWS:
        cmd = (f'timeout /t 2 /nobreak >nul & start "" /b '
               f'"{pythonw_path()}" "{target}" --background')
        subprocess.Popen([os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", cmd],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, **_hidden_kwargs())
    else:
        launch_hidden(target)
    os._exit(0)

# ─────────────────────────────────────────────────────────────────
# 5. SYSTEM INFO (extended)
# ─────────────────────────────────────────────────────────────────

def sys_info() -> dict:
    cpu   = psutil.cpu_percent(interval=0.3)
    ram   = psutil.virtual_memory()
    swap  = psutil.swap_memory()
    disk_root = Path.home().anchor or str(Path.home())
    disk  = psutil.disk_usage(disk_root)
    boot  = psutil.boot_time()
    un    = platform.uname()
    la    = os.getloadavg() if hasattr(os, "getloadavg") else (cpu, cpu, cpu)
    net   = psutil.net_io_counters()
    try:
        battery = psutil.sensors_battery()
    except Exception:
        battery = None
    winver = platform.win32_ver()
    return dict(
        os=(f"Windows {winver[0]} {winver[1]}" if IS_WINDOWS
            else f"{un.system} {un.release}"), node=un.node,
        arch=un.machine, python=platform.python_version(),
        cpu_pct=cpu,
        cpu_cores=psutil.cpu_count(logical=True),
        cpu_cores_phys=psutil.cpu_count(logical=False) or 1,
        load1=round(la[0], 2), load5=round(la[1], 2), load15=round(la[2], 2),
        ram_total=fmt_bytes(ram.total), ram_used=fmt_bytes(ram.used),
        ram_free=fmt_bytes(ram.available), ram_pct=ram.percent,
        ram_total_raw=ram.total, ram_used_raw=ram.used,
        swap_total=fmt_bytes(swap.total), swap_used=fmt_bytes(swap.used),
        swap_pct=swap.percent,
        disk_total=fmt_bytes(disk.total), disk_used=fmt_bytes(disk.used),
        disk_free=fmt_bytes(disk.free), disk_pct=disk.percent,
        net_sent=fmt_bytes(net.bytes_sent), net_recv=fmt_bytes(net.bytes_recv),
        net_bytes_sent=net.bytes_sent, net_bytes_recv=net.bytes_recv,
        uptime=fmt_time(time.time() - boot),
        uptime_sec=int(time.time() - boot),
        local_ip=get_local_ip(),
        pid_count=len(psutil.pids()),
        battery=(round(battery.percent, 1) if battery else None),
        plugged=(bool(battery.power_plugged) if battery else None),
        admin=is_admin(),
    )

def get_disk_partitions() -> list:
    result = []
    for p in psutil.disk_partitions(all=False):
        try:
            u = psutil.disk_usage(p.mountpoint)
            result.append(dict(
                device=p.device, mountpoint=p.mountpoint, fstype=p.fstype,
                total=fmt_bytes(u.total), used=fmt_bytes(u.used),
                free=fmt_bytes(u.free), pct=u.percent,
            ))
        except (PermissionError, OSError):
            pass
    return result

def get_net_interfaces() -> list:
    try:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        ios = psutil.net_io_counters(pernic=True)
    except (PermissionError, psutil.AccessDenied, OSError):
        return []
    result = []
    for name, addr_list in addrs.items():
        ipv4 = next((a.address for a in addr_list
                     if a.family == socket.AF_INET), "—")
        st = stats.get(name)
        io = ios.get(name)
        result.append(dict(
            name=name, ip=ipv4,
            up=st.isup if st else False,
            speed=f"{st.speed} Mbps" if st and st.speed else "—",
            sent=fmt_bytes(io.bytes_sent) if io else "—",
            recv=fmt_bytes(io.bytes_recv) if io else "—",
        ))
    return result

def get_listening_ports() -> list:
    result = []
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.status == "LISTEN":
                try:
                    pname = psutil.Process(conn.pid).name() if conn.pid else "—"
                except Exception:
                    pname = "—"
                result.append(dict(
                    port=conn.laddr.port,
                    ip=conn.laddr.ip or "0.0.0.0",
                    pid=conn.pid or "—",
                    process=pname,
                ))
    except (psutil.AccessDenied, Exception):
        pass
    return sorted(result, key=lambda x: x["port"])

def get_all_procs(limit: int = 80) -> list:
    procs = []
    for p in psutil.process_iter(["pid", "name", "status", "cpu_percent",
                                   "memory_info", "create_time", "username"]):
        try:
            mi = p.info["memory_info"]
            procs.append(dict(
                pid=p.info["pid"],
                name=(p.info["name"] or "")[:24],
                status=p.info["status"],
                cpu=p.info["cpu_percent"],
                mem_raw=mi.rss if mi else 0,
                mem=fmt_bytes(mi.rss if mi else 0),
                age=fmt_time(time.time() - p.info["create_time"]),
                user=(p.info["username"] or "")[:14],
            ))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    procs.sort(key=lambda x: x["mem_raw"], reverse=True)
    return procs[:limit]

# ─────────────────────────────────────────────────────────────────
# 6. USER PYTHON PROCESS DETECTOR
# ─────────────────────────────────────────────────────────────────

def get_user_py_procs() -> list:
    result = []
    for p in psutil.process_iter(["pid", "name", "cmdline", "username",
                                   "status", "cpu_percent", "memory_info", "create_time"]):
        try:
            uname = p.info.get("username") or ""
            short_user = uname.rsplit("\\", 1)[-1]
            if short_user.lower() != CURRENT_USER.lower():
                continue

            cmdline = p.info.get("cmdline") or []
            if not cmdline: continue
            exe = cmdline[0].lower()
            if not any(x in exe for x in ["python", "pythonw", "py.exe"]): continue

            py_file = next((a for a in cmdline if a.endswith(".py")), None)
            if not py_file: continue
            if any(py_file.lower().startswith(sp) for sp in SYSTEM_PREFIXES): continue

            mi = p.info.get("memory_info")
            try:
                pr          = p.parent()
                parent_name = pr.name() if pr else ""
            except Exception:
                parent_name = ""

            cmd_str  = " ".join(cmdline)
            launcher = ("Task Scheduler" if "taskeng" in parent_name.lower()
                        else "pythonw" if "pythonw" in exe
                        else "python")

            log_f = str(NOHUP_LOG_DIR / (Path(py_file).stem + ".log"))
            result.append(dict(
                pid=p.info["pid"],
                script=py_file,
                script_name=Path(py_file).name,
                cmd=cmd_str[:80],
                status=p.info.get("status", "?"),
                cpu=p.info.get("cpu_percent", 0.0),
                mem=fmt_bytes(mi.rss if mi else 0),
                age=fmt_time(time.time() - (p.info.get("create_time") or time.time())),
                launcher=launcher,
                log=log_f,
            ))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return result

# ─────────────────────────────────────────────────────────────────
# 7. SCRIPT FINDER
# ─────────────────────────────────────────────────────────────────

def find_user_scripts(max_depth: int = 4, limit: int = 200) -> list:
    found = []; seen = set()
    def _scan(root: Path, depth: int):
        if depth < 0 or not root.exists(): return
        try:
            for entry in sorted(root.iterdir(), key=lambda e: e.name):
                ep = str(entry)
                if ep in seen: continue
                seen.add(ep)
                if entry.is_symlink(): continue
                if any(ep.lower().startswith(sp) for sp in SYSTEM_PREFIXES): continue
                if entry.is_dir() and not entry.name.startswith("."):
                    _scan(entry, depth - 1)
                elif entry.is_file() and entry.suffix.lower() in (
                        ".py", ".ps1", ".bat", ".cmd", ".exe"):
                    try:
                        if entry.stat().st_size < 10: continue
                    except Exception: continue
                    found.append(entry)
                    if len(found) >= limit: return
        except (PermissionError, OSError): pass
    for base in SCRIPT_SEARCH_PATHS:
        _scan(base, max_depth)
        if len(found) >= limit: break
    return sorted(found, key=lambda p: (str(p.parent), p.name))

# ─────────────────────────────────────────────────────────────────
# 8. HIDDEN WINDOWS PROCESS RUNNER
# ─────────────────────────────────────────────────────────────────

def nohup_run(script_path: str, custom_cmd: str = None,
              custom_cwd: str = None) -> dict:
    sp       = Path(script_path).resolve()
    log_file = str(NOHUP_LOG_DIR / f"{sp.stem}.log")
    killed   = []
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if str(sp) in cmd or (sp.name in cmd and "python" in cmd.lower()):
                if p.pid != os.getpid():
                    killed.append(p.pid)
                    kill_process_tree(p.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied): pass
    if killed: time.sleep(1)
    cwd      = custom_cwd or str(sp.parent)
    suffix = sp.suffix.lower()
    if custom_cmd:
        command = custom_cmd
        use_shell = True
    elif suffix == ".py":
        command = [sys.executable, "-u", str(sp)]
        use_shell = False
    elif suffix == ".ps1":
        command = [shutil.which("powershell.exe") or "powershell.exe", "-NoProfile",
                   "-ExecutionPolicy", "Bypass", "-File", str(sp)]
        use_shell = False
    elif suffix in (".bat", ".cmd"):
        command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(sp)]
        use_shell = False
    else:
        command = [str(sp)]
        use_shell = False
    full_cmd = command if isinstance(command, str) else subprocess.list2cmdline(command)
    log_handle = None
    try:
        log_handle = open(log_file, "a", encoding="utf-8", buffering=1)
        subprocess.Popen(command, shell=use_shell, cwd=cwd,
                         stdin=subprocess.DEVNULL, stdout=log_handle,
                         stderr=subprocess.STDOUT, **_hidden_kwargs())
    except Exception as e:
        log.error(f"Gagal menjalankan proses Windows: {e}")
    finally:
        if log_handle:
            try: log_handle.close()
            except Exception: pass
    time.sleep(1.5)
    new_pid = None
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            if str(sp) in " ".join(p.info.get("cmdline") or []):
                new_pid = p.pid; break
        except Exception: pass
    key = f"nohup_{sp.stem}_{int(time.time())}"
    if new_pid:
        PROC_REG[key] = dict(pid=new_pid, name=sp.stem, path=str(sp),
                              cmd=full_cmd, started=time.time(), log=log_file)
    return dict(pid=new_pid, log=log_file, killed=killed, key=key)

def restart_proc(pid: int, script_path: str) -> dict:
    custom_cmd = None; custom_cwd = None
    try:
        p = psutil.Process(pid)
        cmd_list = p.cmdline()
        if cmd_list:
            custom_cmd = subprocess.list2cmdline(cmd_list)
        custom_cwd = p.cwd()
    except Exception: pass
    return nohup_run(script_path, custom_cmd=custom_cmd, custom_cwd=custom_cwd)

def find_running_pid(script_path: str):
    sp = Path(script_path).resolve()
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            if str(sp) in " ".join(p.info.get("cmdline") or []):
                return p.pid
        except Exception: pass
    return None

# ─────────────────────────────────────────────────────────────────
# 9. FILE MANAGER STATE (Telegram)
# ─────────────────────────────────────────────────────────────────

def get_nav(ctx) -> Path:
    raw = ctx.user_data.get("nav_path", str(Path.home()))
    p   = Path(raw)
    return p if p.is_dir() else Path.home()

def set_nav(ctx, path: Path):
    ctx.user_data["nav_path"] = str(path.resolve())

def get_show_hidden(ctx) -> bool:
    return bool(ctx.user_data.get("show_hidden", False))

def is_hidden_path(path: Path) -> bool:
    if path.name.startswith("."):
        return True
    if IS_WINDOWS:
        try:
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
            return attrs != -1 and bool(attrs & 0x6)  # HIDDEN or SYSTEM
        except Exception:
            pass
    return False

def list_dir(path: Path, page: int, show_hidden: bool):
    try:
        entries = sorted(path.iterdir(),
                         key=lambda e: (e.is_file(), e.name.lower()))
        if not show_hidden:
            entries = [e for e in entries if not is_hidden_path(e)]
    except PermissionError:
        return [], 0, 0
    return paginate(entries, page, per_page=20)

# ─────────────────────────────────────────────────────────────────
# 10. TERMINAL SHORTCUTS  (20 quick commands)
# ─────────────────────────────────────────────────────────────────

SHORTCUTS = [
    ("dir /a",                                                           "📂 Dir"),
    ("cd",                                                               "📌 Lokasi"),
    ("wmic logicaldisk get caption,freespace,size",                      "💾 Disk"),
    ("systeminfo | findstr /C:\"Total Physical Memory\" /C:\"Available Physical Memory\"", "🧠 RAM"),
    ("net statistics workstation | findstr /C:\"Statistics since\"",  "⏱ Uptime"),
    ("powershell -NoProfile -Command \"Get-Process|Sort CPU -Desc|Select -First 20 Id,ProcessName,CPU,WS\"", "🔥 Top CPU"),
    ("powershell -NoProfile -Command \"Get-Process|Sort WS -Desc|Select -First 20 Id,ProcessName,CPU,WS\"", "🧠 Top RAM"),
    ("netstat -ano | findstr LISTENING",                                  "🌐 Ports"),
    ("query user",                                                        "👤 Sessions"),
    ("powershell -NoProfile -Command \"Get-WinEvent -LogName System -MaxEvents 20|Format-Table TimeCreated,Id,LevelDisplayName,Message -Wrap\"", "📜 Event Log"),
    ("where /r %USERPROFILE% *.py",                                      "🐍 Find .py"),
    ("python -m pip list",                                               "📦 pip list"),
    ("sc query state= all",                                              "🔧 Services"),
    ("ipconfig /all",                                                    "🌐 IP Config"),
    ("netstat -e -s",                                                    "📡 Net Stats"),
    ("powershell -NoProfile -Command \"Get-ChildItem $HOME|Sort Length -Desc|Select -First 20 Name,Length\"", "📁 Home Size"),
    ("powershell -NoProfile -Command \"Get-CimInstance Win32_Processor|Select Name,NumberOfCores,MaxClockSpeed\"", "⚡ CPU Info"),
    ("set",                                                              "🔣 Env Vars"),
    ("schtasks /Query /FO TABLE",                                        "⏰ Tasks"),
    ("git -C %USERPROFILE% log --oneline -5",                            "🔀 Git Log"),
]

# ─────────────────────────────────────────────────────────────────
# 11. BACKGROUND THREADS
# ─────────────────────────────────────────────────────────────────

def history_collector():
    """Collect CPU / RAM / Net I/O into ring-buffer every 5 s."""
    prev_net = psutil.net_io_counters()
    prev_t   = time.time()
    while True:
        try:
            time.sleep(5)
            now  = time.time(); dt = max(now - prev_t, 1); prev_t = now
            cpu  = psutil.cpu_percent(interval=0)
            ram  = psutil.virtual_memory().percent
            net  = psutil.net_io_counters()
            sent = max(0, (net.bytes_sent - prev_net.bytes_sent) / dt)
            recv = max(0, (net.bytes_recv - prev_net.bytes_recv) / dt)
            prev_net = net
            ts   = datetime.datetime.now().strftime("%H:%M:%S")
            HISTORY["cpu"].append(round(cpu, 1))
            HISTORY["ram"].append(round(ram, 1))
            HISTORY["net_s"].append(round(sent, 0))
            HISTORY["net_r"].append(round(recv, 0))
            HISTORY["labels"].append(ts)
        except Exception as e:
            log.debug(f"history_collector: {e}")

def alert_monitor():
    """Kirim notifikasi Telegram saat threshold terlampaui."""
    while True:
        try:
            time.sleep(60)
            if not (ALERTS_ENABLED and _BOT_APP and _BOT_LOOP and OWNER_ID):
                continue
            si  = sys_info()
            now = time.time()
            checks = [
                ("cpu",  si["cpu_pct"],  ALERT_CPU_THRESH,  "🔥 CPU"),
                ("ram",  si["ram_pct"],  ALERT_RAM_THRESH,  "🧠 RAM"),
                ("disk", si["disk_pct"], ALERT_DISK_THRESH, "💾 Disk"),
            ]
            for key, val, thresh, label in checks:
                if val > thresh and now - ALERT_LAST[key] > ALERT_COOLDOWN:
                    ALERT_LAST[key] = now
                    msg = (
                        f"🚨 *Windows Alert* — `{platform.node()}`\n"
                        f"{label}: `{val}%` melebihi batas `{thresh}%`\n"
                        f"⏱ Uptime: `{si['uptime']}`"
                    )
                    asyncio.run_coroutine_threadsafe(
                        _BOT_APP.bot.send_message(
                            OWNER_ID, msg, parse_mode=ParseMode.MARKDOWN),
                        _BOT_LOOP,
                    )
        except Exception as e:
            log.debug(f"alert_monitor: {e}")

# ─────────────────────────────────────────────────────────────────
# 12. TELEGRAM HANDLERS
# ─────────────────────────────────────────────────────────────────

def menu_main():
    return kb([
        [btn("📁 File Manager",  "fm:open:0"),   btn("⚙️ Processes",    "pm:list:0")],
        [btn("🐍 My Scripts",    "up:list:0"),   btn("📜 Find Scripts",  "sc:list:0")],
        [btn("🔧 Services",      "sv:list"),     btn("🐋 Docker",        "dk:list")],
        [btn("💾 Storage",       "st:info"),     btn("🖥 System Info",   "si:info")],
        [btn("🌐 Network",       "nt:info"),     btn("📊 Live Stats",    "ls:show")],
        [btn("🛡 Firewall",      "ip:list"),     btn("⏰ Scheduled Tasks", "cj:list")],
        [btn("💻 Terminal",      "ex:menu"),     btn("⚙️ Config",        "cfg:show")],
        [btn("🚨 Alerts",        "al:status"),   btn("❓ Help",          "help:show")],
    ])

def menu_back():
    return kb([[btn("🏠 Main Menu", "main:menu")]])

# ── /start & Main Menu ────────────────────────────────────────────
@owner_only
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    si = sys_info()
    def bar(p): return "█" * int(p / 10) + "░" * (10 - int(p / 10))
    txt = (
        f"🪟 *Windows Control Suite v5*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🖥 `{si['node']}` — {si['os']}\n"
        f"⏱ Uptime: `{si['uptime']}`\n"
        f"🌐 IP: `{si['local_ip']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"CPU  `{si['cpu_pct']}%` [{bar(si['cpu_pct'])}]\n"
        f"RAM  `{si['ram_pct']}%` [{bar(si['ram_pct'])}]\n"
        f"Disk `{si['disk_pct']}%`  Procs `{si['pid_count']}`"
    )
    await update.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN,
                                    reply_markup=menu_main())

@owner_only
async def cb_main_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    si = sys_info()
    def bar(p): return "█" * int(p / 10) + "░" * (10 - int(p / 10))
    txt = (
        f"🪟 *Windows Control Suite v5*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🖥 `{si['node']}` — {si['os']}\n"
        f"⏱ `{si['uptime']}`  🌐 `{si['local_ip']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"CPU `{si['cpu_pct']}%` [{bar(si['cpu_pct'])}]\n"
        f"RAM `{si['ram_pct']}%` [{bar(si['ram_pct'])}]\n"
        f"Disk `{si['disk_pct']}%`  Procs `{si['pid_count']}`"
    )
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=menu_main())

# ── Help ──────────────────────────────────────────────────────────
@owner_only
async def cb_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ip = get_local_ip()
    txt = (
        "❓ *Windows Control v5 — Panduan*\n\n"
        "📁 *File Manager* — Browse, upload, download, buat, hapus, rename, run/restart tersembunyi\n\n"
        "⚙️ *Processes* — List + Kill by PID (tree kill)\n\n"
        "🐍 *My Scripts* — Deteksi Python user berjalan; Kill/Restart/Log\n\n"
        "📜 *Find Scripts* — Cari .py/.ps1/.bat/.cmd/.exe; Run/Restart/Kill/Download\n\n"
        "💾 *Storage* — Disk usage per partisi\n\n"
        "🖥 *System Info* — OS, CPU, RAM, Swap, Load, Net\n\n"
        "💻 *Terminal* — 20 shortcut + ketik manual\n\n"
        "📊 *Live Stats* — Top 8 proses real-time\n\n"
        "🌐 *Network* — Interface, listening ports, koneksi aktif\n\n"
        "🔧 *Services* — Kelola Windows Services (Start/Stop/Restart)\n\n"
        "🛡 *Firewall* — Kelola rule port Windows Defender Firewall\n\n"
        "⏰ *Scheduled Tasks* — Jadwal script dan cek startup aplikasi\n\n"
        "🚨 *Alerts* — Threshold CPU/RAM/Disk → notif Telegram\n\n"
        f"🌐 *Web Dashboard*: `http://{ip}:{WEB_PORT}`\n"
        f"🔑 Token: `{DASH_TOKEN}`\n\n"
        f"🛡 Akses LAN memerlukan rule Firewall (dibuat otomatis saat setup Administrator)."
    )
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=menu_back())

# ── System Info ───────────────────────────────────────────────────
@owner_only
async def cb_sys_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    si = sys_info()
    def bar(p): return "█" * int(p / 10) + "░" * (10 - int(p / 10))
    txt = (
        f"🖥 *System Information*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"OS     : `{si['os']}`\n"
        f"Host   : `{si['node']}`\n"
        f"Arch   : `{si['arch']}`\n"
        f"Python : `{si['python']}`\n"
        f"Uptime : `{si['uptime']}`\n"
        f"IP     : `{si['local_ip']}`\n"
        f"Proses : `{si['pid_count']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"CPU    : `{si['cpu_pct']}%` ({si['cpu_cores']}c) [{bar(si['cpu_pct'])}]\n"
        f"Load   : `{si['load1']}` `{si['load5']}` `{si['load15']}`\n"
        f"RAM    : `{si['ram_used']}/{si['ram_total']}` ({si['ram_pct']}%) [{bar(si['ram_pct'])}]\n"
        f"Swap   : `{si['swap_used']}/{si['swap_total']}` ({si['swap_pct']}%)\n"
        f"Disk   : `{si['disk_used']}/{si['disk_total']}` ({si['disk_pct']}%)\n"
        f"Net ↑  : `{si['net_sent']}`  ↓ `{si['net_recv']}`"
    )
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("🔄 Refresh", "si:info")],
                         [btn("🏠 Main", "main:menu")]]))

# ── Live Stats ────────────────────────────────────────────────────
@owner_only
async def cb_live_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    si  = sys_info()
    top = get_all_procs(8)
    def bar(p): return "█" * int(p / 10) + "░" * (10 - int(p / 10))
    lines = "\n".join(
        f"`{p['pid']:>7}` `{p['name']:<18}` CPU`{p['cpu']:>5.1f}%` `{p['mem']}`"
        for p in top
    )
    txt = (
        f"📊 *Live Stats*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔥 CPU : `{si['cpu_pct']}%` [{bar(si['cpu_pct'])}]\n"
        f"🧠 RAM : `{si['ram_pct']}%` [{bar(si['ram_pct'])}]\n"
        f"💾 Disk: `{si['disk_pct']}%`  ⏱ `{si['uptime']}`\n"
        f"📦 Proses: `{si['pid_count']}`  Load: `{si['load1']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"*Top 8 by Memory:*\n{lines}"
    )
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("🔄 Refresh", "ls:show")],
                         [btn("🏠 Main", "main:menu")]]))

# ── Storage ───────────────────────────────────────────────────────
@owner_only
async def cb_storage(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    parts = get_disk_partitions()
    lines = []
    for p in parts[:6]:
        bn  = int(p["pct"] / 5)
        bar = "█" * bn + "░" * (20 - bn)
        lines.append(
            f"`{p['mountpoint']}`\n"
            f"  {p['used']}/{p['total']} ({p['pct']}%) [{bar}]"
        )
    si = sys_info()
    txt = (
        f"💾 *Storage Monitor*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        + "\n\n".join(lines) +
        f"\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Net ↑ `{si['net_sent']}` ↓ `{si['net_recv']}`"
    )
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("🔄 Refresh", "st:info")],
                         [btn("🏠 Main", "main:menu")]]))

# ── Network Info ──────────────────────────────────────────────────
@owner_only
async def cb_net_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ifaces = get_net_interfaces()[:6]
    ports  = get_listening_ports()[:12]
    iface_lines = "\n".join(
        f"{'🟢' if i['up'] else '🔴'} `{i['name']}` `{i['ip']}`\n"
        f"   ↑{i['sent']}  ↓{i['recv']}  {i['speed']}"
        for i in ifaces
    )
    port_lines = "\n".join(
        f"  `:{p['port']}` — `{p['process']}` (PID {p['pid']})"
        for p in ports
    )
    txt = (
        f"🌐 *Network Info*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"*Interfaces:*\n{iface_lines or '(tidak ada)'}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"*Listening Ports:*\n{port_lines or '(tidak ada)'}"
    )
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("🔄 Refresh", "nt:info")],
                         [btn("🏠 Main", "main:menu")]]))

# ── Services ──────────────────────────────────────────────────────
@owner_only
async def cb_services(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    lines = []
    try:
        services = sorted(psutil.win_service_iter(), key=lambda s: s.name().lower())
        for svc in services:
            info = svc.as_dict()
            if info.get("status") == "running":
                lines.append(f"{info.get('name','')[:30]:<30} {info.get('display_name','')[:45]}")
            if len(lines) >= 30:
                break
    except Exception as exc:
        lines = [f"Gagal membaca Windows Services: {exc}"]
    out = "\n".join(lines) or "Tidak ada service berjalan."
    txt = (
        f"🔧 *Running Services*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"```\n{out[:2500]}\n```"
    )
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([
            [btn("🔄 Refresh", "sv:list")],
            [btn("⌨️ Jalankan service command", "sv:prompt")],
            [btn("🏠 Main", "main:menu")],
        ]))

@owner_only
async def cb_sv_prompt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["await_input"] = "svc_cmd"
    await q.edit_message_text(
        "🔧 *Service Command*\n"
        "Format aman: `restart Spooler`, `start wuauserv`, atau `stop NamaService`.\n"
        "Aksi tertentu memerlukan Administrator. Kirim perintah:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("❌ Batal", "sv:list")]]),
    )

# ── Alert System ──────────────────────────────────────────────────
@owner_only
async def cb_alert_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    status = "✅ Aktif" if ALERTS_ENABLED else "❌ Nonaktif"
    now    = time.time()
    txt = (
        f"🚨 *Alert System*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Status   : {status}\n"
        f"CPU      : >{ALERT_CPU_THRESH}%\n"
        f"RAM      : >{ALERT_RAM_THRESH}%\n"
        f"Disk     : >{ALERT_DISK_THRESH}%\n"
        f"Cooldown : {ALERT_COOLDOWN}s\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Last CPU  : {int(now - ALERT_LAST['cpu'])}s ago\n"
        f"Last RAM  : {int(now - ALERT_LAST['ram'])}s ago\n"
        f"Last Disk : {int(now - ALERT_LAST['disk'])}s ago"
    )
    toggle_lbl = "🔕 Matikan Alert" if ALERTS_ENABLED else "🔔 Aktifkan Alert"
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([
            [btn(toggle_lbl, "al:toggle")],
            [btn("🧪 Test Alert", "al:test")],
            [btn("🏠 Main", "main:menu")],
        ]))

@owner_only
async def cb_alert_toggle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global ALERTS_ENABLED
    q = update.callback_query
    ALERTS_ENABLED = not ALERTS_ENABLED
    await q.answer(f"Alert {'diaktifkan ✅' if ALERTS_ENABLED else 'dimatikan ❌'}")
    await cb_alert_status.__wrapped__(update, ctx)

@owner_only
async def cb_alert_test(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer("📨 Mengirim test alert...")
    si = sys_info()
    txt = (
        f"🧪 *Test Alert — OK ✅*\n"
        f"Host : `{si['node']}`\n"
        f"CPU  : `{si['cpu_pct']}%`  (threshold >{ALERT_CPU_THRESH}%)\n"
        f"RAM  : `{si['ram_pct']}%`  (threshold >{ALERT_RAM_THRESH}%)\n"
        f"Disk : `{si['disk_pct']}%`  (threshold >{ALERT_DISK_THRESH}%)\n"
        f"Alert sistem berfungsi normal!"
    )
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("◀ Back", "al:status")],
                         [btn("🏠 Main", "main:menu")]]))

# ── All Processes ─────────────────────────────────────────────────
@owner_only
async def cb_proc_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE, page: int):
    q = update.callback_query; await q.answer()
    procs = get_all_procs(200)
    chunk, pg, pages = paginate(procs, page, 10)
    lines = "\n".join(
        f"`{p['pid']:>6}` `{p['name']:<20}` CPU`{p['cpu']:>5.1f}%` `{p['mem']}`"
        for p in chunk
    )
    txt = (
        f"⚙️ *All Processes* (hal {pg + 1}/{pages})\n"
        f"```\n{'PID':>6} {'NAME':<20} {'CPU':>5} MEM\n{lines}\n```"
    )
    nav_r = []
    if pg > 0: nav_r.append(btn("◀", f"pm:list:{pg - 1}"))
    if pg < pages - 1: nav_r.append(btn("▶", f"pm:list:{pg + 1}"))
    rows = []
    if nav_r: rows.append(nav_r)
    rows.append([btn("🔴 Kill PID", "pm:kill_ask"),
                 btn("🔄 Refresh", f"pm:list:{pg}")])
    rows.append([btn("🏠 Main", "main:menu")])
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=kb(rows))

@owner_only
async def cb_proc_kill_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["await_input"] = "kill_pid"
    await q.edit_message_text(
        "🔴 *Kill Process*\nKirim PID yang akan dimatikan:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("❌ Batal", "pm:list:0")]]),
    )

# ── My Scripts (Running User Python) ──────────────────────────────
@owner_only
async def cb_user_procs(update: Update, ctx: ContextTypes.DEFAULT_TYPE, page: int):
    q = update.callback_query; await q.answer()
    procs = get_user_py_procs()
    if not procs:
        await q.edit_message_text(
            "🐍 *My Running Scripts*\n\nTidak ada script Python yang berjalan.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb([[btn("🔄 Refresh", "up:list:0")],
                             [btn("🏠 Main", "main:menu")]]))
        return
    chunk, pg, pages = paginate(procs, page, 4)
    icons = {"Task Scheduler": "⏰", "pythonw": "🪟", "python": "🐍"}
    lines = []; action_rows = []
    for p in chunk:
        ico = icons.get(p["launcher"], "🐍")
        lines.append(
            f"{ico} `{p['pid']}` *{p['script_name']}*\n"
            f"   CPU:`{p['cpu']:.1f}%` MEM:`{p['mem']}` Age:`{p['age']}`\n"
            f"   Via `{p['launcher']}` | {p['status']}"
        )
        safe_script = path_token(p["script"])
        action_rows.append([
            btn(f"🔴 Kill {p['pid']}", f"up:kill:{p['pid']}"),
            btn("🔁 Restart",          f"up:rst:{p['pid']}:{safe_script}"),
            btn("📋 Log",              f"up:log:{p['pid']}"),
        ])
    txt = (f"🐍 *My Running Scripts* ({pg + 1}/{pages})\n"
           f"━━━━━━━━\n" + "\n\n".join(lines))
    nav_r = []
    if pg > 0: nav_r.append(btn("◀", f"up:list:{pg - 1}"))
    if pg < pages - 1: nav_r.append(btn("▶", f"up:list:{pg + 1}"))
    rows = list(action_rows)
    if nav_r: rows.append(nav_r)
    rows.append([btn("🔄 Refresh", "up:list:0"), btn("🏠 Main", "main:menu")])
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=kb(rows))

@owner_only
async def cb_up_kill(update: Update, ctx: ContextTypes.DEFAULT_TYPE, pid: int):
    q = update.callback_query; await q.answer()
    try:
        p_name = psutil.Process(pid).name()
        ok     = kill_process_tree(pid)
        msg    = (f"✅ PID `{pid}` (`{p_name}`) dihentikan (Tree Kill)." if ok
                  else f"❌ Gagal mematikan PID `{pid}`.")
    except psutil.NoSuchProcess:
        msg = f"⚠️ PID `{pid}` sudah tidak ada."
    except Exception as e:
        msg = f"❌ Error: `{e}`"
    await q.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("🐍 My Scripts", "up:list:0")],
                         [btn("🏠 Main", "main:menu")]]))

@owner_only
async def cb_up_restart(update: Update, ctx: ContextTypes.DEFAULT_TYPE,
                         pid: int, script: str):
    q = update.callback_query; await q.answer("🔁 Restarting...")
    r = restart_proc(pid, script)
    txt = (
        f"🔁 *Restart Selesai*\n"
        f"Script  : `{Path(script).name}`\n"
        f"PID lama: `{r.get('killed')}`\n"
        f"PID baru: `{r.get('pid', 'unknown')}`\n"
        f"Log     : `{r.get('log')}`"
    )
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("🐍 My Scripts", "up:list:0")],
                         [btn("🏠 Main", "main:menu")]]))

@owner_only
async def cb_up_log(update: Update, ctx: ContextTypes.DEFAULT_TYPE, pid: int):
    q = update.callback_query; await q.answer()
    content = "(log tidak ditemukan)"
    for info in PROC_REG.values():
        if info.get("pid") == pid:
            lf = Path(info.get("log", ""))
            if lf.is_file(): content = tail_file(lf, 30)
            break
    else:
        try:
            p = psutil.Process(pid)
            for arg in p.cmdline():
                if arg.endswith(".py"):
                    lf = NOHUP_LOG_DIR / (Path(arg).stem + ".log")
                    if lf.is_file(): content = tail_file(lf, 30)
                    break
        except Exception: pass
    await q.edit_message_text(
        f"📋 *Log PID {pid}*\n```\n{content[:3000]}\n```",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("◀ Back", "up:list:0")],
                         [btn("🏠 Main", "main:menu")]]))

# ── Find Scripts ──────────────────────────────────────────────────
@owner_only
async def cb_script_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE, page: int):
    q = update.callback_query; await q.answer("🔍 Mencari...")
    scripts = find_user_scripts()
    chunk, pg, pages = paginate(scripts, page, 12)
    rows = []
    for s in chunk:
        ico   = "🐍" if s.suffix == ".py" else "📜"
        label = trunc(f"{ico} {s.name}", 34)
        enc = path_token(s)
        rows.append([btn(label, f"sc:file:{enc}")])
    nav_r = []
    if pg > 0: nav_r.append(btn("◀ Prev", f"sc:list:{pg - 1}"))
    if pg < pages - 1: nav_r.append(btn("Next ▶", f"sc:list:{pg + 1}"))
    if nav_r: rows.append(nav_r)
    rows.append([btn("🔄 Refresh", f"sc:list:{pg}"),
                 btn("🏠 Main", "main:menu")])
    await q.edit_message_text(
        f"📜 *Find Scripts* — {len(scripts)} file — Hal {pg + 1}/{pages}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=kb(rows))

@owner_only
async def cb_sc_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE, path: str):
    q = update.callback_query; await q.answer()
    sp  = Path(path)
    running_pid = find_running_pid(path)
    try: size = fmt_bytes(sp.stat().st_size)
    except: size = "?"
    status = f"🟢 Running PID `{running_pid}`" if running_pid else "⚫ Tidak berjalan"
    log_f  = str(NOHUP_LOG_DIR / f"{sp.stem}.log")
    txt = (
        f"📄 *{sp.name}*\n"
        f"📂 `{sp.parent}`\n"
        f"Size  : `{size}`\n"
        f"Status: {status}\n"
        f"Log   : `{log_f}`"
    )
    enc = path_token(sp)
    rows = [
        [btn("▶️ Run Hidden",  f"sc:run:{enc}"),
         btn("🔁 Restart",      f"sc:rst:{enc}")],
        [btn("🔴 Kill",         f"sc:killpath:{enc}"),
         btn("📋 Log",          f"sc:log:{enc}")],
        [btn("⬇️ Download",     f"sc:dl:{enc}")],
        [btn("◀ Back",          "sc:list:0")],
    ]
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=kb(rows))

@owner_only
async def cb_sc_run(update: Update, ctx: ContextTypes.DEFAULT_TYPE, path: str):
    q = update.callback_query; await q.answer("▶️ Menjalankan...")
    r = nohup_run(path)
    txt = (
        f"✅ *Script Dijalankan*\n"
        f"File: `{Path(path).name}`\n"
        f"PID : `{r.get('pid', 'unknown')}`\n"
        f"Log : `{r.get('log')}`"
        + (f"\nPID lama: `{r.get('killed')}`" if r.get("killed") else "")
    )
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("🐍 My Scripts", "up:list:0")],
                         [btn("📜 Scripts", "sc:list:0")],
                         [btn("🏠 Main", "main:menu")]]))

@owner_only
async def cb_sc_restart(update: Update, ctx: ContextTypes.DEFAULT_TYPE, path: str):
    """Restart: cari PID aktif → restart_proc, atau nohup_run baru."""
    q = update.callback_query; await q.answer("🔁 Restarting...")
    sp          = Path(path)
    running_pid = find_running_pid(path)
    r = restart_proc(running_pid, path) if running_pid else nohup_run(path)
    txt = (
        f"🔁 *Restart Selesai*\n"
        f"Script  : `{sp.name}`\n"
        f"PID lama: `{running_pid}`\n"
        f"PID baru: `{r.get('pid', 'unknown')}`\n"
        f"Log     : `{r.get('log')}`"
    )
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("🐍 My Scripts", "up:list:0")],
                         [btn("🏠 Main", "main:menu")]]))

@owner_only
async def cb_sc_log(update: Update, ctx: ContextTypes.DEFAULT_TYPE, path: str):
    q = update.callback_query; await q.answer()
    sp  = Path(path)
    lf  = NOHUP_LOG_DIR / f"{sp.stem}.log"
    out = tail_file(lf, 40)
    enc = path_token(sp)
    await q.edit_message_text(
        f"📋 *Log: {sp.name}*\n```\n{out[:3000]}\n```",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("🔄 Refresh", f"sc:log:{enc}")],
                         [btn("◀ Back", f"sc:file:{enc}")],
                         [btn("🏠 Main", "main:menu")]]))

@owner_only
async def cb_sc_killpath(update: Update, ctx: ContextTypes.DEFAULT_TYPE, path: str):
    q = update.callback_query; await q.answer()
    sp = Path(path); killed = []
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            if str(sp) in " ".join(p.info.get("cmdline") or []):
                if p.pid != os.getpid():
                    killed.append(p.pid)
                    kill_process_tree(p.pid)
        except Exception: pass
    enc = path_token(sp)
    txt = (f"✅ `{sp.name}` PID {killed} dihentikan." if killed
           else f"⚠️ Tidak ada proses `{sp.name}` yang berjalan.")
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("◀ Back", f"sc:file:{enc}")],
                         [btn("🏠 Main", "main:menu")]]))

@owner_only
async def cb_sc_dl(update: Update, ctx: ContextTypes.DEFAULT_TYPE, path: str):
    q = update.callback_query
    sp = Path(path)
    if sp.is_file() and sp.stat().st_size < 50 * 1024 * 1024:
        await q.answer("⬇️ Mengirim...")
        with open(sp, "rb") as f:
            await q.message.reply_document(
                InputFile(f, filename=sp.name),
                caption=f"`{sp}`", parse_mode=ParseMode.MARKDOWN)
    else:
        await q.answer("❌ File tidak ditemukan / >50MB.", show_alert=True)

# ── File Manager ──────────────────────────────────────────────────
@owner_only
async def cb_fm_open(update: Update, ctx: ContextTypes.DEFAULT_TYPE, page: int):
    q = update.callback_query; await q.answer()
    path   = get_nav(ctx)
    hidden = get_show_hidden(ctx)
    chunk, pg, pages = list_dir(path, page, hidden)
    rows = []; btns = []
    for e in chunk:
        ico   = "📁" if e.is_dir() else ("🐍" if e.suffix == ".py" else "📄")
        label = trunc(f"{ico} {e.name}", 28)
        name_ref = path_token(e.name)
        data  = (f"fm:cd:{name_ref}:{pg}" if e.is_dir()
                 else f"fm:file:{name_ref}:{pg}")
        btns.append(btn(label, data))
    for i in range(0, len(btns), 2):
        rows.append(btns[i:i + 2])
    nav_r = []
    if pg > 0: nav_r.append(btn("◀", f"fm:open:{pg - 1}"))
    if pg < pages - 1: nav_r.append(btn("▶", f"fm:open:{pg + 1}"))
    if nav_r: rows.append(nav_r)
    hl = "👁 Hide" if hidden else "👁 Hidden"
    rows.append([btn("⬆️ Parent", f"fm:up:{pg}"), btn(hl, "fm:toggle_hidden")])
    rows.append([btn("📝 New File", "fm:new_file"), btn("📁 New Dir", "fm:new_dir")])
    rows.append([btn("📤 Upload", "fm:upload_prompt"),
                 btn("🔄 Refresh", f"fm:open:{pg}")])
    rows.append([btn("🏠 Main", "main:menu")])
    dot = " (+hidden)" if hidden else ""
    txt = (f"📁 *File Manager*{dot}\n"
           f"`{path}`\nHal {pg + 1}/{pages} — {len(chunk)} item")
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=kb(rows))

@owner_only
async def cb_fm_toggle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["show_hidden"] = not get_show_hidden(ctx)
    await cb_fm_open.__wrapped__(update, ctx, 0)

@owner_only
async def cb_fm_cd(update: Update, ctx: ContextTypes.DEFAULT_TYPE,
                   name: str, page: int):
    q = update.callback_query; await q.answer()
    new = get_nav(ctx) / name
    if new.is_dir(): set_nav(ctx, new)
    await cb_fm_open.__wrapped__(update, ctx, 0)

@owner_only
async def cb_fm_up(update: Update, ctx: ContextTypes.DEFAULT_TYPE, page: int):
    q = update.callback_query; await q.answer()
    set_nav(ctx, get_nav(ctx).parent)
    await cb_fm_open.__wrapped__(update, ctx, 0)

@owner_only
async def cb_fm_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE,
                     name: str, page: int):
    q = update.callback_query; await q.answer()
    path      = get_nav(ctx) / name
    try: size = fmt_bytes(path.stat().st_size)
    except: size = "?"
    is_script = name.lower().endswith((".py", ".ps1", ".bat", ".cmd", ".exe"))
    name_ref = path_token(name)
    txt = f"📄 *{name}*\nSize: `{size}`\nPath: `{path}`"
    rows = [
        [btn("⬇️ Download", f"fm:dl:{name_ref}"),
         btn("🗑 Delete",    f"fm:del_ask:{name_ref}")],
        [btn("✏️ Rename",   f"fm:ren_ask:{name_ref}"),
         btn("📤 Upload",   "fm:upload_prompt")],
    ]
    if is_script:
        rows.append([
            btn("▶️ Run Hidden", f"fm:run:{name_ref}"),
            btn("🔁 Restart",     f"fm:restart:{name_ref}"),
        ])
    rows.append([btn("◀ Back", f"fm:open:{page}")])
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
                              reply_markup=kb(rows))

@owner_only
async def cb_fm_dl(update: Update, ctx: ContextTypes.DEFAULT_TYPE, name: str):
    q = update.callback_query; await q.answer("⬇️ Mengirim...")
    path = get_nav(ctx) / name
    if not path.is_file():
        await q.message.reply_text("❌ File tidak ditemukan."); return
    if path.stat().st_size > 50 * 1024 * 1024:
        await q.message.reply_text("❌ File >50MB."); return
    with open(path, "rb") as f:
        await q.message.reply_document(
            InputFile(f, filename=name),
            caption=f"`{path}`", parse_mode=ParseMode.MARKDOWN)

@owner_only
async def cb_fm_del_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE, name: str):
    q = update.callback_query; await q.answer()
    await q.edit_message_text(
        f"⚠️ *Pindahkan `{name}` ke Recycle Bin?*\nFile dapat dipulihkan dari Recycle Bin.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("✅ Ya, Hapus", f"fm:del_ok:{path_token(name)}"),
                          btn("❌ Batal", "fm:open:0")]]))

@owner_only
async def cb_fm_del_ok(update: Update, ctx: ContextTypes.DEFAULT_TYPE, name: str):
    q = update.callback_query; await q.answer()
    path = get_nav(ctx) / name
    try:
        send2trash(str(path))
        await q.edit_message_text(
            f"✅ `{name}` dipindahkan ke Recycle Bin.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb([[btn("📁 File Manager", "fm:open:0")],
                             [btn("🏠 Main", "main:menu")]]))
    except Exception as e:
        await q.edit_message_text(f"❌ Gagal: `{e}`",
            parse_mode=ParseMode.MARKDOWN, reply_markup=menu_back())

@owner_only
async def cb_fm_ren_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE, name: str):
    q = update.callback_query; await q.answer()
    ctx.user_data["await_input"]   = "rename"
    ctx.user_data["rename_target"] = name
    await q.edit_message_text(
        f"✏️ Rename `{name}`\nKirim nama baru:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("❌ Batal", "fm:open:0")]]))

@owner_only
async def cb_fm_new_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["await_input"] = "new_file"
    await q.edit_message_text(
        "📝 *New File* — Kirim nama file (mis: `script.py`):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("❌ Batal", "fm:open:0")]]))

@owner_only
async def cb_fm_new_dir(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["await_input"] = "new_dir"
    await q.edit_message_text(
        "📁 *New Folder* — Kirim nama folder:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("❌ Batal", "fm:open:0")]]))

@owner_only
async def cb_fm_upload_prompt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["await_input"] = "upload"
    path = get_nav(ctx)
    await q.edit_message_text(
        f"📤 *Upload File*\nKirim file ke chat ini.\nTujuan: `{path}`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("❌ Batal", "fm:open:0")]]))

@owner_only
async def cb_fm_run(update: Update, ctx: ContextTypes.DEFAULT_TYPE, name: str):
    """Run a script as a detached/hidden Windows process."""
    q = update.callback_query; await q.answer("🚀 Menjalankan...")
    path = get_nav(ctx) / name
    if not path.is_file():
        await q.edit_message_text("❌ File tidak ditemukan.",
                                  reply_markup=menu_back()); return
    r = nohup_run(str(path))
    txt = (
        f"✅ *Script Dijalankan Tersembunyi*\n"
        f"File: `{name}`\n"
        f"PID : `{r.get('pid', 'unknown')}`\n"
        f"Log : `{r.get('log')}`"
        + (f"\nPID lama: `{r.get('killed')}`" if r.get("killed") else "")
    )
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("🐍 My Scripts", "up:list:0")],
                         [btn("🏠 Main", "main:menu")]]))

@owner_only
async def cb_fm_restart(update: Update, ctx: ContextTypes.DEFAULT_TYPE, name: str):
    """Restart script dari File Manager: temukan PID aktif lalu restart."""
    q = update.callback_query; await q.answer("🔁 Restarting...")
    path        = get_nav(ctx) / name
    running_pid = find_running_pid(str(path))
    r = restart_proc(running_pid, str(path)) if running_pid else nohup_run(str(path))
    txt = (
        f"🔁 *Restart Selesai*\n"
        f"File    : `{name}`\n"
        f"PID lama: `{running_pid}`\n"
        f"PID baru: `{r.get('pid', 'unknown')}`\n"
        f"Log     : `{r.get('log')}`"
    )
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("🐍 My Scripts", "up:list:0")],
                         [btn("🏠 Main", "main:menu")]]))

# ── Terminal ──────────────────────────────────────────────────────
@owner_only
async def cb_terminal_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    rows = []
    for i in range(0, min(len(SHORTCUTS), 16), 2):
        pair = SHORTCUTS[i:i + 2]
        rows.append([btn(s[1], f"ex:run:{i + j}") for j, s in enumerate(pair)])
    rows.append([btn("⌨️ Ketik Perintah Manual", "ex:prompt")])
    rows.append([btn("🏠 Main", "main:menu")])
    cwd = str(get_nav(ctx))
    await q.edit_message_text(
        f"💻 *Terminal*\n📂 CWD: `{cwd}`\nPilih shortcut atau ketik manual:",
        parse_mode=ParseMode.MARKDOWN, reply_markup=kb(rows))

@owner_only
async def cb_terminal_shortcut(update: Update, ctx: ContextTypes.DEFAULT_TYPE, idx: int):
    q = update.callback_query; await q.answer("⏳ Running...")
    if idx < 0 or idx >= len(SHORTCUTS):
        await q.answer("Invalid shortcut", show_alert=True); return
    cmd, label = SHORTCUTS[idx]
    out = safe_exec(cmd, cwd=str(get_nav(ctx)), timeout=20)
    for c in [out[i:i + 3800] for i in range(0, len(out), 3800)]:
        await q.message.reply_text(
            f"*{label}*\n```\n{c}\n```",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb([[btn("💻 Terminal", "ex:menu")],
                             [btn("🏠 Main", "main:menu")]]))

@owner_only
async def cb_terminal_prompt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["await_input"] = "exec_cmd"
    cwd = str(get_nav(ctx))
    await q.edit_message_text(
        f"💻 *Terminal Windows*\n📂 CWD: `{cwd}`\nKirim perintah CMD atau PowerShell:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("💻 Shortcuts", "ex:menu")],
                         [btn("❌ Tutup", "main:menu")]]))

# ── Message Handler ───────────────────────────────────────────────
@owner_only
async def msg_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # ── File upload
    if update.message.document:
        ctx.user_data.pop("await_input", None)
        doc  = update.message.document
        file = await ctx.bot.get_file(doc.file_id)
        dest = get_nav(ctx) / doc.file_name
        await file.download_to_drive(dest)
        await update.message.reply_text(
            f"✅ File diupload:\n`{dest}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb([[btn("📁 File Manager", "fm:open:0")],
                             [btn("🏠 Main", "main:menu")]]))
        log.info(f"Upload: {dest}")
        return

    mode = ctx.user_data.get("await_input")
    text = (update.message.text or "").strip()
    if not text: return
    ctx.user_data.pop("await_input", None)

    if mode in ("exec_cmd", None):
        await update.message.reply_text("⏳ Running...")
        out = safe_exec(text, cwd=str(get_nav(ctx)))
        for c in [out[i:i + 3800] for i in range(0, len(out), 3800)]:
            await update.message.reply_text(
                f"```\n{c}\n```", parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb([[btn("💻 Terminal", "ex:menu")],
                                 [btn("🏠 Main", "main:menu")]]))
        log.info(f"Exec: {text[:100]}")

    elif mode == "kill_pid":
        try:
            pid    = int(text)
            p_name = psutil.Process(pid).name()
            kill_process_tree(pid)
            await update.message.reply_text(
                f"✅ PID `{pid}` (`{p_name}`) dihentikan.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb([[btn("⚙️ Processes", "pm:list:0")],
                                 [btn("🏠 Main", "main:menu")]]))
        except Exception as e:
            await update.message.reply_text(
                f"❌ Gagal: `{e}`", parse_mode=ParseMode.MARKDOWN)

    elif mode == "rename":
        target = ctx.user_data.pop("rename_target", None)
        if target:
            try:
                (get_nav(ctx) / target).rename(get_nav(ctx) / text)
                await update.message.reply_text(
                    f"✅ `{target}` → `{text}`",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=kb([[btn("📁 File Manager", "fm:open:0")]]))
            except Exception as e:
                await update.message.reply_text(
                    f"❌ Gagal: `{e}`", parse_mode=ParseMode.MARKDOWN)

    elif mode == "new_file":
        try:
            (get_nav(ctx) / text).touch()
            await update.message.reply_text(
                f"✅ File `{text}` dibuat.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb([[btn("📁 File Manager", "fm:open:0")]]))
        except Exception as e:
            await update.message.reply_text(
                f"❌ Gagal: `{e}`", parse_mode=ParseMode.MARKDOWN)

    elif mode == "new_dir":
        try:
            (get_nav(ctx) / text).mkdir(parents=True, exist_ok=True)
            await update.message.reply_text(
                f"✅ Folder `{text}` dibuat.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb([[btn("📁 File Manager", "fm:open:0")]]))
        except Exception as e:
            await update.message.reply_text(
                f"❌ Gagal: `{e}`", parse_mode=ParseMode.MARKDOWN)

    elif mode == "upload":
        await update.message.reply_text(
            "⏳ Kirim *file* (bukan teks) ke chat ini.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb([[btn("❌ Batal", "fm:open:0")]]))
        ctx.user_data["await_input"] = "upload"

    elif mode == "svc_cmd":
        match = re.fullmatch(r"(start|stop|restart)\s+([A-Za-z0-9_. -]+)", text, re.I)
        if not match:
            await update.message.reply_text(
                "❌ Format harus: `start NamaService`, `stop NamaService`, atau "
                "`restart NamaService`.", parse_mode=ParseMode.MARKDOWN)
            return
        action, service = match.group(1).lower(), match.group(2).strip()
        if action == "restart":
            out = safe_exec(f'sc.exe stop "{service}" & timeout /t 2 /nobreak >nul & '
                            f'sc.exe start "{service}"', timeout=25)
        else:
            out = safe_exec(f'sc.exe {action} "{service}"', timeout=15)
        await update.message.reply_text(
            f"🔧 `{action} {service}`\n```\n{out[:3500]}\n```",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb([[btn("🔧 Services", "sv:list")],
                             [btn("🏠 Main", "main:menu")]]))

    elif mode == "ip_allow":
        parts_t = text.strip().split("/")
        port = parts_t[0]
        proto = (parts_t[1] if len(parts_t) > 1 else "tcp").upper()
        if not port.isdigit():
            await update.message.reply_text("❌ Port harus angka."); return
        name = f"WindowsControl ALLOW {proto} {port}"
        out = safe_exec(f'netsh advfirewall firewall add rule name="{name}" '
                        f'dir=in action=allow protocol={proto} localport={port}', timeout=12)
        await update.message.reply_text(
            f"✅ *Firewall ALLOW {proto}/{port} ditambahkan*\n```\n{out[:500]}\n```",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb([[btn("🛡 Firewall", "ip:list")], [btn("🏠 Main", "main:menu")]]))

    elif mode == "ip_drop":
        port = text.strip()
        if not port.isdigit():
            await update.message.reply_text("❌ Port harus angka."); return
        name = f"WindowsControl BLOCK TCP {port}"
        out = safe_exec(f'netsh advfirewall firewall add rule name="{name}" '
                        f'dir=in action=block protocol=TCP localport={port}', timeout=12)
        await update.message.reply_text(
            f"🚫 *Firewall BLOCK TCP/{port} ditambahkan*\n```\n{out[:500]}\n```",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb([[btn("🛡 Firewall", "ip:list")], [btn("🏠 Main", "main:menu")]]))

    elif mode == "ip_del":
        port = text.strip()
        if not port.isdigit():
            await update.message.reply_text("❌ Kirim nomor port."); return
        outputs = []
        for rule_name in (f"WindowsControl ALLOW TCP {port}",
                          f"WindowsControl ALLOW UDP {port}",
                          f"WindowsControl BLOCK TCP {port}"):
            outputs.append(safe_exec(f'netsh advfirewall firewall delete rule name="{rule_name}"', timeout=8))
        out = "\n".join(outputs)
        await update.message.reply_text(
            f"🗑 *Rule port {port} dihapus*\n```\n{out[:500]}\n```",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb([[btn("🛡 Firewall", "ip:list")], [btn("🏠 Main", "main:menu")]]))

    elif mode == "cj_add":
        parts_c = text.strip().split()
        if len(parts_c) < 2:
            await update.message.reply_text(
                "❌ Format salah. Contoh:\n`*/5 * * * * python C:\\\\Scripts\\\\bot.py`",
                parse_mode=ParseMode.MARKDOWN); return
        ok, out = cron_add(text.strip())
        icon    = "✅" if ok else "❌"
        await update.message.reply_text(
            f"{icon} *Scheduled Task {'ditambahkan' if ok else 'gagal'}*\n`{text}`\n```\n{out[:300]}\n```",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb([[btn("⏰ Scheduled Tasks", "cj:list")], [btn("🏠 Main", "main:menu")]]))

    elif mode == "cj_del":
        if not text.strip().isdigit():
            await update.message.reply_text("❌ Kirim nomor baris."); return
        ok, out = cron_delete_line(int(text.strip()))
        icon    = "✅" if ok else "❌"
        await update.message.reply_text(
            f"{icon} *Task #{text} {'dihapus' if ok else 'gagal'}*\n```\n{out[:300]}\n```",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb([[btn("⏰ Scheduled Tasks", "cj:list")], [btn("🏠 Main", "main:menu")]]))

    elif mode == "cfg_cpu":
        global ALERT_CPU_THRESH
        if not text.strip().isdigit() or not (1 <= int(text.strip()) <= 99):
            await update.message.reply_text("❌ Nilai harus 1-99."); return
        ALERT_CPU_THRESH = int(text.strip())
        save_runtime_config()
        await update.message.reply_text(
            f"✅ CPU Alert threshold diubah ke `{ALERT_CPU_THRESH}%`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb([[btn("⚙️ Config", "cfg:show")], [btn("🏠 Main", "main:menu")]]))

    elif mode == "cfg_ram":
        global ALERT_RAM_THRESH
        if not text.strip().isdigit() or not (1 <= int(text.strip()) <= 99):
            await update.message.reply_text("❌ Nilai harus 1-99."); return
        ALERT_RAM_THRESH = int(text.strip())
        save_runtime_config()
        await update.message.reply_text(
            f"✅ RAM Alert threshold diubah ke `{ALERT_RAM_THRESH}%`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb([[btn("⚙️ Config", "cfg:show")], [btn("🏠 Main", "main:menu")]]))

    elif mode == "cfg_disk":
        global ALERT_DISK_THRESH
        if not text.strip().isdigit() or not (1 <= int(text.strip()) <= 99):
            await update.message.reply_text("❌ Nilai harus 1-99."); return
        ALERT_DISK_THRESH = int(text.strip())
        save_runtime_config()
        await update.message.reply_text(
            f"✅ Disk Alert threshold diubah ke `{ALERT_DISK_THRESH}%`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb([[btn("⚙️ Config", "cfg:show")], [btn("🏠 Main", "main:menu")]]))

    elif mode == "docker_pull":
        img = text.strip()
        await update.message.reply_text(f"⏳ Pulling `{img}`...", parse_mode=ParseMode.MARKDOWN)
        out = safe_exec(f"docker pull {img} 2>&1", timeout=120)
        await update.message.reply_text(
            f"🐋 *Pull: {img}*\n```\n{out[:2000]}\n```",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb([[btn("🖼 Images", "dk:images")], [btn("🏠 Main", "main:menu")]]))

# ─────────────────────────────────────────────────────────────────
# HELPERS: Docker / iptables / Cron / Config
# ─────────────────────────────────────────────────────────────────

def docker_ok() -> bool:
    return bool(shutil.which("docker"))

def iptables_ok() -> bool:
    return IS_WINDOWS and bool(shutil.which("netsh"))

def get_docker_containers() -> list:
    if not docker_ok(): return []
    out = safe_exec(
        "docker ps -a --format \"{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}\"",
        timeout=10)
    result = []
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) >= 4:
            result.append(dict(
                id=parts[0][:12], name=parts[1], image=parts[2],
                status=parts[3], ports=parts[4] if len(parts) > 4 else "—",
                running="Up" in parts[3],
            ))
    return result

def get_docker_images() -> list:
    if not docker_ok(): return []
    out = safe_exec(
        "docker images --format \"{{.Repository}}:{{.Tag}}|{{.ID}}|{{.Size}}|{{.CreatedSince}}\"",
        timeout=10)
    result = []
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) >= 3:
            result.append(dict(
                repo=parts[0], id=parts[1][:12],
                size=parts[2], created=parts[3] if len(parts) > 3 else "—",
            ))
    return result

def get_iptables_rules(chain: str = "INPUT") -> str:
    if not iptables_ok():
        return "(Windows Defender Firewall tidak tersedia)"
    direction = "Inbound" if chain.upper() == "INPUT" else "Outbound"
    return powershell(
        "$ErrorActionPreference='SilentlyContinue';"
        f"Get-NetFirewallRule -Direction {direction} | Select-Object -First 80 | ForEach-Object {{"
        "$pf=$_ | Get-NetFirewallPortFilter; [pscustomobject]@{Name=$_.DisplayName;Enabled=$_.Enabled;"
        "Action=$_.Action;Protocol=$pf.Protocol;Port=$pf.LocalPort;Profile=$_.Profile}} | "
        "Format-Table -AutoSize | Out-String -Width 240",
        timeout=15)

def get_crontab_raw() -> str:
    jobs = _read_json(TASKS_FILE, [])
    if not jobs:
        return "(belum ada task yang dikelola aplikasi)"
    lines = []
    for i, job in enumerate(jobs, 1):
        query = subprocess.run(["schtasks.exe", "/Query", "/TN", job["name"],
                                "/FO", "LIST"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        status = "aktif" if query.returncode == 0 else "hilang"
        lines.append(f"{i}. [{status}] {job['schedule']}  {job['command']}  ({job['name']})")
    return "\n".join(lines)

def get_crontab_lines() -> list:
    return [l for l in get_crontab_raw().splitlines()
            if l.strip() and not l.startswith("(")]

def _parse_windows_schedule(expression: str) -> tuple[list[str], str, str]:
    """Translate familiar cron/preset syntax into schtasks arguments."""
    exp = expression.strip()
    patterns = [
        (r"^@reboot\s+(.+)$", lambda m: (["/SC", "ONLOGON"], "@reboot", m.group(1))),
        (r"^@startup\s+(.+)$", lambda m: (["/SC", "ONSTART"], "@startup", m.group(1))),
        (r"^@hourly\s+(.+)$", lambda m: (["/SC", "HOURLY", "/MO", "1"], "@hourly", m.group(1))),
        (r"^@daily(?:\s+(\d{1,2}:\d{2}))?\s+(.+)$",
         lambda m: (["/SC", "DAILY", "/ST", m.group(1) or "00:00"],
                    f"@daily {m.group(1) or '00:00'}", m.group(2))),
        (r"^\*/(\d+)\s+\*\s+\*\s+\*\s+\*\s+(.+)$",
         lambda m: (["/SC", "MINUTE", "/MO", str(max(1, min(1439, int(m.group(1)))))],
                    f"setiap {m.group(1)} menit", m.group(2))),
        (r"^(\d{1,2})\s+(\d{1,2})\s+\*\s+\*\s+\*\s+(.+)$",
         lambda m: (["/SC", "DAILY", "/ST", f"{int(m.group(2)):02d}:{int(m.group(1)):02d}"],
                    f"harian {int(m.group(2)):02d}:{int(m.group(1)):02d}", m.group(3))),
        (r"^MINUTE:(\d+)\s+(.+)$", lambda m: (["/SC", "MINUTE", "/MO", m.group(1)],
                                                f"setiap {m.group(1)} menit", m.group(2))),
        (r"^DAILY:(\d{1,2}:\d{2})\s+(.+)$", lambda m: (["/SC", "DAILY", "/ST", m.group(1)],
                                                       f"harian {m.group(1)}", m.group(2))),
        (r"^ONLOGON\s+(.+)$", lambda m: (["/SC", "ONLOGON"], "saat login", m.group(1))),
    ]
    for pattern, build in patterns:
        match = re.match(pattern, exp, re.I)
        if match:
            return build(match)
    raise ValueError("Format jadwal: */5 * * * * perintah, @reboot perintah, "
                     "@hourly perintah, atau @daily 23:30 perintah")

def cron_add(expression: str) -> tuple:
    try:
        schedule_args, schedule_text, command = _parse_windows_schedule(expression)
        digest = hashlib.sha1(expression.encode("utf-8")).hexdigest()[:10]
        task_name = f"WindowsControl User {digest}"
        ps_script = f"& {{ {command} }} *> '{str(NOHUP_LOG_DIR / (digest + '.log')).replace(chr(39), chr(39)*2)}'"
        encoded = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
        task_run = (f'"{shutil.which("powershell.exe") or "powershell.exe"}" '
                    f'-NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand {encoded}')
        args = ["schtasks.exe", "/Create", "/TN", task_name, "/TR", task_run,
                *schedule_args, "/F"]
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        if r.returncode == 0:
            jobs = [j for j in _read_json(TASKS_FILE, []) if j.get("name") != task_name]
            jobs.append({"name": task_name, "schedule": schedule_text,
                         "command": command, "created": datetime.datetime.now().isoformat()})
            _write_json(TASKS_FILE, jobs)
            return True, out or "Scheduled Task dibuat."
        return False, out or f"schtasks exit {r.returncode}"
    except Exception as exc:
        return False, str(exc)

def cron_delete_line(n: int) -> tuple:
    jobs = _read_json(TASKS_FILE, [])
    if n < 1 or n > len(jobs):
        return False, "Nomor task tidak valid"
    job = jobs[n - 1]
    r = subprocess.run(["schtasks.exe", "/Delete", "/TN", job["name"], "/F"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if r.returncode == 0:
        jobs.pop(n - 1)
        _write_json(TASKS_FILE, jobs)
        return True, out or "Task dihapus."
    return False, out or f"schtasks exit {r.returncode}"

# ─────────────────────────────────────────────────────────────────
# TELEGRAM HANDLERS — Docker (dk:)
# ─────────────────────────────────────────────────────────────────

@owner_only
async def cb_docker_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not docker_ok():
        await q.edit_message_text(
            "🐋 *Docker*\n\n❌ Docker tidak terinstal di server ini.",
            parse_mode=ParseMode.MARKDOWN, reply_markup=menu_back())
        return
    containers = get_docker_containers()
    if not containers:
        txt = "🐋 *Docker Containers*\n\n_(tidak ada container)_"
    else:
        lines = []
        for c in containers:
            ico = "🟢" if c["running"] else "⚫"
            lines.append(f"{ico} `{c['name']}` ({c['id']})\n   {c['image'][:35]}\n   {c['status'][:40]}")
        txt = "🐋 *Docker Containers*\n━━━━━━━━━━━━━━━━\n" + "\n\n".join(lines[:8])

    rows = []
    for c in containers[:6]:
        cid = c["id"]
        cnm = trunc(c["name"], 16)
        if c["running"]:
            rows.append([btn(f"⏹ {cnm}", f"dk:stop:{cid}"),
                         btn(f"🔁",       f"dk:restart:{cid}"),
                         btn(f"📋 Log",  f"dk:log:{cid}")])
        else:
            rows.append([btn(f"▶️ {cnm}", f"dk:start:{cid}"),
                         btn(f"🗑 Rm",   f"dk:rm:{cid}")])
    rows.append([btn("🖼 Images",   "dk:images"),
                 btn("📊 Stats",   "dk:stats"),
                 btn("🧹 Prune",   "dk:prune_ask")])
    rows.append([btn("🔄 Refresh", "dk:list"), btn("🏠 Main", "main:menu")])
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=kb(rows))

@owner_only
async def cb_docker_action(update: Update, ctx: ContextTypes.DEFAULT_TYPE,
                            action: str, cid: str):
    q = update.callback_query
    cmds = {"start": "docker start", "stop": "docker stop",
             "restart": "docker restart", "rm": "docker rm"}
    cmd = cmds.get(action)
    if not cmd:
        await q.answer("Unknown action", show_alert=True); return
    await q.answer(f"⏳ {action} {cid}...")
    out = safe_exec(f"{cmd} {cid} 2>&1", timeout=20)
    icon = "✅" if cid in out or out.strip() == cid else "⚠️"
    txt = f"🐋 *Docker {action.title()}*\n`{cid}`\n```\n{out[:500]}\n```"
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("◀ Back", "dk:list")], [btn("🏠 Main", "main:menu")]]))

@owner_only
async def cb_docker_log(update: Update, ctx: ContextTypes.DEFAULT_TYPE, cid: str):
    q = update.callback_query; await q.answer("📋 Mengambil log...")
    out = safe_exec(f"docker logs --tail 50 {cid} 2>&1", timeout=15)
    txt = f"📋 *Log: {cid}*\n```\n{out[:3000]}\n```"
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("🔄 Refresh", f"dk:log:{cid}")],
                         [btn("◀ Back", "dk:list")], [btn("🏠 Main", "main:menu")]]))

@owner_only
async def cb_docker_images(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    images = get_docker_images()
    if not images:
        txt = "🖼 *Docker Images*\n\n_(tidak ada image)_"
    else:
        lines = [f"`{i['id']}` {i['repo'][:36]}\n   Size: {i['size']}  {i['created']}"
                 for i in images[:10]]
        txt = "🖼 *Docker Images*\n━━━━━━━━━━━━━━━━\n" + "\n\n".join(lines)
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("⌨️ Pull Image", "dk:pull_ask")],
                         [btn("🧹 Prune Images", "dk:imgprune_ask")],
                         [btn("◀ Back", "dk:list")], [btn("🏠 Main", "main:menu")]]))

@owner_only
async def cb_docker_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer("📊 Mengambil stats...")
    out = safe_exec("docker stats --no-stream --format "
                    "'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}' 2>&1", timeout=15)
    df  = safe_exec("docker system df 2>&1", timeout=10)
    txt = (f"📊 *Docker Stats*\n```\n{out[:1800]}\n```\n"
           f"💾 *Disk Usage*\n```\n{df[:800]}\n```")
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("🔄 Refresh", "dk:stats")],
                         [btn("◀ Back", "dk:list")], [btn("🏠 Main", "main:menu")]]))

@owner_only
async def cb_docker_prune_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text(
        "🧹 *Docker Prune*\nHapus semua container stopped?\nTindakan ini tidak bisa dibatalkan!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("✅ Ya, Prune", "dk:prune_ok"),
                          btn("❌ Batal", "dk:list")]]))

@owner_only
async def cb_docker_prune_ok(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer("🧹 Pruning...")
    out = safe_exec("docker container prune -f 2>&1 && docker image prune -f 2>&1", timeout=30)
    txt = f"🧹 *Docker Prune Selesai*\n```\n{out[:2000]}\n```"
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("◀ Back", "dk:list")], [btn("🏠 Main", "main:menu")]]))

@owner_only
async def cb_docker_pull_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["await_input"] = "docker_pull"
    await q.edit_message_text(
        "🖼 *Pull Docker Image*\nKirim nama image (mis: `nginx:latest`):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("❌ Batal", "dk:images")]]))

@owner_only
async def cb_docker_imgprune_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text(
        "🧹 *Prune Docker Images*\nHapus semua dangling images?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("✅ Ya", "dk:imgprune_ok"),
                          btn("❌ Batal", "dk:images")]]))

@owner_only
async def cb_docker_imgprune_ok(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer("🧹 Pruning images...")
    out = safe_exec("docker image prune -af 2>&1", timeout=30)
    await q.edit_message_text(
        f"🧹 *Images Pruned*\n```\n{out[:1500]}\n```",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("◀ Back", "dk:images")], [btn("🏠 Main", "main:menu")]]))

# ─────────────────────────────────────────────────────────────────
# TELEGRAM HANDLERS — Windows Defender Firewall (ip: compatibility prefix)
# ─────────────────────────────────────────────────────────────────

@owner_only
async def cb_ip_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    chain = ctx.user_data.get("ip_chain", "INPUT")
    if not iptables_ok():
        await q.edit_message_text(
            "🛡 *Windows Defender Firewall*\n\n❌ Firewall CLI tidak tersedia.",
            parse_mode=ParseMode.MARKDOWN, reply_markup=menu_back())
        return
    out = get_iptables_rules(chain)
    txt = f"🛡 *Windows Defender Firewall — {chain}*\n```\n{out[:2500]}\n```"
    rows = [
        [btn("INPUT",   "ip:chain:INPUT"),
         btn("OUTPUT",  "ip:chain:OUTPUT")],
        [btn("✅ Allow port", "ip:allow_ask"),
         btn("🚫 Block port", "ip:drop_ask")],
        [btn("🗑 Hapus port", "ip:del_ask"),
         btn("💾 Status", "ip:save")],
        [btn("🔄 Refresh",     "ip:list"),
         btn("🧹 Hapus rule aplikasi", "ip:flush_ask")],
        [btn("🏠 Main", "main:menu")],
    ]
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=kb(rows))

@owner_only
async def cb_ip_chain(update: Update, ctx: ContextTypes.DEFAULT_TYPE, chain: str):
    q = update.callback_query; await q.answer()
    ctx.user_data["ip_chain"] = chain
    await cb_ip_list.__wrapped__(update, ctx)

@owner_only
async def cb_ip_allow_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["await_input"] = "ip_allow"
    await q.edit_message_text(
        "✅ *Allow port*\nKirim nomor port (mis: `8080`) atau `port/proto` (mis: `53/udp`):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("❌ Batal", "ip:list")]]))

@owner_only
async def cb_ip_drop_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["await_input"] = "ip_drop"
    await q.edit_message_text(
        "🚫 *Block port*\nKirim nomor port TCP yang akan diblokir:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("❌ Batal", "ip:list")]]))

@owner_only
async def cb_ip_del_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["await_input"] = "ip_del"
    chain = ctx.user_data.get("ip_chain", "INPUT")
    out = get_iptables_rules(chain)
    await q.edit_message_text(
        f"🗑 *Hapus Rule Port — {chain}*\n```\n{out[:1200]}\n```\n\n"
        "Kirim nomor port. Aplikasi hanya menghapus rule yang dibuat melalui Windows Control:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("❌ Batal", "ip:list")]]))

@owner_only
async def cb_ip_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer("🛡 Membaca status...")
    out = safe_exec("netsh advfirewall show allprofiles state", timeout=10)
    txt = f"🛡 *Status Windows Firewall*\n```\n{out[:1000]}\n```\nRule Windows tersimpan otomatis."
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("◀ Back", "ip:list")], [btn("🏠 Main", "main:menu")]]))

@owner_only
async def cb_ip_flush_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text(
        "⚠️ *Hapus Rule Windows Control*\n\nHanya rule dengan nama `WindowsControl ...` "
        "yang akan dihapus. Rule aplikasi lain tidak disentuh. Lanjutkan?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("🧹 Ya, Hapus", "ip:flush_ok"),
                          btn("❌ Batal", "ip:list")]]))

@owner_only
async def cb_ip_flush_ok(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer("🧹 Menghapus...")
    out = powershell("Get-NetFirewallRule -DisplayName 'WindowsControl*' -ErrorAction SilentlyContinue | Remove-NetFirewallRule", timeout=15)
    txt = f"🧹 *Rule Windows Control dihapus*\n```\n{out[:800]}\n```"
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("◀ Back", "ip:list")], [btn("🏠 Main", "main:menu")]]))

# ─────────────────────────────────────────────────────────────────
# TELEGRAM HANDLERS — Windows Scheduled Tasks (cj: compatibility prefix)
# ─────────────────────────────────────────────────────────────────

@owner_only
async def cb_cron_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    raw   = get_crontab_raw()
    jobs  = get_crontab_lines()
    txt = (
        f"⏰ *Windows Scheduled Tasks*\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"```\n{raw[:2000]}\n```\n"
        f"Total: `{len(jobs)}` task dikelola aplikasi"
    )
    startup = scheduled_task_status()
    txt += f"\nStartup `{TASK_NAME}`: `{'terpasang' if startup['installed'] else 'belum terpasang'}`"
    rows = [
        [btn("➕ Tambah Job",  "cj:add_ask"),
         btn("🗑 Hapus Job",   "cj:del_ask")],
        [btn("📋 Task History", "cj:log"),
         btn("🪟 Startup Task", "cj:etccron")],
        [btn("🔄 Refresh",    "cj:list"), btn("🏠 Main", "main:menu")],
    ]
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=kb(rows))

@owner_only
async def cb_cron_add_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["await_input"] = "cj_add"
    await q.edit_message_text(
        "➕ *Tambah Windows Scheduled Task*\n\n"
        "Format kompatibel dan preset Windows:\n\n"
        "Contoh:\n"
        "`*/5 * * * * python C:\\\\Scripts\\\\bot.py`\n"
        "`@daily 02:00 python C:\\\\Scripts\\\\backup.py`\n"
        "`@reboot python C:\\\\Scripts\\\\bot.py`\n\n"
        "Kirim jadwal dan perintah:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("❌ Batal", "cj:list")]]))

@owner_only
async def cb_cron_del_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    jobs = get_crontab_lines()
    if not jobs:
        await q.edit_message_text("⚠️ Tidak ada scheduled task yang bisa dihapus.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb([[btn("◀ Back", "cj:list")]])); return
    lines = "\n".join(f"`{i+1}.` `{trunc(j, 50)}`" for i, j in enumerate(jobs))
    ctx.user_data["await_input"] = "cj_del"
    await q.edit_message_text(
        f"🗑 *Hapus Scheduled Task*\n\n{lines}\n\nKirim nomor task yang akan dihapus:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("❌ Batal", "cj:list")]]))

@owner_only
async def cb_cron_log(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    out = powershell("Get-WinEvent -LogName 'Microsoft-Windows-TaskScheduler/Operational' "
                     "-MaxEvents 40 -ErrorAction SilentlyContinue | Select TimeCreated,Id,LevelDisplayName,Message | Format-Table -Wrap | Out-String -Width 200", timeout=15)
    await q.edit_message_text(
        f"📋 *Task Scheduler History*\n```\n{out[:3000]}\n```",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("🔄 Refresh", "cj:log")],
                         [btn("◀ Back", "cj:list")], [btn("🏠 Main", "main:menu")]]))

@owner_only
async def cb_cron_etccron(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    status = scheduled_task_status()
    out = status.get("detail") or status.get("status")
    await q.edit_message_text(
        f"🪟 *Startup Task: {TASK_NAME}*\nStatus: `{status.get('status')}`\n```\n{out[:2500]}\n```",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("◀ Back", "cj:list")], [btn("🏠 Main", "main:menu")]]))

# ─────────────────────────────────────────────────────────────────
# TELEGRAM HANDLERS — Config (cfg:)
# ─────────────────────────────────────────────────────────────────

@owner_only
async def cb_cfg_show(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ip   = get_local_ip()
    al   = "✅ Aktif" if ALERTS_ENABLED else "❌ Mati"
    txt = (
        f"⚙️ *Windows Control Config*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 IP / Port   : `{ip}:{WEB_PORT}`\n"
        f"🔑 Web Token   : `{DASH_TOKEN}`\n"
        f"👤 Owner ID    : `{OWNER_ID}`\n"
        f"📁 Script Logs : `{NOHUP_LOG_DIR}`\n"
        f"📋 App Log     : `{LOG_FILE}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🚨 Alerts      : {al}\n"
        f"🔥 CPU thresh  : `{ALERT_CPU_THRESH}%`\n"
        f"🧠 RAM thresh  : `{ALERT_RAM_THRESH}%`\n"
        f"💾 Disk thresh : `{ALERT_DISK_THRESH}%`\n"
        f"⏱ Cooldown    : `{ALERT_COOLDOWN}s`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🐋 Docker      : {'✅' if docker_ok() else '❌'}\n"
        f"🛡 Firewall    : {'✅' if iptables_ok() else '❌'}\n"
        f"🪟 Startup Task: {'✅' if scheduled_task_status().get('installed') else '❌'}\n"
        f"🐍 Python      : `{platform.python_version()}`"
    )
    rows = [
        [btn("🔥 Set CPU thresh",  "cfg:cpu_ask"),
         btn("🧠 Set RAM thresh",  "cfg:ram_ask")],
        [btn("💾 Set Disk thresh", "cfg:disk_ask"),
         btn("🔄 Restart Bot",     "cfg:restart_ask")],
        [btn("📋 View App Log",    "cfg:log"),
         btn("🗑 Hapus Log",       "cfg:clearlog_ask")],
        [btn("🔄 Refresh", "cfg:show"), btn("🏠 Main", "main:menu")],
    ]
    await q.edit_message_text(txt, parse_mode=ParseMode.MARKDOWN, reply_markup=kb(rows))

@owner_only
async def cb_cfg_cpu_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["await_input"] = "cfg_cpu"
    await q.edit_message_text(
        f"🔥 *Set CPU Alert Threshold*\nSekarang: `{ALERT_CPU_THRESH}%`\nKirim nilai baru (1-99):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("❌ Batal", "cfg:show")]]))

@owner_only
async def cb_cfg_ram_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["await_input"] = "cfg_ram"
    await q.edit_message_text(
        f"🧠 *Set RAM Alert Threshold*\nSekarang: `{ALERT_RAM_THRESH}%`\nKirim nilai baru (1-99):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("❌ Batal", "cfg:show")]]))

@owner_only
async def cb_cfg_disk_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["await_input"] = "cfg_disk"
    await q.edit_message_text(
        f"💾 *Set Disk Alert Threshold*\nSekarang: `{ALERT_DISK_THRESH}%`\nKirim nilai baru (1-99):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("❌ Batal", "cfg:show")]]))

@owner_only
async def cb_cfg_log(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    out = tail_file(LOG_FILE, 50)
    await q.edit_message_text(
        f"📋 *Windows Control Log*\n```\n{out[:3000]}\n```",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("🔄 Refresh", "cfg:log")],
                         [btn("◀ Back", "cfg:show")], [btn("🏠 Main", "main:menu")]]))

@owner_only
async def cb_cfg_clearlog_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text(
        f"🗑 *Hapus App Log*\n`{LOG_FILE}` akan dikosongkan. Lanjutkan?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("✅ Ya, Hapus", "cfg:clearlog_ok"),
                          btn("❌ Batal", "cfg:show")]]))

@owner_only
async def cb_cfg_clearlog_ok(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    try:
        open(LOG_FILE, "w").close()
        msg = "✅ Log berhasil dikosongkan."
    except Exception as e:
        msg = f"❌ Gagal: `{e}`"
    await q.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("◀ Back", "cfg:show")], [btn("🏠 Main", "main:menu")]]))

@owner_only
async def cb_cfg_restart_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text(
        "🔄 *Restart Windows Control*\n\nAplikasi akan direstart tersembunyi.\nLanjutkan?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[btn("✅ Ya, Restart", "cfg:restart_ok"),
                          btn("❌ Batal", "cfg:show")]]))

@owner_only
async def cb_cfg_restart_ok(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer("🔄 Restarting...")
    script = Path(__file__).resolve()
    await q.edit_message_text(
        f"🔄 *Restarting...*\n`{script.name}` akan direstart.\nBot akan kembali dalam beberapa detik.",
        parse_mode=ParseMode.MARKDOWN)
    threading.Thread(target=_delayed_restart, daemon=True).start()

# ─────────────────────────────────────────────────────────────────
# Extended msg_handler (tambah mode baru untuk ip/cj/cfg/docker)
# ─────────────────────────────────────────────────────────────────

# (Ditambahkan di dalam msg_handler yang sudah ada via elif)

# ── Callback Router ───────────────────────────────────────────────
@owner_only
async def cb_router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    data = q.data
    if data == "noop": await q.answer(); return
    parts = data.split(":")
    try:
        # ── static routes
        if   data == "main:menu":  await cb_main_menu.__wrapped__(update, ctx)
        elif data == "help:show":  await cb_help.__wrapped__(update, ctx)
        elif data == "si:info":    await cb_sys_info.__wrapped__(update, ctx)
        elif data == "ls:show":    await cb_live_stats.__wrapped__(update, ctx)
        elif data == "st:info":    await cb_storage.__wrapped__(update, ctx)
        elif data == "nt:info":    await cb_net_info.__wrapped__(update, ctx)
        elif data == "sv:list":    await cb_services.__wrapped__(update, ctx)
        elif data == "sv:prompt":  await cb_sv_prompt.__wrapped__(update, ctx)
        elif data == "al:status":  await cb_alert_status.__wrapped__(update, ctx)
        elif data == "al:toggle":  await cb_alert_toggle.__wrapped__(update, ctx)
        elif data == "al:test":    await cb_alert_test.__wrapped__(update, ctx)

        # ── pm: all processes
        elif parts[0] == "pm":
            if   parts[1] == "list":     await cb_proc_list.__wrapped__(update, ctx, int(parts[2]))
            elif parts[1] == "kill_ask": await cb_proc_kill_ask.__wrapped__(update, ctx)

        # ── up: running user scripts
        elif parts[0] == "up":
            if   parts[1] == "list": await cb_user_procs.__wrapped__(update, ctx, int(parts[2]))
            elif parts[1] == "kill": await cb_up_kill.__wrapped__(update, ctx, int(parts[2]))
            elif parts[1] == "log":  await cb_up_log.__wrapped__(update, ctx, int(parts[2]))
            elif parts[1] == "rst":
                pid    = int(parts[2])
                script = token_path(parts[3])
                await cb_up_restart.__wrapped__(update, ctx, pid, script)

        # ── sc: find scripts
        elif parts[0] == "sc":
            if parts[1] == "list":
                await cb_script_list.__wrapped__(update, ctx, int(parts[2]))
                return
            path = token_path(parts[2])
            if   parts[1] == "file":     await cb_sc_file.__wrapped__(update, ctx, path)
            elif parts[1] == "run":      await cb_sc_run.__wrapped__(update, ctx, path)
            elif parts[1] == "rst":      await cb_sc_restart.__wrapped__(update, ctx, path)
            elif parts[1] == "log":      await cb_sc_log.__wrapped__(update, ctx, path)
            elif parts[1] == "killpath": await cb_sc_killpath.__wrapped__(update, ctx, path)
            elif parts[1] == "dl":       await cb_sc_dl.__wrapped__(update, ctx, path)

        # ── fm: file manager
        elif parts[0] == "fm":
            if   parts[1] == "open":           await cb_fm_open.__wrapped__(update, ctx, int(parts[2]))
            elif parts[1] == "toggle_hidden":   await cb_fm_toggle.__wrapped__(update, ctx)
            elif parts[1] == "cd":              await cb_fm_cd.__wrapped__(update, ctx, token_path(parts[2]), int(parts[3]))
            elif parts[1] == "up":              await cb_fm_up.__wrapped__(update, ctx, int(parts[2]))
            elif parts[1] == "file":            await cb_fm_file.__wrapped__(update, ctx, token_path(parts[2]), int(parts[3]))
            elif parts[1] == "dl":              await cb_fm_dl.__wrapped__(update, ctx, token_path(parts[2]))
            elif parts[1] == "del_ask":         await cb_fm_del_ask.__wrapped__(update, ctx, token_path(parts[2]))
            elif parts[1] == "del_ok":          await cb_fm_del_ok.__wrapped__(update, ctx, token_path(parts[2]))
            elif parts[1] == "ren_ask":         await cb_fm_ren_ask.__wrapped__(update, ctx, token_path(parts[2]))
            elif parts[1] == "new_file":        await cb_fm_new_file.__wrapped__(update, ctx)
            elif parts[1] == "new_dir":         await cb_fm_new_dir.__wrapped__(update, ctx)
            elif parts[1] == "upload_prompt":   await cb_fm_upload_prompt.__wrapped__(update, ctx)
            elif parts[1] == "run":             await cb_fm_run.__wrapped__(update, ctx, token_path(parts[2]))
            elif parts[1] == "restart":         await cb_fm_restart.__wrapped__(update, ctx, token_path(parts[2]))

        # ── ex: terminal
        elif parts[0] == "ex":
            if   parts[1] == "menu":   await cb_terminal_menu.__wrapped__(update, ctx)
            elif parts[1] == "prompt": await cb_terminal_prompt.__wrapped__(update, ctx)
            elif parts[1] == "run":    await cb_terminal_shortcut.__wrapped__(update, ctx, int(parts[2]))

        # ── dk: docker
        elif parts[0] == "dk":
            if   data == "dk:list":            await cb_docker_list.__wrapped__(update, ctx)
            elif data == "dk:images":          await cb_docker_images.__wrapped__(update, ctx)
            elif data == "dk:stats":           await cb_docker_stats.__wrapped__(update, ctx)
            elif data == "dk:prune_ask":       await cb_docker_prune_ask.__wrapped__(update, ctx)
            elif data == "dk:prune_ok":        await cb_docker_prune_ok.__wrapped__(update, ctx)
            elif data == "dk:pull_ask":        await cb_docker_pull_ask.__wrapped__(update, ctx)
            elif data == "dk:imgprune_ask":    await cb_docker_imgprune_ask.__wrapped__(update, ctx)
            elif data == "dk:imgprune_ok":     await cb_docker_imgprune_ok.__wrapped__(update, ctx)
            elif parts[1] in ("start","stop","restart","rm"):
                await cb_docker_action.__wrapped__(update, ctx, parts[1], parts[2])
            elif parts[1] == "log":            await cb_docker_log.__wrapped__(update, ctx, parts[2])

        # ── ip: iptables
        elif parts[0] == "ip":
            if   data == "ip:list":            await cb_ip_list.__wrapped__(update, ctx)
            elif data == "ip:allow_ask":       await cb_ip_allow_ask.__wrapped__(update, ctx)
            elif data == "ip:drop_ask":        await cb_ip_drop_ask.__wrapped__(update, ctx)
            elif data == "ip:del_ask":         await cb_ip_del_ask.__wrapped__(update, ctx)
            elif data == "ip:save":            await cb_ip_save.__wrapped__(update, ctx)
            elif data == "ip:flush_ask":       await cb_ip_flush_ask.__wrapped__(update, ctx)
            elif data == "ip:flush_ok":        await cb_ip_flush_ok.__wrapped__(update, ctx)
            elif parts[1] == "chain":          await cb_ip_chain.__wrapped__(update, ctx, parts[2])

        # ── cj: cron jobs
        elif parts[0] == "cj":
            if   data == "cj:list":            await cb_cron_list.__wrapped__(update, ctx)
            elif data == "cj:add_ask":         await cb_cron_add_ask.__wrapped__(update, ctx)
            elif data == "cj:del_ask":         await cb_cron_del_ask.__wrapped__(update, ctx)
            elif data == "cj:log":             await cb_cron_log.__wrapped__(update, ctx)
            elif data == "cj:etccron":         await cb_cron_etccron.__wrapped__(update, ctx)

        # ── cfg: config
        elif parts[0] == "cfg":
            if   data == "cfg:show":           await cb_cfg_show.__wrapped__(update, ctx)
            elif data == "cfg:cpu_ask":        await cb_cfg_cpu_ask.__wrapped__(update, ctx)
            elif data == "cfg:ram_ask":        await cb_cfg_ram_ask.__wrapped__(update, ctx)
            elif data == "cfg:disk_ask":       await cb_cfg_disk_ask.__wrapped__(update, ctx)
            elif data == "cfg:log":            await cb_cfg_log.__wrapped__(update, ctx)
            elif data == "cfg:clearlog_ask":   await cb_cfg_clearlog_ask.__wrapped__(update, ctx)
            elif data == "cfg:clearlog_ok":    await cb_cfg_clearlog_ok.__wrapped__(update, ctx)
            elif data == "cfg:restart_ask":    await cb_cfg_restart_ask.__wrapped__(update, ctx)
            elif data == "cfg:restart_ok":     await cb_cfg_restart_ok.__wrapped__(update, ctx)

        else:
            await q.answer("Unknown action")

    except Exception as e:
        log.error(f"CB [{data}]: {e}\n{traceback.format_exc()}")
        try: await q.answer(f"Error: {str(e)[:100]}", show_alert=True)
        except Exception: pass

# ─────────────────────────────────────────────────────────────────
# 13. FLASK WEB DASHBOARD
# ─────────────────────────────────────────────────────────────────

flask_app = Flask(__name__)
flask_app.secret_key = SECRET_KEY
flask_app.config.update(
    MAX_CONTENT_LENGTH=250 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    PERMANENT_SESSION_LIFETIME=datetime.timedelta(hours=12),
)
_LOGIN_ATTEMPTS: dict[str, deque] = {}

@flask_app.before_request
def web_security_guard():
    if request.method == "POST" and session.get("ok"):
        origin = request.headers.get("Origin")
        if origin and urlparse(origin).netloc != request.host:
            abort(403)

@flask_app.after_request
def web_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.path != "/ping":
        response.headers["Cache-Control"] = "no-store"
    return response

def web_auth(f):
    @wraps(f)
    def dec(*a, **kw):
        if not session.get("ok"): return redirect("/login")
        return f(*a, **kw)
    return dec

# ── CSS (modern dark, mobile-first) ──────────────────────────────
CSS = """<style>
:root{
  --bg:#060c1a;--c:#0c1628;--c2:#111e35;--b:#1a2e4a;
  --a:#4fa3f7;--a2:#7b72f2;--g:#2dd4aa;--r:#f76b6b;
  --y:#f5b942;--p:#c47ff8;--o:#f58542;
  --t:#dde8f8;--m:#7a90b5;--s:#3d5275;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--t);font-family:'Segoe UI',system-ui,sans-serif;min-height:100vh}
a{color:var(--a);text-decoration:none}a:hover{color:var(--t)}
/* NAV */
.nav{background:rgba(6,12,26,.94);backdrop-filter:blur(12px);
  border-bottom:1px solid var(--b);padding:0 20px;
  display:flex;align-items:center;height:50px;
  position:sticky;top:0;z-index:100}
.logo{font-weight:800;color:var(--a);font-size:.95rem;white-space:nowrap;margin-right:20px;letter-spacing:-.2px}
.logo span{color:var(--g)}
.nav-links{display:flex;align-items:center;gap:2px;flex:1;overflow-x:auto}
.nav-links::-webkit-scrollbar{display:none}
.nav-links a{color:var(--m);font-size:.76rem;padding:5px 9px;border-radius:6px;white-space:nowrap;transition:.13s}
.nav-links a:hover,.nav-links a.active{color:var(--t);background:var(--c2)}
.nav-ip{margin-left:auto;font-size:.7rem;color:var(--s);white-space:nowrap;padding-left:14px}
/* LAYOUT */
.con{max-width:1360px;margin:0 auto;padding:20px 16px}
/* GRIDS */
.grid{display:grid;gap:14px;margin-bottom:20px}
.g4{grid-template-columns:repeat(auto-fit,minmax(190px,1fr))}
.g3{grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.g2{grid-template-columns:repeat(auto-fit,minmax(370px,1fr))}
/* METRIC CARD */
.card{background:var(--c);border:1px solid var(--b);border-radius:10px;
  padding:16px 18px;position:relative;overflow:hidden;transition:.2s}
.card:hover{border-color:var(--s)}
.card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:var(--grad,var(--a))}
.c-cpu::before{--grad:linear-gradient(90deg,var(--r),var(--o))}
.c-ram::before{--grad:linear-gradient(90deg,var(--a),var(--a2))}
.c-disk::before{--grad:linear-gradient(90deg,var(--y),var(--o))}
.c-net::before{--grad:linear-gradient(90deg,var(--g),var(--a))}
.c-swap::before{--grad:linear-gradient(90deg,var(--a2),var(--p))}
.card h3{font-size:.65rem;text-transform:uppercase;letter-spacing:.08em;
  color:var(--m);margin-bottom:8px;font-weight:600}
.val{font-size:1.9rem;font-weight:800;line-height:1}
.sub{font-size:.72rem;color:var(--m);margin-top:4px}
.bar{height:4px;background:var(--b);border-radius:2px;margin-top:11px;overflow:hidden}
.bar div{height:100%;border-radius:2px;transition:width .4s ease}
/* SECTION */
.sec{background:var(--c);border:1px solid var(--b);border-radius:10px;
  margin-bottom:18px;overflow:hidden}
.sh{padding:12px 16px;border-bottom:1px solid var(--b);font-weight:700;
  font-size:.86rem;display:flex;align-items:center;justify-content:space-between;gap:10px}
.sh-l{display:flex;align-items:center;gap:8px}
.sh-r{display:flex;align-items:center;gap:7px}
/* TABLE */
table{width:100%;border-collapse:collapse;font-size:.78rem}
th{text-align:left;padding:9px 14px;color:var(--m);font-size:.66rem;
  text-transform:uppercase;letter-spacing:.06em;border-bottom:1px solid var(--b);
  font-weight:600;cursor:pointer;user-select:none;white-space:nowrap}
th:hover{color:var(--a)}
td{padding:8px 14px;border-bottom:1px solid #0d1a2e;vertical-align:middle;white-space:nowrap}
tr:last-child td{border-bottom:none}
tr:hover td{background:rgba(255,255,255,.022)}
/* BADGE */
.badge{padding:2px 7px;border-radius:20px;font-size:.64rem;font-weight:700;letter-spacing:.02em}
.bg{background:rgba(45,212,170,.14);color:var(--g)}
.br{background:rgba(247,107,107,.14);color:var(--r)}
.by{background:rgba(245,185,66,.14);color:var(--y)}
.bb{background:rgba(79,163,247,.14);color:var(--a)}
.bx{background:rgba(122,144,181,.1);color:var(--m)}
/* BUTTONS */
.btn{padding:5px 12px;border-radius:6px;border:none;cursor:pointer;font-size:.74rem;
  font-weight:600;transition:.13s;display:inline-flex;align-items:center;gap:4px}
.bd{background:rgba(247,107,107,.14);color:var(--r);border:1px solid rgba(247,107,107,.28)}
.bd:hover{background:rgba(247,107,107,.24)}
.bs{background:rgba(79,163,247,.14);color:var(--a);border:1px solid rgba(79,163,247,.28)}
.bs:hover{background:rgba(79,163,247,.24)}
.bg_{background:rgba(45,212,170,.14);color:var(--g);border:1px solid rgba(45,212,170,.28)}
.bg_:hover{background:rgba(45,212,170,.24)}
.bn{background:var(--b);color:var(--t);border:1px solid var(--s)}
.bn:hover{background:var(--s)}
.by_{background:rgba(245,185,66,.14);color:var(--y);border:1px solid rgba(245,185,66,.28)}
.by_:hover{background:rgba(245,185,66,.24)}
.btn-sm{padding:3px 9px;font-size:.7rem}
/* INPUT */
input,textarea,select{background:#040a14;border:1px solid var(--b);color:var(--t);
  border-radius:6px;padding:7px 11px;font-size:.8rem;outline:none;transition:.15s}
input:focus,textarea:focus,select:focus{border-color:var(--a);box-shadow:0 0 0 2px rgba(79,163,247,.1)}
textarea{font-family:monospace;resize:vertical}
/* TERMINAL */
.term{background:#020810;border-radius:8px;padding:15px;
  font-family:'Cascadia Code','Fira Code',monospace;font-size:.78rem;
  min-height:150px;max-height:480px;overflow-y:auto;color:#4eff91;
  white-space:pre-wrap;word-break:break-all;border:1px solid var(--b);line-height:1.5}
/* FILE ITEM */
.fi{display:flex;align-items:center;padding:8px 14px;border-bottom:1px solid #0d1a2e;
  gap:9px;font-size:.78rem}
.fi:hover{background:rgba(255,255,255,.022)}
.fi:last-child{border-bottom:none}
.fin{flex:1;color:var(--a);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.fid .fin{color:var(--y);font-weight:600}
.fsz{color:var(--m);font-size:.7rem;min-width:65px;text-align:right;white-space:nowrap}
.fac{display:flex;gap:4px;flex-shrink:0}
/* SHORTCUTS */
.sc-btn{padding:5px 10px;border-radius:5px;background:var(--c2);color:var(--m);
  border:1px solid var(--b);cursor:pointer;font-size:.71rem;margin:2px;transition:.13s}
.sc-btn:hover{background:var(--b);color:var(--t)}
/* MISC */
.flex{display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.chart-wrap{padding:14px;height:175px;position:relative}
.path-bar{padding:6px 14px;background:#030910;border-bottom:1px solid var(--b);
  font-family:monospace;font-size:.75rem;color:var(--m);overflow-x:auto;white-space:nowrap}
.dot{width:7px;height:7px;border-radius:50%;display:inline-block;margin-right:4px;vertical-align:middle}
.dot-g{background:var(--g);box-shadow:0 0 5px var(--g)}
.dot-r{background:var(--r);box-shadow:0 0 5px var(--r)}
/* TOAST */
#toast{position:fixed;bottom:18px;right:18px;background:var(--c2);border:1px solid var(--g);
  color:var(--t);padding:9px 16px;border-radius:8px;font-size:.8rem;z-index:999;
  opacity:0;transform:translateY(8px);transition:.22s;pointer-events:none}
#toast.show{opacity:1;transform:translateY(0)}
/* SCROLLBAR */
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--b);border-radius:3px}
/* RESPONSIVE */
@media(max-width:640px){
  .con{padding:12px 9px}.nav{padding:0 10px}
  .nav-links a{font-size:.7rem;padding:4px 6px}
  td,th{padding:7px 9px}.fi{padding:7px 9px}
  .val{font-size:1.5rem}
  .g2,.g3,.g4{grid-template-columns:1fr}
  .sh{align-items:flex-start;flex-wrap:wrap}.sh-r{width:100%;overflow-x:auto}
  .nav-ip{display:none}.logo{margin-right:8px}
  .fac{max-width:46vw;overflow-x:auto}.term{font-size:.71rem}
}
</style>"""

CHART_JS = ('<script src="https://cdnjs.cloudflare.com/ajax/libs/'
            'Chart.js/4.4.1/chart.umd.min.js"></script>')

NAV_LINKS = [
    ("/",           "📊 Dashboard"),
    ("/files",      "📁 Files"),
    ("/my-scripts", "🐍 Scripts"),
    ("/processes",  "⚙️ Procs"),
    ("/terminal",   "💻 Terminal"),
    ("/network",    "🌐 Network"),
    ("/services",   "🔧 Services"),
    ("/docker",     "🐋 Docker"),
    ("/iptables",   "🛡 Firewall"),
    ("/cron",       "⏰ Tasks"),
    ("/logs",       "📜 Logs"),
    ("/config",     "⚙️ Config"),
]

def page(title: str, body: str, extra_head: str = "", active: str = "/") -> str:
    ip   = get_local_ip()
    nav_items = "".join(
        f'<a href="{href}" class="{"active" if href == active else ""}">{label}</a>'
        for href, label in NAV_LINKS
    )
    return (
        f'<!DOCTYPE html><html lang="id"><head>'
        f'<meta charset="UTF-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{h(title)} — Windows Control</title>'
        f'{CSS}{extra_head}</head><body>'
        f'<div class="nav">'
        f'<span class="logo">🪟 Windows<span>Ctrl</span></span>'
        f'<div class="nav-links">{nav_items}</div>'
        f'<span class="nav-ip">🌐 {h(ip)}</span>'
        f'</div>'
        f'<div class="con">{body}</div>'
        f'<div id="toast"></div>'
        f'<script>function toast(msg,ok){{var t=document.getElementById("toast");'
        f't.textContent=msg;t.style.borderColor=ok?"var(--g)":"var(--r)";'
        f't.classList.add("show");setTimeout(()=>t.classList.remove("show"),2600);}}</script>'
        f'</body></html>'
    )

def pbar(pct: float, col: str = None) -> str:
    c = col or ("var(--g)" if pct < 60 else ("var(--y)" if pct < 85 else "var(--r)"))
    return f'<div class="bar"><div style="width:{pct}%;background:{c}"></div></div>'

def badge(text: str, kind: str = "x") -> str:
    return f'<span class="badge b{kind}">{h(text)}</span>'

def status_badge(status: str) -> str:
    m = {"running":"g","sleeping":"b","stopped":"r","zombie":"r","disk-sleep":"y"}
    return badge(status, m.get(status, "x"))

# ── Auth Routes ───────────────────────────────────────────────────
@flask_app.route("/ping")
def w_ping():
    return "pong", 200

@flask_app.route("/login", methods=["GET", "POST"])
def w_login():
    err = ""
    if request.method == "POST":
        ip = request.remote_addr or "unknown"
        now = time.time()
        attempts = _LOGIN_ATTEMPTS.setdefault(ip, deque())
        while attempts and now - attempts[0] > 300:
            attempts.popleft()
        if len(attempts) >= 8:
            return "Terlalu banyak percobaan login. Coba lagi dalam 5 menit.", 429
        supplied = request.form.get("token", "").strip()
        if secrets.compare_digest(supplied, DASH_TOKEN):
            attempts.clear()
            session["ok"] = True
            session.permanent = True
            return redirect("/")
        attempts.append(now)
        err = "Token salah. Coba lagi."
    err_html = f'<p style="color:var(--r);font-size:.8rem;margin-bottom:12px">{h(err)}</p>' if err else ""
    body = f"""
<style>
.lw{{display:flex;align-items:center;justify-content:center;min-height:90vh}}
.lb{{background:var(--c);border:1px solid var(--b);border-radius:12px;padding:38px;
  width:100%;max-width:370px}}
.lb h2{{margin-bottom:4px;font-size:1.15rem}}
.lb p{{color:var(--m);font-size:.78rem;margin-bottom:22px}}
label{{font-size:.73rem;color:var(--m);text-transform:uppercase;letter-spacing:.05em}}
</style>
<div class="lw"><div class="lb">
<h2>🔐 Windows Control</h2>
<p>v5.0 — Login aman dengan access token</p>
{err_html}
<form method="post">
<label>Access Token</label><br>
<input type="password" name="token" placeholder="Token..." autofocus
  style="width:100%;margin:6px 0 16px"><br>
<button type="submit" class="btn bs" style="width:100%;padding:10px;justify-content:center">
  Login →</button>
</form>
<p style="margin-top:16px;font-size:.7rem;color:var(--s)">Token tampil di banner saat script dijalankan</p>
</div></div>"""
    return (f'<!DOCTYPE html><html lang="id"><head><meta charset="UTF-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Login — Windows Control</title>{CSS}</head><body>{body}</body></html>')

@flask_app.route("/logout")
def w_logout():
    session.clear(); return redirect("/login")

# ── Dashboard ─────────────────────────────────────────────────────
@flask_app.route("/")
@web_auth
def w_dashboard():
    si    = sys_info()
    procs = get_all_procs(20)

    def prow(p):
        pid_s  = h(str(p['pid']))
        name_s = h(p['name'])
        user_s = h(p['user'])
        return (
            f"<tr>"
            f"<td><code>{pid_s}</code></td>"
            f"<td style='max-width:155px;overflow:hidden;text-overflow:ellipsis'>{name_s}</td>"
            f"<td style='color:var(--m)'>{user_s}</td>"
            f"<td>{status_badge(p['status'])}</td>"
            f"<td id='cpu-{pid_s}'>{p['cpu']}%</td>"
            f"<td>{h(p['mem'])}</td>"
            f"<td style='color:var(--m)'>{h(p['age'])}</td>"
            f"<td>"
            f'<form method="post" action="/processes/kill" style="display:inline"'
            f' onsubmit="return confirm(\'Kill PID {pid_s}?\');">'
            f'<input type="hidden" name="pid" value="{pid_s}">'
            f'<button class="btn bd btn-sm" type="submit">Kill</button></form>'
            f"</td></tr>"
        )

    proc_rows = "".join(prow(p) for p in procs)

    body = f"""
<div class="grid g4">
<div class="card c-cpu">
  <h3>🔥 CPU Usage</h3>
  <div class="val" id="d-cpu">{si['cpu_pct']}%</div>
  <div class="sub" id="d-cpu-s">{si['cpu_cores']} cores · Load {si['load1']}</div>
  {pbar(si['cpu_pct'])}
</div>
<div class="card c-ram">
  <h3>🧠 RAM Usage</h3>
  <div class="val" id="d-ram">{si['ram_pct']}%</div>
  <div class="sub" id="d-ram-s">{h(si['ram_used'])} / {h(si['ram_total'])}</div>
  {pbar(si['ram_pct'])}
</div>
<div class="card c-disk">
  <h3>💾 Disk Usage</h3>
  <div class="val" id="d-disk">{si['disk_pct']}%</div>
  <div class="sub" id="d-disk-s">{h(si['disk_used'])} / {h(si['disk_total'])} · Free {h(si['disk_free'])}</div>
  {pbar(si['disk_pct'])}
</div>
<div class="card c-net">
  <h3>🌐 Network I/O</h3>
  <div class="val" style="font-size:1.15rem" id="d-ns">↑ {h(si['net_sent'])}</div>
  <div class="sub" id="d-nr">↓ {h(si['net_recv'])}</div>
  <div class="bar"><div id="d-nb" style="width:0%;background:var(--g)"></div></div>
</div>
<div class="card c-swap">
  <h3>🔄 Swap</h3>
  <div class="val" id="d-swap">{si['swap_pct']}%</div>
  <div class="sub" id="d-swap-s">{h(si['swap_used'])} / {h(si['swap_total'])}</div>
  {pbar(si['swap_pct'])}
</div>
<div class="card">
  <h3>⏱ Uptime</h3>
  <div class="val" style="font-size:1.15rem" id="d-uptime">{h(si['uptime'])}</div>
  <div class="sub">{h(si['os'])}</div>
</div>
<div class="card" style="--grad:linear-gradient(90deg,var(--o),var(--y))">
  <h3>📦 Proses</h3>
  <div class="val" id="d-pid">{si['pid_count']}</div>
  <div class="sub">🐍 {h(si['python'])} · {h(si['arch'])}</div>
</div>
<div class="card" style="--grad:linear-gradient(90deg,var(--g),var(--a))">
  <h3>📡 Host · IP</h3>
  <div class="val" style="font-size:.95rem;font-family:monospace" id="d-ip">{h(si['local_ip'])}</div>
  <div class="sub">{h(si['node'])} · {si['cpu_cores_phys']}p/{si['cpu_cores']}l cores</div>
</div>
</div>

<div class="grid g2">
<div class="sec">
  <div class="sh">
    <span class="sh-l">📈 CPU &amp; RAM History</span>
    <span style="font-size:.68rem;color:var(--m)" id="chart-ts">—</span>
  </div>
  <div class="chart-wrap"><canvas id="cr-chart"></canvas></div>
</div>
<div class="sec">
  <div class="sh"><span class="sh-l">📡 Network I/O History</span></div>
  <div class="chart-wrap"><canvas id="net-chart"></canvas></div>
</div>
</div>

<div class="sec">
<div class="sh">
  <span class="sh-l">⚙️ Top Processes</span>
  <div class="sh-r">
    <input id="psrch" placeholder="🔍 Filter..." style="width:145px;padding:4px 9px;font-size:.74rem"
      oninput="filterP(this.value)">
    <span style="font-size:.68rem;color:var(--m)">⟳ auto 8s · sort: klik header</span>
  </div>
</div>
<div style="overflow-x:auto">
<table id="pt">
<thead><tr>
  <th onclick="sP(0)">PID ↕</th><th onclick="sP(1)">Name ↕</th>
  <th>User</th><th>Status</th>
  <th onclick="sP(4)">CPU ↕</th><th onclick="sP(5)">Mem ↕</th>
  <th onclick="sP(6)">Age</th><th>Kill</th>
</tr></thead>
<tbody id="ptb">{proc_rows}</tbody>
</table></div></div>

<script>
const cOpts = (yFmt) => ({{
  responsive:true,maintainAspectRatio:false,animation:{{duration:250}},
  plugins:{{legend:{{labels:{{color:'#7a90b5',font:{{size:11}},boxWidth:12}}}}}},
  scales:{{
    x:{{ticks:{{color:'#3d5275',maxTicksLimit:8,maxRotation:0}},grid:{{color:'#0e1a2e'}}}},
    y:{{ticks:{{color:'#3d5275',callback:yFmt}},grid:{{color:'#0e1a2e'}},min:0}}
  }}
}});
const ds = (l,c,d=[]) => ({{
  label:l,data:d,borderColor:c,backgroundColor:c+'1a',borderWidth:1.5,
  pointRadius:0,fill:true,tension:.32
}});
const crChart = new Chart(document.getElementById('cr-chart').getContext('2d'),{{
  type:'line',
  data:{{labels:[],datasets:[ds('CPU %','#f76b6b'),ds('RAM %','#4fa3f7')]}},
  options:cOpts(v=>v+'%')
}});
const netChart = new Chart(document.getElementById('net-chart').getContext('2d'),{{
  type:'line',
  data:{{labels:[],datasets:[ds('↑ Sent','#2dd4aa'),ds('↓ Recv','#c47ff8')]}},
  options:cOpts(v=>v>1048576?(v/1048576).toFixed(1)+'M/s':v>1024?(v/1024).toFixed(0)+'K/s':v+'B/s')
}});
async function rfStats(){{
  try{{
    const d=await(await fetch('/api/stats')).json();
    document.getElementById('d-cpu').textContent=d.cpu_pct+'%';
    document.getElementById('d-cpu-s').textContent=d.cpu_cores+' cores · Load '+d.load1;
    document.getElementById('d-ram').textContent=d.ram_pct+'%';
    document.getElementById('d-ram-s').textContent=d.ram_used+' / '+d.ram_total;
    document.getElementById('d-disk').textContent=d.disk_pct+'%';
    document.getElementById('d-disk-s').textContent=d.disk_used+' / '+d.disk_total+' · Free '+d.disk_free;
    document.getElementById('d-ns').textContent='↑ '+d.net_sent;
    document.getElementById('d-nr').textContent='↓ '+d.net_recv;
    document.getElementById('d-swap').textContent=d.swap_pct+'%';
    document.getElementById('d-swap-s').textContent=d.swap_used+' / '+d.swap_total;
    document.getElementById('d-uptime').textContent=d.uptime;
    document.getElementById('d-pid').textContent=d.pid_count;
  }}catch(e){{}}
}}
async function rfHistory(){{
  try{{
    const d=await(await fetch('/api/history')).json();
    crChart.data.labels=d.labels;
    crChart.data.datasets[0].data=d.cpu;
    crChart.data.datasets[1].data=d.ram;
    crChart.update('none');
    netChart.data.labels=d.labels;
    netChart.data.datasets[0].data=d.net_s;
    netChart.data.datasets[1].data=d.net_r;
    netChart.update('none');
    document.getElementById('chart-ts').textContent='⟳ '+new Date().toLocaleTimeString();
  }}catch(e){{}}
}}
let pd=1,pc=4;
function sP(col){{
  const tb=document.getElementById('ptb');
  const rs=Array.from(tb.querySelectorAll('tr'));
  pd=(col===pc)?-pd:1;pc=col;
  rs.sort((a,b)=>{{
    const av=(a.cells[col]?.textContent||'').trim().replace(/[%,]/g,'');
    const bv=(b.cells[col]?.textContent||'').trim().replace(/[%,]/g,'');
    const an=parseFloat(av),bn=parseFloat(bv);
    return pd*(isNaN(an)||isNaN(bn)?av.localeCompare(bv):an-bn);
  }});
  rs.forEach(r=>tb.appendChild(r));
}}
function filterP(q){{
  const l=q.toLowerCase();
  document.querySelectorAll('#ptb tr').forEach(r=>{{
    r.style.display=r.textContent.toLowerCase().includes(l)?'':'none';
  }});
}}
setInterval(rfStats,4000);setInterval(rfHistory,5000);
rfStats();rfHistory();
</script>"""
    return page("Dashboard", body, extra_head=CHART_JS)

# ── Files ─────────────────────────────────────────────────────────
@flask_app.route("/files")
@web_auth
def w_files():
    cwd    = request.args.get("path", str(Path.home()))
    show_h = request.args.get("hidden", "0") == "1"
    p = Path(cwd)
    if not p.is_dir(): p = Path.home()
    entries = []
    try:
        for e in sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
            if not show_h and is_hidden_path(e): continue
            try: sz = fmt_bytes(e.stat().st_size) if e.is_file() else "—"
            except: sz = "?"
            entries.append(dict(name=e.name, path=str(e),
                                is_dir=e.is_dir(), size=sz, suffix=e.suffix))
    except PermissionError: pass

    parent = str(p.parent) if p.parent != p else None
    tl     = "0" if show_h else "1"
    tl_lbl = "👁 Hide Hidden" if show_h else "👁 Show Hidden"
    rows   = ""

    if parent:
        rows += (f'<div class="fi fid"><span>📁</span>'
                 f'<a class="fin" href="/files?path={urlquote(parent)}">.. (parent)</a>'
                 f'<span class="fsz">—</span><div class="fac"></div></div>')

    for e in entries:
        ep   = h(e["path"])
        ep_url = urlquote(e["path"])
        en   = h(e["name"])
        cp   = h(str(p))
        if e["is_dir"]:
            ico  = "📁"
            nm   = f'<a class="fin" href="/files?path={ep_url}">{en}</a>'
            acts = (f'<form method="post" action="/files/delete" style="display:inline"'
                    f' onsubmit="return confirm(\'Hapus {en}?\')">'
                    f'<input type="hidden" name="path" value="{ep}">'
                    f'<input type="hidden" name="cwd" value="{cp}">'
                    f'<button class="btn bd btn-sm" type="submit">🗑</button></form>')
            rows += (f'<div class="fi fid"><span>{ico}</span>{nm}'
                     f'<span class="fsz">{h(e["size"])}</span>'
                     f'<div class="fac">{acts}</div></div>')
        else:
            ico = "🐍" if e["suffix"] == ".py" else "⚡" if e["suffix"] in (".ps1", ".bat", ".cmd") else "📄"
            nm  = f'<span class="fin">{en}</span>'
            dl  = (f'<a href="/files/download?path={ep_url}">'
                   f'<button class="btn bg_ btn-sm">⬇</button></a>')
            run = ""
            if e["suffix"] in (".py", ".ps1", ".bat", ".cmd", ".exe"):
                run = (f'<form method="post" action="/files/run" style="display:inline">'
                       f'<input type="hidden" name="path" value="{ep}">'
                       f'<button class="btn bs btn-sm" type="submit">▶</button></form>')
            editable = e["suffix"] in (".py",".ps1",".bat",".cmd",".txt",".md",".conf",".cfg",
                                        ".json",".yaml",".yml",".env",".ini",".log")
            edit = (f'<a href="/editor?path={ep_url}">'
                    f'<button class="btn by_ btn-sm">✏</button></a>') if editable else ""
            rm   = (f'<form method="post" action="/files/delete" style="display:inline"'
                    f' onsubmit="return confirm(\'Hapus {en}?\')">'
                    f'<input type="hidden" name="path" value="{ep}">'
                    f'<input type="hidden" name="cwd" value="{cp}">'
                    f'<button class="btn bd btn-sm" type="submit">🗑</button></form>')
            rows += (f'<div class="fi"><span>{ico}</span>{nm}'
                     f'<span class="fsz">{h(e["size"])}</span>'
                     f'<div class="fac">{dl}{run}{edit}{rm}</div></div>')

    n = len(entries)
    drive_links = "".join(
        f'<a href="/files?path={urlquote(d.mountpoint)}"><button class="btn bn btn-sm">'
        f'💾 {h(d.mountpoint)}</button></a>'
        for d in psutil.disk_partitions(all=False)
    )
    body = f"""
<div class="sec">
<div class="sh">
  <span class="sh-l">📁 File Manager
    <span style="color:var(--m);font-size:.73rem">({n} item)</span>
  </span>
  <div class="sh-r">
    {drive_links}
    <a href="/files?path={urlquote(str(p))}&hidden={tl}">
      <button class="btn bn btn-sm">{tl_lbl}</button></a>
  </div>
</div>
<div class="path-bar">
  <form method="get" action="/files" class="flex">
    <span>📂</span><input name="path" value="{h(str(p))}" style="flex:1;font-family:monospace;padding:4px 8px">
    <button class="btn bn btn-sm" type="submit">Buka</button>
  </form>
</div>
{rows}
<div style="padding:12px 14px;border-top:1px solid var(--b);display:flex;gap:10px;flex-wrap:wrap;align-items:center">
  <form method="post" action="/files/mkdir" class="flex">
    <input type="hidden" name="cwd" value="{h(str(p))}">
    <input name="name" placeholder="Nama folder baru..." style="width:155px">
    <button class="btn bn btn-sm" type="submit">+ Dir</button>
  </form>
  <form method="post" action="/files/upload" enctype="multipart/form-data" class="flex">
    <input type="hidden" name="cwd" value="{h(str(p))}">
    <input type="file" name="file" style="font-size:.74rem">
    <button class="btn bs btn-sm" type="submit">⬆ Upload</button>
  </form>
</div>
</div>"""
    return page("File Manager", body, active="/files")

@flask_app.route("/files/download")
@web_auth
def w_file_dl():
    p = Path(request.args.get("path", ""))
    if not p.is_file(): abort(404)
    return send_file(p, as_attachment=True, download_name=p.name)

@flask_app.route("/files/upload", methods=["POST"])
@web_auth
def w_file_upload():
    cwd  = request.form.get("cwd", str(Path.home()))
    file = request.files.get("file")
    if file and file.filename:
        dest = Path(cwd) / Path(file.filename).name
        file.save(dest)
    return redirect(f"/files?path={urlquote(cwd)}")

@flask_app.route("/files/delete", methods=["POST"])
@web_auth
def w_file_delete():
    path = request.form.get("path", "")
    cwd  = request.form.get("cwd", str(Path.home()))
    try:
        pp = Path(path)
        send2trash(str(pp))
    except Exception: pass
    return redirect(f"/files?path={urlquote(cwd)}")

@flask_app.route("/files/mkdir", methods=["POST"])
@web_auth
def w_file_mkdir():
    cwd  = request.form.get("cwd", str(Path.home()))
    name = request.form.get("name", "").strip()
    if name and "/" not in name and "\\" not in name:
        (Path(cwd) / name).mkdir(parents=True, exist_ok=True)
    return redirect(f"/files?path={urlquote(cwd)}")

@flask_app.route("/files/run", methods=["POST"])
@web_auth
def w_file_run():
    path = request.form.get("path", "")
    nohup_run(path)
    return redirect("/my-scripts")

# ── File Editor ───────────────────────────────────────────────────
@flask_app.route("/editor")
@web_auth
def w_editor_get():
    path  = request.args.get("path", "")
    saved = request.args.get("saved", "")
    err   = request.args.get("err", "")
    p     = Path(path)
    if not p.is_file(): abort(404)
    try:
        fsize = p.stat().st_size
        if fsize > 512 * 1024:
            return page("Editor", f'<div class="sec"><div class="sh">❌ File terlalu besar ({fmt_bytes(fsize)}) untuk diedit di browser</div></div>', active="/files")
        content = p.read_text(errors="replace")
    except Exception as ex:
        content = f"# Error membaca file: {ex}"

    lang_map = {"py":"Python","ps1":"PowerShell","bat":"Batch","cmd":"Batch",
                "md":"Markdown","json":"JSON",
                "yaml":"YAML","yml":"YAML","conf":"Config","cfg":"Config",
                "txt":"Text","env":"Env","ini":"INI","log":"Log"}
    lang = lang_map.get(p.suffix.lstrip("."), "Text")
    notif = ""
    if saved:
        notif = '<div style="background:rgba(45,212,170,.12);border:1px solid var(--g);border-radius:6px;padding:8px 14px;margin-bottom:12px;font-size:.8rem;color:var(--g)">✅ File berhasil disimpan!</div>'
    elif err:
        notif = f'<div style="background:rgba(247,107,107,.12);border:1px solid var(--r);border-radius:6px;padding:8px 14px;margin-bottom:12px;font-size:.8rem;color:var(--r)">❌ Error: {h(err)}</div>'

    ep = h(path)
    body = f"""
{notif}
<div class="sec">
<div class="sh">
  <span class="sh-l">✏️ Editor — <code style="font-size:.8rem">{h(p.name)}</code>
    <span class="badge bb" style="margin-left:6px">{lang}</span></span>
  <div class="sh-r">
    <a href="/files?path={urlquote(str(p.parent))}">
      <button class="btn bn btn-sm">◀ Back</button></a>
  </div>
</div>
<div class="path-bar">📂 {h(str(p))}</div>
<form method="post" action="/editor">
  <input type="hidden" name="path" value="{ep}">
  <textarea name="content" id="editor-ta"
    style="width:100%;min-height:520px;border-radius:0;border:none;
      border-bottom:1px solid var(--b);padding:16px;font-size:.8rem;
      background:#020810;color:#4eff91;line-height:1.6">{h(content)}</textarea>
  <div style="padding:11px 14px;display:flex;gap:9px;align-items:center">
    <button type="submit" class="btn bg_">💾 Simpan</button>
    <a href="/files?path={urlquote(str(p.parent))}">
      <button type="button" class="btn bn">❌ Batal</button></a>
    <span style="color:var(--m);font-size:.74rem">Ctrl+S simpan · Tab = 4 spasi</span>
  </div>
</form>
</div>
<script>
const ta=document.getElementById('editor-ta');
document.addEventListener('keydown',e=>{{
  if((e.ctrlKey||e.metaKey)&&e.key==='s'){{e.preventDefault();ta.closest('form').submit();}}
}});
ta.addEventListener('keydown',e=>{{
  if(e.key==='Tab'){{
    e.preventDefault();
    const s=ta.selectionStart,en=ta.selectionEnd;
    ta.value=ta.value.substring(0,s)+'    '+ta.value.substring(en);
    ta.selectionStart=ta.selectionEnd=s+4;
  }}
}});
</script>"""
    return page(f"Editor — {p.name}", body, active="/files")

@flask_app.route("/editor", methods=["POST"])
@web_auth
def w_editor_post():
    path    = request.form.get("path", "")
    content = request.form.get("content", "")
    p = Path(path)
    try:
        p.write_text(content)
        return redirect(f"/editor?path={path}&saved=1")
    except Exception as ex:
        return redirect(f"/editor?path={path}&err={str(ex)[:60]}")

# ── My Scripts ────────────────────────────────────────────────────
@flask_app.route("/my-scripts")
@web_auth
def w_my_scripts():
    procs = get_user_py_procs()
    icons = {"Task Scheduler":"⏰","pythonw":"🪟","python":"🐍"}
    rows  = ""
    for p in procs:
        ico  = icons.get(p["launcher"], "🐍")
        pid  = h(str(p["pid"]))
        sc   = h(p["script"])
        sn   = h(p["script_name"])
        kill = (f'<form method="post" action="/processes/kill" style="display:inline"'
                f' onsubmit="return confirm(\'Kill PID {pid}?\');">'
                f'<input type="hidden" name="pid" value="{pid}">'
                f'<button class="btn bd btn-sm" type="submit">Kill</button></form>')
        rst  = (f'<form method="post" action="/files/run" style="display:inline">'
                f'<input type="hidden" name="path" value="{sc}">'
                f'<button class="btn bs btn-sm" type="submit">🔁</button></form>')
        lf   = h(p["log"])
        logb = f'<a href="/logs?file={lf}"><button class="btn bn btn-sm">📋</button></a>'
        rows += (
            f"<tr><td><code>{pid}</code></td>"
            f"<td>{ico} {sn}</td>"
            f"<td style='max-width:190px;overflow:hidden;text-overflow:ellipsis'>"
            f"<code style='font-size:.7rem;color:var(--m)'>{sc[:58]}</code></td>"
            f"<td>{badge(p['launcher'],'b')}</td>"
            f"<td>{status_badge(p['status'])}</td>"
            f"<td>{p['cpu']}%</td><td>{h(p['mem'])}</td><td>{h(p['age'])}</td>"
            f"<td class='flex'>{kill}{rst}{logb}</td></tr>"
        )
    empty = ("<tr><td colspan='9' style='text-align:center;color:var(--m);padding:22px'>"
             "⚫ Tidak ada script Python yang berjalan</td></tr>" if not rows else "")
    body = f"""
<div class="sec">
<div class="sh">
  <span>🐍 Running Python Scripts</span>
  <span style="font-size:.68rem;color:var(--m)" id="rf-ts">⟳ auto 8s</span>
</div>
<div style="overflow-x:auto">
<table><thead><tr>
  <th>PID</th><th>Script</th><th>Path</th><th>Via</th><th>Status</th>
  <th>CPU</th><th>Mem</th><th>Age</th><th>Actions</th>
</tr></thead>
<tbody>{rows}{empty}</tbody>
</table></div></div>
<script>
setInterval(()=>fetch('/api/my-scripts').then(r=>r.json()).then(ps=>{{
  document.getElementById('rf-ts').textContent=
    '⟳ '+new Date().toLocaleTimeString()+' ('+ps.length+' scripts)';
}}),8000);
</script>"""
    return page("My Scripts", body, active="/my-scripts")

@flask_app.route("/script-log")
@web_auth
def w_script_log():
    path = request.args.get("path", "")
    sp   = Path(path)
    lf   = NOHUP_LOG_DIR / f"{sp.stem}.log"
    content = tail_file(lf, 100)
    body = f"""
<div class="sec">
<div class="sh">
  <span>📋 Log: {h(sp.name)}</span>
  <a href="/script-log?path={urlquote(path)}">
    <button class="btn bn btn-sm">🔄 Refresh</button></a>
</div>
<div class="term">{h(content)}</div>
</div>
<script>document.querySelector('.term').scrollTop=999999;</script>"""
    return page(f"Log — {sp.name}", body, active="/my-scripts")

# ── Processes ─────────────────────────────────────────────────────
@flask_app.route("/processes")
@web_auth
def w_processes():
    procs = get_all_procs(100)
    def _proc_row(p):
        pid_s = h(str(p["pid"]))
        return (
            f"<tr><td><code>{pid_s}</code></td>"
            f"<td>{h(p['name'])}</td><td style='color:var(--m)'>{h(p['user'])}</td>"
            f"<td>{status_badge(p['status'])}</td>"
            f"<td>{p['cpu']}%</td><td>{h(p['mem'])}</td>"
            f"<td style='color:var(--m)'>{h(p['age'])}</td>"
            f"<td>"
            f'<form method="post" action="/processes/kill" style="display:inline"'
            f' onsubmit="return confirm(\'Kill PID {pid_s}?\');">'
            f'<input type="hidden" name="pid" value="{pid_s}">'
            f'<button class="btn bd btn-sm" type="submit">Kill</button></form>'
            f"</td></tr>"
        )
    rows = "".join(_proc_row(p) for p in procs)
    body = f"""
<div class="sec">
<div class="sh">
  <span>⚙️ All Processes ({len(procs)})</span>
  <div class="sh-r">
    <input id="psrch" placeholder="🔍 Filter..." style="width:145px;padding:4px 9px;font-size:.74rem"
      oninput="filterP(this.value)">
    <span style="font-size:.68rem;color:var(--m)">sort: klik header</span>
  </div>
</div>
<div style="overflow-x:auto">
<table id="pt"><thead><tr>
  <th onclick="sP(0)">PID ↕</th><th onclick="sP(1)">Name ↕</th>
  <th>User</th><th>Status</th>
  <th onclick="sP(4)">CPU ↕</th><th onclick="sP(5)">Mem ↕</th>
  <th onclick="sP(6)">Age</th><th>Kill</th>
</tr></thead>
<tbody id="ptb">{rows}</tbody>
</table></div></div>
<script>
let pd=1,pc=5;
function sP(col){{
  const tb=document.getElementById('ptb');
  const rs=Array.from(tb.querySelectorAll('tr'));
  pd=(col===pc)?-pd:1;pc=col;
  rs.sort((a,b)=>{{
    const av=(a.cells[col]?.textContent||'').trim().replace(/[%,]/g,'');
    const bv=(b.cells[col]?.textContent||'').trim().replace(/[%,]/g,'');
    const an=parseFloat(av),bn=parseFloat(bv);
    return pd*(isNaN(an)||isNaN(bn)?av.localeCompare(bv):an-bn);
  }});
  rs.forEach(r=>tb.appendChild(r));
}}
function filterP(q){{
  const l=q.toLowerCase();
  document.querySelectorAll('#ptb tr').forEach(r=>{{
    r.style.display=r.textContent.toLowerCase().includes(l)?'':'none';
  }});
}}
</script>"""
    return page("Processes", body, active="/processes")

@flask_app.route("/processes/kill", methods=["POST"])
@web_auth
def w_proc_kill():
    pid = request.form.get("pid", "")
    try: kill_process_tree(int(pid))
    except Exception: pass
    return redirect(request.referrer or "/processes")

# ── Terminal ──────────────────────────────────────────────────────
@flask_app.route("/terminal", methods=["GET", "POST"])
@web_auth
def w_terminal():
    output  = ""
    cmd_val = ""
    cwd = session.get("term_cwd", str(Path.home()))
    if not Path(cwd).is_dir(): cwd = str(Path.home())
    hist = session.get("term_hist", [])

    if request.method == "POST":
        cmd_val = request.form.get("cmd", "").strip()
        if cmd_val:
            if cmd_val.startswith("cd "):
                target = cmd_val[3:].strip().strip("'\"")
                new_p = Path(target)
                if not new_p.is_absolute():
                    new_p = Path(cwd) / new_p
                try:
                    new_p = new_p.resolve()
                    if new_p.is_dir():
                        cwd = str(new_p)
                        session["term_cwd"] = cwd
                        output = f"📂 CWD diubah ke: {cwd}"
                    else:
                        output = f"cd: {target}: bukan direktori"
                except Exception as e:
                    output = f"cd error: {e}"
            else:
                output = safe_exec(cmd_val, cwd=cwd, timeout=30)
            if cmd_val not in hist: hist.insert(0, cmd_val)
            hist = hist[:30]
            session["term_hist"] = hist

    sc_btns = "".join(
        f'<button class="sc-btn" onclick="runCmd(this)" data-cmd="{h(c)}">{h(l)}</button>'
        for c, l in SHORTCUTS
    )
    hist_html = "".join(
        f'<button class="sc-btn" onclick="setCmd(this)" data-cmd="{h(hc)}" title="{h(hc)}">'
        f'{h(trunc(hc, 28))}</button>'
        for hc in hist[:12]
    )
    hist_sec = ""
    if hist_html:
        hist_sec = (f'<div class="sec"><div class="sh">🕐 History</div>'
                    f'<div style="padding:9px;display:flex;flex-wrap:wrap">{hist_html}</div></div>')

    body = f"""
<div class="grid g2">
<div>
<div class="sec" style="margin-bottom:14px">
  <div class="sh">⚡ Quick Commands</div>
  <div style="padding:10px;display:flex;flex-wrap:wrap">{sc_btns}</div>
</div>
{hist_sec}
</div>
<div>
<div class="sec">
  <div class="sh">
    <span>💻 Terminal</span>
    <code style="font-family:monospace;font-size:.72rem;color:var(--m)">📂 {h(cwd)}</code>
  </div>
  <form method="post" id="tf">
    <div style="display:flex;gap:8px;padding:11px;border-bottom:1px solid var(--b)">
      <input name="cmd" id="cmd" placeholder="&gt; perintah CMD / PowerShell..." value="{h(cmd_val)}"
        autocomplete="off" autofocus style="flex:1;font-family:monospace">
      <button type="submit" class="btn bg_">▶ Run</button>
      <a href="/terminal"><button type="button" class="btn bn">Clear</button></a>
    </div>
  </form>
  <div class="term" id="out">{h(output)}</div>
</div>
</div>
</div>
<script>
document.getElementById('out').scrollTop=999999;
document.getElementById('cmd').select();
function runCmd(b){{document.getElementById('cmd').value=b.dataset.cmd;document.getElementById('tf').submit();}}
function setCmd(b){{document.getElementById('cmd').value=b.dataset.cmd;document.getElementById('cmd').focus();}}
document.addEventListener('keydown',e=>{{if(e.ctrlKey&&e.key==='l'){{e.preventDefault();window.location='/terminal';}}}} );
</script>"""
    return page("Terminal", body, active="/terminal")

# ── Network ───────────────────────────────────────────────────────
@flask_app.route("/network")
@web_auth
def w_network():
    ifaces = get_net_interfaces()
    ports  = get_listening_ports()
    try:
        conns = psutil.net_connections(kind="inet")
        n_est = sum(1 for c in conns if c.status == "ESTABLISHED")
        n_tw  = sum(1 for c in conns if c.status == "TIME_WAIT")
        n_tot = len(conns)
    except Exception:
        n_est = n_tw = n_tot = 0

    def _iface_row(i):
        dot    = "dot-g" if i["up"] else "dot-r"
        status = '<span class="badge bg">UP</span>' if i["up"] else '<span class="badge br">DOWN</span>'
        return (
            f"<tr>"
            f"<td><span class='dot {dot}'></span>{h(i['name'])}</td>"
            f"<td><code>{h(i['ip'])}</code></td>"
            f"<td>{status}</td>"
            f"<td>{h(i['speed'])}</td>"
            f"<td>↑ {h(i['sent'])}</td>"
            f"<td>↓ {h(i['recv'])}</td></tr>"
        )

    iface_rows = "".join(_iface_row(i) for i in ifaces)
    port_rows = "".join(
        (f"<tr><td><code>:{p['port']}</code></td>"
         f"<td><code>{h(str(p['ip']))}</code></td>"
         f"<td><code>{h(str(p['pid']))}</code></td>"
         f"<td>{h(str(p['process']))}</td></tr>")
        for p in ports
    )
    body = f"""
<div class="grid g4">
<div class="card"><h3>🌐 Total Sockets</h3>
  <div class="val">{n_tot}</div><div class="sub">Semua koneksi</div></div>
<div class="card"><h3>✅ Established</h3>
  <div class="val" style="color:var(--g)">{n_est}</div><div class="sub">Aktif tersambung</div></div>
<div class="card"><h3>⏳ TIME_WAIT</h3>
  <div class="val" style="color:var(--y)">{n_tw}</div><div class="sub">Sedang menutup</div></div>
<div class="card"><h3>👂 Listening</h3>
  <div class="val" style="color:var(--a)">{len(ports)}</div><div class="sub">Port terbuka</div></div>
</div>

<div class="sec">
<div class="sh"><span>🖧 Network Interfaces</span></div>
<div style="overflow-x:auto">
<table><thead><tr>
  <th>Interface</th><th>IP Address</th><th>Status</th><th>Speed</th><th>Sent</th><th>Received</th>
</tr></thead>
<tbody>{iface_rows or "<tr><td colspan='6' style='text-align:center;color:var(--m);padding:18px'>Tidak ada interface</td></tr>"}</tbody>
</table></div></div>

<div class="sec">
<div class="sh">
  <span>👂 Listening Ports</span>
  <input placeholder="🔍 Filter port / proses..." style="width:175px;padding:4px 9px;font-size:.74rem"
    oninput="filterPort(this.value)">
</div>
<div style="overflow-x:auto">
<table><thead><tr><th>Port</th><th>Bind IP</th><th>PID</th><th>Process</th></tr></thead>
<tbody id="portbody">{port_rows or "<tr><td colspan='4' style='text-align:center;color:var(--m);padding:18px'>Tidak ada listening port</td></tr>"}</tbody>
</table></div></div>

<script>
function filterPort(q){{
  const l=q.toLowerCase();
  document.querySelectorAll('#portbody tr').forEach(r=>{{
    r.style.display=r.textContent.toLowerCase().includes(l)?'':'none';
  }});
}}
</script>"""
    return page("Network", body, active="/network")

# ── Services ──────────────────────────────────────────────────────
@flask_app.route("/services")
@web_auth
def w_services():
    rows = ""
    try:
        svc_items = sorted((s.as_dict() for s in psutil.win_service_iter()),
                           key=lambda item: item.get("name", "").lower())
    except Exception:
        svc_items = []
    for item in svc_items:
        name = item.get("name", "")
        active = item.get("status", "unknown")
        sub = item.get("start_type", "unknown")
        desc = item.get("display_name", name)
        ab = "g" if active == "running" else "r" if active == "stopped" else "y"
        sb = "g" if sub == "automatic" else "x"
        sn = h(name[:44])
        rows += (
            f"<tr>"
            f"<td><code style='font-size:.76rem'>{sn}</code></td>"
            f"<td>{badge(active, ab)}</td>"
            f"<td>{badge(sub, sb)}</td>"
            f"<td style='color:var(--m);font-size:.74rem;max-width:190px;"
            f"overflow:hidden;text-overflow:ellipsis'>{h(desc[:60])}</td>"
            f"<td class='flex'>"
            f'<form method="post" action="/services/action" style="display:inline">'
            f'<input type="hidden" name="svc" value="{sn}">'
            f'<input type="hidden" name="action" value="start">'
            f'<button class="btn bg_ btn-sm" type="submit">Start</button></form>'
            f'<form method="post" action="/services/action" style="display:inline"'
            f' onsubmit="return confirm(\'Stop {sn}?\');">'
            f'<input type="hidden" name="svc" value="{sn}">'
            f'<input type="hidden" name="action" value="stop">'
            f'<button class="btn bd btn-sm" type="submit">Stop</button></form>'
            f'<form method="post" action="/services/action" style="display:inline">'
            f'<input type="hidden" name="svc" value="{sn}">'
            f'<input type="hidden" name="action" value="restart">'
            f'<button class="btn by_ btn-sm" type="submit">↺ Restart</button></form>'
            f"</td></tr>"
        )
    if not rows:
        rows = ("<tr><td colspan='5' style='text-align:center;color:var(--m);padding:22px'>"
                "Windows Services tidak dapat dibaca. Coba jalankan sebagai Administrator.</td></tr>")
    body = f"""
<div class="sec">
<div class="sh">
  <span>🔧 System Services</span>
  <div class="sh-r">
    <input placeholder="🔍 Filter..." style="width:145px;padding:4px 9px;font-size:.74rem"
      oninput="filterSvc(this.value)">
    <a href="/services"><button class="btn bn btn-sm">🔄 Refresh</button></a>
  </div>
</div>
<div style="overflow-x:auto">
<table><thead><tr>
  <th>Service</th><th>Active</th><th>Sub</th><th>Description</th><th>Actions</th>
</tr></thead>
<tbody id="svcb">{rows}</tbody>
</table></div></div>
<script>
function filterSvc(q){{
  const l=q.toLowerCase();
  document.querySelectorAll('#svcb tr').forEach(r=>r.style.display=r.textContent.toLowerCase().includes(l)?'':'none');
}}
</script>"""
    return page("Services", body, active="/services")

@flask_app.route("/services/action", methods=["POST"])
@web_auth
def w_svc_action():
    svc    = request.form.get("svc", "").strip()
    action = request.form.get("action", "").strip()
    if svc and action in ("start", "stop", "restart"):
        svc_safe = re.sub(r"[^a-zA-Z0-9@._ -]", "", svc)
        if action == "restart":
            safe_exec(f'sc.exe stop "{svc_safe}" & timeout /t 2 /nobreak >nul & '
                      f'sc.exe start "{svc_safe}"', timeout=25)
        else:
            safe_exec(f'sc.exe {action} "{svc_safe}"', timeout=15)
    return redirect("/services")

# ── Logs ──────────────────────────────────────────────────────────
LOG_SOURCES = [
    ("system", "Get-WinEvent -LogName System -MaxEvents 150 | Select TimeCreated,Id,LevelDisplayName,ProviderName,Message | Format-Table -Wrap | Out-String -Width 240"),
    ("application", "Get-WinEvent -LogName Application -MaxEvents 150 | Select TimeCreated,Id,LevelDisplayName,ProviderName,Message | Format-Table -Wrap | Out-String -Width 240"),
    ("security", "Get-WinEvent -LogName Security -MaxEvents 100 | Select TimeCreated,Id,LevelDisplayName,Message | Format-Table -Wrap | Out-String -Width 240"),
    ("defender", "Get-WinEvent -LogName 'Microsoft-Windows-Windows Defender/Operational' -MaxEvents 100 | Select TimeCreated,Id,LevelDisplayName,Message | Format-Table -Wrap | Out-String -Width 240"),
    ("tasks", "Get-WinEvent -LogName 'Microsoft-Windows-TaskScheduler/Operational' -MaxEvents 100 | Select TimeCreated,Id,LevelDisplayName,Message | Format-Table -Wrap | Out-String -Width 240"),
    ("sc_log", ""),
    ("script_logs", ""),
]

@flask_app.route("/logs")
@web_auth
def w_logs():
    src    = request.args.get("src", "system")
    grep_q = request.args.get("q", "").strip()
    custom = request.args.get("file", "")

    if custom and Path(custom).is_file():
        src_lbl = Path(custom).name
        content = tail_file(custom, 150)
    else:
        cmd_map = {k: v for k, v in LOG_SOURCES}
        src_lbl = src
        if src == "sc_log":
            content = tail_file(LOG_FILE, 150)
        elif src == "script_logs":
            logs = sorted(NOHUP_LOG_DIR.glob("*.log"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
            content = "\n".join(f"{p.name:<45} {fmt_bytes(p.stat().st_size):>10}  "
                                f"{datetime.datetime.fromtimestamp(p.stat().st_mtime)}"
                                for p in logs[:80]) or "(belum ada log script)"
        else:
            content = powershell(cmd_map.get(src, cmd_map["system"]), timeout=20)
    if grep_q:
        lines   = [l for l in content.splitlines() if grep_q.lower() in l.lower()]
        content = "\n".join(lines) if lines else f"(tidak ada hasil untuk: {grep_q})"

    src_opts = "".join(
        f'<option value="{k}" {"selected" if k == src else ""}>{k}</option>'
        for k, _ in LOG_SOURCES
    )
    body = f"""
<div class="sec">
<div class="sh">
  <span>📜 Log Viewer</span>
  <form method="get" action="/logs" class="flex" style="margin:0">
    <select name="src" style="padding:4px 8px;font-size:.74rem">{src_opts}</select>
    <input name="q" value="{h(grep_q)}" placeholder="🔍 Filter teks..."
      style="width:145px;padding:4px 9px;font-size:.74rem">
    <button type="submit" class="btn bs btn-sm">View</button>
    <a href="/logs?src={h(src)}">
      <button type="button" class="btn bn btn-sm">🔄</button></a>
  </form>
</div>
<div class="path-bar">📋 {h(src_lbl)}{f'  |  grep: {h(grep_q)}' if grep_q else ''}</div>
<div class="term" style="max-height:580px" id="lout">{h(content)}</div>
</div>
<script>document.getElementById('lout').scrollTop=999999;</script>"""
    return page("Logs", body, active="/logs")

# ── Docker Page ───────────────────────────────────────────────────
@flask_app.route("/docker")
@web_auth
def w_docker():
    if not docker_ok():
        body = '<div class="sec"><div class="sh">🐋 Docker</div><div style="padding:24px;color:var(--m)">❌ Docker tidak terinstal di server ini.</div></div>'
        return page("Docker", body, active="/docker")

    containers = get_docker_containers()
    images     = get_docker_images()
    df_out     = safe_exec("docker system df 2>&1", timeout=10)

    def cstatus(c):
        return '<span class="badge bg">Running</span>' if c["running"] else '<span class="badge bx">Stopped</span>'

    c_rows = ""
    for c in containers:
        cid = h(c["id"]); cnm = h(c["name"]); cimg = h(c["image"][:40])
        cst = h(c["status"][:35]); cpo = h(c["ports"][:40])
        if c["running"]:
            acts = (
                f'<form method="post" action="/docker/action" style="display:inline">'
                f'<input type="hidden" name="cid" value="{cid}"><input type="hidden" name="action" value="stop">'
                f'<button class="btn bd btn-sm" type="submit" onclick="return confirm(\'Stop {cnm}?\')">⏹ Stop</button></form>'
                f'<form method="post" action="/docker/action" style="display:inline">'
                f'<input type="hidden" name="cid" value="{cid}"><input type="hidden" name="action" value="restart">'
                f'<button class="btn by_ btn-sm" type="submit">↺ Restart</button></form>'
                f'<a href="/docker/logs?id={cid}"><button class="btn bn btn-sm">📋 Logs</button></a>'
            )
        else:
            acts = (
                f'<form method="post" action="/docker/action" style="display:inline">'
                f'<input type="hidden" name="cid" value="{cid}"><input type="hidden" name="action" value="start">'
                f'<button class="btn bg_ btn-sm" type="submit">▶ Start</button></form>'
                f'<form method="post" action="/docker/action" style="display:inline">'
                f'<input type="hidden" name="cid" value="{cid}"><input type="hidden" name="action" value="rm">'
                f'<button class="btn bd btn-sm" type="submit" onclick="return confirm(\'Remove {cnm}?\')">🗑 Rm</button></form>'
            )
        c_rows += (f"<tr><td><code>{cid}</code></td><td><b>{cnm}</b></td>"
                   f"<td style='color:var(--m)'>{cimg}</td><td>{cstatus(c)}</td>"
                   f"<td style='color:var(--m);font-size:.72rem'>{cst}</td>"
                   f"<td style='color:var(--m);font-size:.7rem'>{cpo}</td>"
                   f"<td class='flex'>{acts}</td></tr>")

    i_rows = "".join(
        f"<tr><td><code>{h(i['id'])}</code></td><td>{h(i['repo'])}</td>"
        f"<td>{h(i['size'])}</td><td style='color:var(--m)'>{h(i['created'])}</td></tr>"
        for i in images
    )

    n_run  = sum(1 for c in containers if c["running"])
    n_stop = len(containers) - n_run

    body = f"""
<div class="grid g4">
<div class="card"><h3>📦 Containers</h3><div class="val">{len(containers)}</div><div class="sub">Total</div></div>
<div class="card"><h3>🟢 Running</h3><div class="val" style="color:var(--g)">{n_run}</div><div class="sub">Aktif</div></div>
<div class="card"><h3>⚫ Stopped</h3><div class="val" style="color:var(--m)">{n_stop}</div><div class="sub">Berhenti</div></div>
<div class="card"><h3>🖼 Images</h3><div class="val" style="color:var(--a)">{len(images)}</div><div class="sub">Tersedia</div></div>
</div>

<div class="sec">
<div class="sh">
  <span>🐋 Containers</span>
  <div class="sh-r">
    <input placeholder="🔍 Filter..." style="width:145px;padding:4px 9px;font-size:.74rem" oninput="filterDk(this.value)">
    <form method="post" action="/docker/prune" style="display:inline" onsubmit="return confirm('Prune semua container stopped?')">
      <button class="btn bd btn-sm" type="submit">🧹 Prune</button></form>
    <a href="/docker"><button class="btn bn btn-sm">🔄</button></a>
  </div>
</div>
<div style="overflow-x:auto">
<table><thead><tr>
  <th>ID</th><th>Name</th><th>Image</th><th>Status</th><th>Info</th><th>Ports</th><th>Actions</th>
</tr></thead>
<tbody id="dkbody">{c_rows or "<tr><td colspan='7' style='text-align:center;color:var(--m);padding:20px'>Tidak ada container</td></tr>"}</tbody>
</table></div></div>

<div class="grid g2">
<div class="sec">
<div class="sh"><span>🖼 Images</span></div>
<div style="overflow-x:auto">
<table><thead><tr><th>ID</th><th>Repository:Tag</th><th>Size</th><th>Created</th></tr></thead>
<tbody>{i_rows or "<tr><td colspan='4' style='text-align:center;color:var(--m);padding:18px'>Tidak ada image</td></tr>"}</tbody>
</table></div></div>

<div class="sec">
<div class="sh"><span>📊 Docker System</span></div>
<div class="term" style="max-height:220px">{h(df_out)}</div>
</div>
</div>

<script>
function filterDk(q){{const l=q.toLowerCase();document.querySelectorAll('#dkbody tr').forEach(r=>r.style.display=r.textContent.toLowerCase().includes(l)?'':'none');}}
</script>"""
    return page("Docker", body, active="/docker")

@flask_app.route("/docker/action", methods=["POST"])
@web_auth
def w_docker_action():
    cid    = re.sub(r"[^a-zA-Z0-9_-]", "", request.form.get("cid", ""))
    action = request.form.get("action", "")
    if cid and action in ("start", "stop", "restart", "rm"):
        safe_exec(f"docker {action} {cid} 2>&1", timeout=20)
    return redirect("/docker")

@flask_app.route("/docker/logs")
@web_auth
def w_docker_logs():
    cid  = re.sub(r"[^a-zA-Z0-9_-]", "", request.args.get("id", ""))
    n    = int(request.args.get("n", 100))
    out  = safe_exec(f"docker logs --tail {n} {cid} 2>&1", timeout=15) if cid else "(no id)"
    body = f"""
<div class="sec">
<div class="sh">
  <span>📋 Docker Logs — <code>{h(cid)}</code></span>
  <div class="sh-r">
    <a href="/docker/logs?id={h(cid)}&n=50"><button class="btn bn btn-sm">50</button></a>
    <a href="/docker/logs?id={h(cid)}&n=200"><button class="btn bn btn-sm">200</button></a>
    <a href="/docker/logs?id={h(cid)}"><button class="btn bn btn-sm">🔄</button></a>
    <a href="/docker"><button class="btn bn btn-sm">◀ Back</button></a>
  </div>
</div>
<div class="term" style="max-height:600px" id="dlogs">{h(out)}</div>
</div>
<script>document.getElementById('dlogs').scrollTop=999999;</script>"""
    return page(f"Docker Logs — {cid}", body, active="/docker")

@flask_app.route("/docker/prune", methods=["POST"])
@web_auth
def w_docker_prune():
    safe_exec("docker container prune -f 2>&1", timeout=30)
    return redirect("/docker")

# ── iptables Page ─────────────────────────────────────────────────
@flask_app.route("/iptables")
@web_auth
def w_iptables():
    chain   = request.args.get("chain", "INPUT")
    safe_ch = chain if chain in ("INPUT", "OUTPUT") else "INPUT"
    raw     = get_iptables_rules(safe_ch)

    saved = request.args.get("saved", "")
    notif = (f'<div style="background:rgba(45,212,170,.12);border:1px solid var(--g);border-radius:6px;'
             f'padding:8px 14px;margin-bottom:12px;color:var(--g);font-size:.8rem">✅ {h(saved)}</div>') if saved else ""

    chain_btns = "".join(
        f'<a href="/iptables?chain={c}"><button class="btn {"bs" if c==safe_ch else "bn"} btn-sm">{c}</button></a>'
        for c in ("INPUT", "OUTPUT")
    )
    body = f"""
{notif}
<div class="grid g3">
<div class="card"><h3>🔗 Active Chain</h3><div class="val" style="font-size:1.2rem">{safe_ch}</div></div>
<div class="card"><h3>📋 Rules</h3><div class="val">{len([l for l in raw.splitlines() if l.strip() and not l.startswith('Chain') and not l.startswith('target')])}</div><div class="sub">baris aktif</div></div>
<div class="card"><h3>🛡 Status</h3><div class="val" style="font-size:1.1rem">{'✅ Active' if iptables_ok() else '❌ N/A'}</div></div>
</div>

<div class="sec">
<div class="sh">
  <span>🛡 Windows Defender Firewall — {safe_ch}</span>
  <div class="sh-r">
    {chain_btns}
    <a href="/iptables?chain={safe_ch}"><button class="btn bn btn-sm">🔄</button></a>
  </div>
</div>
<div class="term" style="max-height:350px">{h(raw)}</div>
</div>

<div class="grid g2">
<div class="sec">
<div class="sh"><span>✅ Tambah ACCEPT Rule</span></div>
<form method="post" action="/iptables/add" style="padding:14px;display:flex;flex-direction:column;gap:10px">
  <input type="hidden" name="target" value="ACCEPT">
  <div class="flex">
    <label style="min-width:70px;font-size:.74rem;color:var(--m)">Port</label>
    <input name="port" placeholder="mis: 8080" style="flex:1">
  </div>
  <div class="flex">
    <label style="min-width:70px;font-size:.74rem;color:var(--m)">Proto</label>
    <select name="proto" style="flex:1">
      <option value="tcp">TCP</option><option value="udp">UDP</option>
    </select>
  </div>
  <div class="flex">
    <label style="min-width:70px;font-size:.74rem;color:var(--m)">Chain</label>
    <select name="chain" style="flex:1">
      <option value="INPUT">Inbound</option><option value="OUTPUT">Outbound</option>
    </select>
  </div>
  <button type="submit" class="btn bg_">✅ Tambah ACCEPT</button>
</form>
</div>

<div class="sec">
<div class="sh"><span>🚫 Tambah DROP Rule</span></div>
<form method="post" action="/iptables/add" style="padding:14px;display:flex;flex-direction:column;gap:10px">
  <input type="hidden" name="target" value="DROP">
  <div class="flex">
    <label style="min-width:70px;font-size:.74rem;color:var(--m)">Port</label>
    <input name="port" placeholder="mis: 23">
  </div>
  <div class="flex">
    <label style="min-width:70px;font-size:.74rem;color:var(--m)">Proto</label>
    <select name="proto" style="flex:1">
      <option value="tcp">TCP</option><option value="udp">UDP</option>
    </select>
  </div>
  <div class="flex">
    <label style="min-width:70px;font-size:.74rem;color:var(--m)">Chain</label>
    <select name="chain" style="flex:1">
      <option value="INPUT">INPUT</option><option value="OUTPUT">OUTPUT</option>
    </select>
  </div>
  <button type="submit" class="btn bd">🚫 Tambah DROP</button>
</form>
</div>
</div>

<div class="grid g2">
<div class="sec">
<div class="sh"><span>🗑 Hapus Rule by Line Number</span></div>
<form method="post" action="/iptables/delete" style="padding:14px;display:flex;gap:9px">
  <select name="chain" style="flex:0 0 120px">
    <option value="INPUT">Inbound</option><option value="OUTPUT">Outbound</option>
  </select>
  <input name="linenum" placeholder="Nomor port" style="flex:1">
  <button type="submit" class="btn bd" onclick="return confirm('Hapus rule ini?')">🗑 Hapus</button>
</form>
</div>
<div class="sec">
<div class="sh"><span>💾 Save &amp; Flush</span></div>
<div style="padding:14px;display:flex;gap:9px;flex-wrap:wrap">
  <form method="post" action="/iptables/save">
    <button type="submit" class="btn bg_">💾 Save Rules</button></form>
  <form method="post" action="/iptables/flush" onsubmit="return confirm('Hapus hanya rule WindowsControl?')">
    <input type="hidden" name="chain" value="INPUT">
    <button type="submit" class="btn bd">🧹 Hapus Rule Aplikasi</button></form>
</div>
</div>
</div>"""
    return page("Windows Firewall", body, active="/iptables")

@flask_app.route("/iptables/add", methods=["POST"])
@web_auth
def w_ip_add():
    target = request.form.get("target", "ACCEPT")
    port   = re.sub(r"[^0-9]", "", request.form.get("port", ""))
    proto  = request.form.get("proto", "tcp")
    chain  = request.form.get("chain", "INPUT")
    if target not in ("ACCEPT", "DROP"): abort(400)
    if chain not in ("INPUT", "OUTPUT"): abort(400)
    if proto not in ("tcp", "udp"): abort(400)
    if not port: return redirect(f"/iptables?saved=Port+kosong")
    direction = "in" if chain == "INPUT" else "out"
    action = "allow" if target == "ACCEPT" else "block"
    label = "ALLOW" if target == "ACCEPT" else "BLOCK"
    name = f"WindowsControl {label} {proto.upper()} {port} {chain}"
    safe_exec(f'netsh advfirewall firewall add rule name="{name}" dir={direction} '
              f'action={action} protocol={proto.upper()} localport={port}', timeout=12)
    return redirect(f"/iptables?chain={chain}&saved={target}+{proto}/{port}+ditambahkan")

@flask_app.route("/iptables/delete", methods=["POST"])
@web_auth
def w_ip_delete():
    chain   = request.form.get("chain", "INPUT")
    linenum = re.sub(r"[^0-9]", "", request.form.get("linenum", ""))
    if chain not in ("INPUT", "OUTPUT"): abort(400)
    if linenum:
        powershell(f"Get-NetFirewallRule -DisplayName 'WindowsControl*{linenum}*{chain}' "
                   "-ErrorAction SilentlyContinue | Remove-NetFirewallRule", timeout=12)
    return redirect(f"/iptables?chain={chain}&saved=Rule+port+{linenum}+dihapus")

@flask_app.route("/iptables/save", methods=["POST"])
@web_auth
def w_ip_save():
    return redirect("/iptables?saved=Windows+menyimpan+rule+secara+otomatis")

@flask_app.route("/iptables/flush", methods=["POST"])
@web_auth
def w_ip_flush():
    powershell("Get-NetFirewallRule -DisplayName 'WindowsControl*' "
               "-ErrorAction SilentlyContinue | Remove-NetFirewallRule", timeout=15)
    return redirect("/iptables?saved=Rule+WindowsControl+dihapus")

# ── Cron Jobs Page ────────────────────────────────────────────────
@flask_app.route("/cron")
@web_auth
def w_cron():
    raw     = get_crontab_raw()
    managed_jobs = _read_json(TASKS_FILE, [])
    jobs = get_crontab_lines()
    startup = scheduled_task_status()
    etc_out = startup.get("detail") or startup.get("status")
    cron_log = powershell(
        "Get-WinEvent -LogName 'Microsoft-Windows-TaskScheduler/Operational' "
        "-MaxEvents 20 -ErrorAction SilentlyContinue | Select TimeCreated,Id,LevelDisplayName,Message | Format-Table -Wrap | Out-String -Width 220",
        timeout=15)

    saved = request.args.get("saved", "")
    notif = (f'<div style="background:rgba(45,212,170,.12);border:1px solid var(--g);border-radius:6px;'
             f'padding:8px 14px;margin-bottom:12px;color:var(--g);font-size:.8rem">✅ {h(saved)}</div>') if saved else ""
    err   = request.args.get("err","")
    if err:
        notif = (f'<div style="background:rgba(247,107,107,.12);border:1px solid var(--r);border-radius:6px;'
                 f'padding:8px 14px;margin-bottom:12px;color:var(--r);font-size:.8rem">❌ {h(err)}</div>')

    job_rows = ""
    for i, item in enumerate(managed_jobs, 1):
        sched = item.get("schedule", "—")
        cmd_s = item.get("command", "—")
        job_rows += (
            f"<tr><td>{i}</td>"
            f"<td><code style='font-size:.72rem;color:var(--y)'>{h(sched)}</code></td>"
            f"<td style='max-width:280px;overflow:hidden;text-overflow:ellipsis'>"
            f"<code style='font-size:.72rem'>{h(cmd_s[:80])}</code></td>"
            f"<td>"
            f'<form method="post" action="/cron/delete" style="display:inline" onsubmit="return confirm(\'Hapus job #{i}?\');">'
            f'<input type="hidden" name="linenum" value="{i}">'
            f'<button class="btn bd btn-sm" type="submit">🗑</button></form>'
            f"</td></tr>"
        )

    body = f"""
{notif}
<div class="grid g3">
<div class="card"><h3>⏰ Managed Tasks</h3><div class="val">{len(managed_jobs)}</div><div class="sub">dibuat melalui aplikasi</div></div>
<div class="card"><h3>🪟 Startup Task</h3>
  <div class="val" style="font-size:1rem">{'✅ Terpasang' if startup.get('installed') else '❌ Belum'}</div>
  <div class="sub">{h(startup.get('status', 'unknown'))}</div></div>
<div class="card"><h3>🕐 Task Scheduler</h3>
  <div class="val" style="font-size:1rem">✅ Windows</div>
</div>
</div>

<div class="grid g2">
<div>
<div class="sec" style="margin-bottom:14px">
<div class="sh"><span>📋 Scheduled Tasks ({len(managed_jobs)})</span>
  <a href="/cron"><button class="btn bn btn-sm">🔄</button></a></div>
<div style="overflow-x:auto">
<table><thead><tr><th>#</th><th>Schedule</th><th>Command</th><th>Del</th></tr></thead>
<tbody>{job_rows or "<tr><td colspan='4' style='text-align:center;color:var(--m);padding:18px'>Belum ada task yang dikelola aplikasi</td></tr>"}</tbody>
</table></div>
</div>

<div class="sec">
<div class="sh"><span>📋 Task Scheduler History (20 terakhir)</span></div>
<div class="term" style="max-height:180px">{h(cron_log)}</div>
</div>
</div>

<div>
<div class="sec" style="margin-bottom:14px">
<div class="sh"><span>➕ Tambah Windows Scheduled Task</span></div>
<form method="post" action="/cron/add" style="padding:14px;display:flex;flex-direction:column;gap:10px">
  <div>
    <label style="font-size:.73rem;color:var(--m)">Quick Preset</label><br>
    <select id="preset" style="width:100%;margin-top:4px" onchange="applyPreset(this.value)">
      <option value="">— pilih preset —</option>
      <option value="*/5 * * * *">Setiap 5 menit</option>
      <option value="*/15 * * * *">Setiap 15 menit</option>
      <option value="@hourly">Setiap jam</option>
      <option value="@daily 00:00">Setiap tengah malam</option>
      <option value="@daily 02:00">Setiap jam 02:00</option>
      <option value="@reboot">@reboot</option>
    </select>
  </div>
  <div>
    <label style="font-size:.73rem;color:var(--m)">Schedule</label><br>
    <input name="schedule" id="cron-sched" placeholder="*/5 * * * * atau @daily 02:00" style="width:100%;margin-top:4px;font-family:monospace">
  </div>
  <div>
    <label style="font-size:.73rem;color:var(--m)">Command</label><br>
    <input name="command" placeholder="python C:\\Scripts\\backup.py" style="width:100%;margin-top:4px;font-family:monospace">
  </div>
  <button type="submit" class="btn bg_">➕ Tambah Job</button>
</form>
</div>

<div class="sec">
<div class="sh"><span>🪟 Startup Task — {h(TASK_NAME)}</span></div>
<div class="term" style="max-height:220px">{h(etc_out)}</div>
</div>
</div>
</div>

<script>
function applyPreset(v){{if(v)document.getElementById('cron-sched').value=v;}}
</script>"""
    return page("Scheduled Tasks", body, active="/cron")

@flask_app.route("/cron/add", methods=["POST"])
@web_auth
def w_cron_add():
    schedule = request.form.get("schedule", "").strip()
    command  = request.form.get("command",  "").strip()
    if not schedule or not command:
        return redirect("/cron?err=Schedule+dan+command+wajib+diisi")
    expression = f"{schedule} {command}"
    ok, out    = cron_add(expression)
    if ok:
        return redirect(f"/cron?saved=Job+ditambahkan")
    return redirect(f"/cron?err={h(out[:60])}")

@flask_app.route("/cron/delete", methods=["POST"])
@web_auth
def w_cron_delete():
    n = request.form.get("linenum", "")
    if n.isdigit():
        cron_delete_line(int(n))
    return redirect("/cron?saved=Job+dihapus")

# ── Config Page ───────────────────────────────────────────────────
@flask_app.route("/config")
@web_auth
def w_config():
    si    = sys_info()
    saved = request.args.get("saved", "")
    notif = (f'<div style="background:rgba(45,212,170,.12);border:1px solid var(--g);border-radius:6px;'
             f'padding:8px 14px;margin-bottom:14px;color:var(--g);font-size:.8rem">✅ {h(saved)}</div>') if saved else ""

    sc_log_tail = tail_file(LOG_FILE, 30)
    startup = scheduled_task_status()

    def row(k, v, note=""):
        return (f"<tr><td style='color:var(--m);font-size:.75rem;white-space:nowrap'>{k}</td>"
                f"<td><code style='font-size:.8rem'>{h(str(v))}</code></td>"
                f"<td style='color:var(--m);font-size:.72rem'>{note}</td></tr>")

    info_rows = (
        row("Host", si["node"]) +
        row("OS", si["os"]) +
        row("Python", si["python"]) +
        row("IP / Port", f"{si['local_ip']}:{WEB_PORT}") +
        row("Web Token", DASH_TOKEN, "gunakan untuk login") +
        row("Owner Telegram ID", OWNER_ID) +
        row("Script Logs Dir", NOHUP_LOG_DIR) +
        row("App Log File", LOG_FILE) +
        row("Administrator", "✅ Ya" if is_admin() else "⚠️ Tidak") +
        row("Startup Task", "✅ Terpasang" if startup.get("installed") else "❌ Belum") +
        row("Docker", "✅ tersedia" if docker_ok() else "❌ tidak ada") +
        row("Windows Firewall", "✅ tersedia" if iptables_ok() else "❌ tidak ada") +
        row("Script Path", Path(__file__).resolve())
    )

    body = f"""
{notif}
<div class="grid g2">
<div class="sec">
<div class="sh"><span>ℹ️ System Info</span></div>
<table><tbody>{info_rows}</tbody></table>
</div>

<div class="sec">
<div class="sh"><span>🚨 Alert Thresholds</span></div>
<form method="post" action="/config/save" style="padding:14px;display:flex;flex-direction:column;gap:12px">
  <div class="flex">
    <label style="min-width:130px;font-size:.75rem;color:var(--m)">🔥 CPU Alert (%)</label>
    <input type="number" name="cpu" value="{ALERT_CPU_THRESH}" min="1" max="99" style="width:80px">
  </div>
  <div class="flex">
    <label style="min-width:130px;font-size:.75rem;color:var(--m)">🧠 RAM Alert (%)</label>
    <input type="number" name="ram" value="{ALERT_RAM_THRESH}" min="1" max="99" style="width:80px">
  </div>
  <div class="flex">
    <label style="min-width:130px;font-size:.75rem;color:var(--m)">💾 Disk Alert (%)</label>
    <input type="number" name="disk" value="{ALERT_DISK_THRESH}" min="1" max="99" style="width:80px">
  </div>
  <div class="flex">
    <label style="min-width:130px;font-size:.75rem;color:var(--m)">⏱ Cooldown (s)</label>
    <input type="number" name="cooldown" value="{ALERT_COOLDOWN}" min="60" max="86400" style="width:100px">
  </div>
  <div class="flex">
    <label style="min-width:130px;font-size:.75rem;color:var(--m)">Alerts Aktif</label>
    <input type="checkbox" name="alerts_enabled" {"checked" if ALERTS_ENABLED else ""} style="width:18px;height:18px">
  </div>
  <button type="submit" class="btn bg_" style="align-self:flex-start">💾 Simpan Config</button>
</form>
</div>
</div>

<div class="grid g2">
<div class="sec">
<div class="sh">
  <span>📋 Windows Control Log (30 baris terakhir)</span>
  <div class="sh-r">
    <a href="/config"><button class="btn bn btn-sm">🔄</button></a>
    <form method="post" action="/config/clearlog" style="display:inline" onsubmit="return confirm('Hapus log?')">
      <button class="btn bd btn-sm" type="submit">🗑 Clear</button></form>
  </div>
</div>
<div class="term" style="max-height:280px">{h(sc_log_tail)}</div>
</div>

<div class="sec">
<div class="sh"><span>🔄 Actions</span></div>
<div style="padding:14px;display:flex;flex-direction:column;gap:10px">
  <form method="post" action="/config/restart" onsubmit="return confirm('Restart Windows Control?')">
    <button type="submit" class="btn by_" style="width:100%">🔄 Restart Windows Control</button></form>
  <a href="/logout" style="width:100%">
    <button class="btn bd" style="width:100%">🚪 Logout Web</button></a>
  <div style="font-size:.73rem;color:var(--m);padding:4px 0">
    ⚠️ Setelah restart, tunggu ~5 detik lalu refresh halaman ini.
  </div>
</div>
</div>
</div>"""
    return page("Config", body, active="/config")

@flask_app.route("/config/save", methods=["POST"])
@web_auth
def w_config_save():
    global ALERT_CPU_THRESH, ALERT_RAM_THRESH, ALERT_DISK_THRESH, ALERT_COOLDOWN, ALERTS_ENABLED
    try:
        ALERT_CPU_THRESH  = max(1, min(99, int(request.form.get("cpu",  ALERT_CPU_THRESH))))
        ALERT_RAM_THRESH  = max(1, min(99, int(request.form.get("ram",  ALERT_RAM_THRESH))))
        ALERT_DISK_THRESH = max(1, min(99, int(request.form.get("disk", ALERT_DISK_THRESH))))
        ALERT_COOLDOWN    = max(60, int(request.form.get("cooldown", ALERT_COOLDOWN)))
        ALERTS_ENABLED    = "alerts_enabled" in request.form
        save_runtime_config()
    except Exception: pass
    return redirect("/config?saved=Config+disimpan")

@flask_app.route("/config/clearlog", methods=["POST"])
@web_auth
def w_config_clearlog():
    try: open(LOG_FILE, "w").close()
    except Exception: pass
    return redirect("/config?saved=Log+dikosongkan")

@flask_app.route("/config/restart", methods=["POST"])
@web_auth
def w_config_restart():
    threading.Thread(target=_delayed_restart, daemon=True).start()
    return redirect("/config?saved=Restarting...+tunggu+5+detik")

# ── API Endpoints ─────────────────────────────────────────────────
@flask_app.route("/api/stats")
@web_auth
def w_api_stats():
    return jsonify(sys_info())

@flask_app.route("/api/history")
@web_auth
def w_api_history():
    return jsonify(dict(
        labels=list(HISTORY["labels"]),
        cpu=list(HISTORY["cpu"]),
        ram=list(HISTORY["ram"]),
        net_s=list(HISTORY["net_s"]),
        net_r=list(HISTORY["net_r"]),
    ))

@flask_app.route("/api/procs")
@web_auth
def w_api_procs():
    limit = int(request.args.get("limit", 50))
    return jsonify(get_all_procs(limit))

@flask_app.route("/api/my-scripts")
@web_auth
def w_api_my_scripts():
    return jsonify(get_user_py_procs())

@flask_app.route("/api/net")
@web_auth
def w_api_net():
    return jsonify(dict(
        interfaces=get_net_interfaces(),
        ports=get_listening_ports(),
    ))

@flask_app.route("/api/partitions")
@web_auth
def w_api_parts():
    return jsonify(get_disk_partitions())

@flask_app.route("/api/alerts")
@web_auth
def w_api_alerts():
    return jsonify(dict(
        enabled=ALERTS_ENABLED,
        cpu_thresh=ALERT_CPU_THRESH,
        ram_thresh=ALERT_RAM_THRESH,
        disk_thresh=ALERT_DISK_THRESH,
        last=ALERT_LAST,
    ))

# ─────────────────────────────────────────────────────────────────
# 14. STARTUP & MAIN
# ─────────────────────────────────────────────────────────────────

def find_free_port(start: int = 8080) -> int:
    for port in range(start, start + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("", port)); return port
            except OSError:
                continue
    return start + 30

def print_banner(port: int):
    ip = get_local_ip()
    si = sys_info()
    print("\n" + "=" * 70)
    print(f" {APP_NAME.upper()} v{VERSION}")
    print("=" * 70)
    print(f" Host             : {si['node']}")
    print(f" Windows          : {si['os']} ({si['arch']})")
    print(f" Dashboard lokal  : http://127.0.0.1:{port}")
    print(f" Dashboard LAN    : http://{ip}:{port}")
    print(f" Token login      : {DASH_TOKEN}")
    print(f" Startup task     : {'TERPASANG' if scheduled_task_status().get('installed') else 'BELUM'}")
    print(f" Hak Administrator: {'YA' if is_admin() else 'TIDAK'}")
    print("=" * 70)

def run_flask(port: int):
    log.info("Waitress web server starting on %s:%s", WEB_HOST, port)
    waitress_serve(flask_app, host=WEB_HOST, port=port, threads=8,
                   channel_timeout=120, clear_untrusted_proxy_headers=True)

@owner_only
async def cmd_dashboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🌐 *Windows Control Dashboard*\n"
        f"Lokal: http://127.0.0.1:{WEB_PORT}\n"
        f"LAN: http://{get_local_ip()}:{WEB_PORT}\n"
        f"Token: {DASH_TOKEN}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=menu_main(),
    )

@owner_only
async def cmd_bot_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ *Perintah Windows Control*\n"
        "/start atau /menu — panel utama\n"
        "/status — status komputer\n"
        "/dashboard — alamat dan token dashboard\n"
        "/help — panduan singkat\n\n"
        "Semua menu sensitif hanya dapat digunakan oleh Owner ID.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=menu_main(),
    )

async def bot_error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Telegram handler error: %s\n%s", ctx.error,
              "".join(traceback.format_exception(type(ctx.error), ctx.error,
                                                  ctx.error.__traceback__)) if ctx.error else "")

async def bot_post_init(app: Application) -> None:
    global _BOT_LOOP
    _BOT_LOOP = asyncio.get_running_loop()
    await app.bot.set_my_commands([
        BotCommand("start", "Buka Windows Control"),
        BotCommand("menu", "Tampilkan menu utama"),
        BotCommand("status", "Lihat status komputer"),
        BotCommand("dashboard", "Alamat dashboard web"),
        BotCommand("help", "Panduan penggunaan"),
    ])
    me = await app.bot.get_me()
    log.info("Telegram bot connected: @%s", me.username)

def build_bot() -> "Application":
    tg = (Application.builder().token(TOKEN)
          .connect_timeout(30).read_timeout(30).write_timeout(30)
          .post_init(bot_post_init).build())
    tg.add_handler(CommandHandler("start", cmd_start))
    tg.add_handler(CommandHandler("menu",  cmd_start))
    tg.add_handler(CommandHandler("status", cmd_start))
    tg.add_handler(CommandHandler("dashboard", cmd_dashboard))
    tg.add_handler(CommandHandler("help", cmd_bot_help))
    tg.add_handler(CallbackQueryHandler(cb_router))
    tg.add_handler(MessageHandler(
        (filters.TEXT & ~filters.COMMAND) | filters.Document.ALL,
        msg_handler,
    ))
    tg.add_error_handler(bot_error_handler)
    return tg

def main():
    global _BOT_APP, _BOT_LOOP, WEB_PORT

    if not IS_WINDOWS:
        print("❌ Versi ini khusus Windows 10/11. Jalankan file pada komputer Windows.")
        return 2

    if ("--background" not in sys.argv and "--no-elevate" not in sys.argv
            and not is_admin()):
        if request_elevation():
            if sys.stdout:
                print("🔐 Melanjutkan setup sebagai Administrator...")
            return 0
        if sys.stdout:
            print("⚠️ UAC tidak disetujui. Setup dilanjutkan dengan fitur terbatas.")

    if "--uninstall-task" in sys.argv:
        r = subprocess.run(["schtasks.exe", "/Delete", "/TN", TASK_NAME, "/F"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace",
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        print(((r.stdout or "") + (r.stderr or "")).strip())
        return r.returncode

    if not first_run_setup():
        log.error("Konfigurasi belum lengkap. Jalankan python server_control_win.py di terminal.")
        return 2

    installed = ensure_installed_copy()
    task_state = scheduled_task_status()
    if (not task_state.get("installed") or "--reinstall-task" in sys.argv
            or "--background" not in sys.argv):
        ok, detail = install_startup_task(installed)
        log.info("Install startup task: %s - %s", ok, detail)
        if not ok and sys.stdout:
            print("⚠️ Task Scheduler belum berhasil dipasang:", detail)

    foreground = "--foreground" in sys.argv
    background = "--background" in sys.argv
    if not (foreground or background):
        create_dashboard_shortcuts(WEB_PORT)
        fw_ok, fw_detail = ensure_firewall_rule(WEB_PORT)
        log.info("Firewall setup: %s - %s", fw_ok, fw_detail)
        if launch_hidden(installed):
            print_banner(WEB_PORT)
            print("\n✅ Setup selesai. Aplikasi sekarang berjalan tanpa jendela terminal.")
            print("   Shortcut Dashboard dibuat di Desktop dan Start Menu.")
            print("   Anda boleh menutup jendela ini.")
            return 0
        print("❌ Gagal menjalankan background. Coba: python server_control.py --foreground")
        return 3

    if not acquire_single_instance():
        log.info("Instance lain sudah aktif; proses baru dihentikan.")
        return 0

    port = find_free_port(WEB_PORT)
    WEB_PORT = port
    create_dashboard_shortcuts(port)
    if is_admin():
        ensure_firewall_rule(port)
    if foreground:
        print_banner(port)
        if port != WEB_PORT:
            print(f"\n⚠️ Port {WEB_PORT} terpakai; sementara menggunakan {port}.\n")

    # Flask – background daemon thread
    threading.Thread(target=run_flask, args=(port,),
                     daemon=True, name="flask").start()
    log.info("Dashboard: http://%s:%s", get_local_ip(), port)

    # History collector – background daemon thread
    threading.Thread(target=history_collector,
                     daemon=True, name="history").start()
    log.info("History collector started (interval 5s).")

    # Alert monitor – background daemon thread
    threading.Thread(target=alert_monitor,
                     daemon=True, name="alerts").start()
    log.info(f"Alert monitor started (CPU>{ALERT_CPU_THRESH}% "
             f"RAM>{ALERT_RAM_THRESH}% Disk>{ALERT_DISK_THRESH}%).")

    retry = 10
    while True:
        try:
            _BOT_APP = build_bot()
            _BOT_APP.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                close_loop=True,
            )
            break
        except KeyboardInterrupt:
            log.info("Shutdown by user.")
            break
        except Exception as exc:
            _BOT_LOOP = None
            log.error("Telegram polling berhenti: %s. Retry %ss.", exc, retry)
            time.sleep(retry)
            retry = min(120, retry * 2)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
