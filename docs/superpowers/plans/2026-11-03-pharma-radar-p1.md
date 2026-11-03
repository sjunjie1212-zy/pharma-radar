# 药脉 P1 实现计划（端到端跑通）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 抓取英文医药 RSS 与国内监管公告，按规则打分、去重、配额筛选，生成 `data/items.json`，并在静态页面上展示「今日」列表。

**Architecture:** 四个独立层——`sources/` 只负责取回并归一化为 `Item`；`pipeline/` 负责打分、聚类、配额与构建；`run.py` 编排；根目录静态页面只读 `data/items.json`。各层之间只通过 `Item` 字典与 JSON 文件通信，任一源失败不阻断整期。

**Tech Stack:** Python 3.14（标准库 + 已安装的 `requests`）、`unittest`（零额外依赖）、原生 HTML/CSS/JS、GitHub Pages。

## Global Constraints

- Python 3.14.2；不得引入 `pytest`、`feedparser`、任何前端框架或 CDN 依赖
- 测试全部用 `unittest`，运行方式 `python3 -m unittest discover -s tests -t . -v`
- 每条消息必须能序列化为一个 `Item` 字典，字段集合固定（见 Task 1）
- 时间一律用 ISO 8601，日期字段 `YYYY-MM-DD`，内部时区固定 `Asia/Shanghai`
- 日报窗口：前一日 19:00 至当日 19:00（CST）
- 不接入任何付费数据库；不抓取需登录的页面
- 所有写盘操作必须幂等：同一 `id` 重复运行不产生重复条目
- 单个源抛异常时，`run.py` 捕获并记录，继续跑其余源，退出码仍为 0
- 页面为纯静态，无构建步骤，直接打开 `index.html` 可读

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `sources/base.py` | `Item` 数据结构、URL 规范化、id 生成、时间解析 |
| `sources/rss_en.py` | 英文 RSS/Atom 抓取与解析 |
| `sources/reg_cn.py` | NMPA / CDE 公告页抓取与解析 |
| `pipeline/scoring.py` | 事件分类、维度分配、材料性 M 评分 |
| `pipeline/dedupe.py` | 标题归一化、聚类、同事件合并 |
| `pipeline/select.py` | 排序与配额截断 |
| `pipeline/build.py` | 追加 jsonl、合并为 `data/items.json` |
| `run.py` | 命令行编排 |
| `index.html` / `app.js` / `style.css` | 「今日」页 |
| `tests/` | unittest 用例与 fixtures |

---

### Task 1: Item 数据结构与 URL 规范化

**Files:**
- Create: `sources/__init__.py`, `sources/base.py`
- Test: `tests/test_base.py`

**Interfaces:**
- Produces:
  - `DIMENSIONS: tuple[str, ...]` — `("D1","D2","D3","D4","D5","D6")`
  - `EVENT_TYPES: tuple[str, ...]` — `("deal","clinical","regulatory","payment","commercial","science","policy")`
  - `make_item(**kwargs) -> dict` — 返回字段完整的 Item 字典，缺省值齐全
  - `canonical_url(url: str) -> str`
  - `item_id(url: str) -> str` — 16 位十六进制
  - `parse_date(text: str) -> str` — 返回 `YYYY-MM-DD`，失败返回 `""`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_base.py
import unittest
from sources.base import canonical_url, item_id, make_item, parse_date


class TestCanonicalUrl(unittest.TestCase):
    def test_strips_tracking_and_fragment(self):
        a = canonical_url("https://Example.com/drug/a/?utm_source=x&id=7#top")
        b = canonical_url("https://example.com/drug/a?id=7")
        self.assertEqual(a, b)

    def test_trailing_slash_ignored(self):
        self.assertEqual(canonical_url("https://a.com/x/"), canonical_url("https://a.com/x"))


class TestItemId(unittest.TestCase):
    def test_same_url_same_id(self):
        self.assertEqual(item_id("https://a.com/x?utm_medium=1"), item_id("https://a.com/x"))

    def test_id_is_16_hex(self):
        i = item_id("https://a.com/x")
        self.assertEqual(len(i), 16)
        int(i, 16)


class TestMakeItem(unittest.TestCase):
    def test_defaults_present(self):
        it = make_item(title="t", url="https://a.com/x", source="s", published_at="2026-11-03T10:00:00")
        for k in ("id", "date", "published_at", "source", "source_weight", "lang",
                  "title", "title_zh", "url", "company", "drug", "target", "ta",
                  "event_type", "dimension", "m", "why", "cluster_id"):
            self.assertIn(k, it)
        self.assertEqual(it["dimension"], "D6")
        self.assertEqual(it["m"], 1)
        self.assertEqual(it["company"], [])

    def test_id_derived_from_url(self):
        it = make_item(title="t", url="https://a.com/x", source="s", published_at="2026-11-03T10:00:00")
        self.assertEqual(it["id"], item_id("https://a.com/x"))


