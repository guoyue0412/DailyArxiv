# Daily Papers

自动从 arXiv 抓取 VLA / WAM / WM 三个方向最新论文的工具。

- **Vision-Language-Action (VLA)**:Vision Language Action / VLA
- **World Action Model (WAM)**:World Action Model / WAM
- **World Model (WM)**:World Model / World Models

每个方向同时用"全称 + 缩写"检索并合并去重;命中多个方向的论文只列一次,并在 **Directions** 列标注。
术语级交叉索引见 [INDEX.md](INDEX.md)。

本页论文列表由 GitHub Actions 每个工作日自动生成并覆盖。点击 'Watch' 可订阅每日邮件通知。

本地运行:

```bash
pip install -r requirements.txt
python -m unittest test_utils -v   # 单元测试
python main.py                     # 抓取并生成 README.md / INDEX.md / Issue 模板
```

_Based on the [DailyArxiv](https://github.com/Ed1sonChen/DailyArxiv) template by Ed1sonChen._
