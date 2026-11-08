# 药脉：一句话提炼 + 卡片改版 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每条新闻用一句 30 字内的中文 3W 提炼替代原文标题作版面主信息，原文链接缩成句末右箭头。

**Architecture:** 新增 `pipeline/summarize.py`，每天对本轮新增条目与历史缺摘要条目（每批最多 20 条）调用一次本机 `claude` CLI，产出 `{id: {"title_zh": 一句 3W}}` 写入 `data/summaries.json` 缓存；`build()` 按 id 合并缓存后再渲染；前端卡片改为不可点的 `div`，句末 `→` 链接原文。

**Tech Stack:** Python 3.14 标准库（subprocess/shutil/json/tempfile）、`unittest`；前端纯 HTML/CSS/JS。

## Global Constraints

- 运行时依赖只允许标准库 + `requests`；不得新增第三方包
- 测试用 `python3 -m unittest discover -s tests -t . -v`，不得调用真实模型或触网（runner 注入 mock）
- Item 仍是 18 个固定字段，不新增字段；`title_zh` 填一句 3W 提炼，`why` 保持空串
- `data/raw/YYYY-MM.jsonl` 只追加不修改；提炼结果只进 `data/summaries.json`
- 提炼产出：每条 ≤30 个汉字、一句话、3W（Who/What/Why）、不复述原标题、不编造数字
- 模型不可用（找不到 `claude`、`PHARMA_RADAR_MODEL=off`、两次失败）时只记日志，流水线必须照常完成
- 前端无框架、无构建、无 CDN；外部链接只允许 http/https（沿用 `safeUrl`）
- 提交信息结尾 `Co-Authored-By: Claude Code <noreply@anthropic.com>`

---

### Task 1: 提炼模块与缓存

**Files:**
- Create: `pipeline/summarize.py`
- Test: `tests/test_summarize.py`

**Interfaces:**
- Produces: `build_prompt(items: list[dict]) -> str`、`parse_response(text: str, valid_ids: set[str]) -> dict[str, dict]`、`load_cache(path: str = "data/summaries.json") -> dict`、`save_cache(cache: dict, path: str = "data/summaries.json") -> None`、`summarize(items: list[dict], cache: dict, runner=None, enabled=None, limit: int = 20) -> dict`
- Cache shape: `{"<id>": {"title_zh": "<一句 3W>"}}`

- [ ] **Step 1: 写失败测试 `tests/test_summarize.py`**

```python
import json
import os
import tempfile
import unittest

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
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_summarize -v`
Expected: `ModuleNotFoundError: No module named 'pipeline.summarize'`

- [ ] **Step 3: 实现 `pipeline/summarize.py`**

```python
"""把条目压成一句中文 3W 提炼。模型不可用时静默跳过。"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile

log = logging.getLogger(__name__)

MAX_ZH = 30
DEFAULT_PATH = "data/summaries.json"
MODEL = "haiku"
TIMEOUT = 120

PROMPT_HEAD = """你是医药行业情报编辑。给下面每条新闻写一句中文提炼，只回 JSON 数组，不要解释、不要代码块。

要求：
1. 每条一句话，≤30 个汉字，高信息密度，不写形容词与套话。
2. 一句话说清 3W：Who（公司/机构/靶点/疾病）、What（发生了什么）、Why（为什么值得知道——给判断，不复述标题）。
3. 行业口径；不确定的数字不要编造。
4. 输出格式：[{"id": "...", "title_zh": "..."}]，条数与输入一致。

输入：
"""


def build_prompt(items: list[dict]) -> str:
    rows = [
        {k: item.get(k) for k in ("id", "title", "source", "dimension", "event_type", "m")}
        for item in items
    ]
    return PROMPT_HEAD + json.dumps(rows, ensure_ascii=False)


def _extract_json(text: str):
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end <= start:
        raise ValueError("no JSON array in response")
    return json.loads(text[start:end + 1])


def parse_response(text: str, valid_ids: set[str]) -> dict[str, dict]:
    try:
        rows = _extract_json(text or "")
    except (ValueError, json.JSONDecodeError):
        log.warning("summarize: unparseable response")
        return {}
    out: dict[str, dict] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        rid = row.get("id")
        zh = row.get("title_zh")
        if not isinstance(rid, str) or rid not in valid_ids or rid in out:
            continue
        if not isinstance(zh, str):
            continue
        zh = zh.strip()
        if not zh or len(zh) > MAX_ZH:
            continue
        out[rid] = {"title_zh": zh}
    return out


def load_cache(path: str = DEFAULT_PATH) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_cache(cache: dict, path: str = DEFAULT_PATH) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, ensure_ascii=False, indent=1, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def cli_runner(prompt: str) -> str:
    result = subprocess.run(
        ["claude", "-p", "--model", MODEL],
        input=prompt, capture_output=True, text=True, timeout=TIMEOUT, check=True,
    )
    return result.stdout


def _default_enabled() -> bool:
    if os.environ.get("PHARMA_RADAR_MODEL", "").lower() in {"off", "0", "false"}:
        return False
    return shutil.which("claude") is not None


def summarize(items: list[dict], cache: dict, runner=None, enabled=None,
              limit: int = 20) -> dict:
    """就地补齐 cache 中缺失的条目，返回 cache。"""
    pending = [i for i in items
               if isinstance(i.get("id"), str) and i["id"] not in cache
               and (i.get("title") or "").strip()]
    pending = pending[:limit]
    if not pending:
        return cache
    if enabled is None:
        enabled = _default_enabled()
    if not enabled:
        log.info("summarize: disabled, %d items skipped", len(pending))
        return cache
    run = runner or cli_runner
    prompt = build_prompt(pending)
    text = None
    for attempt in (1, 2):
        try:
            text = run(prompt)
            break
        except Exception as exc:
            log.warning("summarize: attempt %d failed: %s", attempt, exc)
    if text is None:
        return cache
    got = parse_response(text, {i["id"] for i in pending})
    cache.update(got)
    log.info("summarize: filled %d of %d", len(got), len(pending))
    return cache
```

