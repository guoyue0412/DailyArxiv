"""把 DailyArxiv 生成的 papers.json 转换为 Obsidian 笔记。

设计:抓取由云端 GitHub Actions 完成并提交 papers.json;本脚本只在本地读取该结构化数据
并写入 Obsidian 库,因此**不会在本地再次请求 arXiv**(规避 IP 限流)。

按"每日 + 每方向"组织:每个方向每天生成一个汇总笔记,如
    <vault>/40_Reading_Queue/DailyArxiv/2026-05-27-VLA.md

用法:
    python to_obsidian.py --vault /path/to/paper-reading-vault
    python to_obsidian.py --data papers.json --vault <vault> --subdir 40_Reading_Queue/DailyArxiv
"""
import os
import json
import argparse
from typing import List, Dict


def _abstract_callout(abstract: str) -> List[str]:
    """渲染为 Obsidian 可折叠摘要 callout。摘要已是单行(换行被压缩)。"""
    text = abstract.strip()
    if not text:
        return []
    return ["> [!abstract]- Abstract", "> " + text]


def render_paper(paper: Dict) -> str:
    """渲染单篇论文为 Markdown 片段。"""
    title = paper.get("Title", "Untitled")
    link = paper.get("Link", "")
    date = paper.get("Date", "").split("T")[0]
    directions = ", ".join(paper.get("Directions", []))
    authors = paper.get("Authors", [])
    author_str = (authors[0] + " et al.") if authors else ""
    comment = paper.get("Comment", "").strip()

    lines = ["### [{0}]({1})".format(title, link)]
    meta = []
    if date:
        meta.append("**Date**: {0}".format(date))
    if directions:
        meta.append("**Directions**: {0}".format(directions))
    if author_str:
        meta.append("**Authors**: {0}".format(author_str))
    if meta:
        lines.append(" · ".join(meta))
    if comment:
        lines.append("**Comment**: {0}".format(comment))
    lines.extend(_abstract_callout(paper.get("Abstract", "")))
    return "\n".join(lines)


def render_direction_note(date: str, label: str, abbrev: str, papers: List[Dict]) -> str:
    """渲染某天某方向的汇总笔记(含 frontmatter)。"""
    frontmatter = [
        "---",
        "date: {0}".format(date),
        "direction: {0}".format(abbrev),
        'direction_full: "{0}"'.format(label),
        "count: {0}".format(len(papers)),
        "source: arXiv",
        "tags: [DailyArxiv, {0}]".format(abbrev),
        "---",
        "",
    ]
    body = [
        "# {0} · {1}".format(date, label),
        "",
        "> 由 DailyArxiv 自动抓取,共 **{0}** 篇。点击标题打开 arXiv。".format(len(papers)),
        "",
    ]
    if not papers:
        body.append("_本日该方向无新论文。_")
    else:
        body.append("\n\n".join(render_paper(p) for p in papers))
    return "\n".join(frontmatter + body) + "\n"


def write_notes(data: Dict, vault: str, subdir: str) -> List[str]:
    """根据 papers.json 数据写入每方向的每日笔记,返回写入的文件路径列表。"""
    date = data["date"]
    out_dir = os.path.join(vault, subdir)
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for direction in data["directions"]:
        note = render_direction_note(
            date, direction["label"], direction["abbrev"], direction["papers"]
        )
        path = os.path.join(out_dir, "{0}-{1}.md".format(date, direction["abbrev"]))
        with open(path, "w") as f:
            f.write(note)
        written.append(path)
    return written


def main():
    parser = argparse.ArgumentParser(description="把 DailyArxiv papers.json 转为 Obsidian 笔记")
    parser.add_argument("--vault", required=True, help="Obsidian 库根目录")
    parser.add_argument("--data", default="papers.json", help="papers.json 路径")
    parser.add_argument(
        "--subdir",
        default="40_Reading_Queue/DailyArxiv",
        help="笔记写入库内的子目录",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.vault):
        raise SystemExit("Vault 目录不存在: {0}".format(args.vault))
    with open(args.data) as f:
        data = json.load(f)

    written = write_notes(data, args.vault, args.subdir)
    for path in written:
        print("写入: {0}".format(path))
    print("完成,共 {0} 个笔记。".format(len(written)))


if __name__ == "__main__":
    main()
