#!/usr/bin/env python3
"""
Fetch newsletter emails from an IMAP mailbox and filter them by sources.yaml.

Secrets are read from environment variables configured in config.yaml.
The script prints JSON to stdout and never writes cache files by itself.
"""
from __future__ import annotations

import argparse
import html
import imaplib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from email import policy
from email.header import decode_header, make_header
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from _runtime import ensure_modules

ensure_modules(["yaml"])

try:
    import yaml
except ImportError:
    print("错误：未安装 PyYAML。请在仓库根目录运行：.venv/bin/python -m pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)


SKILL_ROOT = Path(__file__).resolve().parent.parent
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class ConfigError(Exception):
    pass


def load_timezone(name: str):
    try:
        return ZoneInfo(name)
    except Exception:
        return timezone(timedelta(hours=8))


def default_config_path() -> Path:
    local_config = SKILL_ROOT / "config.yaml"
    if local_config.exists():
        return local_config
    return SKILL_ROOT / "config.example.yaml"


def default_sources_path() -> Path:
    local_sources = SKILL_ROOT / "sources.yaml"
    if local_sources.exists():
        return local_sources
    return SKILL_ROOT / "sources.example.yaml"


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def parse_date(date_str: str, tz) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=tz)


def imap_date(dt: datetime) -> str:
    return f"{dt.day:02d}-{MONTHS[dt.month - 1]}-{dt.year}"


def decode_header_value(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def normalize_email(value: Optional[str]) -> str:
    _, address = parseaddr(decode_header_value(value))
    return address.lower().strip()


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def html_to_text(content: str) -> str:
    content = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", content)
    content = re.sub(r"(?i)<br\s*/?>", "\n", content)
    content = re.sub(r"(?i)</p\s*>", "\n\n", content)
    content = re.sub(r"(?s)<[^>]+>", " ", content)
    return clean_text(html.unescape(content))


def message_text(message) -> str:
    plain_parts = []
    html_parts = []

    if message.is_multipart():
        parts = message.walk()
    else:
        parts = [message]

    for part in parts:
        disposition = part.get_content_disposition()
        if disposition == "attachment":
            continue

        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue

        try:
            content = part.get_content()
        except Exception:
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            content = payload.decode(charset, errors="replace")

        if content_type == "text/plain":
            plain_parts.append(clean_text(content))
        else:
            html_parts.append(html_to_text(content))

    text = "\n\n".join(part for part in plain_parts if part).strip()
    if text:
        return text
    return "\n\n".join(part for part in html_parts if part).strip()


def message_date_matches(message, target_date: datetime, tz) -> bool:
    raw_date = message.get("Date")
    if not raw_date:
        return True

    try:
        parsed = parsedate_to_datetime(raw_date)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(tz).date() == target_date.date()
    except Exception:
        return True


def build_source_index(sources_config: dict) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = {}
    for source in sources_config.get("email", []):
        address = normalize_email(source.get("from"))
        if not address:
            continue
        index.setdefault(address, []).append(source)
    return index


def match_source(source_index: dict[str, list[dict]], from_header: str, subject: str) -> dict | None:
    sender = normalize_email(from_header)
    candidates = source_index.get(sender, [])
    if not candidates:
        return None

    lowered_subject = subject.lower()
    fallback = None
    for source in candidates:
        needle = source.get("subject_contains")
        if needle and str(needle).lower() in lowered_subject:
            return source
        if not needle and fallback is None:
            fallback = source
    return fallback


def resolve_imap_config(config: dict, args) -> dict:
    email_config = config.get("email", {})
    imap_config = email_config.get("imap", {})

    host = args.host or imap_config.get("host")
    port = int(args.port or imap_config.get("port") or 993)
    use_ssl = args.ssl if args.ssl is not None else bool(imap_config.get("ssl", True))
    folder = args.folder or imap_config.get("folder") or "INBOX"
    username_env = args.username_env or imap_config.get("username_env") or "AI_NEWS_IMAP_USERNAME"
    password_env = args.password_env or imap_config.get("password_env") or "AI_NEWS_IMAP_PASSWORD"
    max_body_chars = int(args.max_body_chars or imap_config.get("max_body_chars") or 20000)

    username = os.environ.get(username_env)
    password = os.environ.get(password_env)

    missing = []
    if not host:
        missing.append("email.imap.host")
    if not username:
        missing.append(f"environment variable {username_env}")
    if not password:
        missing.append(f"environment variable {password_env}")
    if missing:
        raise ConfigError("Missing IMAP configuration: " + ", ".join(missing))

    return {
        "host": host,
        "port": port,
        "use_ssl": use_ssl,
        "folder": folder,
        "username": username,
        "password": password,
        "username_env": username_env,
        "password_env": password_env,
        "max_body_chars": max_body_chars,
    }


def connect_imap(imap_config: dict):
    if imap_config["use_ssl"]:
        client = imaplib.IMAP4_SSL(imap_config["host"], imap_config["port"], timeout=30)
    else:
        client = imaplib.IMAP4(imap_config["host"], imap_config["port"], timeout=30)
    client.login(imap_config["username"], imap_config["password"])
    return client


def parse_fetch_response(data) -> bytes | None:
    for item in data:
        if isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], bytes):
            return item[1]
    return None


