"""规则打分：事件分类 → 维度 → 材料性。规则先行，模型只处理边界案例。"""
from __future__ import annotations

import re

# 顺序即优先级：先匹配到的胜出
_EVENT_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("deal", ("授权", "对外授权", "对外许可", "许可协议", "专利许可", "收购", "并购", "首付款",
              "license", "licensing", "acquisition", "acquire", "merger", "collaboration deal",
              "buyout", "deal")),
    ("payment", ("医保", "集采", "谈判", "降价", "支付", "报销", "nrdl", "reimbursement",
                 "medicare", "price cut")),
    ("regulatory", ("获批", "批准", "受理", "上市申请", "附条件", "优先审评", "突破性疗法",
                    "approval", "approved", "approves", "filing", "complete response letter",
                    "regulatory approval",
                    "fda ok", "fda oks", "fda clearance", "wins fda approval")),
    ("clinical", ("iii期", "3期", "临床", "读出", "主要终点", "达到终点", "未达到",
                  "试验终止", "研究中止", "提前终止", "终止试验", "终止临床", "终止 iii",
                  "暂停", "头对头", "phase 3", "phase iii",
                  "topline", "primary endpoint", "readout", "halted", "discontinued",
                  "key trial", "succeeds in")),
    ("policy", ("指导原则", "法规", "合规", "备案", "新规", "监管新规", "guidance", "policy",
                "regulation",
                "pbm", "disclosure rule")),
    ("commercial", ("销售额", "营收", "财报", "出海", "裁员", "管线调整", "业务重组", "公司重组",
                    "revenue", "sales", "earnings", "layoff", "restructur",
                    "bankruptcy", "chapter 11", "ipo", "pbm", "cost cut", "cost-cutting",
                    "biosimilar")),
]

_DIMENSION_BY_EVENT = {
    "clinical": "D2",
    "regulatory": "D3",
    "payment": "D4",
    "deal": "D5",
    "commercial": "D5",
    "policy": "D6",
    # 冲突规则：无法判定时进 D6，不再默认落到疾病格局 D1。
    "science": "D6",
}

_GUIDELINE = ("指南", "共识", "guideline", "consensus")

# 显式的科学/疾病格局信号仍归 D1（仅当事件类型未匹配到其它规则时）。
_D1_SIGNALS = ("机制", "机理", "流行病学", "未满足需求", "标准治疗", "患者组织",
               "疾病负担", "病理", "mechanism", "epidemiology", "unmet need",
               "standard of care", "patient advocacy", "pathophysiology",
               "disease burden", "pathogenesis", "etiology")

_M5 = ("首个", "first-in-class", "first in class", "指南更新", "指南改写", "class effect",
       "撤市", "暂停", "提前终止", "监管规则", "集采规则", "医保规则改变", "推翻")
_M4 = ("获批", "批准", "approves", "approved", "主要终点", "primary endpoint", "医保目录",
       "纳入医保", "纳入指南", "指导原则", "1亿美元", "1亿美元", "$1 billion", "$1bn",
       "readout", "topline")
_M3 = ("iii期", "phase 3", "phase iii", "启动", "initiated", "早期", "受理",
       "人事", "任命", "appoint", "裁员",
       "bankruptcy", "chapter 11", "ipo")

# 注意：不要加入 nda / bla / ind / crl 这类三字母缩写，子串会误伤 standard、substantial 等常用词。
# 需要识别时，用带空格的完整形式，或改 _hit 为带词边界的正则。


_ASCII_ALNUM = re.compile(r"^[a-z0-9]+$")


def _hit(text: str, words: tuple[str, ...]) -> bool:
    """命中关键词。纯 ASCII 字母/数字词要求左词边界（license 可命中 licenses，
    filing 不再命中 profiling）；中文等其它词仍按子串匹配。"""
    for w in words:
        if w == "deal":
            # deal 太短，左边界不足以挡住 dealer/dealing，要求两侧都是边界；deals 复数仍命中。
            if re.search(r"(?<![a-z0-9])deals?(?![a-z0-9])", text):
                return True
        elif _ASCII_ALNUM.match(w):
            if re.search(r"(?<![a-z0-9])" + re.escape(w), text):
                return True
        elif w in text:
            return True
    return False


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
    if event_type == "science" and _hit(low, _D1_SIGNALS):
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
