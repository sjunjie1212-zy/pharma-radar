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

# 格式示例中 "id" 与冒号之间留空格，避免与输入行计数（'"id":'）混淆。
PROMPT_HEAD = """你是医药行业情报编辑。给下面每条新闻写一句中文提炼，只回 JSON 数组，不要解释、不要代码块。

要求：
1. 每条一句话，整句总长 ≤30 个字符（汉字、字母、数字、空格、标点各计 1），高信息密度，不写形容词与套话。公司名过长时用简称或缩写。
2. 一句话说清 3W：Who（公司/机构/靶点/疾病）、What（发生了什么）、Why（为什么值得知道——给判断，不复述标题）。
3. 行业口径；不确定的数字不要编造。
4. 输出格式：[{"id" : "...", "title_zh" : "..."}]，条数与输入一致。

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
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
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
