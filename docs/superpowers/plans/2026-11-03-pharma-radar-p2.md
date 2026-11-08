# P2 实施计划：ClinicalTrials.gov / openFDA / PubMed 接入与催化剂日历

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把三个公开结构化数据源接进流水线，并让催化剂日历首次出现未来的真实事件。

**Architecture:** 三个源各写一个适配器（只取回并归一化为 Item，不打分），源预置的事件类型/维度由 `make_item` 传入、`enrich` 尊重；日期粒度的源（ClinicalTrials、openFDA、PubMed）没有时刻，`in_window` 为此新增一条「只到日的条目落在本期两日之内即算在窗口」的规则。催化剂是独立数据文件 `data/catalysts.json`，每次运行按 id 合并、丢弃过去、排序后重写；条目流仍然是 append-only。页面新增「催化剂」视图，与「今日」共用同一个 `app.js`。

**Tech Stack:** Python 3.14、stdlib + `requests`、`unittest`；前端纯 HTML/CSS/JS，无框架、无 CDN。

## Global Constraints

以下为 spec 的全局约束，每个任务默认全部适用：

- 依赖只有 stdlib 与 `requests`；不引入 pytest、feedparser、任何前端框架或 CDN。
- 时间一律 Asia/Shanghai（`zoneinfo.ZoneInfo("Asia/Shanghai")`）。
- 适配器只负责「取回并归一化」，不做打分；打分、维度分配、配额集中在 `pipeline/`。
- Item 结构是 18 个固定字段：`id, date, published_at, source, source_weight, lang, title, title_zh, url, company, drug, target, ta, event_type, dimension, m, why, cluster_id`。`id = sha1(canonical_url(url))[:16]`。
- `published_at` 是真实发布时刻，`date` 是日报期；跨期条目由 `stamp_issue_date` 把 `date` 改成本期日期，`published_at` 不动。
- 源适配器必须可单独运行、失败不影响其它源；`run.py` 对每个源单独 try/except。
- 不接付费数据库、不在登录态下抓取。
- 测试命令：`python3 -m unittest discover -s tests -t . -v`。
- 提交信息中文，动词开头（`feat:` / `fix:` / `test:` / `docs:`），结尾加：
  `Co-Authored-By: Claude Code <noreply@anthropic.com>`

---

## 文件结构

- 新建 `pipeline/catalysts.py` — 催化剂记录：构造、按 id 合并、丢弃过去、排序、写 `data/catalysts.json` + `data/catalysts.js`。
- 新建 `sources/trials.py` — ClinicalTrials.gov API v2：新登记 III 期研究条目 + III 期主要完成日期催化剂。
- 新建 `sources/openfda.py` — openFDA Drugs@FDA：NDA/BLA 原始批准条目。
- 新建 `sources/pubmed.py` — PubMed E-utilities：近两日入库的指南/共识条目。
- 修改 `sources/base.py` — `make_item` 接受 `event_type` / `dimension` 预置。
- 修改 `pipeline/scoring.py` — `enrich` 尊重源预置的事件类型与维度。
- 修改 `pipeline/window.py` — 只到日的 `published_at` 按日期判定窗口。
- 修改 `pipeline/gate.py` — 三个新源加入 `TRUSTED_SOURCES`。
- 修改 `run.py` — 接入三个源，运行末尾更新催化剂。
- 修改 `index.html` / `app.js` / `style.css` — 「今日 / 催化剂」视图切换与日历渲染。
- 测试：`tests/test_catalysts.py`、`tests/test_trials.py`、`tests/test_openfda.py`、`tests/test_pubmed.py`、`tests/test_run.py`；更新 `tests/test_base.py`、`tests/test_scoring.py`、`tests/test_window.py`、`tests/test_page.py`。

---

### Task 1: 催化剂存储模块

**Files:**
- Create: `pipeline/catalysts.py`
- Test: `tests/test_catalysts.py`

**Interfaces:**
- Produces:
  - `KINDS = ("读出", "审批决定", "会议", "政策窗口")`
  - `make_catalyst(*, date: str, kind: str, entity: str, drug: str = "", note: str = "", source: str = "") -> dict`，返回字段 `id, date, kind, entity, drug, note, source`；`kind` 非法抛 `ValueError`。
  - `merge(existing: list[dict], incoming: list[dict]) -> list[dict]` — 按 `id` 覆盖，`incoming` 胜。
  - `prune(records: list[dict], today: str) -> list[dict]` — 只留 `date >= today` 且 `date` 是合法 `YYYY-MM-DD` 的记录。
  - `write(records: list[dict], out_path: str = "data/catalysts.json") -> dict` — 写 JSON 与 `data/catalysts.js`，返回 `{"generated_at": ..., "catalysts": [...]}`。
  - `load(path: str = "data/catalysts.json") -> list[dict]` — 文件不存在或结构不符返回 `[]`。

**说明（id 设计）：** `id` 由 `source|kind|entity|drug|note` 计算，**不含 `date`**。同一试验被申办方改期时 `id` 不变，新日期覆盖旧日期，不会在日历上留两条。

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_catalysts.py
import json
import os
import tempfile
import unittest

from pipeline.catalysts import KINDS, load, make_catalyst, merge, prune, write


def cat(**kw):
    base = dict(date="2026-12-01", kind="读出", entity="Novartis",
                drug="LOU064", note="CSU（NCT05677451）", source="clinicaltrials.gov")
    base.update(kw)
    return make_catalyst(**base)


class TestMakeCatalyst(unittest.TestCase):
    def test_fields(self):
        c = cat()
        self.assertEqual(
            set(c), {"id", "date", "kind", "entity", "drug", "note", "source"}
        )
        self.assertEqual(c["kind"], "读出")
        self.assertEqual(c["date"], "2026-12-01")
        self.assertEqual(len(c["id"]), 16)
        int(c["id"], 16)

    def test_unknown_kind_rejected(self):
        with self.assertRaises(ValueError):
            cat(kind="发布")

    def test_id_ignores_date_but_tracks_identity(self):
        # 改期后 id 不变（覆盖旧记录），换试验则 id 变化。
        self.assertEqual(cat(date="2026-12-01")["id"], cat(date="2027-01-15")["id"])
        self.assertNotEqual(cat()["id"], cat(note="CSU（NCT99999999）")["id"])


class TestMergePrune(unittest.TestCase):
    def test_merge_overwrites_by_id(self):
        old = cat(date="2026-12-01")
        new = cat(date="2027-01-15")
        other = cat(note="NSCLC（NCT11111111）")
        out = merge([old, other], [new])
        self.assertEqual(len(out), 2)
        self.assertEqual({c["id"]: c["date"] for c in out}[old["id"]], "2027-01-15")

    def test_prune_drops_past_and_bad_dates(self):
        rows = [cat(date="2026-11-02"), cat(date="2026-11-03"), cat(date="2026-13-01")]
        ids = [c["date"] for c in prune(rows, "2026-11-03")]
        self.assertEqual(ids, ["2026-11-03"])


class TestWriteLoad(unittest.TestCase):
    def test_roundtrip_sorted_and_js_parity(self):
        rows = [cat(date="2027-02-01"), cat(date="2026-12-01")]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "catalysts.json")
            payload = write(rows, out_path=path)
            self.assertEqual([c["date"] for c in payload["catalysts"]],
                             ["2026-12-01", "2027-02-01"])
            self.assertEqual(load(path), payload["catalysts"])
            js = open(os.path.join(tmp, "catalysts.js"), encoding="utf-8").read()
            self.assertTrue(js.startswith("window.__CATALYSTS__ = "))
            self.assertEqual(json.loads(js[len("window.__CATALYSTS__ = "):].rstrip(";\n")),
                             payload)

    def test_load_missing_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load(os.path.join(tmp, "nope.json")), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `python3 -m unittest tests.test_catalysts -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.catalysts'`

