import { useEffect, useMemo, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";

import type { CitationTarget, Paper } from "../types";

// 使用 Vite 的 ?url 导入确保 worker 版本与 react-pdf 内置的 pdfjs-dist 一致
import pdfjsWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
pdfjs.GlobalWorkerOptions.workerSrc = pdfjsWorkerUrl;

// CMAP 和标准字体文件通过 CDN 加载，用于支持中文学术PDF的字符映射
const PDFJS_VERSION = "4.8.69";
const CMAP_URL = `https://cdn.jsdelivr.net/npm/pdfjs-dist@${PDFJS_VERSION}/cmaps/`;
const STANDARD_FONT_URL = `https://cdn.jsdelivr.net/npm/pdfjs-dist@${PDFJS_VERSION}/standard_fonts/`;

interface Props {
  paper: Paper | null;
  targetCitation: CitationTarget | null;
  pageWidth?: number;
}

export function PaperReader({ paper, targetCitation, pageWidth = 720 }: Props) {
  const [pageCount, setPageCount] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState({ width: 0, height: 0 });
  const [pdfError, setPdfError] = useState<string | null>(null);

  // 确保 options 引用稳定，避免 Document 组件重复加载
  const documentOptions = useMemo(() => ({
    cMapUrl: CMAP_URL,
    cMapPacked: true,
    standardFontDataUrl: STANDARD_FONT_URL,
  }), []);

  useEffect(() => {
    if (targetCitation?.page) setPage(targetCitation.page);
  }, [targetCitation]);

  useEffect(() => {
    setPage(1);
    setPageCount(0);
    setPageSize({ width: 0, height: 0 });
    setPdfError(null);
  }, [paper?.id]);

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
        <Document
          file={paper.file_url}
          options={documentOptions}
          onLoadSuccess={({ numPages }) => {
            setPageCount(numPages);
            setPage((value) => Math.min(value, numPages));
          }}
          onLoadError={(error) => {
            setPdfError(error.message);
          }}
          loading={<p>正在加载PDF…</p>}
          error={<p>PDF加载失败，请检查后端文件地址。{pdfError && <small>（{pdfError}）</small>}</p>}
        >
          <div className="pdf-page-wrap">
            <Page
              pageNumber={page}
              width={pageWidth}
              renderTextLayer={false}
              renderAnnotationLayer={false}
              onLoadSuccess={(loadedPage) => {
                const viewport = loadedPage.getViewport({ scale: 1 });
                setPageSize({ width: viewport.width, height: viewport.height });
              }}
            />
            {highlight && (
              <div
                className="citation-highlight"
                style={highlight}
                aria-label="引用内容位置"
              />
            )}
          </div>
        </Document>
      </div>
    </section>
  );
}
