#!/usr/bin/env bash
set -euo pipefail

# Prepare the Python build toolchain and pin the NumPy version that keeps the
# PyTorch NumPy bridge enabled in the validated DLC workstation flow.
python3 -m pip install typing_extensions
python3 -m pip install --upgrade packaging 'setuptools>=77.0.3,<81.0.0' 'setuptools-scm>=8.0' wheel ninja jinja2
python3 -m pip install --force-reinstall 'numpy==1.26.4'

if [ $# -gt 0 ]; then
  cache_file="$1/build/CMakeCache.txt"
  if [ -f "$cache_file" ]; then
    echo '== Existing USE_NUMPY cache entry =='
    rg '^USE_NUMPY:BOOL=' "$cache_file" || true
  fi
fi
