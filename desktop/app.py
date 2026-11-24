"""Harf OCR (حرف) as a Windows program. (It was called DocScan until 1.0.2; the data folder, mutex and
taskbar ID below keep that name, so an update replaces 1.0.2 in place and keeps its drafts.)

The reader server runs inside this process on a private local port, and a WebView2 window (pywebview, the
Edge engine built into Windows) shows the app: no browser, no Docker, works offline. Closing the window ends
the program, readers and all, so nothing is left in memory. Drafts and templates live in
%LOCALAPPDATA%\\DocScan, so updating or reinstalling keeps them.

Folder layout (desktop/build.ps1 makes it; the installer copies it):
    python\\            embedded Python and the base packages     app\\server, app\\web, app\\templates, app\\desktop
    tesseract\\         tesseract.exe and its tessdata folders    models\\            PaddleOCR (and optional) models
    parts\\<name>\\site-packages   optional readers (EasyOCR, Nuqta), downloaded by the installer
                                  when chosen, or later from inside the program (server/parts.py)
"""
from __future__ import annotations

import ctypes
import os
import re
import shutil
import socket
import string
import sys
import threading
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent  # {app}\app\desktop
APP = HERE.parent                       # {app}\app
ROOT = APP.parent                       # {app}
VERSION = (HERE / "VERSION").read_text(encoding="utf-8").strip() if (HERE / "VERSION").exists() else "0.0.0"
LOCAL = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "DocScan"
# the server's modules, from here on (messages.py reads the language files for the launcher too)
sys.path.insert(0, str(APP / "server"))
from messages import SOURCE, language_file, languages, render  # noqa: E402


def language() -> str:
    """The interface language: the one picked in Settings (LOCAL\\lang, which the server's /api/lang writes), else the one
    the installer ran in (ROOT\\lang.ini; installer.iss writes it on a fresh install only, so an update changes nothing),
    else Arabic. The page itself keeps its own pick too (web/js/i18n.js) and gets this one as its default."""
    def read(f: Path) -> str:
        try:
            return f.read_text(encoding="utf-8-sig")
        except OSError:
            return ""

    ini = re.search(r"^\s*lang\s*=\s*(\w+)", read(ROOT / "lang.ini"), re.M)
    for v in (read(LOCAL / "lang").strip(), ini and ini.group(1)):
        if v in languages():
            return v
    return SOURCE


LANG = language()


def tr(key: str) -> str:
    """What shows before the page (the window title, the splash, two message boxes) in the interface language."""
    return render(LANG, key)


TITLE = tr("ui.titleFull")
# the same port every start, so the page's address stays the same: its settings (localStorage: theme, name, keys)
# belong to the address, port included, and a new port each start forgot them. If another program holds it, a free
# one is picked once and remembered (LOCAL\port), so the settings still last from then on.
PORT = 47615
# the window's colour before the page draws: the app's --canvas (web/css/app.css), light and dark
BG = {"light": "#e6e8eb", "dark": "#0f1112"}
# a page being scanned: the beam passes and each line lights up as it is read. Colours are web/css/app.css's.
SPLASH = """<!doctype html><html lang="$LANG" dir="$DIR"><head><meta charset="utf-8"><style>
:root{--bg:oklch(93% .005 255);--ink:oklch(23% .006 255);--muted:oklch(48% .008 255);--accent:oklch(53% .19 257);
--track:oklch(86% .005 255);--paper:oklch(99.7% .001 255)}
@media (prefers-color-scheme:dark){:root{--bg:oklch(17.5% .004 255);--ink:oklch(93% .004 255);--muted:oklch(68% .008 255);
--accent:oklch(72% .14 252);--track:oklch(28% .005 255);--paper:oklch(24.5% .004 255)}}
html,body{margin:0;height:100%}
body{display:grid;place-items:center;background:var(--bg);color:var(--ink);font:15px "Segoe UI",Tahoma,sans-serif;
transition:opacity .25s;user-select:none;cursor:default}
body.out{opacity:0}
main{text-align:center;animation:rise .6s cubic-bezier(.22,1,.36,1) both}
.doc{position:relative;width:64px;height:82px;margin:0 auto 26px;border-radius:8px;background:var(--paper);overflow:hidden;
box-shadow:0 0 0 .5px #0001,0 1px 3px #0002,0 12px 32px #0002}
.doc i{position:absolute;inset-inline-start:12px;height:4px;border-radius:2px;background:var(--muted);opacity:.3;animation:read 2.4s infinite}
.doc i:nth-child(1){top:16px;width:40px;animation-delay:.55s}.doc i:nth-child(2){top:28px;width:34px;animation-delay:.75s}
.doc i:nth-child(3){top:40px;width:40px;animation-delay:.95s}.doc i:nth-child(4){top:52px;width:26px;animation-delay:1.15s}
.doc i:nth-child(5){top:64px;width:32px;animation-delay:1.35s}
.beam{position:absolute;left:0;right:0;top:0;height:22px;border-bottom:2px solid var(--accent);
background:linear-gradient(transparent,color-mix(in oklch,var(--accent) 30%,transparent));animation:scan 2.4s cubic-bezier(.45,0,.55,1) infinite}
h1{margin:0 0 6px;font-size:17px;font-weight:600}
p{margin:0 0 18px;color:var(--muted);font-size:13px}
.bar{width:168px;height:3px;margin:auto;border-radius:3px;background:var(--track);overflow:hidden}
.bar b{display:block;width:40%;height:100%;border-radius:3px;background:var(--accent);animation:slide 1.3s cubic-bezier(.65,0,.35,1) infinite}
@keyframes rise{from{opacity:0;transform:translateY(8px)}}
@keyframes scan{0%{transform:translateY(-24px);opacity:0}8%{opacity:1}70%{transform:translateY(84px);opacity:1}80%,100%{transform:translateY(84px);opacity:0}}
@keyframes read{0%{background:var(--accent);opacity:1}45%,100%{background:var(--muted);opacity:.3}}
@keyframes slide{from{transform:translateX(110%)}to{transform:translateX(-260%)}}
@media (prefers-reduced-motion:reduce){.beam,.doc i,.bar b{animation:none}.beam{display:none}.bar b{width:100%;opacity:.5}}
</style></head><body><main>
<div class="doc" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><div class="beam"></div></div>
<h1>$TITLE</h1><p>$STARTING</p>
<div class="bar" role="progressbar" aria-label="$BUSY"><b></b></div></main></body></html>"""
SPLASH = string.Template(SPLASH).substitute(LANG=LANG, DIR=language_file(LANG)[0]["dir"], TITLE=TITLE,
                                            STARTING=tr("launcher.startingProgram"), BUSY=tr("launcher.starting"))


