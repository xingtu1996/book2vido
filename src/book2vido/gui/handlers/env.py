import json, shutil, subprocess, time, urllib.request
from pathlib import Path

from book2vido.paths import project_root

def _check_ollama() -> dict:
    """Check if Ollama is running and list models."""
    try:
        r = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
        data = json.loads(r.read())
        models = [m["name"] for m in data.get("models", [])]
        return {
            "ok": True,
            "models": models,
            "has_model": len(models) > 0,
            "recommended": "qwen3:8b" if any("qwen3" in m for m in models) else (models[0] if models else None),
        }
    except Exception:
        return {"ok": False, "models": [], "has_model": False, "recommended": None}


def _check_ffmpeg() -> bool:
    """Check ffmpeg: first built-in, then system PATH."""
    # 先找 .app 内置的
    builtin = project_root() / "bin" / "ffmpeg"
    if builtin.exists():
        return True
    # 再找系统 PATH
    return shutil.which("ffmpeg") is not None

def _get_brew_path() -> str | None:
    """Find brew executable, including in Homebrew default locations."""
    found = shutil.which("brew")
    if found:
        return found
    for p in ["/opt/homebrew/bin/brew", "/usr/local/bin/brew"]:
        if Path(p).exists():
            return p
    return None


def _check_env() -> dict:
    """Full environment check for the dashboard."""
    ollama = _check_ollama()
    ffmpeg_ok = _check_ffmpeg()
    return {
        "ollama": {
            "ok": ollama["ok"],
            "name": "Ollama",
            "status_text": "Running" if ollama["ok"] else "Not running",
        },
        "model": {
            "ok": ollama["has_model"],
            "name": "Local Model",
            "current": ollama["recommended"],
            "recommended": "qwen3:8b",
            "status_text": ollama["recommended"] or "Not installed",
        },
        "ffmpeg": {
            "ok": ffmpeg_ok,
            "name": "FFmpeg",
            "status_text": "Installed" if ffmpeg_ok else "Not installed",
        },
    }


# ── Install runners ──

def _run_install(component: str, install_id: str):
    """Background thread: run install step and update state."""
    def log(msg: str, ltype: str = "info"):
        with _install_lock:
            _install_jobs[install_id]["logs"].append({"type": ltype, "text": msg})

    def set_progress(pct: float, msg: str):
        with _install_lock:
            _install_jobs[install_id]["progress"] = pct
            _install_jobs[install_id]["message"] = msg

    try:
        import platform
        system = platform.system()

        if component == "ollama":
            set_progress(10, "Preparing Ollama download...")
            log(f"System: {system}")
            ollama_dmg = "/tmp/Ollama-darwin.dmg"

            # Step 1: Download
            if not Path(ollama_dmg).exists():
                set_progress(20, "Downloading Ollama (~500MB)...")
                log("Downloading Ollama from official site...", "info")
                import urllib.request
                # 镜像加速：GitHub 资源国内慢，走 ghproxy 镜像
                # 官方源（备用）
                # url = "https://ollama.com/download/Ollama-darwin.dmg"
                # 镜像源（国内加速）
                url = "https://ghproxy.com/https://github.com/ollama/ollama/releases/latest/download/Ollama-darwin.dmg"
                log("Using China mirror for faster download...", "info")
                def report_hook(count, block_size, total_size):
                    pct = min(80, 20 + int(count * block_size * 100 / total_size * 0.6))
                    set_progress(pct, f"Downloading Ollama... {int(count * block_size / 1024 / 1024)} MB")
                urllib.request.urlretrieve(url, ollama_dmg, reporthook=report_hook)
                log("Download complete", "ok")
            else:
                log("Using cached download", "info")

            # Step 2: Mount dmg
            set_progress(85, "Mounting installer...")
            log("Mounting disk image...", "info")
            mount_point = "/tmp/ollama_mount"
            subprocess.run(["hdiutil", "attach", ollama_dmg, "-nobrowse", "-mountpoint", mount_point],
                         capture_output=True, timeout=60)

            # Step 3: Copy to Applications
            set_progress(90, "Installing...")
            log("Copying Ollama.app to /Applications...", "info")
            subprocess.run(["cp", "-R", f"{mount_point}/Ollama.app", "/Applications/"],
                         capture_output=True, timeout=120)

            # Step 4: Unmount
            subprocess.run(["hdiutil", "detach", mount_point], capture_output=True)

            # Step 5: Start Ollama
            set_progress(95, "Starting Ollama...")
            log("Starting Ollama background service...", "info")
            subprocess.Popen(
                ["/Applications/Ollama.app/Contents/MacOS/Ollama"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(3)
            set_progress(100, "Ready")
            log("Ollama is ready!", "ok")

        elif component == "model":
            set_progress(10, "Preparing model download...")
            model_name = "qwen3:8b"
            log(f"Downloading model {model_name} (~4.9GB)...", "info")
            set_progress(20, "Downloading...")
            proc = subprocess.Popen(
                ["ollama", "pull", model_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            for line in proc.stdout:
                line = line.strip()
                if line:
                    log(line)
                    if "%" in line:
                        try:
                            pct_str = line.split("%")[0].split()[-1]
                            pct = float(pct_str)
                            set_progress(min(95, 20 + pct * 0.7), f"Downloading {pct:.0f}%")
                        except:
                            pass
            proc.wait()
            if proc.returncode == 0:
                log("Model download complete", "ok")
                set_progress(100, "Ready")
            else:
                log(f"Download failed, exit code {proc.returncode}", "error")

        elif component == "ffmpeg":
            set_progress(10, "Preparing FFmpeg download...")
            ffmpeg_bin = project_root() / "bin" / "ffmpeg"
            ffmpeg_bin.parent.mkdir(parents=True, exist_ok=True)

            if ffmpeg_bin.exists():
                log("FFmpeg already installed", "ok")
                set_progress(100, "Ready")
            else:
                set_progress(20, "Downloading FFmpeg...")
                log("Downloading FFmpeg static build (~70MB)...", "info")
                import urllib.request
                url = "https://evermeet.cx/ffmpeg/getrelease/zip"
                zip_path = "/tmp/ffmpeg.zip"

                def report_hook(count, block_size, total_size):
                    pct = min(80, 20 + int(count * block_size * 100 / total_size * 0.6))
                    set_progress(pct, f"Downloading FFmpeg... {int(count * block_size / 1024 / 1024)} MB")

                urllib.request.urlretrieve(url, zip_path, reporthook=report_hook)
                log("Download complete", "ok")

                # Unzip
                set_progress(85, "Extracting...")
                log("Extracting...", "info")
                subprocess.run(["unzip", "-o", zip_path, "-d", str(ffmpeg_bin.parent)],
                             capture_output=True, timeout=60)
                ffmpeg_bin.chmod(0o755)
                set_progress(100, "Ready")
                log("FFmpeg is ready!", "ok")

        with _install_lock:
            _install_jobs[install_id]["done"] = True
    except Exception as e:
        log(f"Install error: {e}", "error")
        with _install_lock:
            _install_jobs[install_id]["done"] = True
            _install_jobs[install_id]["error"] = str(e)


# ── Pipeline runner ──
