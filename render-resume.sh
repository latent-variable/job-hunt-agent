#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "Usage: ./render-resume.sh <input.html> [output.pdf]" >&2
  echo "Example: ./render-resume.sh resumes/generated/company_role/YourName_Company_Role.html" >&2
  exit 1
fi

cd "$ROOT_DIR"
node html2pdf/html-to-pdf.mjs "$@"
