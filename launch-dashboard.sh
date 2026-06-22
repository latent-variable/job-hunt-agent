#!/bin/bash
cd "$(dirname "$0")" && unset PYTHONHOME PYTHONPATH && /opt/anaconda3/bin/python3 tools/serve_dashboard.py
