import os
import re
import time
import datetime
from collections import defaultdict
from typing import List, Dict, Optional, Tuple

import pytz
import shutil
import urllib
import urllib.error
import urllib.parse
import urllib.request

import feedparser
from easydict import EasyDict


# 需要随生成产物一起备份/恢复的文件,任一步骤失败时整体回滚
BACKUP_FILES = ["README.md", ".github/ISSUE_TEMPLATE.md", "INDEX.md"]

# arXiv 建议带上可识别的描述性 User-Agent,有助于降低被限流概率
USER_AGENT = "DailyArxiv/1.0 (https://github.com/guoyue0412/DailyArxiv)"

# 默认领域过滤集合:聚焦机器人 / 机器学习相关方向,
# 既能保留 VLA / WAM / WM 论文,又能滤掉缩写带来的跨领域噪声(如天文 VLA、机械臂 WAM)。
DEFAULT_TARGET_CATEGORIES = {
    "cs.RO", "cs.AI", "cs.CV", "cs.LG", "cs.CL", "cs.MA", "cs.SY", "eess.SY",
}


def remove_duplicated_spaces(text: str) -> str:
    return " ".join(text.split())


def escape_markdown_cell(text: str) -> str:
    """转义 Markdown 表格单元格里的管道符与换行,避免破坏表格结构。"""
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


# ---------------------------------------------------------------------------
# arXiv 检索
# ---------------------------------------------------------------------------

def build_search_query(terms: List[str]) -> str:
    """为一个方向构造 arXiv search_query。

    对每个检索词在标题(ti)或摘要(abs)中做短语匹配,所有检索词与字段之间取并集(OR),
    因此"缩写 + 全称"会一并命中。相比原实现按词数在 AND/OR 间切换,这里逻辑统一且可预测。
    """
    clauses = []
    for term in terms:
        term = term.strip()
        if not term:
            continue
        phrase = '"{0}"'.format(term)
        clauses.append("ti:{0}".format(phrase))
        clauses.append("abs:{0}".format(phrase))
    return "(" + " OR ".join(clauses) + ")"


def request_papers(
    terms: List[str],
    max_results: int,
    sort_by: str = "lastUpdatedDate",
    sort_order: str = "descending",
) -> List[Dict[str, str]]:
    """调用 arXiv API 抓取一个方向的论文。

    使用 urlencode 安全编码查询参数,避免原实现手工拼接 URL 带来的转义隐患。
    """
    params = {
        "search_query": build_search_query(terms),
        "max_results": max_results,
        "sortBy": sort_by,
        "sortOrder": sort_order,
    }
    url = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    response = urllib.request.urlopen(request).read().decode("utf-8")
    feed = feedparser.parse(response)

    papers = []
    for entry in feed.entries:
        entry = EasyDict(entry)
        paper = EasyDict()
        paper.Title = remove_duplicated_spaces(entry.title.replace("\n", " "))
        paper.Abstract = remove_duplicated_spaces(entry.summary.replace("\n", " "))
        paper.Authors = [remove_duplicated_spaces(a["name"].replace("\n", " ")) for a in entry.authors]
        paper.Link = remove_duplicated_spaces(entry.link.replace("\n", " "))
        paper.Tags = [remove_duplicated_spaces(t["term"].replace("\n", " ")) for t in entry.tags]
        paper.Comment = remove_duplicated_spaces(entry.get("arxiv_comment", "").replace("\n", " "))
        paper.Date = entry.updated
        papers.append(paper)
    return papers


def request_papers_with_retries(
    terms: List[str],
    max_results: int,
    sort_by: str = "lastUpdatedDate",
    sort_order: str = "descending",
    retries: int = 6,
    empty_wait: int = 60 * 30,
    error_wait: int = 30,
) -> Optional[List[Dict[str, str]]]:
    """带重试的抓取,处理两类瞬时故障:

    - HTTP/网络错误(如 429 限流、503 不可用):线性退避后重试,避免直接崩溃。
    - 空列表(arXiv API 偶发返回空):等待较长时间后重试。
    重试耗尽返回 None,由调用方据此回滚已备份的文件。
    """
    for attempt in range(retries):
        try:
            papers = request_papers(terms, max_results, sort_by, sort_order)
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            wait = error_wait * (attempt + 1)
            print("arXiv request failed ({0}), retrying in {1}s...".format(exc, wait))
            time.sleep(wait)
            continue
        if len(papers) > 0:
            return papers
        print("Unexpected empty list, retrying...")
        time.sleep(empty_wait)
    return None


