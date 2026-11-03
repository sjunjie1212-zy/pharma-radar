# 药脉 P1.5（主题门 + 19:00 日报窗口）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让每日版面只收录医药产业信息，并让日报窗口按「前一日 19:00 → 当日 19:00」取数。

**Architecture:** 两处独立改动接在同一条流水线上：采集之后先过主题门（`pipeline/gate.py`），再按时间窗口过滤（`pipeline/window.py`），然后进入既有打分、去重、配额、构建。窗口内的条目以「本期日期」（运行日）作为 `date`，原始时间保留在 `published_at`。

**Tech Stack:** Python 3.14.2，标准库；unittest。

## Global Constraints

- Python 3.14.2，标准库 + `requests`，不引入新依赖
- 测试只用 unittest：`python3 -m unittest discover -s tests -t . -v`
- 内部时区固定 Asia/Shanghai；ISO 8601 输出
- Item 字段集固定，不增不减
- id 由规范化 URL 派生，重复运行幂等
- 单源失败不得中断整轮，`run.py` 退出码 0
- 中文词按子串匹配，ASCII 词按词边界匹配，大小写不敏感
- 不做登录抓取，不接付费数据源

---

### Task 1: 主题门

**Files:**
- Create: `pipeline/gate.py`
- Modify: `run.py`（在打分前过滤）
- Test: `tests/test_gate.py`

**Interfaces:**
- Consumes: Item dict（至少含 `title`、`title_zh`）
- Produces: `is_relevant(item: dict) -> bool`、`filter_relevant(items: list[dict]) -> list[dict]`、`TERMS: tuple[str, ...]`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_gate.py
import unittest

from pipeline.gate import filter_relevant, is_relevant


def item(title, title_zh=""):
    return {"title": title, "title_zh": title_zh}


