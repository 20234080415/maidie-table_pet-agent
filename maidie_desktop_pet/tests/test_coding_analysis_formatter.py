from __future__ import annotations

import unittest

from core.formatters import CodingAnalysisFormatter


class CodingAnalysisFormatterTests(unittest.TestCase):
    def setUp(self):
        self.formatter = CodingAnalysisFormatter()

    def test_structured_result_becomes_neutral_sections(self):
        result = self.formatter.format({
            "project_name": "DAY01",
            "project_type": "C 语言学习项目",
            "total_files": 22,
            "language": "C",
            "purpose": "练习 Linux 文件 IO",
            "structure": {"code": "示例代码", "notes": "课程笔记"},
            "priority": ["修复错误的文件打开模式"],
            "validation_suggestions": ["编译并运行 practice.c"],
            "cautions": ["保持只读分析"],
        })
        self.assertIn("DAY01", result["project_overview"])
        self.assertIn("22", result["project_overview"])
        self.assertIn("Linux 文件 IO", result["project_overview"])
        self.assertEqual(result["priority_suggestions"], ["修复错误的文件打开模式"])
        self.assertEqual(result["validation_suggestions"], ["编译并运行 practice.c"])

    def test_python_repr_summary_is_parsed_without_leaking_repr(self):
        result = self.formatter.format({
            "summary": "{'project_name': 'Demo', 'priority': ['先修复入口'], "
                       "'validation_suggestions': ['运行测试']}"
        })
        rendered = self.formatter.to_plain_text(result)
        self.assertIn("Demo", rendered)
        self.assertIn("先修复入口", rendered)
        self.assertIn("运行测试", rendered)
        self.assertNotIn("{'project_name'", rendered)
        self.assertNotIn("priority':", rendered)

    def test_formatter_contains_no_fixed_persona_words(self):
        result = self.formatter.format({
            "project_name": "Demo", "findings": ["存在重复逻辑"],
        })
        rendered = self.formatter.to_plain_text(result)
        for forbidden in ("傲娇", "可爱", "主人", "哼", "人家", "啦啦啦"):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
