"""utils.py 纯逻辑函数的单元测试(无网络依赖)。

运行方式:
    python -m unittest test_utils -v
"""
import unittest

import utils


def make_paper(title, abstract, link, tags, date, comment="", directions=None):
    paper = {
        "Title": title,
        "Abstract": abstract,
        "Link": link,
        "Tags": tags,
        "Date": date,
        "Comment": comment,
    }
    if directions is not None:
        paper["Directions"] = directions
    return paper


class TestSearchQuery(unittest.TestCase):
    def test_or_union_of_terms_and_fields(self):
        query = utils.build_search_query(["Vision Language Action", "VLA"])
        # 每个检索词都应在 ti 与 abs 上展开,且整体用 OR 连接
        self.assertIn('ti:"Vision Language Action"', query)
        self.assertIn('abs:"Vision Language Action"', query)
        self.assertIn('ti:"VLA"', query)
        self.assertIn('abs:"VLA"', query)
        self.assertEqual(query.count(" OR "), 3)  # 4 个子句 -> 3 个 OR
        self.assertTrue(query.startswith("(") and query.endswith(")"))

    def test_blank_terms_skipped(self):
        query = utils.build_search_query(["VLA", "  ", ""])
        self.assertEqual(query.count("ti:"), 1)


class TestArxivId(unittest.TestCase):
    def test_strip_version(self):
        self.assertEqual(utils.extract_arxiv_id("https://arxiv.org/abs/2511.16449v4"), "2511.16449")

    def test_no_version(self):
        self.assertEqual(utils.extract_arxiv_id("https://arxiv.org/abs/2605.25889"), "2605.25889")

    def test_old_style_id(self):
        self.assertEqual(
            utils.extract_arxiv_id("https://arxiv.org/abs/cond-mat/0211034v1"),
            "cond-mat/0211034",
        )


class TestFilterByCategories(unittest.TestCase):
    def test_keep_target_category(self):
        papers = [
            make_paper("a", "x", "l1", ["cs.RO", "cs.AI"], "2026-01-01T00:00:00Z"),
            make_paper("b", "y", "l2", ["astro-ph.IM"], "2026-01-01T00:00:00Z"),
        ]
        kept = utils.filter_by_categories(papers)
        self.assertEqual([p["Title"] for p in kept], ["a"])

    def test_custom_categories(self):
        papers = [make_paper("a", "x", "l1", ["stat.ML"], "2026-01-01T00:00:00Z")]
        self.assertEqual(len(utils.filter_by_categories(papers, {"stat.ML"})), 1)
        self.assertEqual(len(utils.filter_by_categories(papers, {"cs.RO"})), 0)


class TestDeduplicateVersions(unittest.TestCase):
    def test_keep_latest_version(self):
        papers = [
            make_paper("old", "x", "https://arxiv.org/abs/2511.0001v1", ["cs.RO"], "2026-01-01T00:00:00Z"),
            make_paper("new", "x", "https://arxiv.org/abs/2511.0001v3", ["cs.RO"], "2026-03-01T00:00:00Z"),
            make_paper("other", "x", "https://arxiv.org/abs/2511.0002v1", ["cs.RO"], "2026-02-01T00:00:00Z"),
        ]
        result = utils.deduplicate_versions(papers)
        self.assertEqual(len(result), 2)
        ids = {utils.extract_arxiv_id(p["Link"]): p["Title"] for p in result}
        self.assertEqual(ids["2511.0001"], "new")  # 保留最新版本


class TestTermIndex(unittest.TestCase):
    def test_candidate_terms_filters_stopwords(self):
        terms = utils.candidate_terms("We propose a diffusion policy for robot manipulation")
        self.assertIn("diffusion", terms)
        self.assertIn("diffusion policy", terms)
        self.assertNotIn("we", terms)       # 停用词
        self.assertNotIn("propose", terms)  # 学术泛词在停用表内

    def test_build_term_index_df_filter(self):
        papers = [
            make_paper("Diffusion policy for robots", "diffusion policy manipulation", "l1", ["cs.RO"], "d"),
            make_paper("Another diffusion study", "diffusion policy planning", "l2", ["cs.RO"], "d"),
            make_paper("Token pruning method", "token pruning acceleration", "l3", ["cs.RO"], "d"),
        ]
        index = utils.build_term_index(papers, min_df=2, max_df_ratio=1.0)
        terms = {t for t, _ in index}
        # "diffusion" 出现在 2 篇,满足 min_df=2;"token" 仅 1 篇,应被过滤
        self.assertIn("diffusion", terms)
        self.assertNotIn("token", terms)

    def test_empty_papers(self):
        self.assertEqual(utils.build_term_index([]), [])


class TestGenerateTable(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(utils.generate_table([], ["Title", "Date"]), "_No papers found._")

    def test_columns_and_directions(self):
        papers = [
            make_paper(
                "Cool Paper", "abstract text", "https://arxiv.org/abs/2511.0001v1",
                ["cs.RO"], "2026-05-01T00:00:00Z", comment="short",
                directions=["VLA", "WM"],
            )
        ]
        table = utils.generate_table(papers, ["Title", "Date", "Directions", "Comment"])
        lines = table.split("\n")
        self.assertEqual(len(lines), 3)  # header + separator + 1 row
        self.assertIn("[Cool Paper](https://arxiv.org/abs/2511.0001v1)", table)
        self.assertIn("2026-05-01", table)
        self.assertIn("VLA, WM", table)

    def test_pipe_escaped(self):
        papers = [make_paper("Title | with pipe", "a | b", "l", ["cs.RO"], "2026-05-01T00:00:00Z")]
        table = utils.generate_table(papers, ["Title"])
        # 标题中的管道符必须被转义,避免破坏表格
        self.assertNotIn("Title | with pipe", table)
        self.assertIn("Title \\| with pipe", table)


class TestGenerateIndexMarkdown(unittest.TestCase):
    def test_links_and_truncation(self):
        papers = [
            make_paper("P%d" % i, "x", "https://arxiv.org/abs/2511.%04dv1" % i, ["cs.RO"], "d")
            for i in range(25)
        ]
        term_index = [("diffusion", list(range(25)))]
        md = utils.generate_index_markdown(term_index, papers, "2026-05-27", max_links_per_term=20)
        self.assertIn("| diffusion | 25 |", md)
        self.assertIn("(+5 more)", md)  # 25 篇,只显示 20 条


class TestRequestWrapper(unittest.TestCase):
    """request_papers_with_retries 的容错封装(限流/重试已由 arxiv.Client 内部处理)。"""

    def setUp(self):
        self._orig_request = utils.request_papers

    def tearDown(self):
        utils.request_papers = self._orig_request

    def test_returns_papers_on_success(self):
        utils.request_papers = lambda *a, **k: [make_paper("ok", "x", "l", ["cs.RO"], "d")]
        result = utils.request_papers_with_retries(["VLA"], 10)
        self.assertIsNotNone(result)
        self.assertEqual(result[0]["Title"], "ok")

    def test_none_on_exception(self):
        def boom(*args, **kwargs):
            raise utils.arxiv.HTTPError("u", 0, 429)

        utils.request_papers = boom
        self.assertIsNone(utils.request_papers_with_retries(["VLA"], 10))

    def test_none_on_empty(self):
        utils.request_papers = lambda *a, **k: []
        self.assertIsNone(utils.request_papers_with_retries(["VLA"], 10))


if __name__ == "__main__":
    unittest.main()