- [ ] **Step 3: 最小实现**

```python
# pipeline/catalysts.py
"""催化剂日历：未来事件的独立存储（data/catalysts.json）。

与条目流分开：条目是一次性新闻，催化剂是可被改期、到期后应消失的未来事件，
所以每次运行按 id 合并后重写，而不是只追加。
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

CST = ZoneInfo("Asia/Shanghai")
KINDS = ("读出", "审批决定", "会议", "政策窗口")


def _catalyst_id(*, source: str, kind: str, entity: str, drug: str, note: str) -> str:
    # 不含 date：申办方改期时用同一个 id 覆盖旧记录。
    raw = "|".join((source, kind, entity.lower(), drug.lower(), note))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def make_catalyst(*, date: str, kind: str, entity: str, drug: str = "",
                  note: str = "", source: str = "") -> dict:
    if kind not in KINDS:
        raise ValueError(f"未知催化剂类型 {kind!r}，允许：{KINDS}")
    return {
        "id": _catalyst_id(source=source, kind=kind, entity=entity, drug=drug, note=note),
        "date": date,
        "kind": kind,
        "entity": entity,
        "drug": drug,
        "note": note,
        "source": source,
    }


def merge(existing: list[dict], incoming: list[dict]) -> list[dict]:
    """按 id 覆盖：同一事件以本次抓取为准。"""
    by_id = {c["id"]: c for c in existing}
    for c in incoming:
        by_id[c["id"]] = c
    return list(by_id.values())


def _valid_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError):
        return False
    return True


def prune(records: list[dict], today: str) -> list[dict]:
    """丢掉已经过去或日期非法的条目。"""
    return [c for c in records if _valid_date(c.get("date", "")) and c["date"] >= today]


def _sort_key(c: dict):
    return (c.get("date", ""), c.get("entity", ""), c.get("drug", ""))


def write(records: list[dict], out_path: str = "data/catalysts.json") -> dict:
    payload = {
        "generated_at": datetime.now(CST).isoformat(timespec="seconds"),
        "catalysts": sorted(records, key=_sort_key),
    }
    text = json.dumps(payload, ensure_ascii=False, indent=1)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    js_path = os.path.splitext(out_path)[0] + ".js"
    with open(js_path, "w", encoding="utf-8") as fh:
        fh.write("window.__CATALYSTS__ = " + text + ";\n")
    return payload


def load(path: str = "data/catalysts.json") -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        return []
    rows = data.get("catalysts")
    return rows if isinstance(rows, list) else []
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `python3 -m unittest tests.test_catalysts -v`
Expected: PASS（7 个测试）

- [ ] **Step 5: 提交**

```bash
git add pipeline/catalysts.py tests/test_catalysts.py
git commit -m "feat: 催化剂存储模块，按 id 合并并丢弃过期事件

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: 源可预置事件类型与维度

**Files:**
- Modify: `sources/base.py`（`make_item` 签名与返回）
- Modify: `pipeline/scoring.py`（`enrich`）
- Test: `tests/test_base.py`、`tests/test_scoring.py`

**Interfaces:**
- Consumes: 现有 `make_item(*, title, url, source, published_at, source_weight=1.0, lang="zh", title_zh="", date="", company=None, drug=None, target=None, ta=None)`。
- Produces:
  - `make_item(..., event_type: str = "", dimension: str = "")` — 原样写入；空串表示「交给规则判定」。
  - `enrich(item)` — 事件类型优先用已填值，空串才调用 `classify_event`；维度同理，空串才调用 `assign_dimension`。`m` 始终由 `score_m(event_type, title)` 计算。

**为什么：** 结构化源的有效信息在字段里而不在标题里。ClinicalTrials 的标题是「A Study to Investigate …」，规则永远判成 science/D6；openFDA 的批准与 PubMed 的指南同理。让源自己声明类型，规则只在源没声明时兜底。

- [ ] **Step 1: 改测试（先写失败断言）**

把 `tests/test_base.py` 中 `test_defaults_present` 的两行：

```python
        self.assertEqual(it["dimension"], "D6")
        self.assertEqual(it["m"], 1)
```

改成：

```python
        self.assertEqual(it["event_type"], "")
        self.assertEqual(it["dimension"], "")
        self.assertEqual(it["m"], 1)
```

并在 `TestMakeItem` 内新增：

```python
    def test_preset_event_type_and_dimension_are_kept(self):
        it = make_item(title="A Study of GB-0895", url="https://ct.gov/x", source="trials",
                       published_at="2026-11-03", event_type="clinical", dimension="D2")
        self.assertEqual(it["event_type"], "clinical")
        self.assertEqual(it["dimension"], "D2")
```

在 `tests/test_scoring.py` 里，把 `TestEnrich` 中现有那条「重算覆盖原值」用例的输入改成空串：

```python
        item = {"title": "FDA approves drug B", "event_type": "", "dimension": "", "m": 1}
```

并新增两条：

```python
    def test_enrich_keeps_source_preset(self):
        from pipeline.scoring import enrich
        out = enrich({"title": "A Study to Investigate GB-0895",
                      "event_type": "clinical", "dimension": "", "m": 1})
        self.assertEqual(out["event_type"], "clinical")
        self.assertEqual(out["dimension"], "D2")
        self.assertEqual(out["m"], 3)

    def test_enrich_keeps_preset_dimension(self):
        from pipeline.scoring import enrich
        out = enrich({"title": "Continuous glucose monitoring: clinical practice guidelines",
                      "event_type": "science", "dimension": "D1", "m": 1})
        self.assertEqual(out["dimension"], "D1")
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `python3 -m unittest tests.test_base tests.test_scoring -v`
Expected: FAIL — `TypeError: make_item() got an unexpected keyword argument 'event_type'`，且默认值断言失败

- [ ] **Step 3: 实现**

`sources/base.py` — 给 `make_item` 加两个参数：

```python
def make_item(
    *,
    title: str,
    url: str,
    source: str,
    published_at: str,
    source_weight: float = 1.0,
    lang: str = "zh",
    title_zh: str = "",
    date: str = "",
    company: list[str] | None = None,
    drug: list[str] | None = None,
    target: list[str] | None = None,
    ta: list[str] | None = None,
    event_type: str = "",
    dimension: str = "",
) -> dict:
```

返回字典里两行改为：

```python
        "event_type": event_type,
        "dimension": dimension,
```

`pipeline/scoring.py` — `enrich` 改为：

```python
def enrich(item: dict) -> dict:
    # 结构化源（临床试验、openFDA、PubMed）的有效信息不在标题里，
    # 由适配器直接声明事件类型与维度；空串才交给规则判定。
    event_type = item.get("event_type") or classify_event(item["title"])
    item["event_type"] = event_type
    item["dimension"] = item.get("dimension") or assign_dimension(event_type, item["title"])
    item["m"] = score_m(event_type, item["title"])
    return item
```

- [ ] **Step 4: 跑全量测试，确认通过**

Run: `python3 -m unittest discover -s tests -t . -v`
Expected: PASS（既有测试全部仍通过）

- [ ] **Step 5: 提交**

```bash
git add sources/base.py pipeline/scoring.py tests/test_base.py tests/test_scoring.py
git commit -m "feat: Item 支持源预置事件类型与维度

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: 只到日的条目按日期判定窗口