def message(text: str, error: bool = False) -> None:
    ctypes.windll.user32.MessageBoxW(None, text, TITLE, 0x10 if error else 0x40)


def hide_child_consoles() -> None:
    """pythonw has no console, so every console program started from here (tesseract, and whatever the readers'
    libraries run) opened a black window of its own. Start them all without one, unless the caller asked for a
    console or a detached process (the updater's installer)."""
    import subprocess

    init = subprocess.Popen.__init__

    def no_window(self, *args, creationflags=0, **kwargs):
        if not creationflags & (subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS):
            creationflags |= subprocess.CREATE_NO_WINDOW
        init(self, *args, creationflags=creationflags, **kwargs)

    subprocess.Popen.__init__ = no_window


def windows_theme() -> str:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return "light" if winreg.QueryValueEx(k, "AppsUseLightTheme")[0] else "dark"
    except OSError:
        return "light"


def setup() -> None:
    """Where everything is, before the server is imported (it reads these when it starts)."""
    data, templates = LOCAL / "data", LOCAL / "templates"
    data.mkdir(parents=True, exist_ok=True)
    templates.mkdir(parents=True, exist_ok=True)
    for f in (APP / "templates").glob("*"):  # the bundled plain template, once; the user's own are kept
        if not (templates / f.name).exists():
            shutil.copy2(f, templates / f.name)
    tess = ROOT / "tesseract"
    os.environ.update({
        "DOCSCAN_DATA": str(data), "DOCSCAN_TEMPLATES": str(templates),
        "DOCSCAN_DESKTOP": "1", "DOCSCAN_VERSION": VERSION, "DOCSCAN_ROOT": str(ROOT),
        "DOCSCAN_LANG": LANG, "DOCSCAN_LANG_FILE": str(LOCAL / "lang"),  # the page's default; where /api/lang keeps a pick
        "TESSDATA_FAST": str(tess / "tessdata" / "fast"), "TESSDATA_STANDARD": str(tess / "tessdata" / "standard"),
        "TESSDATA_BEST": str(tess / "tessdata" / "best"),
        # every model ships with the program: no downloads, no "checking connectivity" at start
        "PADDLE_PDX_CACHE_HOME": str(ROOT / "models" / "paddlex"), "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "True",
        "EASYOCR_MODELS": str(ROOT / "models" / "easyocr"),
        "HF_HOME": str(ROOT / "models" / "hf"), "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
    })
    os.environ["PATH"] = str(tess) + os.pathsep + os.environ.get("PATH", "")
    for part in sorted((ROOT / "parts").glob("*/site-packages")):
        sys.path.append(str(part))
    # PaddleOCR and torch each bring libiomp5md.dll (Intel OpenMP), in different versions, and Windows keeps the
    # first one loaded: with PaddleOCR's, torch fails ("WinError 127 ... shm.dll"). Torch's first, both work.
    # (paddleocr imports torch itself when it can, so this only makes that order certain.)
    omp = ROOT / "parts" / "heavy" / "site-packages" / "torch" / "lib" / "libiomp5md.dll"
    if omp.exists():
        ctypes.WinDLL(str(omp))
    os.chdir(APP / "server")


