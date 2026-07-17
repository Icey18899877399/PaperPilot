from __future__ import annotations

import json
import re
import zipfile
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any

import httpx
from pypdf import PdfReader

from app.core.config import Settings
from app.models.schemas import PaperChunk


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if value:
            self.parts.append(value)


class MinerUParseError(RuntimeError):
    pass


class PaperParser:
    """PDF parsing boundary.

    MinerU is used when MINERU_API_URL is configured. Its ZIP output is kept
    under data/assets/<paper_id>, while content_list.json is normalized into
    the same chunks consumed by the knowledge base and agents.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    async def parse(self, paper_id: str, path: Path) -> tuple[int, list[PaperChunk]]:
        if self.settings.mineru_api_url:
            return await self._parse_with_mineru(paper_id, path)
        return self._parse_with_pypdf(paper_id, path)

    async def _parse_with_mineru(
        self, paper_id: str, path: Path
    ) -> tuple[int, list[PaperChunk]]:
        headers = {}
        if self.settings.mineru_api_token:
            headers["Authorization"] = f"Bearer {self.settings.mineru_api_token}"

        endpoint = self.settings.mineru_api_url.rstrip("/") + "/file_parse"
        form_data = {
            "lang_list": self.settings.mineru_language,
            "backend": self.settings.mineru_backend,
            "parse_method": "auto",
            "formula_enable": "true",
            "table_enable": "true",
            "return_md": "true",
            "return_middle_json": "false",
            "return_model_output": "false",
            "return_content_list": "true",
            "return_images": "true",
            "response_format_zip": "true",
            "return_original_file": "false",
        }
        timeout = httpx.Timeout(
            connect=10,
            read=self.settings.mineru_timeout_seconds,
            write=300,
            pool=30,
        )
        # MinerU is normally a local service. Ignoring HTTP(S)_PROXY prevents
        # localhost requests from being sent to a system proxy and returning 502.
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            trust_env=False,
        ) as client:
            with path.open("rb") as source:
                response = await client.post(
                    endpoint,
                    headers=headers,
                    data=form_data,
                    files=[("files", (path.name, source, "application/pdf"))],
                )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text[:500].strip()
            raise MinerUParseError(
                f"MinerU解析失败（HTTP {response.status_code}）：{detail or '无错误详情'}"
            ) from exc

        content_type = response.headers.get("content-type", "").lower()
        if "zip" in content_type or response.content.startswith(b"PK"):
            return self._parse_mineru_zip(paper_id, response.content)

        try:
            payload = response.json()
        except ValueError as exc:
            raise MinerUParseError(
                f"MinerU返回了无法识别的内容类型：{content_type or 'unknown'}"
            ) from exc
        items = self._find_content_items(payload)
        if not items:
            raise MinerUParseError("MinerU响应中没有找到content_list")
        return self._normalize_mineru_items(paper_id, items, None, None)

    def _parse_mineru_zip(
        self, paper_id: str, payload: bytes
    ) -> tuple[int, list[PaperChunk]]:
        asset_root = self.settings.assets_dir / paper_id
        asset_root.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(BytesIO(payload)) as archive:
                for member in archive.infolist():
                    member_path = PurePosixPath(member.filename)
                    if member_path.is_absolute() or ".." in member_path.parts:
                        raise MinerUParseError(
                            f"拒绝解压不安全的MinerU ZIP条目：{member.filename}"
                        )
                    target = asset_root.joinpath(*member_path.parts).resolve()
                    resolved_root = asset_root.resolve()
                    if target != resolved_root and resolved_root not in target.parents:
                        raise MinerUParseError(
                            f"拒绝解压越界的MinerU ZIP条目：{member.filename}"
                        )
                    if member.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, target.open("wb") as destination:
                        destination.write(source.read())
        except zipfile.BadZipFile as exc:
            raise MinerUParseError("MinerU返回的ZIP文件已损坏") from exc

        content_files = sorted(asset_root.rglob("content_list.json"))
        content_files.extend(sorted(asset_root.rglob("*_content_list.json")))
        using_v2 = False
        if not content_files:
            content_files = sorted(asset_root.rglob("content_list_v2.json"))
            content_files.extend(sorted(asset_root.rglob("*_content_list_v2.json")))
            using_v2 = True
        if not content_files:
            raise MinerUParseError("MinerU ZIP中没有找到content_list.json")

        content_file = content_files[0]
        data = json.loads(content_file.read_text(encoding="utf-8"))
        items = self._flatten_v2(data) if using_v2 else self._find_content_items(data)
        if not items:
            raise MinerUParseError("MinerU content_list为空")
        return self._normalize_mineru_items(
            paper_id,
            items,
            asset_root,
            content_file.parent,
        )

    def _parse_with_pypdf(self, paper_id: str, path: Path) -> tuple[int, list[PaperChunk]]:
        reader = PdfReader(str(path))
        chunks: list[PaperChunk] = []
        for page_number, page in enumerate(reader.pages, start=1):
            content = (page.extract_text() or "").strip()
            if not content:
                continue
            for index, block in enumerate(self._split(content), start=1):
                chunks.append(
                    PaperChunk(
                        chunk_id=f"{paper_id}-p{page_number}-c{index}",
                        paper_id=paper_id,
                        page=page_number,
                        content=block,
                        metadata={"parser": "pypdf-fallback"},
                    )
                )
        return len(reader.pages), chunks

    @staticmethod
    def _split(text: str, size: int = 900) -> list[str]:
        return [text[start : start + size] for start in range(0, len(text), size)]

    @classmethod
    def _find_content_items(cls, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
            return payload
        if not isinstance(payload, dict):
            return []
        for key in ("content_list", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        for value in payload.values():
            found = cls._find_content_items(value)
            if found:
                return found
        return []

    @staticmethod
    def _flatten_v2(payload: Any) -> list[dict[str, Any]]:
        pages = payload if isinstance(payload, list) else payload.get("pages", [])
        result: list[dict[str, Any]] = []
        for page in pages:
            if not isinstance(page, dict):
                continue
            blocks = page.get("content") or page.get("blocks") or []
            if not isinstance(blocks, list):
                continue
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                normalized = dict(block)
                normalized.setdefault("page_idx", page.get("page_idx", 0))
                result.append(normalized)
        return result

    def _normalize_mineru_items(
        self,
        paper_id: str,
        items: list[dict[str, Any]],
        asset_root: Path | None,
        content_dir: Path | None,
    ) -> tuple[int, list[PaperChunk]]:
        chunks: list[PaperChunk] = []
        max_page = 0
        for index, item in enumerate(items, start=1):
            page = self._page_number(item)
            max_page = max(max_page, page)
            raw_type = str(item.get("type") or "text").lower()
            kind = self._normalize_kind(raw_type)
            content, structured = self._content_for_item(kind, item)
            if not content:
                continue
            resource_url = self._resource_url(
                paper_id,
                item.get("img_path"),
                asset_root,
                content_dir,
            )
            bbox = self._bbox(item.get("bbox"))
            metadata: dict[str, Any] = {
                "parser": "mineru",
                "raw_type": raw_type,
                **structured,
            }
            if item.get("text_level") is not None:
                metadata["text_level"] = item["text_level"]
            if item.get("img_path"):
                metadata["img_path"] = item["img_path"]
            chunks.append(
                PaperChunk(
                    chunk_id=f"{paper_id}-m{index}",
                    paper_id=paper_id,
                    page=page,
                    kind=kind,
                    content=content,
                    resource_url=resource_url,
                    bbox=bbox,
                    metadata=metadata,
                )
            )
        return max_page, chunks

    @staticmethod
    def _page_number(item: dict[str, Any]) -> int:
        if "page_idx" in item:
            try:
                return max(1, int(item["page_idx"]) + 1)
            except (TypeError, ValueError):
                return 1
        try:
            return max(1, int(item.get("page", 1)))
        except (TypeError, ValueError):
            return 1

    @staticmethod
    def _normalize_kind(raw_type: str) -> str:
        aliases = {
            "equation": "equation",
            "interline_equation": "equation",
            "inline_equation": "equation",
            "formula": "equation",
            "image": "image",
            "chart": "chart",
            "table": "table",
            "code": "code",
            "list": "list",
        }
        return aliases.get(raw_type, "text")

    @classmethod
    def _content_for_item(
        cls, kind: str, item: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        text = cls._to_text(item.get("text") or item.get("content"))
        if kind in {"image", "chart"}:
            captions = cls._to_text(item.get("image_caption"))
            footnotes = cls._to_text(item.get("image_footnote"))
            label = "图表" if kind == "chart" else "图片"
            body = "\n".join(value for value in (captions, footnotes, text) if value)
            return f"[{label}] {body or '该页包含一项视觉内容'}", {
                "caption": captions,
                "footnote": footnotes,
            }
        if kind == "table":
            caption = cls._to_text(item.get("table_caption"))
            footnote = cls._to_text(item.get("table_footnote"))
            table_html = cls._to_text(item.get("table_body"), preserve_html=True)
            table_text = cls._html_to_text(table_html)
            body = "\n".join(
                value for value in (caption, table_text, footnote, text) if value
            )
            return f"[表格] {body or '该页包含一张表格'}", {
                "caption": caption,
                "footnote": footnote,
                "table_html": table_html,
                "table_text": table_text,
            }
        if kind == "equation":
            latex = text or cls._to_text(item.get("latex"))
            return (f"[公式] {latex}" if latex else "[公式] 该页包含一个公式"), {
                "latex": latex,
                "text_format": item.get("text_format", "latex"),
            }
        if kind == "code":
            code = text or cls._to_text(item.get("code_body"))
            return (f"[代码] {code}" if code else ""), {"code": code}
        if kind == "list":
            list_text = text or cls._to_text(item.get("list_items"))
            return list_text, {"list_text": list_text}
        return text, {}

    @staticmethod
    def _to_text(value: Any, preserve_html: bool = False) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip() if preserve_html else re.sub(r"\s+", " ", value).strip()
        if isinstance(value, list):
            return "\n".join(
                text for item in value if (text := PaperParser._to_text(item))
            )
        if isinstance(value, dict):
            return " ".join(
                text for item in value.values() if (text := PaperParser._to_text(item))
            )
        return str(value).strip()

    @staticmethod
    def _html_to_text(value: str) -> str:
        if not value:
            return ""
        parser = _HTMLTextExtractor()
        parser.feed(value)
        return " | ".join(parser.parts)

    @staticmethod
    def _bbox(value: Any) -> list[float] | None:
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            return None
        try:
            return [float(number) for number in value]
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _resource_url(
        paper_id: str,
        img_path: Any,
        asset_root: Path | None,
        content_dir: Path | None,
    ) -> str | None:
        if not isinstance(img_path, str) or not img_path.strip() or asset_root is None:
            return None
        relative = PurePosixPath(img_path.replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts:
            return None
        candidates = []
        if content_dir is not None:
            candidates.append(content_dir.joinpath(*relative.parts))
        candidates.append(asset_root.joinpath(*relative.parts))
        resolved_root = asset_root.resolve()
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved_root not in resolved.parents or not resolved.is_file():
                continue
            public_path = resolved.relative_to(resolved_root).as_posix()
            return f"/media/assets/{paper_id}/{public_path}"
        return None
