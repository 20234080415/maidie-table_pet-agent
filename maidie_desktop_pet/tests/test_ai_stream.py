from __future__ import annotations

import unittest
from unittest.mock import patch

import requests

from ai.client import OpenAICompatibleClient


class _StreamResponse:
    def __init__(self, lines):
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def raise_for_status(self):
        pass

    def iter_lines(self, decode_unicode=True):
        return iter(self._lines)


class AIStreamingTests(unittest.TestCase):
    def setUp(self):
        self.client = OpenAICompatibleClient(
            "secret", "https://example.invalid", "deepseek-v4-flash", source="chat"
        )

    @patch("ai.client.requests.post")
    def test_chat_disables_reasoning_and_emits_visible_content(self, post):
        post.return_value = _StreamResponse([
            'data: {"choices":[{"delta":{"content":"你好"}}]}',
            'data: {"choices":[{"delta":{"content":"。"}}]}',
            "data: [DONE]",
        ])
        deltas: list[str] = []

        result = self.client.ask_stream("hi", [], deltas.append)

        self.assertEqual(deltas, ["你好", "。"])
        self.assertEqual(result["text"], "你好。")
        self.assertEqual(
            post.call_args.kwargs["json"]["thinking"], {"type": "disabled"}
        )

    @patch("ai.client.requests.post")
    def test_connection_reset_before_content_retries_once(self, post):
        post.side_effect = [
            requests.ConnectionError("reset"),
            _StreamResponse([
                'data: {"choices":[{"delta":{"content":"恢复了。"}}]}',
                "data: [DONE]",
            ]),
        ]

        result = self.client.ask_stream("hi", [], lambda _delta: None)

        self.assertEqual(post.call_count, 2)
        self.assertEqual(result["text"], "恢复了。")


if __name__ == "__main__":
    unittest.main()
