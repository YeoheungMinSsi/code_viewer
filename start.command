#!/bin/bash
set -e
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  echo "가상환경(.venv)을 만들고 필요한 패키지를 설치합니다..."
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi

echo "코드 산책을 시작합니다. 종료하려면 Ctrl+C를 누르세요."
exec .venv/bin/python viewer.py
