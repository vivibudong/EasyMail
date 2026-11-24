from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

TRANSLATE_PROVIDERS: dict[str, dict[str, Any]] = {
    "free": {
        "id": "free",
        "label": "免费聚合翻译（默认：Google POST + 备用源自动降级）",
        "requires_api_key": False,
        "endpoint": "",
        "default_model": "",
        "models": [],
        "docs_url": "",
        "description": "免密钥开箱即用，自动分段并通过 POST 请求 Google 翻译，失败时自动降级到备用通道与 MyMemory。",
    },
    "deepl_free": {
        "id": "deepl_free",
        "label": "DeepL API Free（免费版每月 50 万字符）",
        "requires_api_key": True,
        "endpoint": "https://api-free.deepl.com/v2/translate",
        "default_model": "",
        "models": [],
        "docs_url": "https://www.deepl.com/zh/pro-api",
        "description": "高质量神经机器翻译，请填写 DeepL API Free 密钥（通常以 :fx 结尾）。",
    },
    "deepl_pro": {
        "id": "deepl_pro",
        "label": "DeepL API Pro（付费专业版）",
        "requires_api_key": True,
        "endpoint": "https://api.deepl.com/v2/translate",
        "default_model": "",
        "models": [],
        "docs_url": "https://www.deepl.com/zh/pro-api",
        "description": "使用 DeepL API Pro 正式密钥进行翻译。",
    },
    "deepseek": {
        "id": "deepseek",
        "label": "DeepSeek 官方 API（中文自然、性价比高）",
        "requires_api_key": True,
        "endpoint": "https://api.deepseek.com/chat/completions",
        "default_model": "deepseek-chat",
        "models": ["deepseek-chat"],
        "docs_url": "https://platform.deepseek.com/api_keys",
        "description": "使用 DeepSeek 官方 API 进行邮件翻译，国内与海外服务器均可稳定访问。",
    },
    "openai": {
        "id": "openai",
        "label": "OpenAI 官方 API",
        "requires_api_key": True,
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "default_model": "gpt-4o-mini",
        "models": ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4o"],
        "docs_url": "https://platform.openai.com/api-keys",
        "description": "使用 OpenAI 官方模型翻译长邮件，语义流畅自然。",
    },
    "siliconflow": {
        "id": "siliconflow",
        "label": "硅基流动 SiliconFlow",
        "requires_api_key": True,
        "endpoint": "https://api.siliconflow.cn/v1/chat/completions",
        "default_model": "Qwen/Qwen2.5-7B-Instruct",
        "models": ["Qwen/Qwen2.5-7B-Instruct", "deepseek-ai/DeepSeek-V3"],
        "docs_url": "https://cloud.siliconflow.cn/account/ak",
        "description": "使用硅基流动官方 API，支持 Qwen / DeepSeek 等开源模型。",
    },
    "google_cloud": {
        "id": "google_cloud",
        "label": "Google Cloud Translation API v2",
        "requires_api_key": True,
        "endpoint": "https://translation.googleapis.com/language/translate/v2",
        "default_model": "",
        "models": [],
        "docs_url": "https://cloud.google.com/translate/docs/setup",
        "description": "使用 Google Cloud 官方 Translation v2 API Key。",
    },
}


def normalize_translate_provider(provider: object) -> str:
    value = str(provider or "free").strip().lower()
    if value in TRANSLATE_PROVIDERS:
        return value
    return "free"


def normalize_translate_model(provider: str, model: object) -> str:
    spec = TRANSLATE_PROVIDERS.get(provider) or TRANSLATE_PROVIDERS["free"]
    allowed_models = spec.get("models") or []
    if not allowed_models:
        return ""
    value = str(model or "").strip()
    if value in allowed_models:
        return value
    return str(spec.get("default_model") or allowed_models[0])


def get_public_translate_providers() -> list[dict[str, Any]]:
    return [
        {
            "id": item["id"],
            "label": item["label"],
            "requires_api_key": bool(item["requires_api_key"]),
            "default_model": item["default_model"],
            "models": list(item["models"]),
            "docs_url": item["docs_url"],
            "description": item["description"],
        }
        for item in TRANSLATE_PROVIDERS.values()
    ]


def _clean_input_text(text: str, max_chars: int = 20000) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[\u200b\u200c\u200d\ufeff\u00ad]", "", cleaned)
    cleaned = re.sub(r"\n{4,}", "\n\n\n", cleaned)
    return cleaned.strip()[:max_chars]


