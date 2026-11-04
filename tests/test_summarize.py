import json
import os
import tempfile
import unittest
from unittest import mock

from pipeline import summarize


def item(i, title="Stat: Some headline", dimension="D3", m=4):
    return {"id": i, "title": title, "source": "stat", "dimension": dimension,
            "event_type": "regulatory", "m": m, "lang": "en"}


class TestBuildPrompt(unittest.TestCase):
    def test_prompt_carries_items_and_rules(self):
        prompt = summarize.build_prompt([item("a"), item("b")])
        self.assertIn('"id": "a"', prompt)
        self.assertIn('"id": "b"', prompt)
        self.assertIn("3W", prompt)
        self.assertIn("30", prompt)
        self.assertIn("一句", prompt)


class TestParseResponse(unittest.TestCase):
    def test_plain_json_array(self):
        text = '[{"id": "a", "title_zh": "特宝 10mg 获批，规格竞争开打"}]'
        got = summarize.parse_response(text, {"a", "b"})
        self.assertEqual(got, {"a": {"title_zh": "特宝 10mg 获批，规格竞争开打"}})

    def test_code_fence_and_surrounding_prose(self):
        text = '说明\n```json\n[{"id": "a", "title_zh": "一句话提炼"}]\\n```\n'
        self.assertEqual(summarize.parse_response(text, {"a"}),
                         {"a": {"title_zh": "一句话提炼"}})

    def test_drops_unknown_ids_blanks_and_too_long(self):
        text = json.dumps([
            {"id": "zzz", "title_zh": "不认识的条目"},
            {"id": "a", "title_zh": "   "},
            {"id": "b", "title_zh": "字" * 31},
            {"id": "c", "title_zh": "字" * 30},
        ], ensure_ascii=False)
        self.assertEqual(summarize.parse_response(text, {"a", "b", "c"}),
                         {"c": {"title_zh": "字" * 30}})

    def test_malformed_returns_empty(self):
        self.assertEqual(summarize.parse_response("模型抽风了", {"a"}), {})
        self.assertEqual(summarize.parse_response("[]", {"a"}), {})


class TestCache(unittest.TestCase):
    def test_round_trip_and_atomic_replace(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "summaries.json")
            summarize.save_cache({"a": {"title_zh": "一"}}, path)
            self.assertEqual(summarize.load_cache(path), {"a": {"title_zh": "一"}})
            self.assertFalse(os.path.exists(path + ".tmp"))

    def test_missing_file_is_empty(self):
        self.assertEqual(summarize.load_cache("/nonexistent/summaries.json"), {})

    def test_non_utf8_file_is_empty(self):
        # build() 无保护地调用 load_cache；坏编码不能让每日构建在 raw 已落盘后崩掉。
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "summaries.json")
            with open(path, "wb") as fh:
                fh.write(b"\xff\xfe")
            self.assertEqual(summarize.load_cache(path), {})


class TestSummarize(unittest.TestCase):
    def test_only_missing_ids_and_respects_limit(self):
        cache = {"old": {"title_zh": "旧的"}}
        calls = []

        def runner(prompt):
            calls.append(prompt)
            return json.dumps([
                {"id": "a", "title_zh": "A 的提炼"},
                {"id": "b", "title_zh": "B 的提炼"},
            ], ensure_ascii=False)

        got = summarize.summarize([item("old"), item("a"), item("b")], cache,
                                  runner=runner, enabled=True)
        self.assertEqual(len(calls), 1)
        self.assertNotIn('"id": "old"', calls[0])
        self.assertEqual(got["old"], {"title_zh": "旧的"})
        self.assertEqual(got["a"], {"title_zh": "A 的提炼"})
        self.assertEqual(cache, got)  # 原地更新

    def test_limit_caps_one_batch(self):
        seen = {}

        def runner(prompt):
            seen["prompt"] = prompt
            return "[]"

        summarize.summarize([item(str(i)) for i in range(30)], {},
                            runner=runner, enabled=True, limit=20)
        self.assertEqual(seen["prompt"].count('"id":'), 20)

    def test_disabled_never_calls_runner(self):
        def runner(prompt):
            raise AssertionError("must not run")

        got = summarize.summarize([item("a")], {}, runner=runner, enabled=False)
        self.assertEqual(got, {})

    def test_failure_is_retried_once_then_gives_up(self):
        calls = []

        def runner(prompt):
            calls.append(prompt)
            raise RuntimeError("claude not available")

        got = summarize.summarize([item("a")], {}, runner=runner, enabled=True)
        self.assertEqual(len(calls), 2)
        self.assertEqual(got, {})

    def test_second_attempt_success(self):
        calls = []

        def runner(prompt):
            calls.append(prompt)
            if len(calls) == 1:
                raise RuntimeError("boom")
            return '[{"id": "a", "title_zh": "重试成功"}]'

        got = summarize.summarize([item("a")], {}, runner=runner, enabled=True)
        self.assertEqual(got["a"]["title_zh"], "重试成功")

    def test_empty_items_skips_runner(self):
        def runner(prompt):
            raise AssertionError("must not run")

        self.assertEqual(summarize.summarize([], {}, runner=runner, enabled=True), {})


class TestDefaultEnabled(unittest.TestCase):
    def test_env_off_or_missing_cli_disables(self):
        clean = {k: v for k, v in os.environ.items() if k != "PHARMA_RADAR_MODEL"}
        with mock.patch.dict(os.environ, {**clean, "PHARMA_RADAR_MODEL": "off"},
                             clear=True), \
             mock.patch.object(summarize.shutil, "which",
                               return_value="/usr/bin/claude"):
            self.assertFalse(summarize._default_enabled())
        with mock.patch.dict(os.environ, clean, clear=True), \
             mock.patch.object(summarize.shutil, "which", return_value=None):
            self.assertFalse(summarize._default_enabled())
        with mock.patch.dict(os.environ, clean, clear=True), \
             mock.patch.object(summarize.shutil, "which",
                               return_value="/usr/bin/claude"):
            self.assertTrue(summarize._default_enabled())
