# 药脉 P3：中文媒体源与跨源聚类 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把三个静态可达的中文医药媒体接入流水线，并让同一事件的多源报道在当期版面只占一条。

**Architecture:** 新增 `sources/media_cn.py`（一个适配器，三个站点的列表页解析，`requests` + 本机代理），条目进既有 collect→enrich→gate→window 链路；在 `pipeline/dedupe.py` 里加强同事件判定（标题相似度 + 中文二元组 Jaccard），新增 `collapse_clusters` 在选稿前把同簇条目折叠成排名最高的一条；`run.py` 改为「先排除已入库 id 再选稿」，修掉两日重叠导致的版面亏空。

**Tech Stack:** Python 3.14、stdlib、`requests`、`unittest`。无新依赖，无框架。

## Global Constraints

- 依赖只有标准库 + `requests`；不引入新包、不使用 pytest。
- 所有「今天」类默认日期必须用 `datetime.now(ZoneInfo("Asia/Shanghai")).date()`，不得用 `date.today()`。
- Item 字典保持 18 个固定字段（见 `sources/base.py:make_item`），**不得新增字段**。
- `data/YYYY-MM.jsonl` 只追加；唯一允许重写的文件是 `data/catalysts.json` / `data/catalysts.js`。
- 页面侧纯 HTML/CSS/JS，无框架、无构建、无外部 CDN。
- 单个源失败只记日志、跳过，不得中止整次运行。
- 新源必须登记进 `pipeline/gate.py:TRUSTED_SOURCES`，并有能证伪的测试（断言源在名单里，而不是只断言 `should_gate` 返回 False——未知源默认也返回 True/False 语义会遮蔽）。
- 测试命令：`python3 -m unittest discover -s tests -t . -v`；测试全部走 fixture/mock，不触网。
- 中文媒体取回走代理：环境变量 `PHARMA_RADAR_PROXY`，缺省 `http://127.0.0.1:7890`；显式空串时不走代理。
- 提交信息用中文一句话 + 类型前缀（`feat:` / `fix:` / `docs:`），结尾空行 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。

---

### Task 1: `sources/media_cn.py` 中文媒体适配器

**Files:**
- Create: `sources/media_cn.py`
- Create: `tests/test_media_cn.py`
- Create: `tests/fixtures/bioon_list.html`
- Create: `tests/fixtures/yaozh_home.html`
- Create: `tests/fixtures/drugtimes_home.html`

**Interfaces:**
- Consumes: `sources.base.make_item`、`sources.base.canonical_url`、`sources.base.CST`
- Produces:
  - `proxies() -> dict[str, str] | None`
  - `parse_bioon(html: str, base: str = "https://news.bioon.com/") -> list[dict]`
  - `parse_yaozh(html: str, base: str = "https://news.yaozh.com") -> list[dict]`
  - `parse_drugtimes(html: str, base: str = "https://www.drugtimes.cn") -> list[dict]`
  - `fetch_all(days: int = 2, today: date | None = None, timeout: int = 20) -> list[dict]`
- 源名固定为 `bioon` / `yaozh` / `drugtimes`（Task 2 的 gate 名单与测试依赖这三个字符串）。

- [ ] **Step 1: 写三个 fixture**

`tests/fixtures/bioon_list.html`（两个条目 + 一个无日期导航链接）：

```html
<html><body>
<div class="item">
  <div class="item-header"><a href="http://news.bioon.com/article/a8da9616261f.html" target="_blank"><img src="x.jpg" /></a></div>
  <div class="item-content">
    <h2><a href="http://news.bioon.com/article/a8da9616261f.html" class="ms-link" target="_blank">Sci Adv：复旦大学张朝/文波发现基因组“古老碎片”不是垃圾</a></h2>
    <p class="text-justify">摘要文字</p>
    <span class="item-meta"><span class="item-meta-item">2026-11-02</span></span>
  </div>
</div>
<div class="item">
  <div class="item-header"><a href="http://news.bioon.com/article/fda190508200.html" target="_blank"><img src="y.jpg" /></a></div>
  <div class="item-content">
    <h2><a href="http://news.bioon.com/article/fda190508200.html" class="ms-link" target="_blank">FDA 批准首款口服 GLP-1 受体激动剂</a></h2>
    <p class="text-justify">摘要文字</p>
    <span class="item-meta"><span class="item-meta-item">2026-11-03</span></span>
  </div>
</div>
<a href="/CAR-T">CAR-T/TCR-T细胞治疗</a>
</body></html>
```