def _split_text_chunks(text: str, max_chars: int = 1800) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current = ""

    def push_current() -> None:
        nonlocal current
        if current:
            chunks.append(current)
            current = ""

    paragraphs = text.split("\n\n")
    for para_index, paragraph in enumerate(paragraphs):
        piece = paragraph if para_index == 0 else "\n\n" + paragraph
        if len(current) + len(piece) <= max_chars:
            current += piece
            continue
        push_current()
        if len(paragraph) <= max_chars:
            current = paragraph
            continue

        # Split oversized paragraph by lines
        for line_index, line in enumerate(paragraph.split("\n")):
            line_piece = line if line_index == 0 else "\n" + line
            if len(current) + len(line_piece) <= max_chars:
                current += line_piece
                continue
            push_current()
            if len(line) <= max_chars:
                current = line
                continue

            # Split oversized line by sentence boundaries or hard slice
            sentences = re.split(r"(?<=[.!?。！？;；])\s+", line)
            for sentence in sentences:
                if not sentence:
                    continue
                if len(sentence) > max_chars:
                    push_current()
                    for offset in range(0, len(sentence), max_chars):
                        chunks.append(sentence[offset : offset + max_chars])
                elif not current:
                    current = sentence
                elif len(current) + 1 + len(sentence) <= max_chars:
                    current += " " + sentence
                else:
                    push_current()
                    current = sentence
        push_current()

    push_current()
    return [chunk for chunk in chunks if chunk.strip()]


