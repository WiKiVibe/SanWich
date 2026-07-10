# -*- coding: ascii -*-
"""Print the correct PyTorch wheel index URL for the installed NVIDIA GPU.
Legacy diagnostic helper; writes gpu_detect_log.txt next to this script."""
import subprocess, re, os, sys

BASE = "https://download.pytorch.org/whl/"
CPU = BASE + "cpu"
LOGLINES = []

def log(msg):
    LOGLINES.append(str(msg))

def _run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        out = (r.stdout or "") + (("\n[stderr] " + r.stderr) if r.stderr else "")
        log("$ %s\n  rc=%s out=%r" % (" ".join(cmd), r.returncode, (r.stdout or "").strip()[:300]))
        if r.returncode == 0:
            return r.stdout
    except Exception as e:
        log("$ %s -> EXC %r" % (" ".join(cmd), e))
    return ""

def _nvsmi_paths():
    cands = ["nvidia-smi"]
    for p in (r"C:\Windows\System32\nvidia-smi.exe",
              r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"):
        if os.path.exists(p):
            cands.append(p)
    return cands

def idx_from_cc(cc_text):
    vals = []
    for m in re.finditer(r"(\d+)\.(\d+)", cc_text or ""):
        vals.append(int(m.group(1)) * 10 + int(m.group(2)))
    if not vals:
        return None
    v = max(vals)
    log("compute_cap score = %d" % v)
    if v >= 120: return "cu128"
    if v >= 80:  return "cu126"
    if v >= 70:  return "cu124"
    if v >= 50:  return "cu118"
    return "cpu"

def idx_from_name(name):
    n = (name or "").upper()
    if not n.strip():
        return None
    if "NVIDIA" not in n and "GEFORCE" not in n and "RTX" not in n and "GTX" not in n and "QUADRO" not in n and "TESLA" not in n:
        return None
    log("name-based on: %r" % n.strip()[:200])
    if re.search(r"RTX\s*5\d{3}", n) or re.search(r"RTX\s*50", n): return "cu128"
    if re.search(r"RTX\s*[34]\d{3}", n) or re.search(r"RTX\s*[34]0", n): return "cu126"
    if re.search(r"RTX\s*2\d{3}", n) or "GTX 16" in n: return "cu124"
    if "GTX 10" in n: return "cu118"
    return "cu126"  # some other NVIDIA card -> modern default

idx = None

# 1) nvidia-smi compute_cap
for exe in _nvsmi_paths():
    txt = _run([exe, "--query-gpu=compute_cap", "--format=csv,noheader"])
    idx = idx_from_cc(txt)
    if idx:
        break

# 2) nvidia-smi name
if not idx:
    for exe in _nvsmi_paths():
        txt = _run([exe, "--query-gpu=name", "--format=csv,noheader"])
        idx = idx_from_name(txt)
        if idx:
            break

# 3) nvidia-smi -L
if not idx:
    for exe in _nvsmi_paths():
        txt = _run([exe, "-L"])
        idx = idx_from_name(txt)
        if idx:
            break

# 4) PowerShell Win32_VideoController (works without nvidia-smi)
if not idx:
    txt = _run(["powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"])
    idx = idx_from_name(txt)

if not idx:
    idx = "cpu"

log("FINAL idx = %s" % idx)
try:
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "gpu_detect_log.txt"), "w") as f:
        f.write("\n".join(LOGLINES) + "\n")
except Exception:
    pass

print(CPU if idx == "cpu" else BASE + idx)
