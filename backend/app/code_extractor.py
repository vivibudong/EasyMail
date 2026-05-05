from __future__ import annotations

import re
from dataclasses import dataclass


CODE_KEYWORDS = [
    "验证码",
    "校验码",
    "动态码",
    "安全码",
    "验证代码",
    "一次性代码",
    "verification",
    "verify",
    "code",
    "otp",
    "passcode",
    "security code",
]

NEGATIVE_KEYWORDS = [
    "订单",
    "order",
    "invoice",
    "金额",
    "price",
    "端口",
    "port",
    "ip",
    "request id",
]


@dataclass
class CodeCandidate:
    code: str
    confidence: float
    source: str
    matched_rule: str
    context: str


def _normalize_text(value: str) -> str:
    text = value.replace("\r", "\n")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _mask_context(text: str, start: int, end: int, radius: int = 60) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return text[left:right].strip()


def _looks_like_noise(code: str, context: str) -> bool:
    lowered = context.lower()
    if re.fullmatch(r"\d{6}[A-Z]{1,2}", code) and any(word in lowered for word in ("openai", "chatgpt")):
        return True
    if re.fullmatch(r"[A-Z]{4,8}", code):
        return True
    if len(code) >= 9:
        return True
    if re.fullmatch(r"20\d{2}", code):
        return True
    if re.fullmatch(r"\d{1,3}", code):
        return True
    if any(word in lowered for word in NEGATIVE_KEYWORDS):
        return True
    if re.search(r"\d+\.\d+\.\d+\.\d+", context):
        return True
    return False


def _score_candidate(code: str, context: str, source: str, rule: str) -> float:
    lowered = context.lower()
    score = 0.35
    if source == "subject":
        score += 0.12
    if any(keyword in lowered for keyword in CODE_KEYWORDS):
        score += 0.36
    if re.search(r"(验证码|校验码|动态码|安全码|code|otp|passcode)\s*[:：是为\-]?\s*" + re.escape(code), context, re.IGNORECASE):
        score += 0.18
    if code.isdigit() and 4 <= len(code) <= 8:
        score += 0.08
    if re.search(r"[A-Z]", code) and re.search(r"\d", code):
        score += 0.08
    if rule == "keyword_prefix":
        score += 0.1
    if any(word in lowered for word in NEGATIVE_KEYWORDS):
        score -= 0.25
    return max(0.0, min(0.99, score))


def extract_verification_codes(subject: str = "", from_text: str = "", body_text: str = "") -> list[dict]:
    fields = [
        ("subject", _normalize_text(subject)),
        ("body", _normalize_text(body_text)),
    ]
    candidates: list[CodeCandidate] = []
    openai_pattern = re.compile(
        r"(?:openai|chatgpt|temporary\s+chatgpt\s+login\s+code)[^0-9]{0,80}(\d{6})(?=[A-Za-z\s.,:;!?<]|$)",
        re.IGNORECASE,
    )
    keyword_pattern = re.compile(
        r"(验证码|校验码|动态码|安全码|验证代码|一次性代码|verification code|security code|passcode|otp|code)"
        r"[^A-Za-z0-9]{0,24}"
        r"([A-Z0-9]{4,8}|\d{4,8})",
        re.IGNORECASE,
    )
    loose_pattern = re.compile(r"(?<![A-Za-z0-9])([A-Z0-9]{4,8}|\d{4,8})(?![A-Za-z0-9])")

    for source, text in fields:
        if not text:
            continue
        for match in openai_pattern.finditer(text):
            code = match.group(1).strip()
            context = _mask_context(text, match.start(), match.end())
            if _looks_like_noise(code, context):
                continue
            candidates.append(
                CodeCandidate(
                    code=code,
                    confidence=0.99,
                    source=source,
                    matched_rule="openai_login_code",
                    context=context,
                )
            )
        for match in keyword_pattern.finditer(text):
            code = match.group(2).strip().upper()
            context = _mask_context(text, match.start(), match.end())
            if _looks_like_noise(code, context):
                continue
            candidates.append(
                CodeCandidate(
                    code=code,
                    confidence=_score_candidate(code, context, source, "keyword_prefix"),
                    source=source,
                    matched_rule="keyword_prefix",
                    context=context,
                )
            )
        if any(keyword in text.lower() for keyword in CODE_KEYWORDS):
            for match in loose_pattern.finditer(text):
                code = match.group(1).strip().upper()
                context = _mask_context(text, match.start(), match.end())
                if _looks_like_noise(code, context):
                    continue
                candidates.append(
                    CodeCandidate(
                        code=code,
                        confidence=_score_candidate(code, context, source, "near_keyword"),
                        source=source,
                        matched_rule="near_keyword",
                        context=context,
                    )
                )

    best_by_code: dict[str, CodeCandidate] = {}
    for item in candidates:
        existing = best_by_code.get(item.code)
        if existing is None or item.confidence > existing.confidence:
            best_by_code[item.code] = item

    ranked = sorted(best_by_code.values(), key=lambda item: (-item.confidence, item.code))
    return [
        {
            "code": item.code,
            "confidence": round(item.confidence, 2),
            "source": item.source,
            "matched_rule": item.matched_rule,
            "context": item.context,
            "from": from_text,
        }
        for item in ranked[:5]
        if item.confidence >= 0.55
    ]
