import { MouseEvent, useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";

import { api } from "../api";
import type { BilingualBlock, BilingualPage, Paper } from "../types";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "../../node_modules/react-pdf/node_modules/pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString();

interface Props {
  paper: Paper | null;
}

interface SelectionHighlight {
  left: number;
  top: number;
  width: number;
  height: number;
}

const PAGE_WIDTH = 620;

function TranslatedBlock({ block, sourcePageWidth }: {
  block: BilingualBlock;
  sourcePageWidth: number;
}) {
  const textLevel = Number(block.metadata.text_level);
  const imageWidth = block.bbox?.length === 4 && sourcePageWidth
    ? Math.min(100, Math.max(35, ((block.bbox[2] - block.bbox[0]) / sourcePageWidth) * 100))
    : 76;

  if ((block.kind === "image" || block.kind === "chart" || block.kind === "table") && block.resource_url) {
    return (
      <figure className={`translated-visual translated-${block.kind}`} style={{ width: `${imageWidth}%` }}>
        <img src={block.resource_url} alt={block.translated_text.slice(0, 80)} />
        {block.translated_text && <figcaption>{block.translated_text}</figcaption>}
      </figure>
    );
  }

  if (block.kind === "equation" || block.kind === "code") {
    return <pre className={`translated-${block.kind}`}>{block.source_text}</pre>;
  }

  if (Number.isFinite(textLevel)) {
    return textLevel <= 1
      ? <h2>{block.translated_text}</h2>
      : <h3>{block.translated_text}</h3>;
  }

  return <p className={block.kind === "list" ? "translated-list" : undefined}>{block.translated_text}</p>;
}

export function BilingualReader({ paper }: Props) {
  const [page, setPage] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [pageSize, setPageSize] = useState({ width: 0, height: 0 });
  const [translation, setTranslation] = useState<BilingualPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [checkingCache, setCheckingCache] = useState(false);
  const [error, setError] = useState("");
  const [selectedText, setSelectedText] = useState("");
  const [selectionHighlights, setSelectionHighlights] = useState<SelectionHighlight[]>([]);
  const [selectedTranslation, setSelectedTranslation] = useState("");
  const [selectionLoading, setSelectionLoading] = useState(false);
  const [selectionError, setSelectionError] = useState("");
  const sourceSheetRef = useRef<HTMLElement>(null);
  const translationRequestId = useRef(0);

  const clearSelection = () => {
    translationRequestId.current += 1;
    setSelectedText("");
    setSelectionHighlights([]);
    setSelectedTranslation("");
    setSelectionLoading(false);
    setSelectionError("");
    window.getSelection()?.removeAllRanges();
  };

  useEffect(() => {
    setPage(1);
    setPageCount(0);
    setPageSize({ width: 0, height: 0 });
    setTranslation(null);
    setError("");
    clearSelection();
  }, [paper?.id]);

  useEffect(() => {
    clearSelection();
  }, [page]);

  useEffect(() => {
    if (!paper || paper.status !== "ready") return;
    let cancelled = false;
    setCheckingCache(true);
    setTranslation(null);
    setError("");
    api.cachedBilingual(paper.id, page)
      .then((cached) => {
        if (!cancelled) setTranslation(cached);
      })
      .catch((reason) => {
        if (!cancelled) setError((reason as Error).message);
      })
      .finally(() => {
        if (!cancelled) setCheckingCache(false);
      });
    return () => { cancelled = true; };
  }, [paper?.id, paper?.status, page]);

  const generate = async (refresh = false) => {
    if (!paper || loading) return;
    setLoading(true);
    setError("");
    try {
      setTranslation(await api.createBilingual(paper.id, page, refresh));
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const translateSelectedText = async (text: string) => {
    if (!paper) return;
    const requestId = ++translationRequestId.current;
    setSelectionLoading(true);
    setSelectedTranslation("");
    setSelectionError("");
    try {
      const result = await api.translate(paper.id, text);
      if (requestId === translationRequestId.current) {
        setSelectedTranslation(result.translated_text);
      }
    } catch (reason) {
      if (requestId === translationRequestId.current) {
        setSelectionError((reason as Error).message);
      }
    } finally {
      if (requestId === translationRequestId.current) {
        setSelectionLoading(false);
      }
    }
  };

  const selectText = (event: MouseEvent<HTMLElement>) => {
    const sourceSheet = sourceSheetRef.current;
    const selection = window.getSelection();
    if (!sourceSheet || !selection || selection.isCollapsed || !selection.rangeCount) return;

    const range = selection.getRangeAt(0);
    if (!sourceSheet.contains(range.commonAncestorContainer)) return;
    const text = selection.toString().replace(/\s+/g, " ").trim().slice(0, 3000);
    if (!text) return;

    const sheetRect = sourceSheet.getBoundingClientRect();
    const highlights = Array.from(range.getClientRects())
      .filter((rect) => rect.width > 1 && rect.height > 1)
      .map((rect) => ({
        left: rect.left - sheetRect.left,
        top: rect.top - sheetRect.top,
        width: rect.width,
        height: rect.height
      }));
    if (!highlights.length) return;

    event.stopPropagation();
    setSelectedText(text);
    setSelectionHighlights(highlights);
    void translateSelectedText(text);
  };

  if (!paper || paper.status !== "ready") {
    return (
      <section className="content-page bilingual-page-view">
        <div className="bilingual-empty">
          <strong>中英对照阅读</strong>
          <p>请先在阅读工作台选择一篇已解析完成的论文。</p>
        </div>
      </section>
    );
  }

  const translatedMinHeight = pageSize.width
    ? (PAGE_WIDTH * pageSize.height) / pageSize.width
    : 800;

  return (
    <section className="content-page bilingual-page-view">
      <header className="bilingual-toolbar">
        <div>
          <span className="eyebrow">AI 学术翻译</span>
          <h1>中英双页对照</h1>
          <p>{paper.filename}</p>
        </div>
        <div className="bilingual-actions">
          <button disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>上一页</button>
          <span>{page} / {pageCount || paper.page_count || "—"}</span>
          <button
            disabled={page >= (pageCount || paper.page_count)}
            onClick={() => setPage((value) => value + 1)}
          >下一页</button>
          <button className="primary" disabled={loading || checkingCache} onClick={() => void generate(Boolean(translation))}>
            {loading ? "正在翻译本页…" : translation ? "重新翻译本页" : "生成本页中文"}
          </button>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <div className={`bilingual-spread ${selectedText ? "has-selection" : ""}`}>
        <article
          className="bilingual-sheet source-sheet"
          ref={sourceSheetRef}
          onMouseUp={selectText}
        >
          <div className="sheet-language"><span>EN</span> 英文原文</div>
          <Document
            file={paper.file_url}
            onLoadSuccess={({ numPages }) => {
              setPageCount(numPages);
              setPage((value) => Math.min(value, numPages));
            }}
            loading={<p className="sheet-status">正在加载英文原文…</p>}
            error={<p className="sheet-status">PDF 加载失败。</p>}
          >
            <Page
              pageNumber={page}
              width={PAGE_WIDTH}
              renderTextLayer
              renderAnnotationLayer={false}
              onLoadSuccess={(loadedPage) => {
                const viewport = loadedPage.getViewport({ scale: 1 });
                setPageSize({ width: viewport.width, height: viewport.height });
              }}
            />
          </Document>
          {selectionHighlights.map((selectionHighlight, index) => (
            <div
              className="selected-text-highlight"
              style={selectionHighlight}
              key={`${selectionHighlight.left}-${selectionHighlight.top}-${index}`}
              aria-hidden="true"
            />
          ))}
        </article>

        <article className="bilingual-sheet translated-sheet" style={{ minHeight: translatedMinHeight }}>
          <div className="sheet-language"><span>中</span> 中文译文</div>
          {checkingCache && <p className="sheet-status">正在读取本页译文…</p>}
          {!checkingCache && !translation && (
            <div className="translation-placeholder">
              <div>译</div>
              <strong>本页尚未生成中文译文</strong>
              <p>生成后会保留标题、正文、公式与插图的阅读顺序，并自动缓存。</p>
              <button disabled={loading} onClick={() => void generate()}>
                {loading ? "正在翻译…" : "生成本页中文"}
              </button>
            </div>
          )}
          {translation && (
            <div className="translated-paper">
              {translation.blocks.map((block) => (
                <TranslatedBlock
                  block={block}
                  key={block.chunk_id}
                  sourcePageWidth={pageSize.width}
                />
              ))}
            </div>
          )}
        </article>
        {selectedText && (
          <aside className="selection-translation-panel bilingual-selection-panel">
            <header>
              <div>
                <span>划词翻译</span>
                <strong>选中内容</strong>
              </div>
              <button type="button" onClick={clearSelection} aria-label="关闭划词翻译">×</button>
            </header>
            <section>
              <span>原文</span>
              <p>{selectedText}</p>
            </section>
            <section className="selection-translation-result">
              <span>中文译文</span>
              {selectionLoading && <p className="selection-loading">正在翻译…</p>}
              {selectionError && <p className="selection-error">{selectionError}</p>}
              {selectedTranslation && <p>{selectedTranslation}</p>}
            </section>
            <small>选区已持续高亮，原文可以复制。</small>
          </aside>
        )}
      </div>
    </section>
  );
}