**Files:**
- Modify: `pipeline/window.py`
- Test: `tests/test_window.py`

**Interfaces:**
- Produces: `in_window(item, now)` 新增分支——`published_at` 形如 `YYYY-MM-DD`（无时刻）时，日期是「锚点当日或前一日」即算在窗口内。
- 不变：`published_at` 为空/无法解析时仍退回到 `date == 本期日期`；带时刻的条目仍走严格 24 小时开区间。

**为什么：** ClinicalTrials 的 `studyFirstPostDate`、openFDA 的 `submission_status_date`、PubMed 的 `sortpubdate` 都只到日。19:00→19:00 的窗口跨两个日历日，所以只到日的条目落在这两天里都无法排除。

- [ ] **Step 1: 写失败的测试**

在 `tests/test_window.py` 的 `TestInWindow` 类里新增：

```python
    def test_date_only_yesterday_included(self):
        self.assertTrue(in_window(item("2026-11-02"), self.now))

    def test_date_only_today_included(self):
        self.assertTrue(in_window(item("2026-11-03"), self.now))

    def test_date_only_two_days_ago_excluded(self):
        self.assertFalse(in_window(item("2026-11-01"), self.now))

    def test_date_only_future_excluded(self):
        self.assertFalse(in_window(item("2026-11-04"), self.now))

    def test_timestamped_item_still_uses_24h_rule(self):
        # 有时刻的条目不受「两日」放宽影响：前一日 15:00 仍属于上一期。
        self.assertFalse(in_window(item("2026-11-02T15:00:00+08:00"), self.now))
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `python3 -m unittest tests.test_window -v`
Expected: FAIL — `test_date_only_yesterday_included`（`2026-11-02` 被解析成 11-02 00:00，落在窗口外）

- [ ] **Step 3: 实现**

`pipeline/window.py` — 顶部加 `import re`，并在 `parse_timestamp` 之后加常量与方法：

```python
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def in_window(item: dict, now: datetime) -> bool:
    ts = parse_timestamp(item.get("published_at", ""))
    if ts is None:
        # 时间戳缺失或解析失败时，退回到「date == 本期日期（北京时间）」。
        # 平时本期日期就是运行日；`--date` 补跑时是补跑的那一期，与运行时刻无关。
        return item.get("date", "") == now.astimezone(CST).strftime("%Y-%m-%d")
    if _DATE_ONLY.match((item.get("published_at") or "").strip()):
        # 结构化源（临床试验、openFDA、PubMed）只给日期。窗口跨两个日历日，
        # 落在其中任何一天都无法排除，两天都收。
        anchor_day = now.astimezone(CST).date()
        day = ts.astimezone(CST).date()
        return day in (anchor_day, anchor_day - timedelta(days=1))
    start = now - timedelta(hours=24)
    # 左边界取开区间：恰好 24 小时前发布的条目属于上一期（见 test_exactly_24h_old_excluded）。
    return start < ts < now
```

（`timedelta` 已在文件顶部导入。）

- [ ] **Step 4: 跑测试，确认通过**

Run: `python3 -m unittest tests.test_window -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add pipeline/window.py tests/test_window.py
git commit -m "feat: 只到日的条目按本期两个日历日判定窗口

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: ClinicalTrials.gov 适配器与试验读数催化剂

**Files:**
- Create: `sources/trials.py`
- Modify: `pipeline/gate.py`（`TRUSTED_SOURCES` 加 `"trials"`）
- Test: `tests/test_trials.py`

**Interfaces:**
- Consumes: `make_item(..., event_type="clinical", company=..., drug=..., ta=...)`（Task 2）；`make_catalyst(...)`（Task 1）。
- Produces:
  - `fetch_items(days: int = 7, today: date | None = None, timeout: int = 30) -> list[dict]` — 近 `days` 天首次登记（`studyFirstPostDate`）的 III 期研究，`source="trials"`，`url=https://clinicaltrials.gov/study/<NCT>`，`published_at` 为 `YYYY-MM-DD`。
  - `fetch_catalysts(today: date | None = None, days: int = 90, timeout: int = 30) -> list[dict]` — 主要完成日期（`primaryCompletionDate`）在未来 `days` 天内的 III 期研究，`kind="读出"`，`source="clinicaltrials.gov"`。
  - `fetch_all(timeout: int = 30) -> list[dict]` — 等于 `fetch_items(timeout=timeout)`，供 `run.py` 统一收集条目。
  - `parse_study(study: dict) -> dict | None` — 纯函数，测试直接喂字典。

**API 事实（已实测）：** `GET https://clinicaltrials.gov/api/v2/studies`，`query.term=AREA[Phase]PHASE3`，`filter.overallStatus=RECRUITING|ACTIVE_NOT_RECRUITING`，`filter.advanced=AREA[PrimaryCompletionDate]RANGE[<start>,<end>]`，`fields=` 逗号分隔，`sort=StudyFirstPostDate:desc` / `PrimaryCompletionDate:asc`。响应形如 `{"studies": [{"protocolSection": {"identificationModule": {...}, "statusModule": {"primaryCompletionDateStruct": {"date": "2026-11-03"}, "lastUpdatePostDateStruct": {...}, "studyFirstPostDateStruct": {...}}, "sponsorCollaboratorsModule": {"leadSponsor": {"name": ...}}, "conditionsModule": {"conditions": [...]}, "designModule": {"phases": [...]}, "armsInterventionsModule": {"interventions": [{"name": ...}]}}}]}`。`primaryCompletionDate` 可能是 `2029-01`（月精度），这种不收进催化剂。

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_trials.py
import unittest
from datetime import date

from sources.trials import parse_study

STUDY = {
    "protocolSection": {
        "identificationModule": {"nctId": "NCT05677451",
                                 "briefTitle": "A Study of LOU064 in Chronic Spontaneous Urticaria"},
        "statusModule": {"overallStatus": "RECRUITING",
                         "startDateStruct": {"date": "2026-01-20"},
                         "studyFirstPostDateStruct": {"date": "2026-11-02"},
                         "primaryCompletionDateStruct": {"date": "2026-12-15"}},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Novartis Pharmaceuticals"}},
        "conditionsModule": {"conditions": ["Chronic Spontaneous Urticaria"]},
        "designModule": {"phases": ["PHASE3"]},
        "armsInterventionsModule": {"interventions": [
            {"name": "Placebo"}, {"name": "LOU064 (blinded)"}]},
    }
}


class TestParseStudy(unittest.TestCase):
    def test_fields_extracted(self):
        s = parse_study(STUDY)
        self.assertEqual(s["nct"], "NCT05677451")
        self.assertEqual(s["sponsor"], "Novartis Pharmaceuticals")
        self.assertEqual(s["drug"], "LOU064 (blinded)")
        self.assertEqual(s["first_post"], "2026-11-02")
        self.assertEqual(s["completion"], "2026-12-15")
        self.assertEqual(s["conditions"], ["Chronic Spontaneous Urticaria"])

    def test_missing_nct_returns_none(self):
        self.assertIsNone(parse_study({"protocolSection": {}}))

    def test_missing_intervention_is_empty_string(self):
        s = parse_study({"protocolSection": {
            "identificationModule": {"nctId": "NCT1", "briefTitle": "t"}}})
        self.assertEqual(s["drug"], "")
