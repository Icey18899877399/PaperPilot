import { MouseEvent, useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";

import { api } from "../api";
import type { CitationTarget, Paper } from "../types";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "../../node_modules/react-pdf/node_modules/pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString();

interface Props {
  paper: Paper | null;
  targetCitation: CitationTarget | null;
  pageWidth?: number;
  onPageChange?: (page: number) => void;
}

interface SelectionHighlight {
  left: number;
  top: number;
  width: number;
  height: number;
}

interface SearchablePdfDocument {
  numPages: number;
  getPage: (pageNumber: number) => Promise<{
    getTextContent: () => Promise<{ items: unknown[] }>;
  }>;
}

export function PaperReader({ paper, targetCitation, pageWidth = 720, onPageChange }: Props) {
  const [pageCount, setPageCount] = useState(0);
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(100);
  const [fitPageWidth, setFitPageWidth] = useState(pageWidth);
  const [pageSize, setPageSize] = useState({ width: 0, height: 0 });
  const [pdfDocument, setPdfDocument] = useState<SearchablePdfDocument | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeSearchQuery, setActiveSearchQuery] = useState("");
  const [searchMatchPages, setSearchMatchPages] = useState<number[]>([]);
  const [searchMatchIndex, setSearchMatchIndex] = useState(-1);
  const [searching, setSearching] = useState(false);
  const [searchMessage, setSearchMessage] = useState("");
  const [selectedText, setSelectedText] = useState("");
  const [selectionHighlights, setSelectionHighlights] = useState<SelectionHighlight[]>([]);
  const [selectedTranslation, setSelectedTranslation] = useState("");
  const [translationLoading, setTranslationLoading] = useState(false);
  const [translationError, setTranslationError] = useState("");
  const pageWrapRef = useRef<HTMLDivElement>(null);
  const pdfCanvasRef = useRef<HTMLDivElement>(null);
  const translationRequestId = useRef(0);
  const searchRequestId = useRef(0);

  const clearSelection = () => {
    translationRequestId.current += 1;
    setSelectedText("");
    setSelectionHighlights([]);
    setSelectedTranslation("");
    setTranslationLoading(false);
    setTranslationError("");
    window.getSelection()?.removeAllRanges();
  };

  useEffect(() => {
    if (targetCitation?.page) setPage(targetCitation.page);
  }, [targetCitation]);

  useEffect(() => {
    onPageChange?.(page);
  }, [onPageChange, page]);

  useEffect(() => {
    const container = pdfCanvasRef.current;
    if (!container) return;
    const updateWidth = () => {
      const available = Math.max(280, container.clientWidth - 48);
      setFitPageWidth(Math.min(pageWidth, available));
    };
    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    observer.observe(container);
    return () => observer.disconnect();
  }, [pageWidth, paper?.id]);

  useEffect(() => {
    setPage(1);
    setPageCount(0);
    setZoom(100);
    setPageSize({ width: 0, height: 0 });
    setPdfDocument(null);
    setSearchQuery("");
    setActiveSearchQuery("");
    setSearchMatchPages([]);
    setSearchMatchIndex(-1);
    setSearchMessage("");
    searchRequestId.current += 1;
    clearSelection();
  }, [paper?.id]);

  useEffect(() => {
    clearSelection();
  }, [page, zoom]);

  const searchDocument = async () => {
    const query = searchQuery.trim().toLocaleLowerCase();
    if (!pdfDocument || !query || searching) return;

    if (query === activeSearchQuery && searchMatchPages.length) {
      const nextIndex = (searchMatchIndex + 1) % searchMatchPages.length;
      setSearchMatchIndex(nextIndex);
      setPage(searchMatchPages[nextIndex]);
      setSearchMessage(`${nextIndex + 1} / ${searchMatchPages.length} 个匹配页`);
      return;
    }

    const requestId = ++searchRequestId.current;
    setSearching(true);
    setSearchMessage("正在搜索全文…");
    try {
      const matches: number[] = [];
      for (let pageNumber = 1; pageNumber <= pdfDocument.numPages; pageNumber += 1) {
        const pdfPage = await pdfDocument.getPage(pageNumber);
        const textContent = await pdfPage.getTextContent();
        if (requestId !== searchRequestId.current) return;
        const pageText = textContent.items
          .map((item) => (
            typeof item === "object"
            && item !== null
            && "str" in item
            && typeof item.str === "string"
              ? item.str
              : ""
          ))
          .join(" ")
          .toLocaleLowerCase();
        if (pageText.includes(query)) matches.push(pageNumber);
      }

      if (requestId !== searchRequestId.current) return;
      setActiveSearchQuery(query);
      setSearchMatchPages(matches);
      if (!matches.length) {
        setSearchMatchIndex(-1);
        setSearchMessage("未找到匹配内容");
        return;
      }
      const firstIndex = matches.findIndex((matchPage) => matchPage >= page);
      const nextIndex = firstIndex >= 0 ? firstIndex : 0;
      setSearchMatchIndex(nextIndex);
      setPage(matches[nextIndex]);
      setSearchMessage(`${nextIndex + 1} / ${matches.length} 个匹配页`);
    } catch {
      setSearchMessage("全文搜索失败，请重试");
    } finally {
      if (requestId === searchRequestId.current) setSearching(false);
    }
  };

  const translateSelectedText = async (text: string) => {
    if (!paper) return;
    const requestId = ++translationRequestId.current;
    setTranslationLoading(true);
    setSelectedTranslation("");
    setTranslationError("");
    try {
      const result = await api.translate(paper.id, text);
      if (requestId === translationRequestId.current) {
        setSelectedTranslation(result.translated_text);
      }
    } catch (reason) {
      if (requestId === translationRequestId.current) {
        setTranslationError((reason as Error).message);
      }
    } finally {
      if (requestId === translationRequestId.current) {
        setTranslationLoading(false);
      }
    }
  };

  const selectText = (event: MouseEvent<HTMLDivElement>) => {
    const wrapper = pageWrapRef.current;
    const selection = window.getSelection();
    if (!wrapper || !selection || selection.isCollapsed || !selection.rangeCount) return;

    const range = selection.getRangeAt(0);
    if (!wrapper.contains(range.commonAncestorContainer)) return;
    const text = selection.toString().replace(/\s+/g, " ").trim().slice(0, 3000);
    if (!text) return;

    const wrapperRect = wrapper.getBoundingClientRect();
    const highlights = Array.from(range.getClientRects())
      .filter((rect) => rect.width > 1 && rect.height > 1)
      .map((rect) => ({
        left: rect.left - wrapperRect.left,
        top: rect.top - wrapperRect.top,
        width: rect.width,
        height: rect.height
      }));
    if (!highlights.length) return;

    event.stopPropagation();
    setSelectedText(text);
    setSelectionHighlights(highlights);
    void translateSelectedText(text);
  };

  const bbox = targetCitation?.page === page ? targetCitation.bbox : null;
  const renderedPageWidth = Math.round(fitPageWidth * zoom / 100);
  const scale = pageSize.width ? renderedPageWidth / pageSize.width : 1;
  const highlight = bbox?.length === 4
    ? {
        left: bbox[0] * scale,
        top: bbox[1] * scale,
        width: Math.max(10, (bbox[2] - bbox[0]) * scale),
        height: Math.max(10, (bbox[3] - bbox[1]) * scale)
      }
    : null;

  if (!paper) {
    return (
      <div className="empty-reader">
        <div className="empty-document">PDF</div>
        <h2>选择一篇论文开始阅读</h2>
        <p>上传后可查看原文、生成导读并进行溯源问答。</p>
      </div>
    );
  }

  return (
    <section className="reader">
      <header className="reader-toolbar">
        <div className="reader-document-meta">
          <strong>{paper.filename}</strong>
          <span>{paper.page_count || pageCount} 页</span>
        </div>
        <div className="reader-tools">
          <div className="page-control">
            <button disabled={page <= 1} onClick={() => setPage((value) => value - 1)} aria-label="上一页">‹</button>
            <span>{page} / {pageCount || "—"} 页</span>
            <button
              disabled={!pageCount || page >= pageCount}
              onClick={() => setPage((value) => value + 1)}
              aria-label="下一页"
            >›</button>
          </div>
          <div className="zoom-control">
            <button disabled={zoom <= 50} onClick={() => setZoom((value) => Math.max(50, value - 10))}>−</button>
            <span>{zoom}%</span>
            <button disabled={zoom >= 200} onClick={() => setZoom((value) => Math.min(200, value + 10))}>+</button>
          </div>
          <label className="pdf-search">
            <input
              value={searchQuery}
              onChange={(event) => {
                setSearchQuery(event.target.value);
                if (event.target.value.trim().toLocaleLowerCase() !== activeSearchQuery) {
                  setSearchMessage("");
                }
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  void searchDocument();
                }
              }}
              placeholder="全文搜索…回车检索"
              aria-label="全文搜索，按回车检索"
            />
            {searchMessage && <small>{searchMessage}</small>}
          </label>
        </div>
      </header>
      <div className="pdf-canvas" ref={pdfCanvasRef}>
        <div className="pdf-reader-stage">
          <Document
            file={paper.file_url}
            onLoadSuccess={(loadedDocument) => {
              setPdfDocument(loadedDocument);
              setPageCount(loadedDocument.numPages);
              setPage((value) => Math.min(value, loadedDocument.numPages));
            }}
            loading={<p>正在加载PDF…</p>}
            error={<p>PDF加载失败，请检查后端文件地址。</p>}
          >
            <div className="pdf-page-wrap" ref={pageWrapRef} onMouseUp={selectText}>
              <Page
                pageNumber={page}
                width={renderedPageWidth}
                renderTextLayer
                renderAnnotationLayer
                onLoadSuccess={(loadedPage) => {
                  const viewport = loadedPage.getViewport({ scale: 1 });
                  setPageSize({ width: viewport.width, height: viewport.height });
                }}
              />
              {selectionHighlights.map((selectionHighlight, index) => (
                <div
                  className="selected-text-highlight"
                  style={selectionHighlight}
                  key={`${selectionHighlight.left}-${selectionHighlight.top}-${index}`}
                  aria-hidden="true"
                />
              ))}
              {highlight && (
                <div
                  className="citation-highlight"
                  style={highlight}
                  aria-label="引用内容位置"
                />
              )}
            </div>
          </Document>
          {selectedText && (
            <aside className="selection-translation-panel">
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
                {translationLoading && <p className="selection-loading">正在翻译…</p>}
                {translationError && <p className="selection-error">{translationError}</p>}
                {selectedTranslation && <p>{selectedTranslation}</p>}
              </section>
              <small>选区已持续高亮，原文可以复制。</small>
            </aside>
          )}
        </div>
      </div>
    </section>
  );
}