`tests/fixtures/yaozh_home.html`（同一条目出现两次，验证去重）：

```html
<html><body>
<div class="zjltoutiao"><a href="/archive/49307.html" target="_blank"><div title="特宝生物10mg获批，长效生长激素的规格竞争" class="zjltoutiao_tit"><span>特宝生物10mg获批，长效生长激素的规格竞争</span></div> <div class="clearfix zjltoutiao_info"><div class="fl"><div class="info_bg"><span class="co_tit_one">特宝生物</span></div></div> <div class="fr"> 2026-11-03 </div></div></a></div>
<div class="zjltoutiao"><a href="/archive/49301.html" target="_blank"><div title="流感季营销怎么打：感冒清热&amp;止咳祛痰" class="zjltoutiao_tit"><span>流感季营销怎么打</span></div> <div class="clearfix zjltoutiao_info"><div class="fl"></div> <div class="fr"> 2026-11-03 </div></div></a></div>
<div class="zjltoutiao"><a href="/archive/49307.html" target="_blank"><div title="特宝生物10mg获批，长效生长激素的规格竞争" class="zjltoutiao_tit"><span>重复出现</span></div> <div class="clearfix zjltoutiao_info"><div class="fl"></div> <div class="fr"> 2026-11-03 </div></div></a></div>
</body></html>
```

`tests/fixtures/drugtimes_home.html`（日期来自 URL 路径）：

```html
<html><body>
<h2><a href="https://www.drugtimes.cn/2026/11/03/757yimeiyuanxiyuananjianpiantongguanxian/" target="_blank">7.57亿美元！熙源安健偏头痛管线出海艾伯维</a></h2>
<h2><a href="https://www.drugtimes.cn/2026/11/02/1880yimeiyuanjiuweililai/" target="_blank">1880亿美元就位！礼来、强生等MNC将押注何处？</a></h2>
<a href="https://www.drugtimes.cn/category/drugnews/">药物资讯</a>
</body></html>
```

- [ ] **Step 2: 写失败测试**

`tests/test_media_cn.py`：

