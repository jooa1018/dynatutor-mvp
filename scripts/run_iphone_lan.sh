#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST_IP="$(python - <<'PY'
import socket
s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s.connect(('8.8.8.8', 80))
    print(s.getsockname()[0])
finally:
    s.close()
PY
)"
echo "DynaTutor iPhone 14 LAN Mode"
echo "1) iPhone과 이 컴퓨터를 같은 Wi‑Fi에 연결하세요."
echo "2) iPhone Safari에서 아래 주소를 여세요:"
echo "   http://${HOST_IP}:3000"
echo "3) 공유 버튼 → 홈 화면에 추가를 누르면 앱처럼 실행됩니다."
echo ""
echo "Backend:  http://${HOST_IP}:8000"
echo "Frontend: http://${HOST_IP}:3000"
echo ""
if command -v tmux >/dev/null 2>&1; then
  tmux new-session -d -s dynatutor_iphone "cd '$ROOT/backend' && if [ ! -d .venv ]; then python -m venv .venv; fi && source .venv/bin/activate && pip install -r requirements.txt && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
  tmux split-window -h "cd '$ROOT/frontend' && if [ ! -d node_modules ]; then npm install; fi && npm run dev -- -H 0.0.0.0"
  tmux attach -t dynatutor_iphone
else
  echo "tmux가 없어서 백엔드만 실행합니다. 새 터미널에서 아래 명령을 실행하세요:"
  echo "cd '$ROOT/frontend' && npm run dev -- -H 0.0.0.0"
  cd "$ROOT/backend"
  if [ ! -d .venv ]; then python -m venv .venv; fi
  source .venv/bin/activate
  pip install -r requirements.txt
  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
fi
