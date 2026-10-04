#!/usr/bin/env bash
# Build the C++ vision module into brain/vision/board_prep*.so
# Needs: g++, cmake, libopencv-dev, and the project venv (pybind11 installed).
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-$(cd ../.. && pwd)/.venv/bin/python}"
[ -x "$PY" ] || PY=python3

# Not `python -m pybind11 --cmakedir`: it shell-quotes paths with odd characters
# (our folder has an apostrophe) and CMake then can't open them.
PYBIND11_DIR="$("$PY" -c 'import pybind11; print(pybind11.get_cmake_dir())')"

# Build somewhere without odd characters in the path (Make chokes on the
# apostrophe in "Hackathon26'"), then copy the module back here.
BUILD_DIR="${BUILD_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/otter-tutor/board_prep}"
mkdir -p "$BUILD_DIR"

cmake -S . -B "$BUILD_DIR" \
  -Dpybind11_DIR="$PYBIND11_DIR" \
  -DPython_EXECUTABLE="$PY" -DPYTHON_EXECUTABLE="$PY"
cmake --build "$BUILD_DIR" -j"$(nproc)"
cp "$BUILD_DIR"/board_prep*.so .

echo
"$PY" -c "import sys; sys.path.insert(0, '..'); from vision import BACKEND; print('vision backend:', BACKEND)"
