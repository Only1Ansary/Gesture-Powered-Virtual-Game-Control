#!/usr/bin/env bash
# ============================================================
#  install.sh — Linux / macOS installer for all project libraries
#  Usage:
#      chmod +x install.sh && ./install.sh
#  Requires: Python 3.10 or 3.11, pip, git, internet access
#  Linux extra: sudo apt install cmake build-essential (for dlib)
#  macOS extra: xcode-select --install && brew install cmake
# ============================================================

set -euo pipefail

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARNING]${NC} $*"; }
fail() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

echo
echo "============================================================"
echo " Project Library Installer (Linux / macOS)"
echo "============================================================"
echo

# ── Resolve python & pip ─────────────────────────────────────
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    fail "Python not found. Install Python 3.11 from https://python.org"
fi

PYVER=$($PYTHON --version 2>&1 | awk '{print $2}')
ok "Found Python $PYVER"

PIP="$PYTHON -m pip"

# ── Check cmake (needed to build dlib from source) ───────────
if ! command -v cmake &>/dev/null; then
    warn "cmake not found — needed to build dlib (face-recognition + GazeTracking)."
    echo "  Linux:  sudo apt install cmake build-essential"
    echo "  macOS:  brew install cmake   (after: xcode-select --install)"
    echo
    read -rp "Continue anyway? (y/N): " ans
    [[ "$ans" =~ ^[Yy]$ ]] || exit 1
fi

# ── Upgrade pip & setuptools ─────────────────────────────────
echo
echo "[1/8] Upgrading pip and setuptools..."
$PIP install --upgrade pip setuptools wheel

# ── Core numerics first ──────────────────────────────────────
echo
echo "[2/8] Installing numpy (pinned to 1.26.4 — required by tensorflow + mediapipe)..."
$PIP install numpy==1.26.4

# ── OpenCV contrib ───────────────────────────────────────────
echo
echo "[3/8] Installing OpenCV contrib (mediapipe requires this exact build)..."
# Remove plain opencv-python to avoid cv2 symbol conflict
$PIP uninstall -y opencv-python opencv-python-headless 2>/dev/null || true
$PIP install opencv-contrib-python==4.10.0.84

# ── protobuf ─────────────────────────────────────────────────
echo
echo "[4/8] Installing protobuf (4.25.x satisfies both tensorflow and mediapipe)..."
$PIP install protobuf==4.25.5

# ── dlib (source build on Linux/macOS) ───────────────────────
echo
echo "[5/8] Building and installing dlib from source (this may take a few minutes)..."
$PIP install dlib==19.24.6

# ── Main package list ────────────────────────────────────────
echo
echo "[6/8] Installing all remaining libraries..."
$PIP install \
    Pillow==10.4.0 \
    python-osc==1.9.3 \
    bleak==0.22.3 \
    pyautogui==0.9.54 \
    mediapipe==0.10.21 \
    ultralytics==8.3.40 \
    torch==2.5.1 \
    torchvision==0.20.1 \
    tensorflow==2.18.1 \
    keras==3.9.0 \
    deepface==0.0.100 \
    face-recognition==1.3.0 \
    face-recognition-models==0.3.0 \
    pandas==2.2.3 \
    seaborn==0.13.2 \
    matplotlib==3.9.4

# ── GazeTracking (GitHub only) ───────────────────────────────
echo
echo "[7/8] Installing GazeTracking from GitHub (--no-deps so dlib is not rebuilt)..."
if command -v git &>/dev/null; then
    $PIP install --no-deps git+https://github.com/antoinelame/GazeTracking.git
else
    warn "git not found — skipping GazeTracking."
    echo "  Install git, then run:"
    echo "  pip install --no-deps git+https://github.com/antoinelame/GazeTracking.git"
fi

# ── Verify imports ────────────────────────────────────────────
echo
echo "[8/8] Verifying key imports..."
$PYTHON - <<'EOF'
imports = ["cv2", "numpy", "mediapipe", "torch", "tensorflow",
           "deepface", "face_recognition", "ultralytics"]
failed = []
for mod in imports:
    try:
        __import__(mod)
        print(f"  OK  {mod}")
    except ImportError as e:
        print(f"  FAIL  {mod}: {e}")
        failed.append(mod)
if failed:
    print(f"\nWARNING: {len(failed)} import(s) failed: {', '.join(failed)}")
else:
    print("\nAll core imports successful.")
EOF

echo
echo "============================================================"
echo " Installation complete!"
echo "============================================================"
echo