```python
import os
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from sources import media_cn

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class TestParseBioon(unittest.TestCase):
    def test_titles_urls_dates(self):
        items = media_cn.parse_bioon(_fixture("bioon_list.html"))
        self.assertEqual(len(items), 2)
        first = items[0]
        self.assertEqual(first["source"], "bioon")
        self.assertEqual(first["date"], "2026-11-02")
        self.assertEqual(first["published_at"], "2026-11-02T00:00:00+08:00")
        self.assertEqual(first["url"], "http://news.bioon.com/article/a8da9616261f.html")
        self.assertIn("复旦大学", first["title"])
        self.assertEqual(items[1]["date"], "2026-11-03")
        self.assertEqual(first["lang"], "zh")

    def test_navigation_links_skipped(self):
        items = media_cn.parse_bioon(_fixture("bioon_list.html"))
        self.assertNotIn("CAR-T/TCR-T细胞治疗", [i["title"] for i in items])


class TestParseYaozh(unittest.TestCase):
    def test_entity_unescaped_and_duplicates_collapsed(self):
        items = media_cn.parse_yaozh(_fixture("yaozh_home.html"))
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["source"], "yaozh")
        self.assertEqual(items[0]["url"], "https://news.yaozh.com/archive/49307.html")
        self.assertTrue(any("&" in i["title"] for i in items))
        self.assertTrue(all("&amp;" not in i["title"] for i in items))

    def test_date_captured(self):
        items = media_cn.parse_yaozh(_fixture("yaozh_home.html"))
        self.assertEqual({i["date"] for i in items}, {"2026-11-03"})


class TestParseDrugtimes(unittest.TestCase):
    def test_date_from_url_path(self):
        items = media_cn.parse_drugtimes(_fixture("drugtimes_home.html"))
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["date"], "2026-11-03")
        self.assertEqual(items[1]["date"], "2026-11-02")
        self.assertEqual(items[0]["source"], "drugtimes")
        self.assertTrue(items[0]["url"].startswith("https://www.drugtimes.cn/2026/11/03/"))

    def test_category_links_skipped(self):
        items = media_cn.parse_drugtimes(_fixture("drugtimes_home.html"))
        self.assertNotIn("药物资讯", [i["title"] for i in items])


class TestProxies(unittest.TestCase):
    def test_default_proxy(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(media_cn.proxies(),
                             {"http": "http://127.0.0.1:7890",
                              "https": "http://127.0.0.1:7890"})

    def test_env_override(self):
        with mock.patch.dict(os.environ, {"PHARMA_RADAR_PROXY": "http://127.0.0.1:1080"}, clear=True):
            self.assertEqual(media_cn.proxies()["https"], "http://127.0.0.1:1080")

    def test_empty_disables_proxy(self):
        with mock.patch.dict(os.environ, {"PHARMA_RADAR_PROXY": "  "}, clear=True):
            self.assertIsNone(media_cn.proxies())


class TestFetchAll(unittest.TestCase):
    def test_filters_old_items_and_isolates_failure(self):
        html = {
            "https://news.bioon.com/1.html": _fixture("bioon_list.html"),
            "https://news.bioon.com/2.html": _fixture("bioon_list.html"),
            "https://news.yaozh.com/": _fixture("yaozh_home.html"),
        }

        def fake_get(url, **kwargs):
            if url not in html:
                raise RuntimeError("boom")
            resp = mock.Mock()
            resp.text = html[url]
            resp.raise_for_status = mock.Mock()
            return resp

        with mock.patch.object(media_cn.requests, "get", side_effect=fake_get):
            items = media_cn.fetch_all(days=2, today=date(2026, 11, 3))

        self.assertTrue(items)
        self.assertTrue(all(i["date"] >= "2026-11-02" for i in items))
        self.assertNotIn("drugtimes", {i["source"] for i in items})

    def test_ids_unique(self):
        with mock.patch.object(media_cn, "_get", return_value=_fixture("yaozh_home.html")):
            items = media_cn.fetch_all(days=2, today=date(2026, 11, 3))
        ids = [i["id"] for i in items]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: 跑测试确认失败**

Run: `python3 -m unittest tests.test_media_cn -v`
Expected: `ModuleNotFoundError: No module named 'sources.media_cn'`（或 import 失败）。

- [ ] **Step 4: 实现 `sources/media_cn.py`**

```python
"""中文医药媒体列表页解析。页面结构变化时只改这个文件。

代理：环境变量 PHARMA_RADAR_PROXY，缺省本机 7890；设为空串时不走代理
（GitHub Actions 用）。决定见 spec §7 的 2026-11-04 条。
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime, timedelta
from html import unescape
from urllib.parse import urljoin

import requests

from sources.base import CST, canonical_url, make_item

log = logging.getLogger(__name__)

DEFAULT_PROXY = "http://127.0.0.1:7890"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

BIOON_PAGES = 2
BIOON_URL = "https://news.bioon.com/{page}.html"
YAOZH_URL = "https://news.yaozh.com/"
DRUGTIMES_URL = "https://www.drugtimes.cn/"

_BIOON_ITEM = re.compile(r'<div class="item">(.*?)(?=<div class="item">|\Z)', re.S)
_BIOON_LINK = re.compile(r'<h2>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_BIOON_DATE = re.compile(r'item-meta-item">\s*(\d{4}-\d{2}-\d{2})')

_YAOZH_LINK = re.compile(
    r'<a[^>]+href="(/archive/\d+\.html)"[^>]*>\s*<div[^>]*title="([^"]+)"[^>]*>'
    r'.*?class="fr">\s*(\d{4}-\d{2}-\d{2})',
    re.S,
)

_DRUGTIMES_LINK = re.compile(
    r'<a[^>]+href="(https://www\.drugtimes\.cn/(\d{4})/(\d{2})/(\d{2})/[^"]+)"[^>]*>(.*?)</a>',
    re.S,
)

_TAG = re.compile(r"<[^>]+>")


def proxies() -> dict[str, str] | None:
    value = os.environ.get("PHARMA_RADAR_PROXY", DEFAULT_PROXY).strip()
    return {"http": value, "https": value} if value else None


def _get(url: str, timeout: int) -> str:
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": UA},
                        proxies=proxies())
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def _clean(raw: str) -> str:
    return re.sub(r"\s+", " ", unescape(_TAG.sub(" ", raw))).strip()


def _item(title: str, url: str, source: str, day: str, weight: float) -> dict:
    return make_item(
        title=title,
        url=canonical_url(url),
        source=source,
        published_at=f"{day}T00:00:00+08:00",
        date=day,
        source_weight=weight,
        lang="zh",
    )


def parse_bioon(html: str, base: str = "https://news.bioon.com/") -> list[dict]:
    items: list[dict] = []
    for block in _BIOON_ITEM.findall(html):
        link = _BIOON_LINK.search(block)
        day = _BIOON_DATE.search(block)
        if not link or not day:
            continue
        title = _clean(link.group(2))
        if len(title) < 6:
            continue
        items.append(_item(title, urljoin(base, link.group(1)), "bioon",
                           day.group(1), 1.3))
    return items


def parse_yaozh(html: str, base: str = "https://news.yaozh.com") -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for href, raw_title, day in _YAOZH_LINK.findall(html):
        url = base.rstrip("/") + href
        title = _clean(raw_title)
        if not title or url in seen:
            continue
        seen.add(url)
        items.append(_item(title, url, "yaozh", day, 1.2))
    return items


def parse_drugtimes(html: str, base: str = "https://www.drugtimes.cn") -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for href, year, month, day, raw_title in _DRUGTIMES_LINK.findall(html):
        title = _clean(raw_title)
        if len(title) < 6 or href in seen:
            continue
        seen.add(href)
        items.append(_item(title, href, "drugtimes",
                           f"{year}-{month}-{day}", 1.2))
    return items


def fetch_all(days: int = 2, today: date | None = None,
              timeout: int = 20) -> list[dict]:
    today = today or datetime.now(CST).date()
    floor = (today - timedelta(days=days - 1)).isoformat()
    plan = [
        ("bioon", [BIOON_URL.format(page=p) for p in range(1, BIOON_PAGES + 1)],
         parse_bioon),
        ("yaozh", [YAOZH_URL], parse_yaozh),
        ("drugtimes", [DRUGTIMES_URL], parse_drugtimes),
    ]
    out: list[dict] = []
    for name, urls, parser in plan:
        try:
            parsed: list[dict] = []
            for url in urls:
                parsed.extend(parser(_get(url, timeout), url))
            fresh = [i for i in parsed if i["date"] and i["date"] >= floor]
            log.info("source %s: %d parsed, %d fresh", name, len(parsed), len(fresh))
            out.extend(fresh)
        except Exception as exc:
            log.warning("source %s failed: %s", name, exc)
    return out
```

注意：`fetch_all` 把列表页 URL 作为 `base` 传入。`parse_bioon` 用 `urljoin`（fixture 与真实页面都是绝对 href，`base` 基本不参与）；`parse_yaozh` 用 `base.rstrip("/") + href` 拼站根，避免 `https://news.yaozh.com//archive/...` 双斜杠；`parse_drugtimes` 的 URL 自带域名，不使用 `base`。

- [ ] **Step 5: 跑测试确认通过**

Run: `python3 -m unittest tests.test_media_cn -v`
Expected: 全部通过（10 个用例）。

- [ ] **Step 6: 提交**

```bash
git add sources/media_cn.py tests/test_media_cn.py tests/fixtures/bioon_list.html tests/fixtures/yaozh_home.html tests/fixtures/drugtimes_home.html
git commit -m "feat: 新增中文医药媒体适配器（生物谷/药智/药时代）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: 接入 `run.py` 与主题门

**Files:**
- Modify: `run.py:16,26-27`
- Modify: `pipeline/gate.py`（`TRUSTED_SOURCES`）
- Modify: `tests/test_gate.py`（新增 `TestChineseMediaTrusted`）

**Interfaces:**
- Consumes: `sources.media_cn.fetch_all(days=2, today=None, timeout=20)`
- Produces: gate 白名单含 `"bioon"`, `"yaozh"`, `"drugtimes"`；`collect()` 纳入 `media_cn.fetch_all`。

- [ ] **Step 1: 写失败测试**

在 `tests/test_gate.py` 末尾（`if __name__` 之前）追加：

```python
class TestChineseMediaTrusted(unittest.TestCase):
    def test_bioon_trusted(self):
        self.assertIn("bioon", TRUSTED_SOURCES)
        self.assertFalse(should_gate({"source": "bioon"}))

    def test_yaozh_trusted(self):
        self.assertIn("yaozh", TRUSTED_SOURCES)
        self.assertFalse(should_gate({"source": "yaozh"}))

    def test_drugtimes_trusted(self):
        self.assertIn("drugtimes", TRUSTED_SOURCES)
        self.assertFalse(should_gate({"source": "drugtimes"}))

    def test_non_pharma_media_still_gated(self):
        # 36氪、界面这类综合媒体必须逐条过词表，不能因为中文媒体接入而整源放行。
        self.assertTrue(should_gate({"source": "36kr"}))
        self.assertTrue(should_gate({"source": "jiemian"}))
```

并把文件首行的 import 改为：

```python
from pipeline.gate import (GATED_SOURCES, TRUSTED_SOURCES, filter_relevant,
                           is_relevant, should_gate)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_gate -v`
Expected: `NameError: name 'TRUSTED_SOURCES' is not defined`（import 失败），或 `AssertionError` on `assertIn`。

- [ ] **Step 3: 改 `pipeline/gate.py`**

```python
TRUSTED_SOURCES: tuple[str, ...] = (
    "biopharmadive", "endpoints", "fierce-biotech", "fierce-pharma", "nmpa", "trials",
    "openfda", "pubmed", "bioon", "yaozh", "drugtimes",
)
```

- [ ] **Step 4: 改 `run.py` 的 collect**

第 16 行改为：

```python
from sources import media_cn, openfda, pubmed, reg_cn, trials
```

`collect()` 的元组改为：

```python
    for fn in (fetch_rss, reg_cn.fetch_all, trials.fetch_all,
               openfda.fetch_all, pubmed.fetch_all, media_cn.fetch_all):
```

- [ ] **Step 5: 跑全量测试**

Run: `python3 -m unittest discover -s tests -t . -v`
Expected: 全部通过（原 206 + 10 + 4 = 220）。

- [ ] **Step 6: 提交**

```bash
git add run.py pipeline/gate.py tests/test_gate.py
git commit -m "feat: 中文媒体源接入流水线与主题门白名单

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: 同事件聚类与折叠

**Files:**
- Modify: `pipeline/dedupe.py`
- Modify: `tests/test_dedupe.py`

**Interfaces:**
- Consumes: `sources.base.normalize_title`
- Produces:
  - `similarity(a: str, b: str) -> float`（0–1；`SequenceMatcher` 与中文二元组 Jaccard 取大）
  - `assign_clusters(items, threshold: float = 0.85, jaccard_threshold: float = 0.5) -> list[dict]`（签名向后兼容，新增关键字参数）
  - `collapse_clusters(items: list[dict]) -> list[dict]`（保留每个 `cluster_id` 中 `(m, source_weight, published_at)` 最大的一条，输出保持输入顺序）

- [ ] **Step 1: 写失败测试**

在 `tests/test_dedupe.py` 的 import 行改为：

```python
from pipeline.dedupe import assign_clusters, collapse_clusters, dedupe, similarity
```

在 `TestClusters` 类后追加：

```python
class TestSimilarity(unittest.TestCase):
    def test_identical_is_one(self):
        self.assertEqual(similarity("特宝生物10mg获批", "特宝生物10mg获批"), 1.0)

    def test_empty_is_zero(self):
        self.assertEqual(similarity("", "任何标题"), 0.0)

    def test_paraphrase_scores_high(self):
        a = "特宝生物10mg获批，长效生长激素的规格竞争"
        b = "特宝生物长效生长激素10mg规格获批"
        # 实测：SequenceMatcher 0.615，二元组 Jaccard 0.542。
        self.assertGreaterEqual(similarity(a, b), 0.5)

    def test_unrelated_scores_low(self):
        a = "特宝生物10mg获批，长效生长激素的规格竞争"
        b = "三季报扣除股份支付利润转正，君实的牌面藏不住了"
        # 实测：SequenceMatcher 0.047，二元组 Jaccard 0.0。
        self.assertLess(similarity(a, b), 0.5)


class TestCrossSourceClusters(unittest.TestCase):
    def test_different_wording_same_event_share_cluster(self):
        items = [
            _item("a", "特宝生物10mg获批，长效生长激素的规格竞争", "u1"),
            _item("b", "特宝生物长效生长激素10mg规格获批", "u2"),
        ]
        out = assign_clusters(items)
        self.assertEqual(out[0]["cluster_id"], out[1]["cluster_id"])


class TestCollapse(unittest.TestCase):
    def _item(self, i, title, m, weight=1.0):
        return {"id": i, "title": title, "url": "u" + i, "title_zh": "",
                "cluster_id": "", "m": m, "source_weight": weight,
                "published_at": "2026-11-03T08:00:00+08:00"}

    def test_same_cluster_keeps_highest_m(self):
        items = [self._item("a", "特宝生物10mg获批，长效生长激素的规格竞争", 2),
                 self._item("b", "特宝生物长效生长激素10mg规格获批", 4)]
        items = assign_clusters(items)
        self.assertEqual(items[0]["cluster_id"], items[1]["cluster_id"])
        out = collapse_clusters(items)
        self.assertEqual([i["id"] for i in out], ["b"])

    def test_tie_breaks_on_source_weight(self):
        items = [self._item("a", "特宝生物10mg获批，长效生长激素的规格竞争", 3, 1.0),
                 self._item("b", "特宝生物长效生长激素10mg规格获批", 3, 1.4)]
        items = assign_clusters(items)
        out = collapse_clusters(items)
        self.assertEqual([i["id"] for i in out], ["b"])

    def test_distinct_events_all_kept(self):
        items = [self._item("a", "FDA 批准新药甲", 4),
                 self._item("b", "某公司完成 B 轮融资", 2)]
        items = assign_clusters(items)
        out = collapse_clusters(items)
        self.assertEqual([i["id"] for i in out], ["a", "b"])

    def test_preserves_input_order(self):
        items = [self._item("a", "事件甲", 4), self._item("b", "无关事件乙", 1)]
        items = assign_clusters(items)
        self.assertEqual([i["id"] for i in collapse_clusters(items)], ["a", "b"])

    def test_items_without_cluster_id_survive(self):
        items = [self._item("a", "事件甲", 4), self._item("b", "事件甲", 2)]
        out = collapse_clusters(items)
        self.assertEqual(len(out), 2)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_dedupe -v`
Expected: `ImportError: cannot import name 'collapse_clusters'`。

- [ ] **Step 3: 实现**

把 `pipeline/dedupe.py` 全文替换为：

```python
"""去重与同事件聚类。

