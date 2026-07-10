# -*- coding: ascii -*-
"""setup_torch.py - detect GPU, pick the right PyTorch CUDA build, install, verify.

Single source of truth for torch installation (Packaging Playbook section 3).
Called by: 01_setup.bat.
Run from the repo root: .venv\\Scripts\\python.exe scripts\\install\\setup_torch.py [--detect]

Mapping (compute capability; future cards land on the top row automatically):
  CC >= 12.0 (Blackwell, RTX 50xx+)        -> cu128
  CC  8.0-11.x (Ampere/Ada/Hopper, 30/40)  -> cu126
  CC  7.0-7.5 (Volta/Turing, RTX20/GTX16)  -> cu124
  CC  5.0-6.x (Maxwell/Pascal, GTX9xx/10)  -> cu118
  CC < 5.0 or no NVIDIA GPU                -> cpu

Why Python instead of .bat:
  - cmd for/f mangles index URLs (cu128 silently became cpu before)
  - pip reuses cached +cpu wheels; we do `pip cache remove` + --no-cache-dir
On CUDA install/verify failure: step DOWN one CUDA level and retry
(cu128->cu126->cu124->cu118). CPU only when everything failed (loud warning).
Detection sources (first hit wins): nvidia-smi compute_cap -> nvidia-smi name
-> nvidia-smi -L -> PowerShell Win32_VideoController.
Writes gpu_detect_log.txt next to this script (same as gpu_pick.py).
"""
import os
import re
import subprocess
import sys

BASE = "https://download.pytorch.org/whl/"
LADDER = ["cu128", "cu126", "cu124", "cu118"]
LOGLINES = []


def log(msg):
    LOGLINES.append(str(msg))
    print(msg, flush=True)


def _run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        LOGLINES.append("$ %s -> rc=%s out=%r" % (" ".join(cmd), r.returncode,
                                                  (r.stdout or "").strip()[:300]))
        if r.returncode == 0:
            return r.stdout or ""
    except Exception as e:
        LOGLINES.append("$ %s -> EXC %r" % (" ".join(cmd), e))
    return ""


def _nvsmi_paths():
    cands = ["nvidia-smi"]
    for p in (r"C:\Windows\System32\nvidia-smi.exe",
              r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"):
        if os.path.exists(p):
            cands.append(p)
    return cands


def idx_from_cc(text):
    vals = [int(m.group(1)) * 10 + int(m.group(2))
            for m in re.finditer(r"(\d+)\.(\d+)", text or "")]
    if not vals:
        return None
    v = max(vals)
    log("compute_cap score = %d" % v)
    if v >= 120:
        return "cu128"
    if v >= 80:
        return "cu126"
    if v >= 70:
        return "cu124"
    if v >= 50:
        return "cu118"
    return "cpu"


def idx_from_name(name):
    n = (name or "").upper()
    if not n.strip():
        return None
    if not any(k in n for k in ("NVIDIA", "GEFORCE", "RTX", "GTX", "QUADRO", "TESLA")):
        return None
    log("name-based on: %r" % n.strip()[:200])
    if re.search(r"RTX\s*5\d{3}", n) or re.search(r"RTX\s*50", n):
        return "cu128"
    if re.search(r"RTX\s*[34]\d{3}", n) or re.search(r"RTX\s*[34]0", n):
        return "cu126"
    if re.search(r"RTX\s*2\d{3}", n) or "GTX 16" in n:
        return "cu124"
    if "GTX 10" in n or "GTX 9" in n:
        return "cu118"
    return "cu126"  # unknown modern NVIDIA card


def detect():
    for exe in _nvsmi_paths():
        got = idx_from_cc(_run([exe, "--query-gpu=compute_cap", "--format=csv,noheader"]))
        if got:
            return got
    for exe in _nvsmi_paths():
        got = idx_from_name(_run([exe, "--query-gpu=name", "--format=csv,noheader"]))
        if got:
            return got
    for exe in _nvsmi_paths():
        got = idx_from_name(_run([exe, "-L"]))
        if got:
            return got
    got = idx_from_name(_run(["powershell", "-NoProfile", "-Command",
                              "Get-CimInstance Win32_VideoController | "
                              "Select-Object -ExpandProperty Name"]))
    return got or "cpu"


def pip(args):
    cmd = [sys.executable, "-m", "pip"] + args
    log("$ " + " ".join(cmd))
    return subprocess.call(cmd)


def install(label):
    pip(["cache", "remove", "torch*"])
    pip(["cache", "remove", "torchaudio*"])
    pip(["uninstall", "torch", "torchaudio", "torchvision", "-y"])
    rc = pip(["install", "--no-cache-dir", "torch", "torchaudio",
              "--index-url", BASE + label])
    return rc == 0


def verify_cuda():
    """Verify in a fresh subprocess (this process may hold a stale torch)."""
    return subprocess.call([sys.executable, "-c",
        "import torch,sys;"
        "print('PyTorch', torch.__version__, '| CUDA:', torch.cuda.is_available());"
        "sys.exit(0 if torch.cuda.is_available() else 1)"]) == 0


def save_log():
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "gpu_detect_log.txt"), "w") as f:
            f.write("\n".join(LOGLINES) + "\n")
    except Exception:
        pass


def main():
    label = detect()
    log("Detected PyTorch target: %s" % label)
    if "--detect" in sys.argv:
        save_log()
        return 0

    if label == "cpu":
        log("No usable NVIDIA GPU. Installing CPU build.")
        ok = install("cpu")
        save_log()
        return 0 if ok else 1

    for i, lab in enumerate(LADDER[LADDER.index(label):]):
        if i > 0:
            log("[WARN] Previous CUDA level failed; stepping down to %s ..." % lab)
        if install(lab) and verify_cuda():
            log("[OK] CUDA PyTorch (%s) installed and verified." % lab)
            save_log()
            return 0

    log("=" * 60)
    log("[WARN] All CUDA builds failed. Falling back to CPU (much slower!).")
    log("       Your NVIDIA driver may be outdated - update it, then re-run setup.")
    log("=" * 60)
    ok = install("cpu")
    save_log()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
