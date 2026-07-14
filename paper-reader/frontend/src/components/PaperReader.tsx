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
}

interface SelectionHighlight {
  left: number;
  top: number;
  width: number;
  height: number;
}

export function PaperReader({ paper, targetCitation, pageWidth = 720 }: Props) {
  const [pageCount, setPageCount] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState({ width: 0, height: 0 });
  const [selectedText, setSelectedText] = useState("");
  const [selectionHighlights, setSelectionHighlights] = useState<SelectionHighlight[]>([]);
  const [selectedTranslation, setSelectedTranslation] = useState("");
  const [translationLoading, setTranslationLoading] = useState(false);
  const [translationError, setTranslationError] = useState("");
  const pageWrapRef = useRef<HTMLDivElement>(null);
  const translationRequestId = useRef(0);

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
    setPage(1);
    setPageCount(0);
    setPageSize({ width: 0, height: 0 });
    clearSelection();
  }, [paper?.id]);

  useEffect(() => {
    clearSelection();
  }, [page]);

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
  const scale = pageSize.width ? pageWidth / pageSize.width : 1;
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
        <div>
          <strong>{paper.filename}</strong>
          <span>{paper.page_count || pageCount} 页</span>
        </div>
        <div className="page-control">
          <button disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>
            上一页
          </button>
          <span>{page} / {pageCount || "—"}</span>
          <button
            disabled={!pageCount || page >= pageCount}
            onClick={() => setPage((value) => value + 1)}
          >
            下一页
          </button>
        </div>
      </header>
      <div className="pdf-canvas">
        <div className="pdf-reader-stage">
          <Document
            file={paper.file_url}
            onLoadSuccess={({ numPages }) => {
              setPageCount(numPages);
              setPage((value) => Math.min(value, numPages));
            }}
            loading={<p>正在加载PDF…</p>}
            error={<p>PDF加载失败，请检查后端文件地址。</p>}
          >
            <div className="pdf-page-wrap" ref={pageWrapRef} onMouseUp={selectText}>
              <Page
                pageNumber={page}
                width={pageWidth}
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
