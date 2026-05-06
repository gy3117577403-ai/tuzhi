from __future__ import annotations

from datetime import datetime, timezone


DATA_SOURCE_NOTICE = (
    "采购数据源仅支持 mock、本地报价表导入、官方开放平台、企业授权 API 或供应商授权接口；"
    "系统不提供绕过登录、验证码、风控或反爬限制的网页抓取能力。"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_platform_label(value: str | None) -> str:
    text = (value or "其他").strip()
    if text in {"淘宝", "京东", "1688", "其他"}:
        return text
    return "其他"


def public_source_config(config: dict) -> dict:
    blocked = {"api_key", "token", "secret", "authorization", "headers"}
    return {key: value for key, value in config.items() if key.lower() not in blocked}
