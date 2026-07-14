import { useEffect, useState } from "react";

import { api } from "../api";
import type { CitationTarget, Paper, PaperChunk, PaperContentsResponse } from "../types";
import { PaperReader } from "./PaperReader";

interface Props {
  paper: Paper | null;
  compact?: boolean;
  onLocate?: (target: CitationTarget) => void;
}

const filters = [
  { kind: "image", label: "图片" },
  { kind: "chart", label: "图表" },
  { kind: "table", label: "表格" },
  { kind: "equation", label: "公式" },
  { kind: "text", label: "正文" }
];

export function StructuredContentView({ paper, compact = false, onLocate }: Props) {
  const [kind, setKind] = useState("table");
  const [contents, setContents] = useState<PaperContentsResponse | null>(null);
  const [selected, setSelected] = useState<PaperChunk | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setContents(null);
    setSelected(null);
    if (!paper || paper.status !== "ready") return;
    setLoading(true);
    setError("");
    api.paperContents(paper.id, kind)
      .then((result) => {
        setContents(result);
        setSelected(result.items[0] ?? null);
      })
      .catch((reason) => setError((reason as Error).message))
      .finally(() => setLoading(false));
  }, [paper?.id, paper?.status, kind]);

  if (compact) {
    if (!paper || paper.status !== "ready") {
      return (
        <div className="workspace-panel-empty">
          <strong>结构化切片</strong>
          <p>请先从左侧论文库选择一篇已解析完成的论文。</p>
        </div>
      );
    }

    return (
      <section className="workspace-structured-panel">
        <header>
          <div>
            <span className="eyebrow">MinerU 结构化解析</span>
            <h2>结构化切片</h2>
          </div>
          <b>{contents?.total ?? 0}</b>
        </header>
        <div className="workspace-content-filters">
          {filters.map((filter) => (
            <button
              key={filter.kind}
              className={kind === filter.kind ? "active" : ""}
              onClick={() => setKind(filter.kind)}
            >
              {filter.label}<span>{contents?.counts[filter.kind] ?? "—"}</span>
            </button>
          ))}
        </div>
        {error && <div className="inline-error">{error}</div>}
        <div className="workspace-chunk-list">
          {loading && <p className="empty-copy">正在读取结构化内容…</p>}
          {!loading && contents?.items.map((item) => {
            const latex = typeof item.metadata.latex === "string"
              ? item.metadata.latex
              : "";
            const label = filters.find((filter) => filter.kind === item.kind)?.label
              ?? item.kind;
            return (
              <button
                type="button"
                className={`chunk-card ${selected?.chunk_id === item.chunk_id ? "selected" : ""}`}
                key={item.chunk_id}
                onClick={() => {
                  setSelected(item);
                  onLocate?.({ page: item.page, bbox: null });
                }}
              >
                <header>
                  <strong>第{item.page}页 · {label}</strong>
                  <span>{selected?.chunk_id === item.chunk_id ? "当前切片" : "查看原文"}</span>
                </header>
                {item.resource_url && (
                  <img src={item.resource_url} alt={`第${item.page}页${label}`} />
                )}
                {item.kind === "equation"
                  ? <pre>{latex || item.content}</pre>
                  : item.kind !== "table" && <p>{item.content}</p>}
              </button>
            );
          })}
          {!loading && contents && !contents.items.length && (
            <p className="empty-copy">该论文没有识别到此类内容。</p>
          )}
        </div>
      </section>
    );
  }

  return (
    <section className="content-page structured-page">
      <header className="content-page-header">
        <div>
          <span className="eyebrow">MinerU结构化解析</span>
          <h1>论文多模态内容</h1>
          <p>{paper ? paper.filename : "请先在阅读工作台选择一篇已解析论文"}</p>
        </div>
        {paper?.status === "ready" && <span className="ready-badge">{paper.page_count}页 · 已建立索引</span>}
      </header>

      {paper?.status === "ready" ? (
        <>
          <div className="content-filters">
            {filters.map((filter) => (
              <button
                key={filter.kind}
                className={kind === filter.kind ? "active" : ""}
                onClick={() => setKind(filter.kind)}
              >
                {filter.label}
                <span>{contents?.counts[filter.kind] ?? "—"}</span>
              </button>
            ))}
          </div>
          {error && <div className="error-banner">{error}</div>}
          <div className="chunk-compare-shell">
            <aside className="chunk-pane">
              <div className="chunk-pane-heading">
                <div><strong>解析切片</strong><span>点击任一切片，右侧原文同步翻页</span></div>
                <b>{contents?.total ?? 0}</b>
              </div>
              <div className="chunk-list">
                {loading && <p className="empty-copy">正在读取结构化内容…</p>}
                {!loading && contents?.items.map((item) => {
                  const latex = typeof item.metadata.latex === "string"
                    ? item.metadata.latex
                    : "";
                  const label = filters.find((filter) => filter.kind === item.kind)?.label ?? item.kind;
                  return (
                    <button
                      type="button"
                      className={`chunk-card ${selected?.chunk_id === item.chunk_id ? "selected" : ""}`}
                      key={item.chunk_id}
                      onClick={() => setSelected(item)}
                    >
                      <header>
                        <strong>第{item.page}页 · {label}</strong>
                        <span>{selected?.chunk_id === item.chunk_id ? "正在对照" : "查看原文"}</span>
                      </header>
                      {item.resource_url && <img src={item.resource_url} alt={`第${item.page}页${label}`} />}
                      {item.kind === "equation"
                        ? <pre>{latex || item.content}</pre>
                        : item.kind !== "table" && <p>{item.content}</p>}
                    </button>
                  );
                })}
                {!loading && contents && !contents.items.length && (
                  <p className="empty-copy">该论文没有识别到此类内容。</p>
                )}
              </div>
            </aside>
            <section className="source-pane">
              <PaperReader
                paper={paper}
                targetCitation={selected ? { page: selected.page, bbox: null } : null}
                pageWidth={660}
              />
            </section>
          </div>
        </>
      ) : (
        <p className="empty-copy">返回阅读工作台，选择或上传一篇已解析论文后即可浏览。</p>
      )}
    </section>
  );
}