def fetch_messages(client, target_date: datetime, tz, source_index: dict[str, list[dict]], max_body_chars: int, limit: Optional[int]) -> list[dict]:
    next_date = target_date + timedelta(days=1)
    criteria = ("SINCE", imap_date(target_date), "BEFORE", imap_date(next_date))
    status, data = client.search(None, *criteria)
    if status != "OK":
        raise ConfigError("IMAP search failed")

    message_ids = data[0].split() if data and data[0] else []
    if limit is not None:
        message_ids = message_ids[:limit]

    entries = []
    for message_id in message_ids:
        status, fetch_data = client.fetch(message_id, "(BODY.PEEK[])")
        if status != "OK":
            continue

        raw_message = parse_fetch_response(fetch_data)
        if not raw_message:
            continue

        message = BytesParser(policy=policy.default).parsebytes(raw_message)
        subject = decode_header_value(message.get("Subject"))
        from_header = decode_header_value(message.get("From"))
        source = match_source(source_index, from_header, subject)
        if not source:
            continue
        if not message_date_matches(message, target_date, tz):
            continue

        body = message_text(message)
        if max_body_chars > 0:
            body = body[:max_body_chars]

        entries.append({
            "source": source.get("name"),
            "category": source.get("category", ""),
            "from": normalize_email(from_header),
            "from_name": parseaddr(from_header)[0],
            "subject": subject,
            "date": decode_header_value(message.get("Date")),
            "message_id": decode_header_value(message.get("Message-ID")),
            "body": body,
            "summary": body[:1000],
        })

    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch newsletter emails from IMAP for a given date")
    parser.add_argument("--date", default=None, help="Target date YYYY-MM-DD (default: yesterday)")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    parser.add_argument("--sources", default=None, help="Path to sources.yaml")
    parser.add_argument("--timezone", default=None, help="IANA timezone override")
    parser.add_argument("--host", default=None, help="IMAP host override")
    parser.add_argument("--port", default=None, help="IMAP port override")
    parser.add_argument("--folder", default=None, help="IMAP folder/mailbox override")
    parser.add_argument("--username-env", default=None, help="Environment variable containing IMAP username")
    parser.add_argument("--password-env", default=None, help="Environment variable containing IMAP password/app password")
    parser.add_argument("--max-body-chars", default=None, help="Maximum characters of body text per message")
    parser.add_argument("--limit", type=int, default=None, help="Limit messages fetched after IMAP date search")
    parser.add_argument("--ssl", dest="ssl", action="store_true", default=None, help="Use IMAP over SSL")
    parser.add_argument("--no-ssl", dest="ssl", action="store_false", help="Use plain IMAP")
    args = parser.parse_args()

    config_path = Path(args.config).expanduser() if args.config else default_config_path()
    sources_path = Path(args.sources).expanduser() if args.sources else default_sources_path()

    config = load_yaml(config_path)
    sources_config = load_yaml(sources_path)
    settings = config.get("settings", {})
    tz = load_timezone(args.timezone or settings.get("timezone", "Asia/Shanghai"))

    if args.date:
        target_date = parse_date(args.date, tz)
    else:
        now = datetime.now(tz=tz)
        target_date = now - timedelta(days=1)

    source_index = build_source_index(sources_config)
    if not source_index:
        print(json.dumps({
            "date": target_date.strftime("%Y-%m-%d"),
            "entries": [],
            "error": "No email sources configured",
        }, ensure_ascii=False, indent=2))
        return 0

    try:
        imap_config = resolve_imap_config(config, args)
        client = connect_imap(imap_config)
        try:
            status, _ = client.select(imap_config["folder"], readonly=True)
            if status != "OK":
                raise ConfigError(f"Unable to select IMAP folder: {imap_config['folder']}")
            entries = fetch_messages(
                client,
                target_date,
                tz,
                source_index,
                imap_config["max_body_chars"],
                args.limit,
            )
        finally:
            try:
                client.logout()
            except Exception:
                pass
    except Exception as exc:
        print(json.dumps({
            "date": target_date.strftime("%Y-%m-%d"),
            "entries": [],
            "error": str(exc),
        }, ensure_ascii=False, indent=2))
        return 1

    output = {
        "date": target_date.strftime("%Y-%m-%d"),
        "mode": "imap",
        "entries": entries,
        "stats": {
            "total_entries": len(entries),
            "sources_with_entries": len({entry["source"] for entry in entries}),
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
