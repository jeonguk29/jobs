#!/bin/zsh
# 맥(한국 IP)에서 원티드만 수집해 docs/sources/wanted.json 으로 올린다. launchd 가 매일 08:30 에 실행.
set -e
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
cd "$(dirname "$0")/.."
echo "== $(date '+%Y-%m-%d %H:%M') 시작"
git pull -q --rebase origin main || true
./venv/bin/python scraper/scrape.py --only wanted
git add docs/sources/wanted.json docs/logos
git commit -q -m "chore: 원티드 로컬 수집 $(date '+%Y-%m-%d %H:%M')" || { echo "변경 없음"; exit 0; }
git push -q origin main
echo "== 푸시 완료"
