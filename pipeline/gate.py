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
