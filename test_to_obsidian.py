"""to_obsidian.py 的单元测试(无网络、无外部依赖)。

运行方式:
    python -m unittest test_to_obsidian -v
"""
import os
import tempfile
import unittest

import to_obsidian


def make_paper(title="T", link="http://arxiv.org/abs/2511.0001v1", abstract="abs text",
               authors=None, date="2026-05-25T00:00:00Z", comment="", directions=None):
    return {
        "Title": title,
        "Link": link,
        "Abstract": abstract,
        "Authors": authors if authors is not None else ["Alice", "Bob"],
        "Date": date,
        "Comment": comment,
        "Directions": directions if directions is not None else ["VLA"],
    }


class TestRenderPaper(unittest.TestCase):
    def test_basic_fields(self):
        md = to_obsidian.render_paper(make_paper(directions=["VLA", "WM"], comment="ICML 2026"))
        self.assertIn("### [T](http://arxiv.org/abs/2511.0001v1)", md)
        self.assertIn("**Date**: 2026-05-25", md)
        self.assertIn("**Directions**: VLA, WM", md)
        self.assertIn("**Authors**: Alice et al.", md)
        self.assertIn("**Comment**: ICML 2026", md)
        self.assertIn("> [!abstract]- Abstract", md)
        self.assertIn("> abs text", md)

    def test_empty_abstract_and_comment(self):
        md = to_obsidian.render_paper(make_paper(abstract="", comment=""))
        self.assertNotIn("[!abstract]", md)
        self.assertNotIn("**Comment**", md)

    def test_no_authors(self):
        md = to_obsidian.render_paper(make_paper(authors=[]))
        self.assertNotIn("**Authors**", md)


class TestRenderDirectionNote(unittest.TestCase):
    def test_frontmatter_and_count(self):
        note = to_obsidian.render_direction_note(
            "2026-05-27", "Vision-Language-Action (VLA)", "VLA", [make_paper(), make_paper()]
        )
        self.assertTrue(note.startswith("---\n"))
        self.assertIn("date: 2026-05-27", note)
        self.assertIn("direction: VLA", note)
        self.assertIn('direction_full: "Vision-Language-Action (VLA)"', note)
        self.assertIn("count: 2", note)
        self.assertIn("tags: [DailyArxiv, VLA]", note)
        self.assertIn("# 2026-05-27 · Vision-Language-Action (VLA)", note)

    def test_empty_papers(self):
        note = to_obsidian.render_direction_note("2026-05-27", "World Model (WM)", "WM", [])
        self.assertIn("count: 0", note)
        self.assertIn("无新论文", note)


class TestWriteNotes(unittest.TestCase):
    def test_writes_one_file_per_direction(self):
        data = {
            "date": "2026-05-27",
            "directions": [
                {"label": "Vision-Language-Action (VLA)", "abbrev": "VLA", "papers": [make_paper()]},
                {"label": "World Model (WM)", "abbrev": "WM", "papers": []},
            ],
        }
        with tempfile.TemporaryDirectory() as vault:
            written = to_obsidian.write_notes(data, vault, "40_Reading_Queue/DailyArxiv")
            self.assertEqual(len(written), 2)
            names = sorted(os.path.basename(p) for p in written)
            self.assertEqual(names, ["2026-05-27-VLA.md", "2026-05-27-WM.md"])
            for path in written:
                self.assertTrue(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
