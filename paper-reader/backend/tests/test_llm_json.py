"""LLMClient._parse_json_object 的稳健解析测试（无需网络）。"""

from app.services.llm import LLMClient


def test_parses_plain_json():
    assert LLMClient._parse_json_object('{"a": 1}') == {"a": 1}


def test_strips_markdown_fence():
    raw = '```json\n{"one_liner": "x", "keywords": ["a"]}\n```'
    assert LLMClient._parse_json_object(raw) == {"one_liner": "x", "keywords": ["a"]}


def test_salvages_object_with_surrounding_prose():
    # 模型偶发在JSON前后夹带说明文字时，仍能截取最外层对象
    raw = '好的，这是结果：\n{"method": {"content": "步骤A"}}\n以上。'
    assert LLMClient._parse_json_object(raw) == {"method": {"content": "步骤A"}}


def test_rejects_non_object():
    assert LLMClient._parse_json_object("[1, 2, 3]") is None


def test_rejects_unrecoverable_text():
    assert LLMClient._parse_json_object("这不是JSON") is None
