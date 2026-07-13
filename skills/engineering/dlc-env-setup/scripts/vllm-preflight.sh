#!/usr/bin/env bash
set -euo pipefail

# Install the Python packaging stack required by local vLLM editable installs.
python3 -m pip install --upgrade pip packaging 'setuptools>=77.0.3,<81.0.0' 'setuptools-scm>=8.0' wheel ninja jinja2
python3 -m pip install pybind11 grpcio-tools==1.78.0

python3 -m pip list | rg '^(pip|setuptools|setuptools-scm|wheel|ninja|jinja2|packaging|pybind11|grpcio-tools)\b' || true
