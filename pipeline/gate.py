"""主题门：只放行与医药产业相关的条目。

匹配对象是标题（原文与中文转写）。疾病名单独出现不算相关——流感、阿尔茨海默病之类
的公共卫生报道本身不改变产业判断；要进版面，标题里必须有药品、临床、监管、支付、
交易或平台技术信号。

分源策略：需过词表的源（stat 是综合兴趣台；nmpa-news、nature-biotech 与 bioon 按策略
选择逐条过词表）——stat 混有观点/政治稿，nmpa-news 与 nature-biotech 为审慎起见同样精筛，
生物谷是泛生命科学站，混有消费导购与科普稿，同样逐条精筛。专业医药源整源可信，直接放行，
避免「Karyopharm ... bankruptcy」这类无通用信号词的产业稿被误杀。未知源按需过词表处理
（默认拦截），词表命中才放行。

在放行判定之上还有一层消费意图否决策略：标题表达的是购买/使用/营销意图而不是产业信号时，
不论来源是否在白名单（yaozh 这类整源可信源也算）一律拦截。原因是「药」「品牌」「渠道」
这类通用词会让消费稿误过词表。
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
# 生物谷是泛生命科学站，混有消费导购与科普稿，按策略改为逐条过词表。
GATED_SOURCES: tuple[str, ...] = ("stat", "nmpa-news", "nature-biotech", "bioon")

# 专业医药源白名单：整源放行。未知源不在名单内，按需过词表处理。
TRUSTED_SOURCES: tuple[str, ...] = (
    "biopharmadive", "endpoints", "fierce-biotech", "fierce-pharma", "nmpa", "trials",
    "openfda", "pubmed", "yaozh", "drugtimes",
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

# 消费稿否决词：表达购买/使用/营销意图，而不是产业信号。命中即拦截，与来源白名单无关。
# 判据是意图而非单个名词——「药」「品牌」「渠道」单独出现仍可能是产业稿，
# 只有组合出导购、比价、种草、榜单之类的语境才拦。
BLOCK_TERMS: tuple[str, ...] = (
    "怎么选", "怎么挑", "如何选", "选购", "横评", "智商税",
    "推荐什么品牌", "管用吗", "种草", "销量榜", "调理指南", "营销怎么",
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


def is_consumer_copy(item: dict) -> bool:
    """标题是否表达购买/使用/营销意图。命中即否决，不看来源。"""
    text = f"{item.get('title', '')} {item.get('title_zh', '')}".lower()
    return any(_hit(text, term) for term in BLOCK_TERMS)


def filter_relevant(items: list[dict], gated_sources: tuple[str, ...] = GATED_SOURCES) -> list[dict]:
    """先否决消费稿，再按来源策略与词表决定放行。"""
    return [
        i for i in items
        if not is_consumer_copy(i)
        and (not should_gate(i, gated_sources) or is_relevant(i))
    ]