```

另外用 `unittest.mock.patch` 覆盖网络层，验证：

```python
    def test_fetch_items_filters_old_and_sets_source(self):
        from unittest import mock
        from sources import trials

        rows = [dict(STUDY)]
        with mock.patch.object(trials, "_fetch", return_value=[trials.parse_study(r) for r in rows]):
            items = trials.fetch_items(today=date(2026, 11, 3))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source"], "trials")
        self.assertEqual(items[0]["event_type"], "clinical")
        self.assertEqual(items[0]["published_at"], "2026-11-02")
        self.assertEqual(items[0]["url"], "https://clinicaltrials.gov/study/NCT05677451")

    def test_fetch_items_drops_studies_older_than_lookback(self):
        from unittest import mock
        from sources import trials
        old = {"protocolSection": {
            "identificationModule": {"nctId": "NCT2", "briefTitle": "old"},
            "statusModule": {"studyFirstPostDateStruct": {"date": "2026-10-01"}}}}
        with mock.patch.object(trials, "_fetch", return_value=[trials.parse_study(old)]):
            self.assertEqual(trials.fetch_items(today=date(2026, 11, 3)), [])

    def test_fetch_catalysts_only_day_precision(self):
        from unittest import mock
        from sources import trials
        month_only = {"protocolSection": {
            "identificationModule": {"nctId": "NCT3", "briefTitle": "m"},
            "statusModule": {"primaryCompletionDateStruct": {"date": "2029-01"}}}}
        rows = [trials.parse_study(STUDY), trials.parse_study(month_only)]
        with mock.patch.object(trials, "_fetch", return_value=rows):
            out = trials.fetch_catalysts(today=date(2026, 11, 3))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["date"], "2026-12-15")
        self.assertEqual(out[0]["kind"], "读出")
        self.assertEqual(out[0]["entity"], "Novartis Pharmaceuticals")
        self.assertIn("NCT05677451", out[0]["note"])
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `python3 -m unittest tests.test_trials -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sources.trials'`

- [ ] **Step 3: 实现**

```python
# sources/trials.py
"""ClinicalTrials.gov API v2：新登记的 III 期研究，以及近期主要完成日期（催化剂）。"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import requests

from pipeline.catalysts import make_catalyst
from sources.base import make_item

log = logging.getLogger(__name__)

API = "https://clinicaltrials.gov/api/v2/studies"
BASE_URL = "https://clinicaltrials.gov/study/"
FIELDS = ",".join((
    "NCTId", "BriefTitle", "OverallStatus", "Phase", "LeadSponsorName",
    "StartDate", "PrimaryCompletionDate", "StudyFirstPostDate",
    "Condition", "InterventionName",
))
STATUSES = "RECRUITING|ACTIVE_NOT_RECRUITING"
ITEM_DAYS = 7
CATALYST_DAYS = 90


def _struct(node: dict, key: str) -> str:
    value = (node or {}).get(key)
    return (value or {}).get("date", "") if isinstance(value, dict) else ""


def parse_study(study: dict) -> dict | None:
    protocol = (study or {}).get("protocolSection") or {}
    ident = protocol.get("identificationModule") or {}
    nct = (ident.get("nctId") or "").strip()
    if not nct:
        return None
    status = protocol.get("statusModule") or {}
    sponsor = ((protocol.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {})
    conditions = (protocol.get("conditionsModule") or {}).get("conditions") or []
    drug = ""
    for intervention in (protocol.get("armsInterventionsModule") or {}).get("interventions") or []:
        name = (intervention.get("name") or "").strip()
        if name and name.lower() != "placebo":
            drug = name
            break
    return {
        "nct": nct,
        "title": (ident.get("briefTitle") or "").strip(),
        "sponsor": (sponsor.get("name") or "").strip(),
        "conditions": [c for c in conditions if c],
        "first_post": _struct(status, "studyFirstPostDateStruct"),
        "completion": _struct(status, "primaryCompletionDateStruct"),
        "drug": drug,
    }


def _fetch(params: dict, timeout: int = 30) -> list[dict]:
    resp = requests.get(API, params=params, timeout=timeout,
                        headers={"User-Agent": "pharma-radar/0.1"})
    resp.raise_for_status()
    studies = resp.json().get("studies") or []
    return [s for s in (parse_study(x) for x in studies) if s]


def _base_params() -> dict:
    return {
        "query.term": "AREA[Phase]PHASE3",
        "filter.overallStatus": STATUSES,
        "fields": FIELDS,
        "pageSize": 100,
    }


def fetch_items(days: int = ITEM_DAYS, today: date | None = None,
                timeout: int = 30) -> list[dict]:
    """近 days 天首次登记的 III 期研究。API 只做倒序取前 100 条，日期在本地筛。"""
    today = today or date.today()
    params = dict(_base_params(), sort="StudyFirstPostDate:desc")
    floor = (today - timedelta(days=days)).isoformat()
    out: list[dict] = []
    for study in _fetch(params, timeout):
        if not study["title"] or not study["first_post"] or study["first_post"] < floor:
            continue
        out.append(make_item(
            title=study["title"],
            url=BASE_URL + study["nct"],
            source="trials",
            published_at=study["first_post"],
            source_weight=1.1,
            lang="en",
            company=[study["sponsor"]] if study["sponsor"] else [],
            drug=[study["drug"]] if study["drug"] else [],
            ta=study["conditions"][:3],
            event_type="clinical",
        ))
    return out


def fetch_catalysts(today: date | None = None, days: int = CATALYST_DAYS,
                    timeout: int = 30) -> list[dict]:
    """主要完成日期在未来 days 天内的 III 期研究。"""
    today = today or date.today()
    end = today + timedelta(days=days)
    params = dict(
        _base_params(),
        sort="PrimaryCompletionDate:asc",
        **{"filter.advanced":
           f"AREA[PrimaryCompletionDate]RANGE[{today.isoformat()},{end.isoformat()}]"},
    )
    out: list[dict] = []
    for study in _fetch(params, timeout):
        completion = study["completion"]
        if len(completion) != 10:  # 月精度（2029-01）无法排期
            continue
        condition = "、".join(study["conditions"][:2])
        note = f"{condition}（{study['nct']}）" if condition else study["nct"]
        out.append(make_catalyst(
            date=completion,
            kind="读出",
            entity=study["sponsor"],
            drug=study["drug"],
            note=note,
            source="clinicaltrials.gov",
        ))
    return out


def fetch_all(timeout: int = 30) -> list[dict]:
    return fetch_items(timeout=timeout)
```

`pipeline/gate.py` — `TRUSTED_SOURCES` 增加 `"trials"`：

```python
TRUSTED_SOURCES: tuple[str, ...] = (
    "biopharmadive", "endpoints", "fierce-biotech", "fierce-pharma", "nmpa", "trials",
)
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `python3 -m unittest tests.test_trials tests.test_gate -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add sources/trials.py pipeline/gate.py tests/test_trials.py
git commit -m "feat: 接入 ClinicalTrials.gov，III 期新登记入日报、完成日期入催化剂日历

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: openFDA 新药批准适配器

**Files:**
- Create: `sources/openfda.py`
- Modify: `pipeline/gate.py`（`TRUSTED_SOURCES` 加 `"openfda"`）
- Test: `tests/test_openfda.py`

**Interfaces:**
- Consumes: `make_item(..., event_type="regulatory")`。
- Produces:
  - `parse_results(results: list[dict]) -> list[dict]` — 纯函数，测试直接喂字典。
  - `fetch_all(days: int = 30, today: date | None = None, timeout: int = 30) -> list[dict]` — 近 `days` 天状态变更的 NDA/BLA「原始批准（ORIG + AP）」，`source="openfda"`，`published_at` 为批准日期 `YYYY-MM-DD`。

