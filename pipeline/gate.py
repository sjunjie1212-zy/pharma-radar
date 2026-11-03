"""主题门：只放行与医药产业相关的条目。

匹配对象是标题（原文与中文转写）。疾病名单独出现不算相关——流感、阿尔茨海默病之类
的公共卫生报道本身不改变产业判断；要进版面，标题里必须有药品、临床、监管、支付、
交易或平台技术信号。

分源策略：需过词表的源（stat 是综合兴趣台；nmpa-news 与 nature-biotech 按策略选择
逐条过词表）——stat 混有观点/政治稿，nmpa-news 与 nature-biotech 为审慎起见同样精筛。
专业医药源整源可信，直接放行，避免「Karyopharm ... bankruptcy」这类无通用信号词的
产业稿被误杀。未知源按需过词表处理（默认拦截），词表命中才放行。
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
    # 交易与困境信号词汇（acquisition/merger 原表已有，不重复）。
    # coverage/pricing/valuation/ipo/financing/layoff/restructur 等泛新闻词已移除：
    # 它们会让受控源里的选举、公司市值等无关稿误过门；真正的医药稿仍会带
    # drug/biotech/therapy/clinical 等词。
    "pd-1", "pd-l1", "ctla-4", "acquire", "buyout", "bankruptcy", "chapter 11",
)

# 需过词表的源：STAT 是综合兴趣台（混观点/政治稿）；NMPA 要闻与 Nature Biotechnology
# 按策略选择同样逐条过词表，因此也列在此处。
GATED_SOURCES: tuple[str, ...] = ("stat", "nmpa-news", "nature-biotech")

# 专业医药源白名单：整源放行。未知源不在名单内，按需过词表处理。
TRUSTED_SOURCES: tuple[str, ...] = (
    "biopharmadive", "endpoints", "fierce-biotech", "fierce-pharma", "nmpa", "trials",
    "openfda",
)

# 词干匹配（左边界，无右边界）：覆盖 therapy/therapies、vaccine/vaccines、
# antibody/antibodies、approve/approval 等屈折与派生。
# "immunotherap"/"chemotherap" 单独列出：这两个词里 therapy 前没有词边界，
# 左边界前缀 "therap" 匹配不到；若放宽为词中匹配又会误中 aromatherapy。
STEMS: tuple[str, ...] = (
    "therap", "vaccin", "antibod", "biosimilar", "oncolog", "pharmac",
    "biotech", "biolog", "clinic", "trial", "regulat", "approv",
    "immunotherap", "chemotherap",
)

# "pharmac" 词干会命中零售/执业场景的 pharmacy 同形词；这些不是产业信号，
# 沿用既有 fixture 的判定（pharma 不匹配 pharmacy）。
_STEM_STOPWORDS = frozenset(("pharmacy", "pharmacies", "pharmacist", "pharmacists"))

_ASCII = re.compile(r"^[a-z0-9-]+$")
# 英文术语允许常见屈折后缀：acquire→acquires、approval→approvals、buyout→buyouts。
# "pharma"+"cy" 不是屈折后缀，因此 pharmacy 仍不命中。
_INFLECTION = r"(?:s|es|ed|d|ing)?"


def _hit(text: str, term: str) -> bool:
    if _ASCII.match(term):
        pattern = r"(?<![a-z0-9])" + re.escape(term) + _INFLECTION + r"(?![a-z0-9])"
        return re.search(pattern, text) is not None
    return term in text


def _stem_hit(text: str, stem: str) -> bool:
    pattern = r"(?<![a-z0-9])(" + re.escape(stem) + r"[a-z0-9]*)"
    return any(m.group(1) not in _STEM_STOPWORDS for m in re.finditer(pattern, text))


def should_gate(item: dict, gated_sources: tuple[str, ...] = GATED_SOURCES) -> bool:
    """默认拦截；只有白名单里的专业医药源整源放行。"""
    source = item.get("source", "")
    if source in gated_sources:
        return True
    return source not in TRUSTED_SOURCES


def is_relevant(item: dict) -> bool:
    text = f"{item.get('title', '')} {item.get('title_zh', '')}".lower()
    return any(_hit(text, term) for term in TERMS) or any(_stem_hit(text, stem) for stem in STEMS)


def filter_relevant(items: list[dict], gated_sources: tuple[str, ...] = GATED_SOURCES) -> list[dict]:
    return [i for i in items if not should_gate(i, gated_sources) or is_relevant(i)]