def _read_http_error(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        body = ""
    if body:
        compact = re.sub(r"\s+", " ", body)[:240]
        return f"HTTP {exc.code}: {compact}"
    return f"HTTP {exc.code}: {exc.reason}"


def _translate_google_free(text: str) -> str:
    chunks = _split_text_chunks(text, max_chars=1800)
    translated_chunks: list[str] = []
    for chunk in chunks:
        query = urllib.parse.urlencode(
            {
                "client": "gtx",
                "sl": "auto",
                "tl": "zh-CN",
                "dt": "t",
            }
        )
        body = urllib.parse.urlencode({"q": chunk}).encode("utf-8")
        request = urllib.request.Request(
            f"https://translate.googleapis.com/translate_a/single?{query}",
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise ValueError(f"Google 翻译返回错误 ({_read_http_error(exc)})") from exc
        try:
            payload = json.loads(raw)
        except Exception as exc:
            raise ValueError("Google 翻译返回非 JSON 响应（可能触发风控）") from exc
        if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
            raise ValueError("Google 翻译返回格式异常")
        parts: list[str] = []
        for item in payload[0]:
            if isinstance(item, list) and item and item[0] is not None:
                parts.append(str(item[0]))
        part_text = "".join(parts)
        if not part_text.strip():
            raise ValueError("Google 翻译结果为空")
        translated_chunks.append(part_text)
    return "\n\n".join(translated_chunks).strip()


def _translate_google_clients5_free(text: str) -> str:
    chunks = _split_text_chunks(text, max_chars=1800)
    translated_chunks: list[str] = []
    for chunk in chunks:
        body = urllib.parse.urlencode({"q": chunk}).encode("utf-8")
        request = urllib.request.Request(
            "https://clients5.google.com/translate_a/t?client=dict-chrome-ex&sl=auto&tl=zh-CN",
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise ValueError(f"Google 备用通道返回错误 ({_read_http_error(exc)})") from exc
        try:
            payload = json.loads(raw)
        except Exception as exc:
            raise ValueError("Google 备用通道返回非 JSON 响应") from exc
        part_text = ""
        if isinstance(payload, list) and payload:
            first = payload[0]
            if isinstance(first, list) and first:
                part_text = str(first[0] or "")
            elif isinstance(first, str):
                part_text = first
        if not part_text.strip():
            raise ValueError("Google 备用通道翻译结果为空")
        translated_chunks.append(part_text)
    return "\n\n".join(translated_chunks).strip()


def _translate_mymemory_free(text: str) -> str:
    chunks = _split_text_chunks(text, max_chars=450)
    translated_chunks: list[str] = []
    for chunk in chunks:
        query = urllib.parse.urlencode({"q": chunk, "langpair": "Autodetect|zh-CN"})
        request = urllib.request.Request(
            f"https://api.mymemory.translated.net/get?{query}",
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise ValueError(f"MyMemory 返回错误 ({_read_http_error(exc)})") from exc
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("MyMemory 返回格式异常")
        status_code = int(data.get("responseStatus") or 0)
        if status_code and status_code != 200:
            detail = str(data.get("responseDetails") or f"status={status_code}")
            raise ValueError(f"MyMemory 错误: {detail}")
        response_data = data.get("responseData")
        part_text = str(response_data.get("translatedText") or "") if isinstance(response_data, dict) else ""
        if not part_text.strip():
            raise ValueError("MyMemory 翻译结果为空")
        translated_chunks.append(part_text)
    return "\n\n".join(translated_chunks).strip()


def _translate_free_chain(text: str) -> tuple[str, str]:
    errors: list[str] = []
    chain = [
        ("free:google", _translate_google_free),
        ("free:google_alt", _translate_google_clients5_free),
        ("free:mymemory", _translate_mymemory_free),
    ]
    for provider_name, handler in chain:
        try:
            result = handler(text)
            if result:
                return result, provider_name
        except Exception as exc:
            errors.append(f"{provider_name}: {exc}")
    raise ValueError("所有免费翻译源均失败；" + " | ".join(errors))


def _translate_deepl(text: str, endpoint: str, api_key: str) -> str:
    chunks = _split_text_chunks(text, max_chars=3000)
    payload_bytes = json.dumps(
        {"text": chunks, "target_lang": "ZH"},
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload_bytes,
        headers={
            "Authorization": f"DeepL-Auth-Key {api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise ValueError(f"DeepL API 返回错误 ({_read_http_error(exc)})") from exc
    data = json.loads(raw)
    translations = data.get("translations") if isinstance(data, dict) else None
    if not isinstance(translations, list) or not translations:
        raise ValueError("DeepL API 返回格式异常")
    parts = [str(item.get("text") or "") for item in translations if isinstance(item, dict)]
    result = "\n\n".join(part for part in parts if part.strip()).strip()
    if not result:
        raise ValueError("DeepL 翻译结果为空")
    return result


def _translate_google_cloud(text: str, endpoint: str, api_key: str) -> str:
    chunks = _split_text_chunks(text, max_chars=3000)
    payload_bytes = json.dumps(
        {"q": chunks, "target": "zh-CN", "format": "text"},
        ensure_ascii=False,
    ).encode("utf-8")
    url = f"{endpoint}?key={urllib.parse.quote(api_key, safe='')}"
    request = urllib.request.Request(
        url,
        data=payload_bytes,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise ValueError(f"Google Cloud Translation 返回错误 ({_read_http_error(exc)})") from exc
    data = json.loads(raw)
    translations = (
        data.get("data", {}).get("translations")
        if isinstance(data, dict) and isinstance(data.get("data"), dict)
        else None
    )
    if not isinstance(translations, list) or not translations:
        raise ValueError("Google Cloud Translation 返回格式异常")
    parts = [str(item.get("translatedText") or "") for item in translations if isinstance(item, dict)]
    result = "\n\n".join(part for part in parts if part.strip()).strip()
    if not result:
        raise ValueError("Google Cloud Translation 结果为空")
    return result


def _translate_openai_compatible(text: str, endpoint: str, api_key: str, model: str) -> str:
    chunks = _split_text_chunks(text, max_chars=4000)
    translated_chunks: list[str] = []
    system_prompt = (
        "You are a professional email translator. Translate the user's email content into clear, "
        "natural Simplified Chinese (简体中文). Preserve line breaks, URLs, email addresses, "
        "verification codes, and numbers accurately. Output ONLY the translated text without "
        "any explanation, prefix, or markdown fences."
    )
    for chunk in chunks:
        payload_bytes = json.dumps(
            {
                "model": model,
                "temperature": 0.1,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": chunk},
                ],
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=payload_bytes,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise ValueError(f"LLM 翻译接口返回错误 ({_read_http_error(exc)})") from exc
        data = json.loads(raw)
        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices:
            raise ValueError("LLM 翻译接口返回格式异常")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = str(message.get("content") or "").strip() if isinstance(message, dict) else ""
        if not content:
            raise ValueError("LLM 翻译结果为空")
        translated_chunks.append(content)
    return "\n\n".join(translated_chunks).strip()


def translate_text_to_chinese(
    text: str,
    *,
    provider: str = "free",
    api_key: str = "",
    model: str = "",
    fallback_to_free: bool = True,
) -> tuple[str, str]:
    cleaned = _clean_input_text(text)
    if not cleaned:
        raise ValueError("正文为空，无法翻译")

    normalized_provider = normalize_translate_provider(provider)
    spec = TRANSLATE_PROVIDERS[normalized_provider]

    if normalized_provider == "free":
        return _translate_free_chain(cleaned)

    key = api_key.strip()
    if not key:
        if fallback_to_free:
            return _translate_free_chain(cleaned)
        raise ValueError(f"已选择 {spec['label']}，但尚未配置 API Key")

    endpoint = str(spec["endpoint"])
    chosen_model = normalize_translate_model(normalized_provider, model)

    try:
        if normalized_provider in {"deepl_free", "deepl_pro"}:
            return _translate_deepl(cleaned, endpoint, key), normalized_provider
        if normalized_provider == "google_cloud":
            return _translate_google_cloud(cleaned, endpoint, key), normalized_provider
        if normalized_provider in {"openai", "deepseek", "siliconflow"}:
            return _translate_openai_compatible(cleaned, endpoint, key, chosen_model), normalized_provider
        raise ValueError(f"不支持的翻译服务: {normalized_provider}")
    except Exception as custom_exc:
        if fallback_to_free:
            try:
                translated, fallback_provider = _translate_free_chain(cleaned)
                return translated, f"{fallback_provider}(降级)"
            except Exception as fallback_exc:
                raise ValueError(
                    f"{normalized_provider} 失败: {custom_exc}；降级免费源也失败: {fallback_exc}"
                ) from custom_exc
        raise