class TestIsRelevant(unittest.TestCase):
    def test_pharma_trial_kept(self):
        self.assertTrue(is_relevant(item("Phase 3 trial meets primary endpoint in NSCLC")))

    def test_regulator_kept(self):
        self.assertTrue(is_relevant(item("FDA approves first gene therapy for hemophilia")))

    def test_chinese_drug_news_kept(self):
        self.assertTrue(is_relevant(item("国家药监局发布某创新药指导原则")))

    def test_reimbursement_kept(self):
        self.assertTrue(is_relevant(item("2026 年国家医保药品目录调整结果公布")))

    def test_politics_dropped(self):
        self.assertFalse(is_relevant(item("Opinion: What the 2024 electoral map reveals about America")))

    def test_lifestyle_dropped(self):
        self.assertFalse(is_relevant(item("Opinion: How meditation helped me become a better doctor")))

    def test_disease_name_alone_not_enough(self):
        self.assertFalse(is_relevant(item("Washington state resident dies from bird flu")))

    def test_ascii_word_boundary(self):
        self.assertFalse(is_relevant(item("The pharmaceutical industry is not a pharmacy counter")))

    def test_title_zh_counts(self):
        self.assertTrue(is_relevant(item("Some English headline", title_zh="国产 PD-1 获批新适应症")))

    def test_filter_keeps_order(self):
        items = [item("electoral map"), item("FDA approves drug"), item("FDA rejects drug")]
        kept = filter_relevant(items)
        self.assertEqual([i["title"] for i in kept], ["FDA approves drug", "FDA rejects drug"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_gate -v`
Expected: `ModuleNotFoundError: No module named 'pipeline.gate'`

- [ ] **Step 3: 实现**

```python
"""主题门：只放行与医药产业相关的条目。

匹配对象是标题（原文与中文转写）。疾病名单独出现不算相关——流感、阿尔茨海默病之类
的公共卫生报道本身不改变产业判断；要进版面，标题里必须有药品、临床、监管、支付、
交易或平台技术信号。
"""
from __future__ import annotations

import re

TERMS: tuple[str, ...] = (
    # 中文
    "药", "制药", "创新药", "仿制药", "生物制品", "生物医药", "医药", "中药",
    "临床", "试验", "适应症", "靶点", "管线", "单抗", "双抗", "抗体", "疫苗",
    "细胞治疗", "基因治疗", "小核酸", "获批", "上市申请", "审评", "注册", "监管",
    "指导原则", "附条件批准", "医保", "集采", "带量采购", "定价", "支付", "处方",
    "不良反应", "一致性评价", "授权", "并购", "融资", "license",
    # 英文
    "pharma", "pharmaceutical", "biotech", "biologic", "biologics", "drug", "drugs",
    "therapy", "therapies", "clinical", "trial", "trials", "endpoint", "readout",
    "fda", "ema", "nmpa", "mhra", "approval", "approved", "approve", "pdufa",
    "ind", "nda", "bla", "adc", "mrna", "car-t", "crispr", "antibody", "vaccine",
    "oncology", "efficacy", "dosing", "label", "patent", "pipeline", "licensing",
    "acquisition", "merger", "reimbursement", "formulary", "glp-1", "biosimilar",
)

_ASCII = re.compile(r"^[a-z0-9-]+$")


def _hit(text: str, term: str) -> bool:
    if _ASCII.match(term):
        pattern = r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"
        return re.search(pattern, text) is not None
    return term in text


def is_relevant(item: dict) -> bool:
    text = f"{item.get('title', '')} {item.get('title_zh', '')}".lower()
    return any(_hit(text, term) for term in TERMS)


def filter_relevant(items: list[dict]) -> list[dict]:
    return [i for i in items if is_relevant(i)]
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest tests.test_gate -v`
Expected: 10 tests PASS

- [ ] **Step 5: 接入流水线**

`run.py` 在拿到全部条目、完成补全之后、进入打分之前插入过滤，并记录被丢弃的数量：

```python
from pipeline.gate import filter_relevant

# main() 内，enrich 之后、dedupe 之前
gated = filter_relevant(enriched)
log.info("gate: kept %d of %d", len(gated), len(enriched))
```

- [ ] **Step 6: 全量测试**

Run: `python3 -m unittest discover -s tests -t . -v`
Expected: 全部通过（原 90 + 新增 10）

- [ ] **Step 7: 提交**

```bash
git add pipeline/gate.py run.py tests/test_gate.py
git commit -m "feat: 主题门过滤非医药产业条目"
```

---

### Task 2: 19:00 日报窗口

**Files:**
- Create: `pipeline/window.py`
- Modify: `run.py`（替换「当日日期」过滤）
- Test: `tests/test_window.py`

**Interfaces:**
- Consumes: Item dict（`published_at`、`date`）、`datetime`
- Produces: `parse_timestamp(text: str) -> datetime | None`、`in_window(item: dict, now: datetime) -> bool`、`stamp_issue_date(item: dict, now: datetime) -> dict`

**语义**
- 窗口 = `[now - 24h, now)`。19:00 运行时正好是「前一日 19:00 → 当日 19:00」，与 spec 一致；提前运行则自然收紧，不丢数。
- 时间戳可解析时按时间戳判断；解析不出时退回到 `date == now 的日期`。
- 进入窗口的条目，`date` 改写为运行日（北京时间）作为「本期日期」，真实时间保留在 `published_at`。理由：日报是按期阅读的，跨夜的欧美消息要出现在当晚的「今日」页，而不是被推到前一天的版面。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_window.py
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pipeline.window import in_window, parse_timestamp, stamp_issue_date

CST = ZoneInfo("Asia/Shanghai")


def item(published_at, date=""):
    return {"published_at": published_at, "date": date, "title": "x"}


class TestParseTimestamp(unittest.TestCase):
    def test_rfc2822(self):
        ts = parse_timestamp("Tue, 03 Nov 2026 10:00:00 +0800")
        self.assertEqual(ts.astimezone(CST).strftime("%Y-%m-%d %H:%M"), "2026-11-03 10:00")

    def test_iso_with_offset(self):
        ts = parse_timestamp("2026-11-03T10:00:00+08:00")
        self.assertEqual(ts.strftime("%Y-%m-%d %H:%M"), "2026-11-03 10:00")

    def test_naive_iso_is_cst(self):
        ts = parse_timestamp("2026-11-03T00:00:00")
        self.assertEqual(ts.utcoffset(), timedelta(hours=8))

    def test_garbage_returns_none(self):
        self.assertIsNone(parse_timestamp("not a date"))


class TestInWindow(unittest.TestCase):
    now = datetime(2026, 11, 3, 19, 0, tzinfo=CST)

    def test_overnight_item_included(self):
        # 前一日 23:00 发布，属于本期
        self.assertTrue(in_window(item("Mon, 02 Nov 2026 23:00:00 +0800"), self.now))

    def test_yesterday_afternoon_excluded(self):
        self.assertFalse(in_window(item("Mon, 02 Nov 2026 15:00:00 +0800"), self.now))

    def test_today_before_run_included(self):
        self.assertTrue(in_window(item("Tue, 03 Nov 2026 18:59:00 +0800"), self.now))

    def test_exactly_24h_old_excluded(self):
        self.assertFalse(in_window(item("Mon, 02 Nov 2026 19:00:00 +0800"), self.now))

    def test_date_only_falls_back_to_today(self):
        self.assertTrue(in_window(item("2026-11-03T00:00:00+08:00", "2026-11-03"), self.now))

    def test_empty_timestamp_uses_date(self):
        self.assertTrue(in_window(item("", "2026-11-03"), self.now))
        self.assertFalse(in_window(item("", "2026-11-02"), self.now))


class TestStampIssueDate(unittest.TestCase):
    def test_overnight_gets_run_date(self):
        now = datetime(2026, 11, 3, 19, 0, tzinfo=CST)
        stamped = stamp_issue_date(item("Mon, 02 Nov 2026 23:00:00 +0800", "2026-11-02"), now)
        self.assertEqual(stamped["date"], "2026-11-03")
        self.assertEqual(stamped["published_at"], "Mon, 02 Nov 2026 23:00:00 +0800")

    def test_same_day_unchanged(self):
        now = datetime(2026, 11, 3, 19, 0, tzinfo=CST)
        stamped = stamp_issue_date(item("Tue, 03 Nov 2026 10:00:00 +0800", "2026-11-03"), now)
        self.assertEqual(stamped["date"], "2026-11-03")

    def test_returns_copy(self):
        original = item("Tue, 03 Nov 2026 10:00:00 +0800", "2026-11-02")
        now = datetime(2026, 11, 3, 19, 0, tzinfo=CST)
        stamped = stamp_issue_date(original, now)
        self.assertIsNot(stamped, original)
        self.assertEqual(original["date"], "2026-11-02")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_window -v`
Expected: `ModuleNotFoundError: No module named 'pipeline.window'`

- [ ] **Step 3: 实现**

```python
"""日报窗口：前一日 19:00 至当日 19:00。

等价于「以运行时刻为终点、向前 24 小时」。19:00 定时运行时与 spec 的 19:00 切点一致；
提前手动运行则窗口收紧，不会把更早的条目算进本期。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

CST = ZoneInfo("Asia/Shanghai")


def parse_timestamp(text: str) -> datetime | None:
    """把 RFC 2822 或 ISO 8601 时间串解析成带时区的 datetime；失败返回 None。"""
    if not text:
        return None
    try:
        ts = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        ts = None
    if ts is None:
        try:
            ts = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=CST)
    return ts


def _item_timestamp(item: dict, now: datetime) -> datetime | None:
    ts = parse_timestamp(item.get("published_at", ""))
    if ts is not None:
        return ts
    date_text = item.get("date", "")
    if not date_text:
        return None
    try:
        return datetime.fromisoformat(date_text).replace(hour=12, tzinfo=CST)
    except ValueError:
        return None


def in_window(item: dict, now: datetime) -> bool:
    ts = _item_timestamp(item, now)
    if ts is None:
        return False
    start = now - timedelta(hours=24)
    return start <= ts < now


def stamp_issue_date(item: dict, now: datetime) -> dict:
    """把条目的 date 改写为本期日期，published_at 保持不变；返回新 dict。"""
    stamped = dict(item)
    stamped["date"] = now.astimezone(CST).strftime("%Y-%m-%d")
    return stamped
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest tests.test_window -v`
Expected: 12 tests PASS

- [ ] **Step 5: 接入流水线**

`run.py` 用窗口替换原有的「当日日期」过滤，并对入选条目打上本期日期：

```python
from datetime import datetime
from pipeline.window import in_window, stamp_issue_date

# main() 内，gate 之后
now = datetime.now(ZoneInfo("Asia/Shanghai"))
windowed = [stamp_issue_date(i, now) for i in gated if in_window(i, now)]
```

原来的 `date == today` 过滤删除。

- [ ] **Step 6: 全量测试**

Run: `python3 -m unittest discover -s tests -t . -v`
Expected: 全部通过（原 100 + 新增 12）

- [ ] **Step 7: 端到端冒烟**

Run: `python3 run.py`
Expected: exit 0；日志里 `gate: kept X of Y` 与本期条目数；`data/items.json` 只含医药产业条目

- [ ] **Step 8: 提交**

```bash
git add pipeline/window.py run.py tests/test_window.py
git commit -m "feat: 日报窗口改为前一日 19:00 至当日 19:00"
```

---

### Task 3: 分源门与词表修补（Task 1 审查后追加）

**Files:**
- Modify: `pipeline/gate.py`
- Test: `tests/test_gate.py`

**Interfaces:**
- Produces: `GATED_SOURCES: tuple[str, ...]`、`should_gate(item: dict, gated_sources=GATED_SOURCES) -> bool`；`filter_relevant(items, gated_sources=GATED_SOURCES)` 签名向后兼容

**原因**：词表对任何标题一律生效，会误杀专业源里的正常产业新闻（BioPharmaDive 的「Karyopharm, deep in debt, to sell itself in bankruptcy」），也会因英语屈折变化漏掉「immunotherapy」「antibodies」「approvals」。同时 STAT 这类综合源里的非医药稿必须继续拦。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_gate.py 追加
from pipeline.gate import GATED_SOURCES, filter_relevant, is_relevant, should_gate


class TestSourcePolicy(unittest.TestCase):
    def test_dedicated_pharma_source_not_gated(self):
        self.assertFalse(should_gate({"source": "biopharmadive"}))

    def test_broad_source_gated(self):
        self.assertTrue(should_gate({"source": "stat"}))

    def test_unknown_source_gated(self):
        self.assertTrue(should_gate({"source": "somewhere-new"}))

    def test_ungated_source_keeps_unmatched_title(self):
        items = [{"source": "biopharmadive", "title": "Karyopharm, deep in debt, to sell itself in bankruptcy"}]
        self.assertEqual(len(filter_relevant(items)), 1)

    def test_gated_source_still_drops(self):
        items = [{"source": "stat", "title": "Opinion: how meditation helped me"}]
        self.assertEqual(filter_relevant(items), [])


class TestInflections(unittest.TestCase):
    def test_immunotherapy(self):
        self.assertTrue(is_relevant({"title": "Immunotherapy shows promise in melanoma"}))

    def test_antibodies(self):
        self.assertTrue(is_relevant({"title": "New monoclonal antibodies advance"}))

    def test_approves(self):
        self.assertTrue(is_relevant({"title": "Regulator approves new plant"}))

    def test_aromatherapy_still_rejected(self):
        self.assertFalse(is_relevant({"title": "Aromatherapy oils for sale"}))

    def test_deal_terms(self):
        self.assertTrue(is_relevant({"title": "Pfizer acquires Seagen in $43 billion deal"}))
        self.assertTrue(is_relevant({"title": "Company files for Chapter 11"}))

    def test_pd1_token(self):
        self.assertTrue(is_relevant({"title": "PD-1 inhibitor shows new data"}))
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_gate -v`
Expected: `ImportError: cannot import name 'should_gate'`（或同等失败）

- [ ] **Step 3: 实现**

```python
# pipeline/gate.py 追加/替换相应部分

# 只拦综合源；专业医药源整源可信，不受词表约束
GATED_SOURCES: tuple[str, ...] = ("stat", "nmpa-news", "nature-biotech")

# 前缀匹配（左边界，无右边界）：覆盖 therapy/therapies/immunotherapy/chemotherapy 等
STEMS: tuple[str, ...] = (
    "therap", "vaccin", "antibod", "biosimilar", "oncolog", "pharmac",
    "biotech", "biolog", "clinic", "trial", "regulat", "approv",
)


def _stem_hit(text: str, stem: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(stem), text) is not None


def should_gate(item: dict, gated_sources: tuple[str, ...] = GATED_SOURCES) -> bool:
    return item.get("source", "") in gated_sources


def is_relevant(item: dict) -> bool:
    text = f"{item.get('title', '')} {item.get('title_zh', '')}".lower()
    return any(_hit(text, term) for term in TERMS) or any(_stem_hit(text, stem) for stem in STEMS)


def filter_relevant(items: list[dict], gated_sources: tuple[str, ...] = GATED_SOURCES) -> list[dict]:
    return [i for i in items if not should_gate(i, gated_sources) or is_relevant(i)]
```

`TERMS` 追加：`"pd-1"`, `"pd-l1"`, `"ctla-4"`, `"acquire"`, `"acquisition"`, `"merger"`, `"buyout"`, `"bankruptcy"`, `"chapter 11"`, `"layoff"`, `"restructur"`, `"ipo"`, `"valuation"`, `"financing"`, `"pricing"`, `"coverage"`。

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m unittest tests.test_gate -v`
Expected: 原有 10 + 新增 12 全过

- [ ] **Step 5: 全量测试**

Run: `python3 -m unittest discover -s tests -t . -v`
Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
git add pipeline/gate.py tests/test_gate.py
git commit -m "feat: 主题门按源分级并修补词表屈折与交易词"
```

---

## 完成标志

- `data/items.json` 中不再出现选举、冥想、民生类条目
- 前一日 19:00 之后发布的条目出现在当日版面
- 全部测试通过，`run.py` 退出码 0