def restart(window) -> None:
    """Close, and open again: a detached copy waits for this process to end (its single-instance lock goes
    with it), then starts the program."""
    import subprocess

    wait = ("import ctypes, subprocess, sys; k = ctypes.windll.kernel32; "
            "h = k.OpenProcess(0x00100000, False, int(sys.argv[1])); h and k.WaitForSingleObject(h, 30000); "
            "subprocess.Popen(sys.argv[2:])")
    subprocess.Popen([sys.executable, "-c", wait, str(os.getpid()), sys.executable, str(HERE / "app.py")],
                     close_fds=True, creationflags=subprocess.DETACHED_PROCESS)
    window.destroy()


def save_as(window, name: str) -> str | None:
    """Windows' Save As for an exported file, opening in the folder saved to last (Downloads at first). The path
    chosen, or None when cancelled."""
    import webview

    remembered = LOCAL / "export-folder.txt"
    folder = remembered.read_text(encoding="utf-8").strip() if remembered.exists() else ""
    if not folder or not Path(folder).is_dir():
        folder = str(Path.home() / "Downloads")
    ext = Path(name).suffix.lstrip(".")
    kind = webview.FileDialog.SAVE if hasattr(webview, "FileDialog") else webview.SAVE_DIALOG
    got = window.create_file_dialog(kind, directory=folder, save_filename=name,
                                    file_types=(f"{ext.upper()} (*.{ext})",) if ext else ())
    path = got[0] if isinstance(got, (list, tuple)) else got
    if not path:
        return None
    remembered.write_text(str(Path(path).parent), encoding="utf-8")
    return str(path)


def pick_port() -> int:
    saved = LOCAL / "port"
    try:
        want = int(saved.read_text())
    except (OSError, ValueError):
        want = PORT
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", want))
            return want
        except OSError:
            pass
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    saved.write_text(str(port))
    return port


def main() -> None:
    # one copy at a time: a second start would read the same drafts from two places
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\DocScan.single")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        message(tr("launcher.programAlreadyOpen"))
        return
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Eyasbzour.DocScan")  # taskbar: our icon and name
    (LOCAL / "logs").mkdir(parents=True, exist_ok=True)
    log = open(LOCAL / "logs" / "docscan.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log  # pythonw has no console
    print(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} Harf OCR {VERSION}")
    hide_child_consoles()
    setup()

    # the web engine's own words ("please fill out this field", the right-click menu) in the app's language
    os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", f"--lang={LANG}")
    import webview

    webview.settings["ALLOW_DOWNLOADS"] = True  # a file the page downloads goes to Downloads (exports use save_as)
    window = webview.create_window(TITLE, html=SPLASH, width=1440, height=920, min_size=(900, 600),
                                   background_color=BG[windows_theme()])
    port = pick_port()
    state: dict = {}

    def start_server():
        try:
            import uvicorn

            import main as server

            server.QUIT_APP[0] = window.destroy  # the updater closes the program this way
            server.RESTART_APP[0] = lambda: restart(window)
            server.SAVE_AS[0] = lambda name: save_as(window, name)
            srv = state["server"] = uvicorn.Server(uvicorn.Config(server.app, host="127.0.0.1", port=port, log_level="warning"))
            thread = threading.Thread(target=srv.run, daemon=True, name="server")
            thread.start()
            # listening is enough: the readers are only looked up (not imported) to list them, and load when used
            while not srv.started and thread.is_alive():
                time.sleep(0.02)
            if not srv.started:
                raise RuntimeError(f"the server did not start on port {port}")
            try:
                window.evaluate_js("document.body.classList.add('out')")  # fade the splash out
                time.sleep(0.25)
            except Exception:
                pass
            window.load_url(f"http://127.0.0.1:{port}/")
        except Exception:
            traceback.print_exc()
            message(tr("launcher.programCouldntStartDetails") + "\n" + str(LOCAL / "logs" / "docscan.log"), error=True)
            window.destroy()
            return
        # PaddleOCR, the default reader, takes seconds to load: do it while the user picks a photo, once the page
        # has drawn. A read started meanwhile waits for it (paddle_engine's lock) instead of loading it twice.
        try:
            from engines import paddle_engine

            if paddle_engine.available()[0]:
                time.sleep(2)
                paddle_engine._get("ar")
                print("paddle ready")
        except Exception:
            traceback.print_exc()

    def shown():
        try:  # the window's own icon (WinForms; the taskbar takes it from here)
            import clr  # noqa: F401  (pythonnet, which pywebview uses on Windows)
            from System.Drawing import Icon

            window.native.Icon = Icon(str(ROOT / "docscan.ico"))
        except Exception:
            pass

    window.events.shown += shown
    webview.start(start_server, gui="edgechromium", private_mode=False, storage_path=str(LOCAL / "webview"))
    # the window is closed: stop the server and leave nothing running (readers may hold threads)
    if state.get("server"):
        state["server"].should_exit = True
    try:  # the phone's link (server/remote.py): its cloudflared would outlive this process
        import remote

        remote.stop()
    except Exception:
        traceback.print_exc()
    print("closed")
    log.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