- [ ] **Step 4: 运行测试**

Run: `python3 -m unittest tests.test_summarize -v`
Expected: 13 tests, OK

- [ ] **Step 5: 提交**

```bash
git add pipeline/summarize.py tests/test_summarize.py
git commit -m "feat: 一句话 3W 提炼模块与缓存

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: build 按 id 合并提炼

**Files:**
- Modify: `pipeline/build.py`（`build()` 与模块顶部）
- Test: `tests/test_build.py`

**Interfaces:**
- Consumes: `summarize.load_cache(path)`（Task 1）
- Produces: `build(items, out_path="data/items.json", summaries_path="data/summaries.json")`；合并后的条目 `title_zh` 非空、`why` 仍为空串

- [ ] **Step 1: 加失败测试到 `tests/test_build.py`**

```python
    def test_merges_summaries_by_id(self):
        import json
        import os
        import tempfile
        from pipeline.build import build

        with tempfile.TemporaryDirectory() as td:
            sum_path = os.path.join(td, "summaries.json")
            with open(sum_path, "w", encoding="utf-8") as fh:
                json.dump({"a": {"title_zh": "一句话提炼"}}, fh, ensure_ascii=False)
            items = [self._item(1, url="https://example.com/a"),
                     self._item(2, url="https://example.com/b")]
            items[0]["id"] = "a"
            items[1]["id"] = "b"
            out = os.path.join(td, "items.json")
            build(items, out_path=out, summaries_path=sum_path)
            with open(out, encoding="utf-8") as fh:
                days = json.load(fh)["days"]
        got = {i["id"]: i for i in days[0]["items"]}
        self.assertEqual(got["a"]["title_zh"], "一句话提炼")
        self.assertEqual(got["a"]["why"], "")
        self.assertEqual(got["b"]["title_zh"], "")
```

（`self._item` 用该文件既有夹具构造器；若无，按现有 `_make` 写法改。）

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_build -v`
Expected: TypeError: unexpected keyword `summaries_path`

- [ ] **Step 3: 修改 `pipeline/build.py`**

```python
from pipeline import summarize
```

`build()` 签名改为 `def build(items: list[dict], out_path: str = "data/items.json", summaries_path: str = summarize.DEFAULT_PATH) -> dict:`，在分组前合并：

```python
    cache = summarize.load_cache(summaries_path)
    merged: list[dict] = []
    for item in items:
        entry = cache.get(item.get("id") or "")
        if entry and entry.get("title_zh"):
            merged.append({**item, "title_zh": entry["title_zh"]})
        else:
            merged.append(item)
    items = merged
```

- [ ] **Step 4: 全量测试**

Run: `python3 -m unittest discover -s tests -t . -v`
Expected: 全部 OK

