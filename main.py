import sys
import time
from collections import OrderedDict
from datetime import datetime

import pytz

from utils import (
    request_papers_with_retries,
    filter_by_categories,
    deduplicate_versions,
    extract_arxiv_id,
    generate_table,
    build_term_index,
    generate_index_markdown,
    back_up_files,
    restore_files,
    remove_backups,
    get_daily_date,
)


# 项目仓库地址(用于 Issue 提示)
REPO_URL = "https://github.com/guoyue0412/DailyArxiv"

# 搜索方向配置:每个方向同时检索"全称 + 缩写",结果取并集后去重。
#   label  —— README/Issue 中的小标题
#   abbrev —— 跨方向去重时用于标注论文命中了哪些方向
#   terms  —— 提交给 arXiv 的检索短语
SEARCH_TOPICS = [
    {
        "label": "Vision-Language-Action (VLA)",
        "abbrev": "VLA",
        "terms": ["Vision Language Action", "Vision-Language-Action", "VLA"],
    },
    {
        "label": "World Action Model (WAM)",
        "abbrev": "WAM",
        "terms": ["World Action Model", "World-Action Model", "WAM"],
    },
    {
        "label": "World Model (WM)",
        "abbrev": "WM",
        "terms": ["World Model", "World Models"],
    },
]

MAX_RESULT = 50      # 每个方向从 arXiv 拉取的最大条数
ISSUES_RESULT = 15   # 每个方向写入 Issue 的最大条数

# README 展示列(含跨方向标注 Directions);Issue 省略 Abstract 保持简洁
README_COLUMNS = ["Title", "Date", "Directions", "Abstract", "Comment"]
ISSUE_COLUMNS = ["Title", "Date", "Directions", "Comment"]


def collect_papers():
    """按方向抓取并完成版本去重 + 跨方向去重。

    返回:
        topic_to_papers: OrderedDict[label -> 按时间降序排列的论文列表]
                         每篇论文仅归入其首个命中的方向,并带 Directions 标注。
        all_papers:      去重后的全部论文(供建立术语索引)。
    """
    pool = OrderedDict()          # arxiv_id -> paper(含 Directions)
    primary_ids = OrderedDict()   # label -> 该方向首次命中的 arxiv_id 列表

    for topic in SEARCH_TOPICS:
        label, abbrev, terms = topic["label"], topic["abbrev"], topic["terms"]
        primary_ids.setdefault(label, [])

        papers = request_papers_with_retries(terms, MAX_RESULT)
        if papers is None:
            return None, None  # 抓取失败,交由调用方回滚

        papers = filter_by_categories(papers)
        papers = deduplicate_versions(papers)

        for paper in papers:
            pid = extract_arxiv_id(paper["Link"])
            if pid not in pool:
                paper["Directions"] = [abbrev]
                pool[pid] = paper
                primary_ids[label].append(pid)
            elif abbrev not in pool[pid]["Directions"]:
                pool[pid]["Directions"].append(abbrev)

        time.sleep(5)  # 避免被 arXiv API 限流

    topic_to_papers = OrderedDict()
    for topic in SEARCH_TOPICS:
        label = topic["label"]
        papers = [pool[pid] for pid in primary_ids[label]]
        papers.sort(key=lambda p: p["Date"], reverse=True)  # 按更新时间降序
        topic_to_papers[label] = papers

    return topic_to_papers, list(pool.values())


def main():
    eastern_timezone = pytz.timezone("US/Eastern")
    current_date = datetime.now(eastern_timezone).strftime("%Y-%m-%d")

    back_up_files()

    topic_to_papers, all_papers = collect_papers()
    if topic_to_papers is None:
        print("Failed to get papers!")
        restore_files()
        sys.exit("Failed to get papers!")

    # ---- README.md ----
    with open("README.md", "w") as f_rm:
        f_rm.write("# Daily Papers\n")
        f_rm.write(
            "The project automatically fetches the latest papers from arXiv based on keywords.\n\n"
            "The subheadings in the README file represent the search directions; each direction is "
            "matched by both its full name and abbreviation (e.g. \"Vision Language Action\" and \"VLA\").\n\n"
            "A paper matching multiple directions is listed once, with all matched directions shown in "
            "the **Directions** column. See [INDEX.md](INDEX.md) for a term-level cross-reference index.\n\n"
            "You can click the 'Watch' button to receive daily email notifications.\n\n"
            "Last update: {0}\n\n"
            "_Based on the [DailyArxiv](https://github.com/Ed1sonChen/DailyArxiv) template by Ed1sonChen._\n\n".format(current_date)
        )
        for topic in SEARCH_TOPICS:
            label = topic["label"]
            f_rm.write("## {0}\n".format(label))
            f_rm.write(generate_table(topic_to_papers[label], README_COLUMNS))
            f_rm.write("\n\n")

    # ---- .github/ISSUE_TEMPLATE.md ----
    with open(".github/ISSUE_TEMPLATE.md", "w") as f_is:
        f_is.write("---\n")
        f_is.write("title: Latest {0} Papers - {1}\n".format(ISSUES_RESULT, get_daily_date()))
        f_is.write("labels: documentation\n")
        f_is.write("---\n")
        f_is.write(
            "**Please check the [Github]({0}) page for a better reading experience and more papers.**\n\n".format(REPO_URL)
        )
        for topic in SEARCH_TOPICS:
            label = topic["label"]
            f_is.write("## {0}\n".format(label))
            f_is.write(generate_table(topic_to_papers[label][:ISSUES_RESULT], ISSUE_COLUMNS))
            f_is.write("\n\n")

    # ---- INDEX.md(摘要术语索引)----
    term_index = build_term_index(all_papers)
    with open("INDEX.md", "w") as f_idx:
        f_idx.write(generate_index_markdown(term_index, all_papers, current_date))
        f_idx.write("\n")

    remove_backups()


if __name__ == "__main__":
    main()
