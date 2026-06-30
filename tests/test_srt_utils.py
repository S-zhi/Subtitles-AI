"""SRT 读写工具单测。"""

from __future__ import annotations

from src.core.srt_utils import (
    Subtitle,
    format_timestamp,
    parse_srt,
    parse_timestamp,
    write_srt,
)


def test_format_timestamp_basic():
    assert format_timestamp(0) == "00:00:00,000"
    assert format_timestamp(1.5) == "00:00:01,500"
    assert format_timestamp(3661.123) == "01:01:01,123"


def test_format_timestamp_negative_clamped():
    assert format_timestamp(-5) == "00:00:00,000"


def test_parse_timestamp_comma_and_dot():
    assert parse_timestamp("00:00:01,500") == 1.5
    assert parse_timestamp("00:00:01.500") == 1.5
    assert parse_timestamp("01:01:01,123") == 3661.123


def test_roundtrip(tmp_path):
    subs = [
        Subtitle(1, 0.0, 1.5, "Hello"),
        Subtitle(2, 1.5, 3.0, "World"),
    ]
    p = tmp_path / "x.srt"
    write_srt(subs, p)
    parsed = parse_srt(p)
    assert len(parsed) == 2
    assert parsed[0].text == "Hello"
    assert parsed[1].start == 1.5
    assert parsed[1].end == 3.0


def test_write_reindexes(tmp_path):
    # 传入乱序 index，写出后应重排为 1,2
    subs = [Subtitle(99, 0, 1, "a"), Subtitle(7, 1, 2, "b")]
    p = tmp_path / "x.srt"
    write_srt(subs, p)
    content = p.read_text(encoding="utf-8")
    assert content.startswith("1\n")
    assert "\n2\n" in content


def test_parse_multiline_text(tmp_path):
    p = tmp_path / "x.srt"
    p.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\n原文\n译文\n",
        encoding="utf-8",
    )
    subs = parse_srt(p)
    assert subs[0].text == "原文\n译文"


def test_parse_missing_index(tmp_path):
    # 没有序号行，只有时间行 + 文本
    p = tmp_path / "x.srt"
    p.write_text("00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    subs = parse_srt(p)
    assert len(subs) == 1
    assert subs[0].text == "hi"


def test_parse_empty(tmp_path):
    p = tmp_path / "x.srt"
    p.write_text("", encoding="utf-8")
    assert parse_srt(p) == []
