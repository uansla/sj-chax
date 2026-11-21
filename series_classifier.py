"""Infer a product series from a phone model name when a source table omits it."""

from __future__ import annotations

import re


def _has_prefix(value: str, *prefixes: str) -> bool:
    value = value.casefold().lstrip()
    return any(value.startswith(prefix.casefold()) for prefix in prefixes)


def infer_series(brand: str, model: str) -> str:
    """Return a useful model-family label, preserving vendor sub-brands where known."""
    brand = (brand or "").strip()
    model = re.sub(r"\s+", " ", (model or "").strip())
    if not model:
        return brand

    brand_key = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", brand.casefold())
    text = model.casefold().lstrip()

    if brand_key in {"小米", "xiaomi", "mi"}:
        if _has_prefix(text, "小米红米", "xiaomi redmi", "redmi", "红米"):
            return "红米"
        if _has_prefix(text, "小米黑鲨", "黑鲨", "black shark"):
            return "黑鲨"
        if _has_prefix(text, "小米poco", "poco"):
            return "POCO"
        value = re.sub(r"^(?:小米|xiaomi|mi)\s*", "", text, flags=re.I)
        if re.match(r"mix", value, re.I):
            return "MIX"
        if re.match(r"(?:civi|cc\d)", value, re.I):
            return "Civi"
        if re.match(r"note", value, re.I):
            return "Note"
        if re.match(r"max", value, re.I):
            return "Max"
        if re.match(r"\d", value):
            return "小米数字系列"
        return brand or "小米"

    if brand_key in {"华为", "huawei"}:
        if _has_prefix(text, "荣耀", "honor"):
            return "荣耀"
        value = re.sub(r"^(?:华为|huawei)\s*", "", text, flags=re.I)
        if re.match(r"mate", value, re.I):
            return "Mate"
        if re.match(r"pura|p\s*\d", value, re.I):
            return "P / Pura"
        if re.match(r"nova", value, re.I):
            return "nova"
        if re.match(r"畅享", value):
            return "畅享"
        if re.match(r"麦芒", value):
            return "麦芒"
        return brand or "华为"

    if brand_key in {"oppo"}:
        value = re.sub(r"^oppo\s*", "", text, flags=re.I)
        for pattern, label in ((r"find", "Find"), (r"reno", "Reno"), (r"ace", "Ace"),
                               (r"a\s*\d", "A"), (r"k\s*\d", "K"),
                               (r"f\s*\d", "F"), (r"r\s*\d", "R")):
            if re.match(pattern, value, re.I):
                return label
        return brand

    if brand_key in {"vivo"}:
        value = re.sub(r"^vivo\s*", "", text, flags=re.I)
        if re.match(r"iqoo", value, re.I):
            return "iQOO"
        for pattern, label in ((r"x\s*\d", "X"), (r"s\s*\d", "S"),
                               (r"y\s*\d", "Y"), (r"v\s*\d", "V"),
                               (r"t\s*\d", "T")):
            if re.match(pattern, value, re.I):
                return label
        return brand

    if brand_key in {"三星", "samsung"}:
        value = re.sub(r"^(?:三星|samsung)\s*", "", text, flags=re.I)
        if re.match(r"(?:galaxy\s*)?(?:z\s*(?:fold|flip)|fold|flip)", value, re.I):
            return "Galaxy Z"
        if re.match(r"(?:galaxy\s*)?s\s*\d", value, re.I):
            return "Galaxy S"
        if re.match(r"(?:galaxy\s*)?note", value, re.I):
            return "Galaxy Note"
        for letter in ("a", "m", "f", "j"):
            if re.match(rf"(?:galaxy\s*)?{letter}\s*\d", value, re.I):
                return f"Galaxy {letter.upper()}"
        return brand

    if brand_key in {"苹果", "apple"}:
        if _has_prefix(text, "ipad"):
            return "iPad"
        if _has_prefix(text, "iphone"):
            return "iPhone"
        return brand

    if brand_key in {"荣耀", "honor"}:
        value = re.sub(r"^(?:荣耀|honor)\s*", "", text, flags=re.I)
        if re.match(r"magic", value, re.I):
            return "Magic"
        for pattern, label in ((r"v\s*\d", "V"), (r"x\s*\d", "X"),
                               (r"play", "Play"), (r"\d", "数字系列")):
            if re.match(pattern, value, re.I):
                return label
        return brand

    if brand_key in {"一加", "oneplus", "oneplus手机"}:
        value = re.sub(r"^(?:一加|oneplus)\s*", "", text, flags=re.I)
        if re.match(r"ace", value, re.I):
            return "Ace"
        if re.match(r"nord", value, re.I):
            return "Nord"
        if re.match(r"\d", value):
            return "数字系列"
        return brand

    if brand_key in {"真我", "realme"}:
        value = re.sub(r"^(?:真我|realme)\s*", "", text, flags=re.I)
        for pattern, label in ((r"gt", "GT"), (r"neo", "Neo"), (r"c\s*\d", "C"),
                               (r"q\s*\d", "Q"), (r"\d", "数字系列")):
            if re.match(pattern, value, re.I):
                return label
        return brand

    if brand_key in {"摩托罗拉", "motorola"}:
        value = re.sub(r"^(?:摩托罗拉|motorola|moto)\s*", "", text, flags=re.I)
        if re.match(r"razr", value, re.I):
            return "Razr"
        if re.match(r"edge", value, re.I):
            return "Edge"
        if re.match(r"g\s*\d", value, re.I):
            return "Moto G"
        return brand

    if brand_key in {"努比亚", "nubia"}:
        if _has_prefix(text, "红魔", "redmagic"):
            return "红魔"
        if re.match(r"(?:努比亚|nubia)\s*z\s*\d|z\s*\d", text, re.I):
            return "Z"
        return brand

    # Generic fallback: use the model's leading family token after removing its
    # brand prefix. This groups names such as M6/M7 under M and numeric families.
    value = text
    if brand:
        value = re.sub(r"^" + re.escape(brand.casefold()) + r"\s*", "", value, flags=re.I)
    value = re.sub(r"^(?:手机|机型)\s*", "", value)
    latin = re.match(r"([a-z]+)", value, re.I)
    if latin:
        token = latin.group(1)
        return token.upper() if len(token) <= 2 else token[:1].upper() + token[1:]
    cjk = re.match(r"([\u4e00-\u9fff]{1,3})", value)
    if cjk:
        return cjk.group(1)
    if re.match(r"\d", value):
        return "数字系列"
    return brand or "其他"