**API 事实（已实测）：** `GET https://api.fda.gov/drug/drugsfda.json?search=submissions.submission_status_date:[20261001 TO 20261103] AND submissions.submission_type:ORIG&limit=100`。注意 openFDA 的区间语法要求 `TO` 两侧是空格，用 `requests` 的 `params` 传真实空格即可（会被编码成 `+`）。无结果时返回 **HTTP 404** 与 `{"error": {"code": "NOT_FOUND"}}`，必须当作空结果而不是异常。响应每条含 `application_number`（`NDA…`/`BLA…`/`ANDA…`）、`sponsor_name`、`products[].brand_name`、`products[].active_ingredients[].name`、`submissions[].submission_type/status/status_date`（`YYYYMMDD`）。`meta.last_updated` 显示数据滞后数日，所以默认回看 30 天，由窗口决定哪天入版。

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_openfda.py
import unittest
from datetime import date
from unittest import mock

from sources import openfda
from sources.openfda import parse_results

NDA = {
    "application_number": "NDA221183",
    "sponsor_name": "COSETTE",
    "products": [{"brand_name": "EVOXAC",
                  "active_ingredients": [{"name": "CEVIMELINE HYDROCHLORIDE"}]}],
    "submissions": [
        {"submission_type": "ORIG", "submission_status": "AP",
         "submission_status_date": "20261102"},
        {"submission_type": "SUPPL", "submission_status": "AP",
         "submission_status_date": "20261103"},
    ],
}
ANDA = dict(NDA, application_number="ANDA220010")


class TestParseResults(unittest.TestCase):
    def test_nda_becomes_item(self):
        out = parse_results([NDA])
        self.assertEqual(len(out), 1)
        item = out[0]
        self.assertEqual(item["source"], "openfda")
        self.assertEqual(item["event_type"], "regulatory")
        self.assertEqual(item["published_at"], "2026-11-02")
        self.assertEqual(item["company"], ["COSETTE"])
        self.assertIn("EVOXAC", item["title"])
        self.assertIn("ApplNo=221183", item["url"])

    def test_anda_generic_skipped(self):
        self.assertEqual(parse_results([ANDA]), [])

    def test_submission_without_approval_skipped(self):
        pending = dict(NDA, submissions=[{"submission_type": "ORIG",
                                          "submission_status": "TA",
                                          "submission_status_date": "20261102"}])
        self.assertEqual(parse_results([pending]), [])

    def test_latest_orig_approval_wins(self):
        two = dict(NDA, submissions=NDA["submissions"] + [
            {"submission_type": "ORIG", "submission_status": "AP",
             "submission_status_date": "20261103"}])
        self.assertEqual(parse_results([two])[0]["published_at"], "2026-11-03")