- [ ] **Step 5: 提交**

```bash
git add pipeline/build.py tests/test_build.py
git commit -m "feat: build 按 id 合并 3W 提炼

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: 卡片改版——句末右箭头

**Files:**
- Modify: `app.js`（`card()`）、`style.css`（`.card-orig` 删除，新增 `.card-link`）
- Test: `tests/test_page.py`

**Interfaces:**
- Consumes: 条目字段 `title_zh`（优先）与 `why`；`safeUrl` 仍限制 http/https

- [ ] **Step 1: 加失败测试到 `tests/test_page.py`**

```python
    def test_card_links_only_via_arrow(self):
        js = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("card-link", js)
        self.assertIn('"→"', js)
        self.assertNotIn("card-orig", js)

    def test_css_has_card_link_style(self):
        css = (ROOT / "style.css").read_text(encoding="utf-8")
        self.assertIn(".card-link", css)
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_page -v`
Expected: FAIL on `card-link`

- [ ] **Step 3: 改 `app.js` 的 `card()`**

整卡不再可点：`const node = el("div", "card dim-" + ...)`；标题行渲染 `title_zh || title`；若两类标题都有，原英文标题写进 `h3.title`（悬停可见），不再渲染 `card-orig`；`why` 保留；句末追加：

```js
  if (url) {
    const link = el("a", "card-link", "→");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener";
    link.setAttribute("aria-label", "打开原文：" + (trim(item.title) || title));
    titleNode.appendChild(link);
  }
```

- [ ] **Step 4: 改 `style.css`**

删除 `.card-orig` 规则；新增：

```css
.card-link {
  margin-left: 0.25rem;
  color: var(--muted);
  text-decoration: none;
  font-weight: 400;
}

.card-link:hover,
.card-link:focus-visible {
  color: var(--fg);
}
```

- [ ] **Step 5: 测试 + 截图验证**

Run: `python3 -m unittest discover -s tests -t . -v`
Expected: 全部 OK。再用 CDP 脚本在 390px 下截图确认卡片只剩提炼句 + 箭头。

- [ ] **Step 6: 提交**

```bash
git add app.js style.css tests/test_page.py
git commit -m "feat: 卡片主信息改为一句话提炼，原文链接缩为右箭头

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: run.py 接线

**Files:**
- Modify: `run.py`
- Test: `tests/test_run_main.py`

**Interfaces:**
- Consumes: `summarize.summarize`、`summarize.load_cache`、`summarize.save_cache`、`summarize.DEFAULT_PATH`
- 行为：`chosen` 与非 `chosen` 的历史条目一起参与补齐（每批 ≤20）；提炼失败不得影响 `append_raw` / `build`

- [ ] **Step 1: 加失败测试**（mock `run.summarize.summarize`，断言调用发生在 `append_raw` 之前、且异常时流水线仍返回 0）

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_run_main -v`

- [ ] **Step 3: 在 `run.py` 的 `chosen = select(pending)` 之后插入**

```python
    known_items = load_raw()
    try:
        cache = summarize.load_cache(summarize.DEFAULT_PATH)
        summarize.summarize(known_items + chosen, cache)
        summarize.save_cache(cache)
    except Exception as exc:  # 提炼失败不影响入档与版面
        log.error("summarize failed: %s", exc)
```

（注意：`known_items` 与已有的 `known` 集合来自同一次 `load_raw()`，重构时只读一次。）

- [ ] **Step 4: 全量测试**

Run: `python3 -m unittest discover -s tests -t . -v`

- [ ] **Step 5: 提交**

```bash
git add run.py tests/test_run_main.py
git commit -m "feat: run.py 接入提炼步骤，失败不阻断流水线

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: 真实回填与验收（控制端执行）

- [ ] 运行 `PHARMA_RADAR_MODEL=off python3 run.py --date 2026-11-04` 确认无模型时仍正常
- [ ] 手工对 `load_raw()` 的全部条目跑 `summarize.summarize`（一次或两次批次），写 `data/summaries.json`
- [ ] 检查每条：≤30 字、一句、含 Who/What/Why、没有复述标题、没有编造
- [ ] `python3 run.py --date 2026-11-04` 重建页面；开 390px 截图确认卡片呈现
- [ ] 质量不合格的条目从缓存里删掉重跑
- [ ] 提交 `data/summaries.json` 与 `data/items.json`