# ---------------------------------------------------------------------------
# 过滤与去重
# ---------------------------------------------------------------------------

def extract_arxiv_id(link: str) -> str:
    """从 arXiv 链接提取去版本号的基础 ID。

    例:https://arxiv.org/abs/2511.16449v4 -> 2511.16449
        https://arxiv.org/abs/cond-mat/0211034v1 -> cond-mat/0211034
    """
    match = re.search(r"arxiv\.org/abs/(.+?)(v\d+)?$", link)
    if match:
        return match.group(1)
    return link


def filter_by_categories(
    papers: List[Dict[str, str]],
    target_categories: Optional[set] = None,
) -> List[Dict[str, str]]:
    """只保留至少命中一个目标 arXiv 分类的论文。"""
    if target_categories is None:
        target_categories = DEFAULT_TARGET_CATEGORIES
    results = []
    for paper in papers:
        if any(tag in target_categories for tag in paper["Tags"]):
            results.append(paper)
    return results


def deduplicate_versions(papers: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """同一篇论文(去版本号后 ID 相同)只保留更新时间最新的一条。

    Date 为 ISO8601 字符串(如 2026-05-25T...Z),字典序即时间序,可直接比较。
    """
    by_id: Dict[str, Dict[str, str]] = {}
    for paper in papers:
        pid = extract_arxiv_id(paper["Link"])
        if pid not in by_id or paper["Date"] > by_id[pid]["Date"]:
            by_id[pid] = paper
    return list(by_id.values())


# ---------------------------------------------------------------------------
# 表格生成
# ---------------------------------------------------------------------------

def _format_value(key: str, paper: Dict[str, str]) -> str:
    """按列名渲染单元格内容。"""
    if key == "Title":
        return "**[{0}]({1})**".format(escape_markdown_cell(paper["Title"]), paper["Link"])
    if key == "Date":
        return paper["Date"].split("T")[0]
    if key == "Directions":
        return ", ".join(paper.get("Directions", []))
    if key == "Abstract":
        return "<details><summary>Show</summary><p>{0}</p></details>".format(
            escape_markdown_cell(paper.get("Abstract", ""))
        )
    if key == "Authors":
        authors = paper.get("Authors", [])
        return (escape_markdown_cell(authors[0]) + " et al.") if authors else ""
    if key == "Tags":
        tags = ", ".join(paper.get("Tags", []))
        tags = escape_markdown_cell(tags)
        if len(tags) > 10:
            return "<details><summary>{0}...</summary><p>{1}</p></details>".format(tags[:5], tags)
        return tags
    if key == "Comment":
        comment = escape_markdown_cell(paper.get("Comment", ""))
        if comment == "":
            return ""
        if len(comment) > 20:
            return "<details><summary>{0}...</summary><p>{1}</p></details>".format(comment[:5], comment)
        return comment
    return escape_markdown_cell(str(paper.get(key, "")))


def generate_table(papers: List[Dict[str, str]], columns: List[str]) -> str:
    """根据显式列顺序生成 Markdown 表格。空列表时返回占位文本。"""
    if not papers:
        return "_No papers found._"
    header = "| " + " | ".join("**" + c + "**" for c in columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = ["| " + " | ".join(_format_value(c, paper) for c in columns) + " |" for paper in papers]
    return "\n".join([header, separator] + rows)


# ---------------------------------------------------------------------------
# 摘要术语索引
# ---------------------------------------------------------------------------

# 常见英文停用词 + 学术论文高频泛词,用于剔除无区分度的术语
STOPWORDS = set(
    """
    a an the and or but if then else for to of in on at by with from as is are was were be been being
    this that these those we our us it its they them their he she you your i me my mine ours yours his her
    not no nor so than too very can will would should could may might must shall do does did done have has had
    into over under above below between among through during before after about against without within across
    per via vs etc eg ie also more most much many few some any all each both either neither such only own same
    other another which who whom whose what when where why how there here out off up down again further once
    paper papers method methods approach approaches model models propose proposed using used use uses based
    results result show shows shown demonstrate demonstrates present presents achieve achieves achieved task
    tasks work works study studies novel new framework frameworks via toward towards able enable enables
    learning learn learned train trained training data dataset datasets performance evaluate evaluation
    experiment experiments experimental compared comparison state art existing prior recent recently however
    while given large small high low strong robust effective efficient significantly significant improve
    improves improvement improvements problem problems challenge challenges system systems setting settings
    """.split()
)


def tokenize(text: str) -> List[str]:
    """小写化并切出由字母开头、可含数字与连字符的 token。"""
    return re.findall(r"[a-z][a-z0-9\-]{2,}", text.lower())


def candidate_terms(text: str) -> set:
    """从一段文本中抽取候选术语:过滤停用词后的一元词与二元短语。

    返回集合(每篇论文每个术语只计一次),便于按文档频率(DF)建索引。
    """
    tokens = tokenize(text)
    terms = set()
    for tok in tokens:
        if len(tok) >= 4 and tok not in STOPWORDS:
            terms.add(tok)
    for first, second in zip(tokens, tokens[1:]):
        if first in STOPWORDS or second in STOPWORDS:
            continue
        if len(first) >= 3 and len(second) >= 3:
            terms.add(first + " " + second)
    return terms


def build_term_index(
    papers: List[Dict[str, str]],
    min_df: int = 2,
    max_df_ratio: float = 0.4,
    max_terms: int = 150,
) -> List[Tuple[str, List[int]]]:
    """对全部论文的标题+摘要建立"术语 -> 论文下标"的倒排索引。

    - min_df:术语至少出现在多少篇论文中才纳入(过滤偶发噪声)。
    - max_df_ratio:出现比例超过该阈值的术语视为泛词剔除(类似 IDF 过滤)。
    - max_terms:最终保留的术语数上限。
    结果按文档频率降序、术语字典序升序排列。
    """
    total = len(papers)
    if total == 0:
        return []
    term_to_docs: Dict[str, set] = defaultdict(set)
    for index, paper in enumerate(papers):
        text = paper.get("Title", "") + ". " + paper.get("Abstract", "")
        for term in candidate_terms(text):
            term_to_docs[term].add(index)

    max_df = max(min_df, int(max_df_ratio * total))
    selected = [
        (term, sorted(docs))
        for term, docs in term_to_docs.items()
        if min_df <= len(docs) <= max_df
    ]
    selected.sort(key=lambda item: (-len(item[1]), item[0]))
    return selected[:max_terms]


def generate_index_markdown(
    term_index: List[Tuple[str, List[int]]],
    papers: List[Dict[str, str]],
    current_date: str,
    max_links_per_term: int = 20,
) -> str:
    """根据术语索引生成 INDEX.md 内容。每个术语列出包含它的论文链接。"""
    lines = [
        "# Term Index",
        "",
        "Auto-generated cross-reference of frequent terms extracted from the titles and abstracts of the indexed papers. "
        "Click a paper title to open it on arXiv.",
        "",
        "Last update: {0}".format(current_date),
        "",
        "| **Term** | **# Papers** | **Papers** |",
        "| --- | --- | --- |",
    ]
    for term, doc_ids in term_index:
        shown = doc_ids[:max_links_per_term]
        links = "; ".join(
            "[{0}]({1})".format(escape_markdown_cell(papers[i]["Title"]), papers[i]["Link"])
            for i in shown
        )
        if len(doc_ids) > max_links_per_term:
            links += "; _(+{0} more)_".format(len(doc_ids) - max_links_per_term)
        lines.append("| {0} | {1} | {2} |".format(escape_markdown_cell(term), len(doc_ids), links))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 文件备份 / 恢复
# ---------------------------------------------------------------------------

def back_up_files() -> None:
    """备份待覆写文件(复制而非移动,原文件保留,失败时可整体回滚)。"""
    for path in BACKUP_FILES:
        if os.path.exists(path):
            shutil.copy(path, path + ".bk")


def restore_files() -> None:
    """从备份恢复(覆盖可能已写坏的产物)。"""
    for path in BACKUP_FILES:
        backup = path + ".bk"
        if os.path.exists(backup):
            shutil.move(backup, path)


def remove_backups() -> None:
    """成功后清理备份。"""
    for path in BACKUP_FILES:
        backup = path + ".bk"
        if os.path.exists(backup):
            os.remove(backup)


def get_daily_date() -> str:
    """返回美东时区下形如 'March 01, 2021' 的日期,用于 Issue 标题。"""
    eastern_timezone = pytz.timezone("US/Eastern")
    today = datetime.datetime.now(eastern_timezone)
    return today.strftime("%B %d, %Y")
