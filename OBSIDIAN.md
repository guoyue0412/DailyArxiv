# 同步到 Obsidian

把每日抓取的论文以"每方向一份汇总笔记"的形式写入本地 Obsidian 库。

## 工作原理

```
GitHub Actions(云端,每工作日)
   └─ 抓取 arXiv → 提交 README.md / INDEX.md / papers.json 到本仓库
本地 launchd(每天)
   └─ sync_obsidian.sh: git pull → to_obsidian.py 读取 papers.json → 写入 Obsidian 库
```

抓取只发生在云端,本地脚本不请求 arXiv,因此**不受 arXiv 对本机 IP 的限流影响**。

每个方向每天生成一个笔记,例如:

```
<vault>/40_Reading_Queue/DailyArxiv/2026-05-27-VLA.md
<vault>/40_Reading_Queue/DailyArxiv/2026-05-27-WAM.md
<vault>/40_Reading_Queue/DailyArxiv/2026-05-27-WM.md
```

笔记含 frontmatter(date / direction / count / tags)、可折叠摘要 callout、arXiv 链接与 Directions 标注。

## 手动运行

```bash
python to_obsidian.py --vault /path/to/paper-reading-vault
# 可选:--subdir 自定义子目录;--data 指定 papers.json 路径
```

## 自动运行(macOS launchd)

1. 把下面的 plist 保存为 `~/Library/LaunchAgents/com.guoyue.dailyarxiv.obsidian.plist`,
   按需修改路径(`OBSIDIAN_VAULT`、`PYTHON_BIN`、仓库绝对路径、运行时间):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.guoyue.dailyarxiv.obsidian</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/guoyue/gy_2026/search_paper/DailyArxiv/sync_obsidian.sh</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>OBSIDIAN_VAULT</key><string>/Users/guoyue/gy_2026/paper-reading-vault</string>
    <key>OBSIDIAN_SUBDIR</key><string>40_Reading_Queue/DailyArxiv</string>
    <key>PYTHON_BIN</key><string>/Users/guoyue/anaconda3/bin/python3</string>
    <key>COMMIT_VAULT</key><string>0</string>
    <key>PATH</key><string>/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin:/Users/guoyue/anaconda3/bin</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>/tmp/dailyarxiv-obsidian.log</string>
  <key>StandardErrorPath</key><string>/tmp/dailyarxiv-obsidian.err</string>
</dict>
</plist>
```

2. 加载(开机自动生效):

```bash
launchctl load ~/Library/LaunchAgents/com.guoyue.dailyarxiv.obsidian.plist
```

3. 立即触发一次验证:

```bash
launchctl start com.guoyue.dailyarxiv.obsidian
cat /tmp/dailyarxiv-obsidian.log
```

卸载:`launchctl unload ~/Library/LaunchAgents/com.guoyue.dailyarxiv.obsidian.plist`

## 说明

- `COMMIT_VAULT=0`(默认):只写本地文件;在 Obsidian 中直接可见,提交时机交给你/Obsidian Git 插件。
  置 `1` 则脚本自动 `git commit && git push` 库,便于多设备同步。
- `git pull` 与推送走 SSH;若 launchd 环境取不到 SSH key,改用 Obsidian Git 插件同步,或在脚本中改用本地路径同步。