URL 去重在前；同事件判定用两个信号取大：标题序列相似度（近重复）与
中文二元组 Jaccard（换词改写）。聚类只打标签，折叠由 collapse_clusters
在选稿前完成——原始条目流仍是 append-only。
"""
from __future__ import annotations

from difflib import SequenceMatcher

from sources.base import normalize_title


def _key(item: dict) -> str:
    return normalize_title(item.get("title_zh") or item.get("title") or "")


def _bigrams(text: str) -> set[str]:
    return {text[i:i + 2] for i in range(len(text) - 1)}


def similarity(a: str, b: str) -> float:
    a, b = normalize_title(a), normalize_title(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    seq = SequenceMatcher(None, a, b).ratio()
    ba, bb = _bigrams(a), _bigrams(b)
    jac = len(ba & bb) / len(ba | bb) if ba and bb else 0.0
    return max(seq, jac)


def dedupe(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        out.append(item)
    return out


def _same_event(a: str, b: str, threshold: float, jaccard_threshold: float) -> bool:
    if not a or not b:
        return False
    if SequenceMatcher(None, a, b).ratio() >= threshold:
        return True
    ba, bb = _bigrams(a), _bigrams(b)
    if not ba or not bb:
        return False
    return len(ba & bb) / len(ba | bb) >= jaccard_threshold


def assign_clusters(items: list[dict], threshold: float = 0.85,
                    jaccard_threshold: float = 0.5) -> list[dict]:
    reps: list[tuple[str, str]] = []  # (归一化标题, cluster_id)
    for item in items:
        key = _key(item)
        matched = ""
        for rep_key, rep_id in reps:
            if _same_event(key, rep_key, threshold, jaccard_threshold):
                matched = rep_id
                break
        if matched:
            item["cluster_id"] = matched
        else:
            item["cluster_id"] = item["id"]
            reps.append((key, item["id"]))
    return items


def _rank(item: dict):
    return (item.get("m", 0), item.get("source_weight", 0.0),
            item.get("published_at", ""))


def collapse_clusters(items: list[dict]) -> list[dict]:
    """同一 cluster 只留排名最高的一条；没有 cluster_id 的条目不折叠。"""
    best: dict[str, dict] = {}
    for item in items:
        cid = item.get("cluster_id") or ""
        if not cid:
            continue
        current = best.get(cid)
        if current is None or _rank(item) > _rank(current):
            best[cid] = item
    out: list[dict] = []
    for item in items:
        cid = item.get("cluster_id") or ""
        if not cid or best[cid] is item:
            out.append(item)
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest tests.test_dedupe -v`
Expected: 全部通过（原 3 + 新增 10）。

- [ ] **Step 5: 提交**

```bash
git add pipeline/dedupe.py tests/test_dedupe.py
git commit -m "feat: 同事件聚类改用相似度与二元组 Jaccard，并支持折叠

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: 选稿前排除已入库条目并折叠同簇

**Files:**
- Modify: `run.py:75-79`
- Create: `tests/test_run_main.py`

**Interfaces:**
- Consumes: `pipeline.dedupe.collapse_clusters`、`pipeline.build.load_raw`、`pipeline.build.append_raw`
- Produces: `run.main()` 行为——当期窗口条目先 `dedupe`/`assign_clusters`/`collapse_clusters`，再剔除 `load_raw()` 里已存在的 id，最后 `select()` 与 `append_raw()`。

- [ ] **Step 1: 写失败测试**

`tests/test_run_main.py`：

```python
import unittest
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

import run

CST = ZoneInfo("Asia/Shanghai")
ANCHOR = datetime(2026, 11, 3, 19, 0, tzinfo=CST)
DIMS = ("D1", "D2", "D3", "D4", "D5", "D6")


def _item(i, title, dimension="D3"):
    return {
        "id": i, "date": "2026-11-03", "published_at": "2026-11-03T10:00:00+08:00",
        "source": "bioon", "source_weight": 1.3, "lang": "zh", "title": title,
        "title_zh": "", "url": "u" + i, "company": [], "drug": [], "target": [],
        "ta": [], "event_type": "regulatory", "dimension": dimension, "m": 3,
        "why": "", "cluster_id": "",
    }


class TestMainOrdering(unittest.TestCase):
    def _run(self, collected, existing):
        appended = []

        def fake_append(chosen, month=None):
            appended.extend(chosen)
            return len(chosen)

        with mock.patch("sys.argv", ["run.py"]), \
             mock.patch.object(run, "collect", return_value=collected), \
             mock.patch.object(run, "filter_relevant", side_effect=lambda x: x), \
             mock.patch.object(run, "load_raw", return_value=existing), \
             mock.patch.object(run, "append_raw", side_effect=fake_append), \
             mock.patch.object(run, "build", return_value={"days": []}), \
             mock.patch.object(run, "update_catalysts", return_value={}), \
             mock.patch.object(run, "resolve_anchor", return_value=ANCHOR):
            self.assertEqual(run.main(), 0)
        return appended

    def test_already_stored_items_do_not_consume_quota(self):
        stored = [_item("old", "昨日旧条目")]
        fresh = [_item("new", "今天的新条目")]
        # 六个维度轮转，避免 per_dim=5 把条数卡在 5；26 条足够填满 limit=20。
        fresh.extend(_item(f"filler{n}", f"填充条目{n}", DIMS[n % 6]) for n in range(25))
        appended = self._run(fresh + stored, stored)
        ids = [i["id"] for i in appended]
        self.assertIn("new", ids)
        self.assertNotIn("old", ids)
        self.assertEqual(len(ids), 20)

    def test_collapsed_duplicate_not_appended_twice(self):
        a = _item("a", "特宝生物10mg获批，长效生长激素的规格竞争")
        b = _item("b", "特宝生物长效生长激素10mg规格获批")
        appended = self._run([a, b], [])
        self.assertEqual([i["id"] for i in appended], ["a"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_run_main -v`
Expected: 第一条用例断言失败（旧条目占配额后 `len(ids) < 20`）；第二条因未折叠而返回 `["a", "b"]`。

- [ ] **Step 3: 改 `run.py`**

import 行改为：

```python
from pipeline.dedupe import assign_clusters, collapse_clusters, dedupe
```

第 75-79 行改为：

```python
    fresh = collapse_clusters(assign_clusters(dedupe(windowed)))
    known = {i["id"] for i in load_raw()}
    pending = [i for i in fresh if i["id"] not in known]
    chosen = select(pending)
    log.info("pending: %d of %d after known-id filter", len(pending), len(fresh))

    added = append_raw(chosen, month=today[:7])
    payload = build(load_raw())
```

- [ ] **Step 4: 跑全量测试**

Run: `python3 -m unittest discover -s tests -t . -v`
Expected: 全部通过（220 + 2 = 222）。

- [ ] **Step 5: 提交**

```bash
git add run.py tests/test_run_main.py
git commit -m "fix: 选稿前剔除已入库条目并折叠同簇，修两日重叠版面亏空

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: 真实运行与数据落盘

**Files:**
- Modify: `data/2026-11.jsonl`（追加当期条目）
- Modify: `data/items.json`、`data/items.js`、`data/catalysts.json`、`data/catalysts.js`（由 `run.py` 生成）

- [ ] **Step 1: 净化工作区并确认基线**

```bash
git status --short
python3 -m unittest discover -s tests -t . -v
```

Expected: 工作区干净（除本任务将产生的数据文件），222 测试全绿。

- [ ] **Step 2: 真实运行（走本机代理）**

```bash
python3 run.py --date 2026-11-04
```

Expected: 日志出现 `source bioon:` / `source yaozh:` / `source drugtimes:` 三个源的解析条数；`gate: kept` 大于 0；`pending:` 行给出折叠前后数量。

若三个源全部失败（代理未开、站点改版），报告 `DONE_WITH_CONCERNS` 并贴出 `source ... failed` 日志，不要伪造数据。

- [ ] **Step 3: 验收当期数据**

```bash
python3 - <<'EOF'
import json, collections
rows = [json.loads(l) for l in open("data/2026-11.jsonl", encoding="utf-8")]
today = [r for r in rows if r["date"] == "2026-11-04"]
print("total", len(rows), "today", len(today))
print("sources", collections.Counter(r["source"] for r in today))
ids = [r["id"] for r in rows]
print("dup ids", len(ids) - len(set(ids)))
clusters = collections.Counter(r["cluster_id"] for r in today)
print("rows in multi-item clusters", sum(1 for k, v in clusters.items() if v > 1))
EOF
```

Expected: `dup ids 0`；`today` 不超过 20；出现至少一条 `bioon`/`yaozh`/`drugtimes` 条目。

- [ ] **Step 4: 二次运行验证幂等**

```bash
python3 run.py --date 2026-11-04
python3 -c "import json;rows=[json.loads(l) for l in open('data/2026-11.jsonl',encoding='utf-8')];print(len(rows), len({r['id'] for r in rows}))"
```

Expected: 两个数相等（重复运行不新增条目）。

- [ ] **Step 5: 提交数据**

```bash
git add data/
git commit -m "data: P3 首版中文媒体条目与催化剂

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Self-Review

- §7 决定（静态源 + 代理）由 Task 1 的 `proxies()`/`fetch_all` 落实；三个实测源均有解析用例。✅
- §9 P3 完成标志「同一事件多源报道合并为 1 条」由 Task 3 的 `collapse_clusters` + Task 4 的接入与用例落实。✅
- `TRUSTED_SOURCES` 登记与可证伪测试：Task 2 四条（含综合媒体仍受门控的反向断言）。✅
- 两日重叠版面亏空（P2 ledger 遗留 minor）：Task 4 以「先剔除已入库 id 再选稿」修掉，用例断言恰好 20 条。✅
- Item 字段不变（折叠只删条目不增字段）、raw 仍 append-only：Task 3/4 均未改 schema。✅
- 无占位符、无「同 Task N」引用；类型与签名跨任务一致（`collapse_clusters` / `similarity` / `fetch_all(days, today, timeout)`）。✅