class TestFetchAll(unittest.TestCase):
    def test_404_is_empty_not_error(self):
        resp = mock.Mock(status_code=404)
        with mock.patch.object(openfda.requests, "get", return_value=resp):
            self.assertEqual(openfda.fetch_all(), [])

    def test_results_parsed(self):
        resp = mock.Mock(status_code=200)
        resp.json.return_value = {"results": [NDA]}
        with mock.patch.object(openfda.requests, "get", return_value=resp):
            out = openfda.fetch_all(today=date(2026, 11, 3))
        self.assertEqual([i["source"] for i in out], ["openfda"])

    def test_old_orig_approval_dropped(self):
        # openFDA 的区间命中可能来自别的 submission，原始批准日期可能很旧。
        old = dict(NDA, submissions=[{"submission_type": "ORIG",
                                      "submission_status": "AP",
                                      "submission_status_date": "20200101"}])
        resp = mock.Mock(status_code=200)
        resp.json.return_value = {"results": [old]}
        with mock.patch.object(openfda.requests, "get", return_value=resp):
            self.assertEqual(openfda.fetch_all(today=date(2026, 11, 3)), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `python3 -m unittest tests.test_openfda -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sources.openfda'`

- [ ] **Step 3: 实现**

```python
# sources/openfda.py
"""openFDA Drugs@FDA：NDA/BLA 原始批准。仿制药（ANDA）与补充申请不入日报。"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import requests

from sources.base import make_item

log = logging.getLogger(__name__)

API = "https://api.fda.gov/drug/drugsfda.json"
LABEL_URL = ("https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm"
             "?event=overview.process&ApplNo=")
LOOKBACK_DAYS = 30


def _ymd(value: str) -> str:
    """YYYYMMDD -> YYYY-MM-DD；格式不符返回空串。"""
    text = (value or "").strip()
    if len(text) != 8 or not text.isdigit():
        return ""
    return f"{text[:4]}-{text[4:6]}-{text[6:]}"


def parse_results(results: list[dict]) -> list[dict]:
    out: list[dict] = []
    for record in results or []:
        number = (record.get("application_number") or "").upper()
        if not (number.startswith("NDA") or number.startswith("BLA")):
            continue
        approved = [
            sub for sub in record.get("submissions") or []
            if sub.get("submission_type") == "ORIG"
            and sub.get("submission_status") == "AP"
            and _ymd(sub.get("submission_status_date", ""))
        ]
        if not approved:
            continue
        latest = max(approved, key=lambda s: s["submission_status_date"])
        product = (record.get("products") or [{}])[0]
        brand = (product.get("brand_name") or "").strip()
        ingredients = [i.get("name", "").strip()
                       for i in product.get("active_ingredients") or []]
        ingredient = ingredients[0] if ingredients else ""
        label = brand or ingredient
        if not label:
            continue
        title = f"FDA approves {label}"
        if ingredient and ingredient.lower() != brand.lower():
            title += f" ({ingredient})"
        sponsor = (record.get("sponsor_name") or "").strip()
        out.append(make_item(
            title=title,
            url=LABEL_URL + number[3:],
            source="openfda",
            published_at=_ymd(latest["submission_status_date"]),
            source_weight=1.3,
            lang="en",
            company=[sponsor] if sponsor else [],
            drug=list(dict.fromkeys(d for d in (brand, ingredient) if d)),
            event_type="regulatory",
        ))
    return out


def fetch_all(days: int = LOOKBACK_DAYS, today: date | None = None,
              timeout: int = 30) -> list[dict]:
    today = today or date.today()
    start = (today - timedelta(days=days)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    params = {
        # openFDA 的 TO 是空格分隔的语法；requests 会把空格编码成 +。
        "search": (f"submissions.submission_status_date:[{start} TO {end}]"
                   " AND submissions.submission_type:ORIG"),
        "limit": 100,
    }
    resp = requests.get(API, params=params, timeout=timeout,
                        headers={"User-Agent": "pharma-radar/0.1"})
    if resp.status_code == 404:  # openFDA 用 404 表示「没有匹配」，不是故障
        log.info("openfda: no approvals in window")
        return []
    resp.raise_for_status()
    floor = (today - timedelta(days=days)).isoformat()
    # 区间命中可能来自同一申请下的其它 submission，原始批准日期要在本地再卡一次。
    return [i for i in parse_results(resp.json().get("results") or [])
            if i["published_at"] >= floor]
```

`pipeline/gate.py` — `TRUSTED_SOURCES` 追加 `"openfda"`：

```python
    "biopharmadive", "endpoints", "fierce-biotech", "fierce-pharma", "nmpa", "trials",
    "openfda",
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `python3 -m unittest tests.test_openfda tests.test_gate -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add sources/openfda.py pipeline/gate.py tests/test_openfda.py
git commit -m "feat: 接入 openFDA 新药原始批准

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: PubMed 指南适配器

**Files:**
- Create: `sources/pubmed.py`
- Modify: `pipeline/gate.py`（`TRUSTED_SOURCES` 加 `"pubmed"`）
- Test: `tests/test_pubmed.py`

**Interfaces:**
- Consumes: `make_item(..., event_type="science", dimension="D1")`（Task 2）。
- Produces:
  - `parse_summaries(result: dict, fallback_date: str = "") -> list[dict]` — 纯函数，`result` 是 esummary 的 `result` 字段（`uids` + 每条 pmid 记录）。取 `sortpubdate`（形如 `2026/11/02 00:00`）的前 10 位作日期；缺失或格式不符才用 `fallback_date`，都没有则丢。
  - `fetch_all(days: int = 2, today: date | None = None, timeout: int = 30) -> list[dict]` — 近 `days` 天入库（`[edat]`）的指南/共识。

**API 事实（已实测）：** `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&retmode=json&retmax=100&term=<term>`；日期过滤 `(2026/11/01:2026/11/03[edat])`；`esummary.fcgi?db=pubmed&retmode=json&id=1,2,3` 返回 `{"result": {"uids": [...], "<pmid>": {"title": ..., "fulljournalname": ..., "sortpubdate": "2026/11/02 00:00", ...}}}`。题录页 `https://pubmed.ncbi.nlm.nih.gov/<pmid>/`。

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_pubmed.py
import unittest
from unittest import mock

from sources import pubmed
from sources.pubmed import parse_summaries

SUMMARY = {
    "uids": ["42971815", "42970000"],
    "42971815": {"title": "Continuous glucose monitoring in diabetes: guidelines for primary care",
                 "sortpubdate": "2026/11/02 00:00"},
    "42970000": {"title": "Some accepted manuscript", "sortpubdate": ""},
}


class TestParseSummaries(unittest.TestCase):
    def test_item_fields(self):
        out = parse_summaries(SUMMARY, fallback_date="2026-11-02")
        self.assertEqual(len(out), 2)
        first = out[0]
        self.assertEqual(first["source"], "pubmed")
        self.assertEqual(first["event_type"], "science")
        self.assertEqual(first["dimension"], "D1")
        self.assertEqual(first["published_at"], "2026-11-02")
        self.assertEqual(first["url"], "https://pubmed.ncbi.nlm.nih.gov/42971815/")

    def test_missing_sortpubdate_uses_fallback(self):
        out = parse_summaries(SUMMARY, fallback_date="2026-11-03")
        self.assertEqual(out[1]["published_at"], "2026-11-03")

    def test_no_date_anywhere_skips(self):
        out = parse_summaries(SUMMARY, fallback_date="")
        self.assertEqual([i["title"] for i in out],
                         ["Continuous glucose monitoring in diabetes: guidelines for primary care"])

    def test_empty_title_skipped(self):
        result = {"uids": ["1"], "1": {"title": "  ", "sortpubdate": "2026/11/02 00:00"}}
        self.assertEqual(parse_summaries(result), [])


class TestFetchAll(unittest.TestCase):
    def test_no_ids_returns_empty_without_summary_call(self):
        search = mock.Mock(status_code=200)
        search.json.return_value = {"esearchresult": {"idlist": []}}
        with mock.patch.object(pubmed.requests, "get", return_value=search) as get:
            self.assertEqual(pubmed.fetch_all(), [])
        self.assertEqual(get.call_count, 1)

    def test_two_calls_esearch_then_esummary(self):
        search = mock.Mock(status_code=200)
        search.json.return_value = {"esearchresult": {"idlist": ["42971815"]}}
        summary = mock.Mock(status_code=200)
        summary.json.return_value = {"result": {
            "uids": ["42971815"],
            "42971815": {"title": "G", "sortpubdate": "2026/11/02 00:00"}}}
        with mock.patch.object(pubmed.requests, "get", side_effect=[search, summary]) as get:
            out = pubmed.fetch_all()
        self.assertEqual(len(out), 1)
        self.assertEqual(get.call_count, 2)
        self.assertIn("esummary.fcgi", get.call_args_list[1].args[0])


if __name__ == "__main__":
    unittest.main()
```

`fetch_all` 的测试需要源码写成先检验状态码再解析，并且 esearch 与 esummary 都调用 `requests.get(url, params=..., timeout=...)`，URL 作为位置参数。

- [ ] **Step 2: 跑测试，确认失败**

Run: `python3 -m unittest tests.test_pubmed -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sources.pubmed'`

- [ ] **Step 3: 实现**

```python
# sources/pubmed.py
"""PubMed E-utilities：近两日入库的指南与共识，进 D1 疾病格局。"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import requests

from sources.base import make_item

log = logging.getLogger(__name__)

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TERM = '(guideline[pt] OR "practice guideline"[pt])'
LOOKBACK_DAYS = 2


def _date_arg(day: date) -> str:
    return day.strftime("%Y/%m/%d")


def _item_date(sortpubdate: str, fallback: str) -> str:
    """sortpubdate 形如 2026/11/02 00:00；取到日。拿不到就用兜底日期。"""
    text = (sortpubdate or "").strip()
    if len(text) >= 10 and text[4] == "/" and text[7] == "/":
        return text[:10].replace("/", "-")
    return fallback if len(fallback) == 10 else ""


def parse_summaries(result: dict, fallback_date: str = "") -> list[dict]:
    out: list[dict] = []
    for pmid in result.get("uids") or []:
        record = result.get(pmid) or {}
        title = (record.get("title") or "").strip()
        if not title:
            continue
        day = _item_date(record.get("sortpubdate", ""), fallback_date)
        if not day:
            continue
        out.append(make_item(
            title=title,
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            source="pubmed",
            published_at=day,
            source_weight=1.0,
            lang="en",
            event_type="science",
            dimension="D1",
        ))
    return out


def fetch_all(days: int = LOOKBACK_DAYS, today: date | None = None,
              timeout: int = 30) -> list[dict]:
    today = today or date.today()
    start = today - timedelta(days=days)
    search = requests.get(
        f"{BASE}/esearch.fcgi",
        params={
            "db": "pubmed",
            "retmode": "json",
            "retmax": 100,
            "sort": "pub date",
            "term": f"{TERM} AND ({_date_arg(start)}:{_date_arg(today)}[edat])",
        },
        timeout=timeout,
        headers={"User-Agent": "pharma-radar/0.1"},
    )
    search.raise_for_status()
    ids = (search.json().get("esearchresult") or {}).get("idlist") or []
    if not ids:
        return []
    summary = requests.get(
        f"{BASE}/esummary.fcgi",
        params={"db": "pubmed", "retmode": "json", "id": ",".join(ids)},
        timeout=timeout,
        headers={"User-Agent": "pharma-radar/0.1"},
    )
    summary.raise_for_status()
    return parse_summaries(summary.json().get("result") or {},
                           fallback_date=today.isoformat())
```

`pipeline/gate.py` — `TRUSTED_SOURCES` 追加 `"pubmed"`：

```python
    "biopharmadive", "endpoints", "fierce-biotech", "fierce-pharma", "nmpa", "trials",
    "openfda", "pubmed",
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `python3 -m unittest tests.test_pubmed tests.test_gate -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add sources/pubmed.py pipeline/gate.py tests/test_pubmed.py
git commit -m "feat: 接入 PubMed 指南与共识

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: 流水线接入

**Files:**
- Modify: `run.py`
- Test: `tests/test_run.py`（新建）

**Interfaces:**
- Consumes: `trials.fetch_items` / `openfda.fetch_all` / `pubmed.fetch_all`（Task 4–6）；`catalysts.load/merge/prune/write`（Task 1）；`trials.fetch_catalysts`（Task 4）。
- Produces:
  - `run.update_catalysts(anchor: datetime, timeout: int = 30, path: str = "data/catalysts.json") -> dict` — 读旧文件、抓新催化剂、合并、丢弃 `anchor` 当日的过去事件、写回，返回 `write()` 的 payload。抓取失败只记日志，旧数据保留并照常裁剪。`path` 供测试指向临时目录。
  - `run.collect()` — 收集五个源，逐源 try/except。

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_run.py
import os
import tempfile
import unittest
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

import run
from pipeline.catalysts import make_catalyst

CST = ZoneInfo("Asia/Shanghai")
ANCHOR = datetime(2026, 11, 3, 19, 0, tzinfo=CST)


class TestUpdateCatalysts(unittest.TestCase):
    def _catalyst(self, day, note="NCT1"):
        return make_catalyst(date=day, kind="读出", entity="Novartis",
                             drug="X", note=note, source="clinicaltrials.gov")

    def test_merges_prunes_and_writes(self):
        existing = [self._catalyst("2026-11-02", "OLD"),   # 已过期
                    self._catalyst("2026-12-01", "KEEP")]  # 应保留
        fresh = [self._catalyst("2026-12-20", "NEW")]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "catalysts.json")
            run.catalysts.write(existing, out_path=path)  # 先落一份旧数据
            with mock.patch.object(run.trials, "fetch_catalysts", return_value=fresh):
                run.update_catalysts(ANCHOR, path=path)
            dates = [c["date"] for c in run.catalysts.load(path)]
        self.assertEqual(dates, ["2026-12-01", "2026-12-20"])

    def test_fetch_failure_keeps_existing(self):
        existing = [self._catalyst("2026-12-01", "KEEP")]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "catalysts.json")
            run.catalysts.write(existing, out_path=path)
            with mock.patch.object(run.trials, "fetch_catalysts",
                                   side_effect=RuntimeError("boom")):
                run.update_catalysts(ANCHOR, path=path)
            dates = [c["date"] for c in run.catalysts.load(path)]
        self.assertEqual(dates, ["2026-12-01"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `python3 -m unittest tests.test_run -v`
Expected: FAIL — `AttributeError: module 'run' has no attribute 'catalysts'`（或 `update_catalysts`）

- [ ] **Step 3: 实现**

`run.py` 顶部导入改为：

```python
from pipeline import catalysts
from pipeline.build import append_raw, build, load_raw
from pipeline.dedupe import assign_clusters, dedupe
from pipeline.gate import filter_relevant
from pipeline.scoring import enrich
from pipeline.select import select
from pipeline.window import in_window, resolve_anchor, stamp_issue_date
from sources import openfda, pubmed, reg_cn, trials
from sources.rss_en import fetch_all as fetch_rss
```

`collect()` 改为：

```python
def collect() -> list[dict]:
    items: list[dict] = []
    for fn in (fetch_rss, reg_cn.fetch_all, trials.fetch_all,
               openfda.fetch_all, pubmed.fetch_all):
        try:
            items.extend(fn())
        except Exception as exc:  # 单源失败不影响整体
            log.error("%s failed: %s", fn.__module__, exc)
    return items
```

新增：

```python
def update_catalysts(anchor: datetime, timeout: int = 30,
                     path: str = "data/catalysts.json") -> dict:
    """读旧文件 → 抓新催化剂 → 合并 → 丢弃过去 → 写回。

    抓取失败时保留旧数据并照常裁剪：过期事件仍然要消失。
    """
    today = anchor.astimezone(CST).date()
    existing = catalysts.load(path)
    try:
        fresh = trials.fetch_catalysts(today=today, timeout=timeout)
    except Exception as exc:
        log.error("catalysts: clinicaltrials failed: %s", exc)
        fresh = []
    merged = catalysts.prune(catalysts.merge(existing, fresh), today.isoformat())
    log.info("catalysts: existing=%d fresh=%d kept=%d",
             len(existing), len(fresh), len(merged))
    return catalysts.write(merged, out_path=path)
```

`main()` 在 `build(load_raw())` 之后加一行：

```python
    update_catalysts(anchor)
```

`datetime` 已通过 `from datetime import datetime` 导入？当前 `run.py` 只导入了 `ZoneInfo`。因此顶部补 `from datetime import datetime`。同时保留 `CST = ZoneInfo("Asia/Shanghai")`。

- [ ] **Step 4: 跑测试，确认通过**

Run: `python3 -m unittest tests.test_run -v`，然后 `python3 -m unittest discover -s tests -t . -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add run.py tests/test_run.py
git commit -m "feat: 流水线接入临床试验、openFDA、PubMed 并每日更新催化剂

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 8: 催化剂日历页与数据生成

**Files:**
- Modify: `index.html`、`app.js`、`style.css`
- Modify: `tests/test_page.py`
- 生成：`data/catalysts.json`、`data/catalysts.js`（随运行产出并提交）

**Interfaces:**
- Consumes: `window.__CATALYSTS__ = {"generated_at": ..., "catalysts": [{id, date, kind, entity, drug, note, source}]}`（Task 1 的 `write`）。
- Produces:
  - `app.js` 新增 `renderCatalysts(payload)`、`loadJson(url)`、`setView(view)`；导出 `window.renderCatalysts = renderCatalysts`。
  - 页面顶部「今日 / 催化剂」两个视图按钮；切到催化剂时隐藏维度筛选与日期翻页控件。

- [ ] **Step 1: 写失败的测试**

在 `tests/test_page.py` 的 `TestPageBehaviour` 里新增：

```python
    def test_html_has_catalyst_view_switch(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-view="today"', html)
        self.assertIn('data-view="catalysts"', html)

    def test_html_loads_catalysts_js_before_app_js(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        cat_pos = html.find('<script src="./data/catalysts.js"></script>')
        app_pos = html.find('<script src="./app.js"></script>')
        self.assertNotEqual(cat_pos, -1)
        self.assertLess(cat_pos, app_pos)

    def test_js_exposes_render_catalysts(self):
        js = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertRegex(js, r"window\.renderCatalysts\s*=\s*renderCatalysts")
        self.assertIn("./data/catalysts.json", js)

    def test_js_shows_days_until(self):
        js = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("天后", js)
        self.assertIn("今天", js)

    def test_css_has_catalyst_styles(self):
        css = (ROOT / "style.css").read_text(encoding="utf-8")
        for marker in (".view-tab", ".catalyst-row", ".kind-badge"):
            self.assertIn(marker, css)
```

- [ ] **Step 2: 跑测试，确认失败**

Run: `python3 -m unittest tests.test_page -v`
Expected: FAIL — 找不到 `data-view="today"`

- [ ] **Step 3: 实现**

`index.html` — 在 `<nav class="tabs">` **之前**插入：

```html
<nav class="views" aria-label="切换视图">
  <button class="view-tab active" type="button" data-view="today" aria-pressed="true">今日</button>
  <button class="view-tab" type="button" data-view="catalysts" aria-pressed="false">催化剂</button>
</nav>
```

把脚本段改成：

```html
<script src="./data/catalysts.js"></script>
<script src="./data/items.js"></script>
<script src="./app.js"></script>
```

`app.js` 改动：

1. 顶部常量与状态：

```javascript
const DATA_URL = "./data/items.json";
const CATALYST_URL = "./data/catalysts.json";
const DIMENSIONS = ["D1", "D2", "D3", "D4", "D5", "D6"];

const state = {
  data: null,
  catalysts: null,
  view: "today",
  dim: "all",
  index: 0,
};
```

2. 把 `loadData()` 改成通用函数，原函数删除：

```javascript
function loadJson(url) {
  // 先尝试 fetch；直接以 file:// 打开时部分浏览器会拦截，
  // 再退回 XMLHttpRequest（部分浏览器允许同目录读取）。
  return fetch(url, { cache: "no-store" })
    .then((res) => {
      if (!res.ok) throw new Error("HTTP " + res.status);
      return res.text().then((text) => JSON.parse(text));
    })
    .catch(
      () =>
        new Promise((resolve, reject) => {
          let xhr;
          try {
            xhr = new XMLHttpRequest();
          } catch (err) {
            reject(new Error("无法读取 " + url));
            return;
          }
          xhr.open("GET", url, true);
          xhr.onload = () => {
            if (xhr.status === 0 || (xhr.status >= 200 && xhr.status < 300)) {
              try {
                resolve(JSON.parse(xhr.responseText));
              } catch (err) {
                reject(new Error("JSON 解析失败：" + err.message));
              }
            } else {
              reject(new Error("HTTP " + xhr.status));
            }
          };
          xhr.onerror = () => reject(new Error("无法读取 " + url + "（本地文件访问可能被浏览器拦截）"));
          try {
            xhr.send();
          } catch (err) {
            reject(err);
          }
        })
    );
}
```

3. 新增 `renderCatalysts`、`catalystRow`、`daysUntil`、`setView`（放在 `renderCurrentDay` 之后）：

```javascript
function daysUntil(day) {
  const today = new Date();
  const todayIso =
    today.getFullYear() +
    "-" +
    String(today.getMonth() + 1).padStart(2, "0") +
    "-" +
    String(today.getDate()).padStart(2, "0");
  const diff = Date.parse(day + "T00:00:00") - Date.parse(todayIso + "T00:00:00");
  if (Number.isNaN(diff)) return "";
  const days = Math.round(diff / 86400000);
  if (days === 0) return "今天";
  if (days < 0) return "已过期";
  return days + " 天后";
}

function catalystRow(c) {
  const row = el("div", "catalyst-row");
  const head = el("div", "catalyst-head");
  head.appendChild(el("span", "catalyst-date", String(c.date || "")));
  if (trim(c.kind)) head.appendChild(el("span", "kind-badge", c.kind));
  const left = daysUntil(String(c.date || ""));
  if (left) head.appendChild(el("span", "days-left", left));
  row.appendChild(head);

  const title = [trim(c.entity), trim(c.drug)].filter(Boolean).join(" · ");
  row.appendChild(el("h3", "catalyst-title", title || "(未知对象)"));
  if (trim(c.note)) row.appendChild(el("p", "catalyst-note", c.note));
  if (trim(c.source)) row.appendChild(el("p", "catalyst-source", c.source));
  return row;
}

function renderCatalysts(payload) {
  const app = document.getElementById("app");
  if (!app) return;
  const rows =
    payload && Array.isArray(payload.catalysts)
      ? payload.catalysts.filter((c) => c && typeof c === "object" && !Array.isArray(c))
      : [];

  const section = el("section", "catalysts");
  section.appendChild(el("h2", "day-title", "催化剂日历"));
  section.appendChild(
    el("p", "quiet", "未来 90 天的 III 期主要完成时点，按日期排序。日期来自申办方登记，可能改期。")
  );
  if (!rows.length) {
    section.appendChild(el("p", "quiet", "暂无未来事件。"));
  } else {
    const list = el("div", "catalyst-list");
    rows.forEach((c) => list.appendChild(catalystRow(c)));
    section.appendChild(list);
  }
  app.textContent = "";
  app.appendChild(section);
}

function setView(view) {
  state.view = view === "catalysts" ? "catalysts" : "today";
  document.querySelectorAll(".view-tab").forEach((btn) => {
    const on = btn.dataset.view === state.view;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-pressed", on ? "true" : "false");
  });
  const tabs = document.querySelector(".tabs");
  if (tabs) tabs.hidden = state.view !== "today";
  const dayNav = document.getElementById("day-nav");
  if (dayNav && state.view !== "today") dayNav.hidden = true;
  if (state.view === "catalysts") {
    if (state.catalysts) {
      renderCatalysts(state.catalysts);
    } else {
      loadJson(CATALYST_URL)
        .then((payload) => {
          state.catalysts = payload;
          renderCatalysts(payload);
        })
        .catch((err) =>
          renderNotice("无法读取催化剂数据。", err && err.message ? err.message : String(err))
        );
    }
    return;
  }
  renderCurrentDay();
}
```

4. `start(data)` 不变；`load()` 在 `start(window.__ITEMS__)` 之后补一行缓存催化剂：

```javascript
    if (window.__CATALYSTS__ !== undefined) state.catalysts = window.__CATALYSTS__;
```

5. `bind()` 增加视图按钮绑定：

```javascript
  document.querySelectorAll(".view-tab").forEach((btn) => {
    btn.addEventListener("click", () => setView(btn.dataset.view));
  });
```

6. 文件末尾导出：

```javascript
window.renderDay = renderDay;
window.renderCatalysts = renderCatalysts;
```

`style.css` — 追加：

```css
/* ---------- 视图切换与催化剂日历 ---------- */

.views {
  display: flex;
  gap: 0.5rem;
  padding: 0.2rem 0 0.6rem;
}

.view-tab {
  border: 1px solid var(--line);
  background: var(--card);
  color: var(--fg);
  border-radius: 999px;
  padding: 0.25rem 0.9rem;
  font-size: 0.85rem;
  cursor: pointer;
}

.view-tab.active {
  border-color: var(--d3);
  background: var(--must-bg);
  font-weight: 600;
}

.catalyst-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.catalyst-row {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0.6rem 0.75rem;
}

.catalyst-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.78rem;
  color: var(--muted);
}

.catalyst-date {
  font-variant-numeric: tabular-nums;
}

.kind-badge {
  border: 1px solid var(--d3);
  color: var(--d3);
  border-radius: 4px;
  padding: 0 0.35rem;
}

.days-left {
  color: var(--d1);
  font-weight: 600;
}

.catalyst-title {
  margin: 0.3rem 0 0.1rem;
  font-size: 1rem;
}

.catalyst-note,
.catalyst-source {
  margin: 0;
  font-size: 0.85rem;
  color: var(--muted);
}
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `python3 -m unittest tests.test_page -v`
Expected: PASS

- [ ] **Step 5: 生成真实数据**

Run: `python3 run.py`
Expected: 日志里出现 `catalysts: existing=0 fresh=N kept=N`（N > 0），并生成 `data/catalysts.json`、`data/catalysts.js`。若 `fresh=0`，先用下面命令确认 API 本身有数据，再对照 `fetch_catalysts` 的参数修正：

```bash
python3 -c "from sources.trials import fetch_catalysts; rows=fetch_catalysts(); print(len(rows)); print(rows[:2])"
```

- [ ] **Step 6: 提交**

```bash
git add index.html app.js style.css tests/test_page.py data/catalysts.json data/catalysts.js data/items.json data/items.js data/raw
git commit -m "feat: 催化剂日历视图与首版真实数据

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## 完成标志（对应 spec P2）

- 日历上有真实未来事件：`data/catalysts.json` 的 `catalysts` 非空，最新日期不早于运行日。
- 日报里出现 `source` 为 `trials` / `openfda` / `pubmed` 的条目（窗口内没有新数据时可能是 0 条，不视为失败；以 `python3 run.py` 日志的 `collected=` 为准）。
- 全量测试通过：`python3 -m unittest discover -s tests -t . -v`。
- 连续两次运行 `run.py` 不产生重复：`data/raw/*.jsonl` 行数第二次不变，`data/catalysts.json` 条数不变。