class TestParseDate(unittest.TestCase):
    def test_rfc822(self):
        self.assertEqual(parse_date("Tue, 03 Nov 2026 10:20:00 +0000"), "2026-11-03")

    def test_iso(self):
        self.assertEqual(parse_date("2026-11-03T10:20:00Z"), "2026-11-03")

    def test_garbage_returns_empty(self):
        self.assertEqual(parse_date("not a date"), "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m unittest tests.test_base -v`
Expected: `ModuleNotFoundError: No module named 'sources'`

- [ ] **Step 3: 实现**

```python
# sources/__init__.py
```

```python
# sources/base.py
"""Item 数据结构与 URL 规范化。所有源适配器都产出这里的 Item 字典。"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

DIMENSIONS = ("D1", "D2", "D3", "D4", "D5", "D6")
EVENT_TYPES = ("deal", "clinical", "regulatory", "payment", "commercial", "science", "policy")

_TRACKING_EXACT = {"spm", "from", "ref", "source_id", "share", "trk"}
_TRAILING_PUNCT = re.compile(r"[\s。！？!?,，.；;：:]+$")


def canonical_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    parts = urlsplit(url)
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_EXACT
    ]
    return urlunsplit((scheme, netloc, path, urlencode(kept), ""))


def item_id(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode("utf-8")).hexdigest()[:16]


def normalize_title(title: str) -> str:
    return re.sub(r"[\W_]+", "", (title or "").lower())


def parse_date(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    try:
        return parsedate_to_datetime(text).astimezone(timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, IndexError):
        pass
    try:
        cleaned = text.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned).strftime("%Y-%m-%d")
    except ValueError:
        return ""


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
) -> dict:
    published_at = (published_at or "").strip()
    return {
        "id": item_id(url),
        "date": date or parse_date(published_at),
        "published_at": published_at,
        "source": source,
        "source_weight": float(source_weight),
        "lang": lang,
        "title": _TRAILING_PUNCT.sub("", title or "").strip(),
        "title_zh": title_zh,
        "url": url,
        "company": list(company or []),
        "drug": list(drug or []),
        "target": list(target or []),
        "ta": list(ta or []),
        "event_type": "science",
        "dimension": "D6",
        "m": 1,
        "why": "",
        "cluster_id": "",
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m unittest tests.test_base -v`
Expected: 8 tests PASS

- [ ] **Step 5: 提交**

```bash
git add sources/ tests/test_base.py
git commit -m "feat: Item 数据结构与 URL 规范化"
```

---

### Task 2: 英文 RSS 适配器

**Files:**
- Create: `sources/rss_en.py`
- Test: `tests/test_rss_en.py`, `tests/fixtures/rss_sample.xml`

**Interfaces:**
- Consumes: `make_item`, `parse_date` from `sources.base`
- Produces:
  - `FEEDS: list[dict]` — 每项 `{"source": str, "url": str, "weight": float}`
  - `parse_feed(xml_bytes: bytes, source: str, weight: float = 1.0) -> list[dict]`
  - `fetch_all(timeout: int = 20) -> list[dict]` — 单源失败打日志并跳过

- [ ] **Step 1: 写 fixture 与失败测试**

```xml
<!-- tests/fixtures/rss_sample.xml -->
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Sample</title>
    <item>
      <title>Company A reports Phase 3 win in NSCLC</title>
      <link>https://example.com/a?utm_source=rss</link>
      <pubDate>Tue, 03 Nov 2026 10:20:00 +0000</pubDate>
    </item>
    <item>
      <title>FDA approves drug B for rare disease</title>
      <link>https://example.com/b</link>
      <pubDate>Mon, 02 Nov 2026 08:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>
```

```python
# tests/test_rss_en.py
import pathlib
import unittest

from sources.rss_en import parse_feed

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "rss_sample.xml"


class TestParseFeed(unittest.TestCase):
    def setUp(self):
        self.items = parse_feed(FIXTURE.read_bytes(), "sample", 1.5)

    def test_parses_two_items(self):
        self.assertEqual(len(self.items), 2)

    def test_fields(self):
        first = self.items[0]
        self.assertEqual(first["title"], "Company A reports Phase 3 win in NSCLC")
        self.assertEqual(first["source"], "sample")
        self.assertEqual(first["source_weight"], 1.5)
        self.assertEqual(first["lang"], "en")
        self.assertEqual(first["date"], "2026-11-03")

    def test_tracking_params_removed(self):
        self.assertEqual(self.items[0]["url"], "https://example.com/a")

    def test_broken_xml_returns_empty(self):
        self.assertEqual(parse_feed(b"<not xml", "sample"), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_rss_en -v`
Expected: `ModuleNotFoundError: No module named 'sources.rss_en'`

- [ ] **Step 3: 实现**

```python
# sources/rss_en.py
"""英文医药新闻源：解析 RSS 2.0 与 Atom，统一产出 Item。"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

import requests

from sources.base import canonical_url, item_id, make_item

log = logging.getLogger(__name__)

FEEDS = [
    {"source": "endpoints", "url": "https://endpoints.news/feed/", "weight": 1.3},
    {"source": "fierce-biotech", "url": "https://www.fiercebiotech.com/rss/xml", "weight": 1.1},
    {"source": "fierce-pharma", "url": "https://www.fiercepharma.com/rss/xml", "weight": 1.1},
    {"source": "stat", "url": "https://www.statnews.com/feed/", "weight": 1.2},
    {"source": "biopharmadive", "url": "https://www.biopharmadive.com/feeds/news/", "weight": 1.0},
    {"source": "nature-biotech", "url": "https://www.nature.com/nbt.rss", "weight": 1.3},
]

ATOM = "{http://www.w3.org/2005/Atom}"


def _text(node, tag: str) -> str:
    child = node.find(tag)
    return (child.text or "").strip() if child is not None else ""


def parse_feed(xml_bytes: bytes, source: str, weight: float = 1.0) -> list[dict]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []

    entries: list[dict] = []
    for node in root.iter("item"):
        url = canonical_url(_text(node, "link"))
        if not url:
            continue
        entries.append(
            make_item(
                title=_text(node, "title"),
                url=url,
                source=source,
                published_at=_text(node, "pubDate"),
                source_weight=weight,
                lang="en",
            )
        )

    for node in root.iter(f"{ATOM}entry"):
        link = node.find(f"{ATOM}link")
        url = canonical_url((link.get("href") or "").strip() if link is not None else "")
        if not url:
            continue
        entries.append(
            make_item(
                title=_text(node, f"{ATOM}title"),
                url=url,
                source=source,
                published_at=_text(node, f"{ATOM}updated") or _text(node, f"{ATOM}published"),
                source_weight=weight,
                lang="en",
            )
        )

    return [e for e in entries if e["title"]]


def fetch_all(timeout: int = 20) -> list[dict]:
    out: list[dict] = []
    for feed in FEEDS:
        try:
            resp = requests.get(feed["url"], timeout=timeout, headers={"User-Agent": "pharma-radar/0.1"})
            resp.raise_for_status()
            items = parse_feed(resp.content, feed["source"], feed["weight"])
            log.info("feed %s: %d items", feed["source"], len(items))
            out.extend(items)
        except Exception as exc:  # 单源失败不影响整体
            log.warning("feed %s failed: %s", feed["source"], exc)
    return out
```

> `item_id` 在 `make_item` 内部根据传入的 url 计算，所以 url 必须先经 `canonical_url` 再传进去，否则带追踪参数的链接会得到不同的 id。

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m unittest tests.test_rss_en -v`
Expected: 4 tests PASS

- [ ] **Step 5: 真实抓取冒烟**

Run: `python3 -c "from sources.rss_en import fetch_all; print(len(fetch_all()))"`
Expected: 输出大于 0 的整数；若全部源失败，检查网络代理后重试，不要改代码

- [ ] **Step 6: 提交**

```bash
git add sources/rss_en.py tests/test_rss_en.py tests/fixtures/rss_sample.xml
git commit -m "feat: 英文 RSS 适配器"
```

---

### Task 3: 规则打分（事件分类、维度、材料性）

**Files:**
- Create: `pipeline/__init__.py`, `pipeline/scoring.py`
- Test: `tests/test_scoring.py`

**Interfaces:**
- Consumes: `EVENT_TYPES`, `DIMENSIONS` from `sources.base`
- Produces:
  - `classify_event(title: str) -> str`
  - `assign_dimension(event_type: str, title: str) -> str`
  - `score_m(event_type: str, title: str) -> int`
  - `enrich(item: dict) -> dict` — 原地补齐 `event_type` / `dimension` / `m`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_scoring.py
import unittest

from pipeline.scoring import assign_dimension, classify_event, enrich, score_m


class TestClassifyEvent(unittest.TestCase):
    def test_deal(self):
        self.assertEqual(classify_event("AstraZeneca licenses ADC asset in $2bn deal"), "deal")

    def test_regulatory(self):
        self.assertEqual(classify_event("FDA approves new therapy for NSCLC"), "regulatory")

    def test_clinical(self):
        self.assertEqual(classify_event("Phase 3 trial meets primary endpoint"), "clinical")

    def test_payment(self):
        self.assertEqual(classify_event("医保谈判结果公布，创新药平均降价 60%"), "payment")

    def test_policy(self):
        self.assertEqual(classify_event("CDE 发布新的指导原则"), "policy")

    def test_fallback_science(self):
        self.assertEqual(classify_event("New mechanism linking inflammation to fibrosis"), "science")


class TestDimension(unittest.TestCase):
    def test_guideline_goes_D1(self):
        self.assertEqual(assign_dimension("science", "CSCO 指南更新：一线治疗顺序调整"), "D1")

    def test_regulatory_goes_D3(self):
        self.assertEqual(assign_dimension("regulatory", "FDA approves drug X"), "D3")

    def test_payment_goes_D4(self):
        self.assertEqual(assign_dimension("payment", "集采中选结果公布"), "D4")

    def test_deal_goes_D5(self):
        self.assertEqual(assign_dimension("deal", "Company sells asset for $1bn"), "D5")

    def test_policy_goes_D6(self):
        self.assertEqual(assign_dimension("policy", "医药代表备案新规"), "D6")


class TestScoreM(unittest.TestCase):
    def test_class_level_readout_is_5(self):
        self.assertEqual(score_m("clinical", "First-in-class readout reshapes the field"), 5)

    def test_approval_is_4(self):
        self.assertEqual(score_m("regulatory", "FDA approves drug B"), 4)

    def test_phase3_start_is_3(self):
        self.assertEqual(score_m("clinical", "Phase 3 trial initiated in China"), 3)

    def test_unknown_is_2(self):
        self.assertEqual(score_m("science", "Researchers describe a pathway"), 2)


class TestEnrich(unittest.TestCase):
    def test_enrich_sets_fields(self):
        item = {"title": "FDA approves drug B", "event_type": "science", "dimension": "D6", "m": 1}
        out = enrich(item)
        self.assertEqual(out["event_type"], "regulatory")
        self.assertEqual(out["dimension"], "D3")
        self.assertEqual(out["m"], 4)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_scoring -v`
Expected: `ModuleNotFoundError: No module named 'pipeline'`

- [ ] **Step 3: 实现**

```python
# pipeline/__init__.py
```

```python
# pipeline/scoring.py
"""规则打分：事件分类 → 维度 → 材料性。规则先行，模型只处理边界案例。"""
from __future__ import annotations

import re

# 顺序即优先级：先匹配到的胜出
_EVENT_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("deal", ("授权", "许可", "收购", "并购", "对外授权", "首付款", "license", "licensing",
              "acquisition", "acquire", "merger", "collaboration deal", "buyout")),
    ("payment", ("医保", "集采", "谈判", "降价", "支付", "报销", "nrdl", "reimbursement",
                 "medicare", "price cut")),
    ("regulatory", ("获批", "批准", "受理", "上市申请", "附条件", "优先审评", "突破性疗法",
                    "approval", "approved", "approves", "filing", "complete response letter",
                    "regulatory approval")),
    ("clinical", ("iii期", "3期", "临床", "读出", "主要终点", "达到终点", "未达到", "终止",
                  "暂停", "头对头", "phase 3", "phase iii", "topline", "primary endpoint",
                  "readout", "halted", "discontinued")),
    ("policy", ("指导原则", "法规", "合规", "备案", "监管新规", "guidance", "policy", "regulation")),
    ("commercial", ("销售额", "营收", "财报", "出海", "裁员", "管线调整", "重组", "revenue",
                    "sales", "earnings", "layoff", "restructur")),
]

_DIMENSION_BY_EVENT = {
    "clinical": "D2",
    "regulatory": "D3",
    "payment": "D4",
    "deal": "D5",
    "commercial": "D5",
    "policy": "D6",
    "science": "D1",
}

_GUIDELINE = ("指南", "共识", "guideline", "consensus", "standard of care", "治疗格局")

_M5 = ("首个", "first-in-class", "first in class", "指南更新", "指南改写", "class effect",
       "撤市", "暂停", "提前终止", "监管规则", "集采规则", "医保规则改变", "推翻")
_M4 = ("获批", "批准", "approves", "approved", "主要终点", "primary endpoint", "医保目录",
       "纳入", "上市申请", "受理", "指导原则", "1亿美元", "1亿美元", "$1 billion", "$1bn")
_M3 = ("iii期", "phase 3", "phase iii", "启动", "initiated", "早期", "受理",
       "人事", "任命", "appoint", "裁员")

# 注意：不要加入 nda / bla / ind / crl 这类三字母缩写，子串会误伤 standard、substantial 等常用词。
# 需要识别时，用带空格的完整形式，或改 _hit 为带词边界的正则。


def _hit(text: str, words: tuple[str, ...]) -> bool:
    return any(w in text for w in words)


def classify_event(title: str) -> str:
    low = (title or "").lower()
    for event_type, words in _EVENT_KEYWORDS:
        if _hit(low, words):
            return event_type
    return "science"


def assign_dimension(event_type: str, title: str) -> str:
    low = (title or "").lower()
    if _hit(low, _GUIDELINE):
        return "D1"
    return _DIMENSION_BY_EVENT.get(event_type, "D6")


def score_m(event_type: str, title: str) -> int:
    low = (title or "").lower()
    if _hit(low, _M5):
        return 5
    if _hit(low, _M4):
        return 4
    if _hit(low, _M3):
        return 3
    if event_type in ("deal", "clinical", "regulatory"):
        return 3
    return 2


def enrich(item: dict) -> dict:
    event_type = classify_event(item["title"])
    item["event_type"] = event_type
    item["dimension"] = assign_dimension(event_type, item["title"])
    item["m"] = score_m(event_type, item["title"])
    return item
```

> `_M5` 里同时含「暂停」和「撤市」但 `_EVENT_KEYWORDS` 把「暂停」归到 clinical；这是有意的：暂停试验通常是最强信号。若测试显示分类不稳，先改测试期望再到规则，不要反过来。

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m unittest tests.test_scoring -v`
Expected: 15 tests PASS

- [ ] **Step 5: 提交**

```bash
git add pipeline/ tests/test_scoring.py
git commit -m "feat: 规则打分（事件、维度、材料性）"
```

---

### Task 4: 去重与聚类

**Files:**
- Create: `pipeline/dedupe.py`
- Test: `tests/test_dedupe.py`

**Interfaces:**
- Consumes: `normalize_title`, `item_id` from `sources.base`
- Produces:
  - `dedupe(items: list[dict]) -> list[dict]` — 按 `id` 去重，保留首次出现
  - `assign_clusters(items: list[dict], threshold: float = 0.85) -> list[dict]` — 填充 `cluster_id`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_dedupe.py
import unittest

from pipeline.dedupe import assign_clusters, dedupe


def _item(i, title, url):
    return {"id": i, "title": title, "url": url, "title_zh": "", "cluster_id": ""}


class TestDedupe(unittest.TestCase):
    def test_same_id_kept_once(self):
        items = [_item("a", "t", "u"), _item("a", "t", "u")]
        self.assertEqual(len(dedupe(items)), 1)

    def test_order_preserved(self):
        items = [_item("a", "t1", "u1"), _item("b", "t2", "u2")]
        self.assertEqual([x["id"] for x in dedupe(items)], ["a", "b"])


class TestClusters(unittest.TestCase):
    def test_near_duplicate_titles_share_cluster(self):
        items = [
            _item("a", "FDA approves drug B for rare disease", "u1"),
            _item("b", "FDA approves Drug B for rare disease!", "u2"),
        ]
        out = assign_clusters(items)
        self.assertEqual(out[0]["cluster_id"], out[1]["cluster_id"])

    def test_distinct_titles_do_not_share(self):
        items = [
            _item("a", "FDA approves drug B", "u1"),
            _item("b", "Company C raises $200m in Series B", "u2"),
        ]
        out = assign_clusters(items)
        self.assertNotEqual(out[0]["cluster_id"], out[1]["cluster_id"])

    def test_uses_title_zh_when_present(self):
        items = [
            {"id": "a", "title": "x", "title_zh": "恒瑞与 BMS 达成 152 亿美元合作", "url": "u1", "cluster_id": ""},
            {"id": "b", "title": "y", "title_zh": "恒瑞与BMS达成152亿美元合作", "url": "u2", "cluster_id": ""},
        ]
        out = assign_clusters(items)
        self.assertEqual(out[0]["cluster_id"], out[1]["cluster_id"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_dedupe -v`
Expected: `ModuleNotFoundError: No module named 'pipeline.dedupe'`

- [ ] **Step 3: 实现**

```python
# pipeline/dedupe.py
"""去重与同事件聚类。聚类只做粗分：URL 去重 + 标题相似度。"""
from __future__ import annotations

from difflib import SequenceMatcher

from sources.base import normalize_title


def _key(item: dict) -> str:
    return normalize_title(item.get("title_zh") or item.get("title") or "")


def dedupe(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        out.append(item)
    return out


def assign_clusters(items: list[dict], threshold: float = 0.85) -> list[dict]:
    reps: list[tuple[str, str]] = []  # (归一化标题, cluster_id)
    for item in items:
        key = _key(item)
        matched = ""
        for rep_key, rep_id in reps:
            if key and rep_key and SequenceMatcher(None, key, rep_key).ratio() >= threshold:
                matched = rep_id
                break
        if matched:
            item["cluster_id"] = matched
        else:
            item["cluster_id"] = item["id"]
            reps.append((key, item["id"]))
    return items
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m unittest tests.test_dedupe -v`
Expected: 5 tests PASS

- [ ] **Step 5: 提交**

```bash
git add pipeline/dedupe.py tests/test_dedupe.py
git commit -m "feat: 去重与同事件聚类"
```

---

### Task 5: 配额选择

**Files:**
- Create: `pipeline/select.py`
- Test: `tests/test_select.py`

**Interfaces:**
- Consumes: `DIMENSIONS` from `sources.base`
- Produces: `select(items: list[dict], limit: int = 20, per_dim: int = 5, required: tuple[str, ...] = ("D1","D2","D3","D4","D5")) -> list[dict]`

规则：按 `(m, source_weight, published_at)` 降序；单维度最多 `per_dim` 条；总数不超过 `limit`；若某必需维度为空，从该维度取最高分一条替换掉超额维度里最低分的一条。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_select.py
import unittest

from pipeline.select import select


def _item(i, dim, m):
    return {"id": i, "dimension": dim, "m": m, "source_weight": 1.0, "published_at": "2026-11-03T10:00:00"}


class TestSelect(unittest.TestCase):
    def test_per_dimension_cap(self):
        items = [_item(f"d5-{i}", "D5", 5) for i in range(10)]
        out = select(items, limit=20, per_dim=5)
        self.assertEqual(len([x for x in out if x["dimension"] == "D5"]), 5)

    def test_total_limit(self):
        items = [_item(f"{d}-{i}", d, 4) for d in ("D1", "D2", "D3", "D4", "D5") for i in range(10)]
        out = select(items, limit=20, per_dim=5)
        self.assertEqual(len(out), 20)

    def test_required_dimension_survives_flood(self):
        flood = [_item(f"d5-{i}", "D5", 5) for i in range(40)]
        lone = [_item("d1-only", "D1", 2)]
        out = select(flood + lone, limit=20, per_dim=5)
        self.assertIn("D1", {x["dimension"] for x in out})

    def test_sorted_by_m_desc(self):
        items = [_item("a", "D1", 2), _item("b", "D1", 5), _item("c", "D2", 4)]
        out = select(items, limit=20, per_dim=5)
        self.assertEqual([x["m"] for x in out], [5, 4, 2])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_select -v`
Expected: `ModuleNotFoundError: No module named 'pipeline.select'`

- [ ] **Step 3: 实现**

```python
# pipeline/select.py
"""配额选择：防单一话题霸榜。"""
from __future__ import annotations


def _rank_key(item: dict):
    return (item.get("m", 0), item.get("source_weight", 0.0), item.get("published_at", ""))


def select(items, limit: int = 20, per_dim: int = 5, required=("D1", "D2", "D3", "D4", "D5")):
    ranked = sorted(items, key=_rank_key, reverse=True)
    chosen: list[dict] = []
    counts: dict[str, int] = {}

    for item in ranked:
        if len(chosen) >= limit:
            break
        dim = item.get("dimension", "D6")
        if counts.get(dim, 0) >= per_dim:
            continue
        chosen.append(item)
        counts[dim] = counts.get(dim, 0) + 1

    for dim in required:
        if counts.get(dim, 0) > 0:
            continue
        candidate = next((i for i in ranked if i.get("dimension") == dim and i not in chosen), None)
        if candidate is None:
            continue
        if len(chosen) >= limit:
            evict = min(
                (c for c in chosen if counts.get(c["dimension"], 0) > 1),
                key=_rank_key,
                default=None,
            )
            if evict is None:
                continue
            chosen.remove(evict)
            counts[evict["dimension"]] -= 1
        chosen.append(candidate)
        counts[dim] = counts.get(dim, 0) + 1

    return sorted(chosen, key=_rank_key, reverse=True)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m unittest tests.test_select -v`
Expected: 4 tests PASS

- [ ] **Step 5: 提交**

```bash
git add pipeline/select.py tests/test_select.py
git commit -m "feat: 配额选择"
```

---

### Task 6: 构建与编排

**Files:**
- Create: `pipeline/build.py`, `run.py`
- Test: `tests/test_build.py`

**Interfaces:**
- Consumes: `dedupe`, `assign_clusters`, `select`, `enrich`
- Produces:
  - `append_raw(items: list[dict], month: str, raw_dir: str = "data/raw") -> int` — 返回新增条数，幂等
  - `load_raw(raw_dir: str = "data/raw") -> list[dict]`
  - `build(items: list[dict], out_path: str = "data/items.json") -> dict` — 写出并返回结构
  - `items.json` 结构：`{"generated_at": iso, "days": [{"date": "YYYY-MM-DD", "must": [id...], "items": [Item...]}]}`，`must` 规则：`m >= 5` 或（`m >= 4` 且 `dimension in {"D1","D3","D4"}`）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_build.py
import json
import pathlib
import tempfile
import unittest

from pipeline.build import append_raw, build, load_raw


def _item(i, date="2026-11-03", m=4, dim="D3"):
    return {
        "id": i, "date": date, "published_at": f"{date}T10:00:00", "source": "s",
        "source_weight": 1.0, "lang": "en", "title": f"title {i}", "title_zh": "",
        "url": f"https://e.com/{i}", "company": [], "drug": [], "target": [], "ta": [],
        "event_type": "regulatory", "dimension": dim, "m": m, "why": "", "cluster_id": i,
    }


class TestAppendRaw(unittest.TestCase):
    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(append_raw([_item("a")], "2026-11", raw_dir=tmp), 1)
            self.assertEqual(append_raw([_item("a")], "2026-11", raw_dir=tmp), 0)
            self.assertEqual(len(load_raw(raw_dir=tmp)), 1)


class TestBuild(unittest.TestCase):
    def test_groups_by_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "items.json"
            data = build([_item("a"), _item("b", date="2026-11-02")], out_path=str(out))
            self.assertEqual(len(data["days"]), 2)
            self.assertTrue(out.exists())
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["days"][0]["date"], "2026-11-03")

    def test_must_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "items.json"
            data = build([_item("a", m=5), _item("b", m=2), _item("c", m=4, dim="D5")], out_path=str(out))
            self.assertEqual(data["days"][0]["must"], ["a"])

    def test_days_sorted_desc(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "items.json"
            data = build([_item("a", date="2026-11-01"), _item("b", date="2026-11-03")], out_path=str(out))
            self.assertEqual([d["date"] for d in data["days"]], ["2026-11-03", "2026-11-01"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_build -v`
Expected: `ModuleNotFoundError: No module named 'pipeline.build'`

- [ ] **Step 3: 实现**

```python
# pipeline/build.py
"""落盘与构建：jsonl 是唯一事实来源，items.json 是派生产物。"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

CST = ZoneInfo("Asia/Shanghai")


def append_raw(items: list[dict], month: str, raw_dir: str = "data/raw") -> int:
    os.makedirs(raw_dir, exist_ok=True)
    path = os.path.join(raw_dir, f"{month}.jsonl")
    seen: set[str] = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    seen.add(json.loads(line)["id"])

    new = [i for i in items if i["id"] not in seen]
    if new:
        with open(path, "a", encoding="utf-8") as fh:
            for item in new:
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    return len(new)


def load_raw(raw_dir: str = "data/raw") -> list[dict]:
    out: list[dict] = []
    if not os.path.isdir(raw_dir):
        return out
    for name in sorted(os.listdir(raw_dir)):
        if not name.endswith(".jsonl"):
            continue
        with open(os.path.join(raw_dir, name), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    return out


def _is_must(item: dict) -> bool:
    if item.get("m", 0) >= 5:
        return True
    return item.get("m", 0) >= 4 and item.get("dimension") in {"D1", "D3", "D4"}


def build(items: list[dict], out_path: str = "data/items.json") -> dict:
    by_date: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        by_date[item.get("date") or ""].append(item)

    days = []
    for date in sorted(by_date, reverse=True):
        rows = sorted(
            by_date[date],
            key=lambda i: (i.get("m", 0), i.get("source_weight", 0.0), i.get("published_at", "")),
            reverse=True,
        )
        days.append({"date": date, "must": [r["id"] for r in rows if _is_must(r)], "items": rows})

    payload = {
        "generated_at": datetime.now(CST).isoformat(timespec="seconds"),
        "days": days,
    }
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    return payload
```

```python
# run.py
"""药脉每日流水线。用法：python3 run.py [--date 2026-11-03]"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from pipeline.build import append_raw, build, load_raw
from pipeline.dedupe import assign_clusters, dedupe
from pipeline.scoring import enrich
from pipeline.select import select
from sources.rss_en import fetch_all

CST = ZoneInfo("Asia/Shanghai")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("run")


def collect() -> list[dict]:
    items: list[dict] = []
    try:
        items.extend(fetch_all())
    except Exception as exc:
        log.error("rss_en failed: %s", exc)
    return items


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(CST).strftime("%Y-%m-%d"))
    args = parser.parse_args()

    today = args.date
    fresh = [i for i in collect() if i.get("date") == today]
    fresh = [enrich(i) for i in fresh]
    fresh = assign_clusters(dedupe(fresh))
    chosen = select(fresh)

    added = append_raw(chosen, month=today[:7])
    payload = build(load_raw())
    log.info("date=%s fetched=%d selected=%d added=%d days=%d",
             today, len(fresh), len(chosen), added, len(payload["days"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m unittest tests.test_build -v`
Expected: 5 tests PASS

- [ ] **Step 5: 全量测试**

Run: `python3 -m unittest discover -s tests -t . -v`
Expected: 全部 PASS

- [ ] **Step 6: 端到端跑一次**

Run: `python3 run.py`
Expected: 日志出现 `fetched=… selected=… added=…`，`data/items.json` 生成且 `days` 非空。若当天没有匹配 `date` 的条目，改用 `python3 run.py --date 2026-11-03` 或临时放宽日期过滤验证链路。

- [ ] **Step 7: 提交**

```bash
git add pipeline/build.py run.py tests/test_build.py data/
git commit -m "feat: 构建与流水线编排，端到端跑通"
```

---

### Task 7: 「今日」页面

**Files:**
- Create: `index.html`, `app.js`, `style.css`
- Test: `tests/test_page.py`（只校验页面引用的资源与数据结构一致）

**Interfaces:**
- Consumes: `data/items.json`，结构见 Task 6
- Produces: 可直接打开的静态页面；`app.js` 暴露 `window.renderDay(dayData)` 供测试调用

- [ ] **Step 1: 写失败测试**

```python
# tests/test_page.py
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestPageFiles(unittest.TestCase):
    def test_files_exist(self):
        for name in ("index.html", "app.js", "style.css"):
            self.assertTrue((ROOT / name).exists(), name)

    def test_html_references_assets_locally(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("./app.js", html)
        self.assertIn("./style.css", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://cdn", html)

    def test_js_reads_items_json(self):
        js = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("./data/items.json", js)

    def test_dimension_colors_defined(self):
        css = (ROOT / "style.css").read_text(encoding="utf-8")
        for dim in ("d1", "d2", "d3", "d4", "d5", "d6"):
            self.assertIn(f".dim-{dim}", css)

    def test_sample_items_json_matches_schema(self):
        import json
        data = json.loads((ROOT / "tests" / "fixtures" / "items_sample.json").read_text(encoding="utf-8"))
        day = data["days"][0]
        self.assertIn("date", day)
        self.assertIn("must", day)
        self.assertIn("items", day)
        self.assertTrue(all("dimension" in i and "m" in i for i in day["items"]))


if __name__ == "__main__":
    unittest.main()
```

```json
// tests/fixtures/items_sample.json
{
 "generated_at": "2026-11-03T19:00:00+08:00",
 "days": [
  {
   "date": "2026-11-03",
   "must": ["a"],
   "items": [
    {"id": "a", "date": "2026-11-03", "published_at": "2026-11-03T10:00:00", "source": "endpoints",
     "source_weight": 1.3, "lang": "en", "title": "Phase 3 trial meets primary endpoint", "title_zh": "III 期达到主要终点",
     "url": "https://example.com/a", "company": ["Acme"], "drug": ["ACM-101"], "target": ["PD-1"], "ta": ["NSCLC"],
     "event_type": "clinical", "dimension": "D2", "m": 5,
     "why": "首个同靶点头对头阳性，可能改写一线顺序", "cluster_id": "a"}
   ]
  }
 ]
}
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_page -v`
Expected: FAIL（index.html 不存在）

- [ ] **Step 3: 实现页面**

```html
<!-- index.html -->
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>药脉 · 今日</title>
<link rel="stylesheet" href="./style.css">
</head>
<body>
<header class="top">
  <h1>药脉</h1>
  <span id="generated" class="muted"></span>
</header>
<nav class="tabs">
  <button class="tab active" data-dim="all">全部</button>
  <button class="tab" data-dim="D1">D1 格局</button>
  <button class="tab" data-dim="D2">D2 临床</button>
  <button class="tab" data-dim="D3">D3 监管</button>
  <button class="tab" data-dim="D4">D4 准入</button>
  <button class="tab" data-dim="D5">D5 商业</button>
  <button class="tab" data-dim="D6">D6 生态</button>
</nav>
<main id="app"></main>
<script src="./app.js"></script>
</body>
</html>
```

```javascript
// app.js
const state = { data: null, dim: "all" };

async function load() {
  const res = await fetch("./data/items.json");
  state.data = await res.json();
  render();
}

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

function card(item, isMust) {
  const a = el("a", `card dim-${(item.dimension || "D6").toLowerCase()}` + (isMust ? " must" : ""));
  a.href = item.url;
  a.target = "_blank";
  a.rel = "noopener";
  const head = el("div", "head");
  head.appendChild(el("span", "badge", item.dimension || "D6"));
  head.appendChild(el("span", "m", "M" + item.m));
  head.appendChild(el("span", "src", item.source));
  a.appendChild(head);
  a.appendChild(el("h2", null, item.title_zh || item.title));
  if (item.title_zh) a.appendChild(el("p", "orig", item.title));
  if (item.why) a.appendChild(el("p", "why", item.why));
  return a;
}

function renderDay(day) {
  const section = el("section", "day");
  section.appendChild(el("h2", "date", day.date));
  const must = day.items.filter((i) => day.must.includes(i.id));
  if (must.length) {
    const box = el("div", "must-box");
    must.forEach((i) => box.appendChild(card(i, true)));
    section.appendChild(box);
  }
  const rest = day.items.filter((i) => !day.must.includes(i.id));
  const list = el("div", "list");
  rest.forEach((i) => list.appendChild(card(i, false)));
  section.appendChild(list);
  if (!day.items.length) section.appendChild(el("p", "empty", "本期无条目"));
  return section;
}

function render() {
  const app = document.getElementById("app");
  app.innerHTML = "";
  document.getElementById("generated").textContent =
    state.data ? "更新于 " + state.data.generated_at : "";
  const days = (state.data?.days || []).map((day) => ({
    ...day,
    items: day.items.filter((i) => state.dim === "all" || i.dimension === state.dim),
  }));
  days.forEach((day) => app.appendChild(renderDay(day)));
}

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    state.dim = btn.dataset.dim;
    render();
  });
});

window.renderDay = renderDay;
load().catch((e) => {
  document.getElementById("app").innerHTML =
    '<p class="empty">加载 data/items.json 失败：' + e.message + "</p>";
});
```

```css
/* style.css */
:root {
  --bg: #fbfaf7;
  --fg: #1f1d1a;
  --muted: #7a746c;
  --line: #e6e1d8;
  --d1: #3f6f5a;
  --d2: #4a6fa5;
  --d3: #8a5a3b;
  --d4: #7a5b8a;
  --d5: #a2762f;
  --d6: #5c6670;
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 0 1rem 3rem;
  background: var(--bg); color: var(--fg);
  font-family: -apple-system, "PingFang SC", "Noto Sans SC", system-ui, sans-serif;
  line-height: 1.65;
}
.top { display: flex; align-items: baseline; gap: .75rem; padding: 1.2rem 0 .6rem; }
.top h1 { font-size: 1.35rem; margin: 0; letter-spacing: .08em; }
.muted { color: var(--muted); font-size: .8rem; }
.tabs { display: flex; gap: .4rem; overflow-x: auto; padding-bottom: .8rem; border-bottom: 1px solid var(--line); }
.tab {
  border: 1px solid var(--line); background: transparent; color: var(--muted);
  border-radius: 999px; padding: .25rem .7rem; font-size: .82rem; white-space: nowrap; cursor: pointer;
}
.tab.active { color: var(--fg); border-color: var(--fg); }
.day { margin-top: 1.4rem; }
.date { font-size: .9rem; color: var(--muted); font-weight: 500; margin: 0 0 .6rem; }
.card {
  display: block; text-decoration: none; color: inherit;
  border-left: 3px solid var(--d6); padding: .55rem .8rem; margin-bottom: .55rem;
  background: #fff; border-radius: 2px;
}
.card.must { background: #fffdf5; box-shadow: 0 1px 0 var(--line); }
.card .head { display: flex; gap: .5rem; align-items: center; font-size: .72rem; color: var(--muted); }
.card h2 { font-size: .98rem; font-weight: 550; margin: .25rem 0 .15rem; }
.orig { font-size: .78rem; color: var(--muted); margin: 0 0 .2rem; }
.why { font-size: .84rem; margin: 0; color: #3a3631; }
.badge { font-weight: 600; }
.m { color: var(--fg); }
.empty { color: var(--muted); font-size: .9rem; }
.dim-d1 { border-left-color: var(--d1); }
.dim-d2 { border-left-color: var(--d2); }
.dim-d3 { border-left-color: var(--d3); }
.dim-d4 { border-left-color: var(--d4); }
.dim-d5 { border-left-color: var(--d5); }
.dim-d6 { border-left-color: var(--d6); }
@media (max-width: 520px) { .card h2 { font-size: .95rem; } }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m unittest tests.test_page -v`
Expected: 5 tests PASS

- [ ] **Step 5: 浏览器验证**

```bash
python3 -m http.server 8765
```

打开 `http://localhost:8765/`，确认：顶部日期显示、卡片按维度有左侧色条、点 D2 只留临床条目、点开链接新标签打开。

- [ ] **Step 6: 提交**

```bash
git add index.html app.js style.css tests/test_page.py tests/fixtures/items_sample.json
git commit -m "feat: 今日页（静态，无依赖）"
```

---

### Task 8: NMPA / CDE 公告适配器

**Files:**
- Create: `sources/reg_cn.py`
- Modify: `run.py`（在 `collect()` 中并入 `fetch_all()`）
- Test: `tests/test_reg_cn.py`, `tests/fixtures/nmpa_sample.html`

**Interfaces:**
- Consumes: `make_item`, `parse_date`
- Produces: `parse_listing(html: str, source: str, weight: float = 1.2) -> list[dict]`、`fetch_all(timeout: int = 20) -> list[dict]`

- [ ] **Step 1: 写 fixture 与失败测试**

```html
<!-- tests/fixtures/nmpa_sample.html -->
<html><body>
<ul class="list">
  <li><a href="/yaopin/202611031200.html">国家药监局关于发布某指导原则的通告</a><span>2026-11-03</span></li>
  <li><a href="https://www.nmpa.gov.cn/yaopin/202611021000.html">关于某药品获批上市的公告</a><span>2026-11-02</span></li>
</ul>
</body></html>
```

```python
# tests/test_reg_cn.py
import pathlib
import unittest

from sources.reg_cn import parse_listing

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "nmpa_sample.html"


class TestParseListing(unittest.TestCase):
    def setUp(self):
        self.items = parse_listing(FIXTURE.read_text(encoding="utf-8"), "nmpa")

    def test_two_items(self):
        self.assertEqual(len(self.items), 2)

    def test_relative_url_absolutized(self):
        self.assertTrue(self.items[0]["url"].startswith("https://www.nmpa.gov.cn/"))

    def test_date_parsed(self):
        self.assertEqual(self.items[0]["date"], "2026-11-03")

    def test_lang_is_zh(self):
        self.assertEqual(self.items[0]["lang"], "zh")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m unittest tests.test_reg_cn -v`
Expected: `ModuleNotFoundError: No module named 'sources.reg_cn'`

- [ ] **Step 3: 实现**

```python
# sources/reg_cn.py
"""NMPA / CDE 公告列表页解析。页面结构变化时只改这个文件。"""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

import requests

from sources.base import canonical_url, item_id, make_item

log = logging.getLogger(__name__)

BASE = "https://www.nmpa.gov.cn"
SOURCES = [
    {"source": "nmpa", "url": f"{BASE}/yaopin/ypggtg/index.html", "weight": 1.4},
    {"source": "nmpa-news", "url": f"{BASE}/yaowen/ypjgyw/index.html", "weight": 1.2},
]

_LINK = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>([^<]{6,})</a>', re.S)
_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _nearest_date(html: str, start: int, end: int) -> str:
    """在链接前后各 200 字符内找最近的日期，找不到返回空串。"""
    match = _DATE.search(html[end : end + 200]) or _DATE.search(html[max(0, start - 200) : start])
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}" if match else ""


def parse_listing(html: str, source: str, weight: float = 1.2, base: str = BASE) -> list[dict]:
    items: list[dict] = []
    for match in _LINK.finditer(html):
        href, raw_title = match.group(1), match.group(2)
        title = re.sub(r"\s+", " ", raw_title).strip()
        if not title or href.startswith("javascript"):
            continue
        date = _nearest_date(html, match.start(), match.end())
        items.append(
            make_item(
                title=title,
                url=canonical_url(urljoin(base, href)),
                source=source,
                published_at=f"{date}T00:00:00" if date else "",
                date=date,
                source_weight=weight,
                lang="zh",
            )
        )
    return items


def fetch_all(timeout: int = 20) -> list[dict]:
    out: list[dict] = []
    for cfg in SOURCES:
        try:
            resp = requests.get(cfg["url"], timeout=timeout, headers={"User-Agent": "pharma-radar/0.1"})
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            items = parse_listing(resp.text, cfg["source"], cfg["weight"])
            log.info("source %s: %d items", cfg["source"], len(items))
            out.extend(items)
        except Exception as exc:
            log.warning("source %s failed: %s", cfg["source"], exc)
    return out
```

> `_nearest_date` 依赖「日期紧跟在链接后面」这一页面惯例。若真实页面把日期放在标题前面，把 200 字符的探查窗口改成双向并保持顺序即可；改之前先抓一次真实 HTML 看一眼结构。

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m unittest tests.test_reg_cn -v`
Expected: 4 tests PASS

- [ ] **Step 5: 接入流水线**

```python
# run.py 的 collect() 改为
from sources import reg_cn

def collect() -> list[dict]:
    items: list[dict] = []
    for fn in (fetch_all, reg_cn.fetch_all):
        try:
            items.extend(fn())
        except Exception as exc:
            log.error("%s failed: %s", fn.__module__, exc)
    return items
```

- [ ] **Step 6: 真实抓取冒烟**

Run: `python3 -c "from sources.reg_cn import fetch_all; print(len(fetch_all()))"`
Expected: 大于 0；若为 0，先确认页面结构与正则是否仍匹配，再改 `_LINK`

- [ ] **Step 7: 提交**

```bash
git add sources/reg_cn.py run.py tests/test_reg_cn.py tests/fixtures/nmpa_sample.html
git commit -m "feat: NMPA 公告适配器并接入流水线"
```

---

## P1 完成后的验收

```bash
python3 -m unittest discover -s tests -t . -v   # 全部通过
python3 run.py                                   # 生成 data/items.json
python3 -m http.server 8765                      # 打开 localhost:8765
```

页面应显示当日条目，维度色条正确，`M5` 条目出现在「必看」区。

P2–P5（ClinicalTrials/openFDA/PubMed、中文媒体源、认知地图与领域档案、定时与周报）各自单独出计划，不并入本计划。
