#!/usr/bin/env bash
# 本地同步脚本:拉取云端 GitHub Actions 生成的 papers.json,转换为 Obsidian 笔记。
# 抓取在云端完成,本脚本不请求 arXiv,因此不受 IP 限流影响。
# 路径与行为通过环境变量配置(由 launchd plist 注入):
#   OBSIDIAN_VAULT  必填,Obsidian 库根目录
#   OBSIDIAN_SUBDIR 笔记子目录,默认 40_Reading_Queue/DailyArxiv
#   PYTHON_BIN      python 解释器,默认 python3
#   COMMIT_VAULT    置 1 时自动提交并推送 vault(默认 0,仅写本地文件)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT="${OBSIDIAN_VAULT:?请设置 OBSIDIAN_VAULT 指向 Obsidian 库根目录}"
SUBDIR="${OBSIDIAN_SUBDIR:-40_Reading_Queue/DailyArxiv}"
PYTHON="${PYTHON_BIN:-python3}"
COMMIT_VAULT="${COMMIT_VAULT:-0}"

cd "$REPO_DIR"
echo "[$(date '+%F %T')] 拉取最新 papers.json ..."
git pull --ff-only origin main

echo "生成 Obsidian 笔记到 $VAULT/$SUBDIR ..."
"$PYTHON" to_obsidian.py --vault "$VAULT" --subdir "$SUBDIR"

if [ "$COMMIT_VAULT" = "1" ]; then
  cd "$VAULT"
  git add -- "$SUBDIR"
  if git diff --cached --quiet; then
    echo "vault 无变更,跳过提交。"
  else
    git commit -m "DailyArxiv: $(date '+%F') 更新"
    git push origin "$(git rev-parse --abbrev-ref HEAD)"
    echo "已提交并推送 vault。"
  fi
fi
echo "完成。"
