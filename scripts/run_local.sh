#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "DynaTutor Local Study Mode"
echo "1) 백엔드: http://localhost:8000"
echo "2) 프론트엔드: http://localhost:3000"
echo "터미널 두 개를 띄워 실행합니다. macOS/Linux에서는 터미널 앱 환경에 따라 자동 분할이 다르므로, 아래 명령을 각각 실행해도 됩니다."
echo ""
echo "Backend:  $ROOT/scripts/run_backend.sh"
echo "Frontend: $ROOT/scripts/run_frontend.sh"
echo ""
if command -v tmux >/dev/null 2>&1; then
  tmux new-session -d -s dynatutor "$ROOT/scripts/run_backend.sh"
  tmux split-window -h "$ROOT/scripts/run_frontend.sh"
  tmux attach -t dynatutor
else
  echo "tmux가 없어서 백엔드만 먼저 실행합니다. 새 터미널에서 scripts/run_frontend.sh를 실행하세요."
  "$ROOT/scripts/run_backend.sh"
fi
