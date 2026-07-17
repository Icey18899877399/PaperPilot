import { useEffect, useRef, useState } from "react";

import { api } from "./api";
import { AgentLogView } from "./components/AgentLogView";
import { ChatPanel } from "./components/ChatPanel";
import { GuidePanel } from "./components/GuidePanel";
import { MindMapView } from "./components/MindMapView";
import { PaperReader } from "./components/PaperReader";
import { TranslationPanel } from "./components/TranslationPanel";
import { StructuredContentView } from "./components/StructuredContentView";
import { UploadPanel } from "./components/UploadPanel";
import { VideoLibrary } from "./components/VideoLibrary";
import type { AgentLog, CitationTarget, Guide, ModelStatus, Paper, VideoResource } from "./types";

type View = "workspace" | "contents" | "mindmap" | "logs" | "videos";

export default function App() {
  const [papers, setPapers] = useState<Paper[]>([]);
  const [paper, setPaper] = useState<Paper | null>(null);
  const [guide, setGuide] = useState<Guide | null>(null);
  const [uploading, setUploading] = useState(false);
  const [guideLoading, setGuideLoading] = useState(false);
  const [targetCitation, setTargetCitation] = useState<CitationTarget | null>(null);
  const [error, setError] = useState("");
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null);
  const [view, setView] = useState<View>("workspace");
  const [logs, setLogs] = useState<AgentLog[]>([]);
  const [videos, setVideos] = useState<VideoResource[]>([]);
  const [viewLoading, setViewLoading] = useState(false);
  const [deletingPaperId, setDeletingPaperId] = useState<string | null>(null);
  const [retryingPaperId, setRetryingPaperId] = useState<string | null>(null);
  const monitoringPapers = useRef(new Set<string>());

  const updatePaper = (updated: Paper) => {
    setPapers((items) => items.map((item) => item.id === updated.id ? updated : item));
    setPaper((current) => current?.id === updated.id ? updated : current);
  };

  const openView = (next: View) => {
    if ((next === "contents" || next === "mindmap") && !paper) {
      setPaper(papers.find((item) => item.status === "ready") ?? null);
    }
    setView(next);
  };

  async function monitorPaper(paperId: string) {
    if (monitoringPapers.current.has(paperId)) return;
    monitoringPapers.current.add(paperId);
    try {
      for (let attempt = 0; attempt < 1800; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
        const updated = await api.getPaper(paperId);
        updatePaper(updated);
        if (updated.status !== "parsing") {
          if (updated.status === "failed") {
            setError(updated.error || "论文解析失败");
          }
          return;
        }
      }
      setError("论文解析时间过长，请稍后刷新论文状态");
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      monitoringPapers.current.delete(paperId);
    }
  }

  useEffect(() => {
    api.listPapers().then((items) => {
      setPapers(items);
      items.filter((item) => item.status === "parsing")
        .forEach((item) => void monitorPaper(item.id));
    }).catch(() => undefined);
    api.modelStatus().then(setModelStatus).catch(() => undefined);
  }, []);

  useEffect(() => {
    setGuide(null);
    if (!paper || paper.status !== "ready") return;
    let cancelled = false;
    setGuideLoading(true);
    api.cachedGuide(paper.id)
      .then((cached) => {
        if (!cancelled) setGuide(cached);
      })
      .catch((reason) => {
        if (!cancelled) setError((reason as Error).message);
      })
      .finally(() => {
        if (!cancelled) setGuideLoading(false);
      });
    return () => { cancelled = true; };
  }, [paper?.id, paper?.status]);

  const loadLogs = async () => {
    setViewLoading(true);
    setError("");
    try {
      setLogs(await api.agentLogs());
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setViewLoading(false);
    }
  };

  useEffect(() => {
    if (view === "logs") void loadLogs();
    if (view === "videos") {
      setViewLoading(true);
      api.listVideos()
        .then(setVideos)
        .catch((reason) => setError((reason as Error).message))
        .finally(() => setViewLoading(false));
    }
  }, [view]);

  const upload = async (file: File) => {
    setUploading(true);
    setError("");
    try {
      const created = await api.uploadPaper(file);
      setPapers((items) => [created, ...items]);
      setPaper(created);
      setGuide(null);
      setTargetCitation(null);
      if (created.status === "parsing") void monitorPaper(created.id);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setUploading(false);
    }
  };

  const generateGuide = async () => {
    if (!paper) return;
    setGuideLoading(true);
    setError("");
    try {
      setGuide(await api.createGuide(paper.id, Boolean(guide)));
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setGuideLoading(false);
    }
  };

  const retryPaper = async (item: Paper) => {
    if (item.status !== "failed" || retryingPaperId) return;
    setRetryingPaperId(item.id);
    setError("");
    try {
      const updated = await api.retryPaper(item.id);
      updatePaper(updated);
      setPaper(updated);
      setGuide(null);
      setTargetCitation(null);
      void monitorPaper(updated.id);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setRetryingPaperId(null);
    }
  };

  const deletePaper = async (item: Paper) => {
    if (item.status === "parsing" || deletingPaperId) return;
    const confirmed = window.confirm(
      `确定删除“${item.filename}”吗？\n将同时删除PDF、解析资源、检索索引和思维导图。`
    );
    if (!confirmed) return;
    setDeletingPaperId(item.id);
    setError("");
    try {
      await api.deletePaper(item.id);
      setPapers((items) => items.filter((value) => value.id !== item.id));
      if (paper?.id === item.id) {
        setPaper(null);
        setGuide(null);
        setTargetCitation(null);
      }
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setDeletingPaperId(null);
    }
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-mark">P</div>
        <div>
          <strong>PaperPilot</strong>
          <span>多Agent论文智能阅读系统</span>
        </div>
        <nav>
          <button className={view === "workspace" ? "active" : ""} onClick={() => openView("workspace")}>阅读工作台</button>
          <button className={view === "contents" ? "active" : ""} onClick={() => openView("contents")}>结构化内容</button>
          <button className={view === "mindmap" ? "active" : ""} onClick={() => openView("mindmap")}>思维导图</button>
          <button className={view === "logs" ? "active" : ""} onClick={() => setView("logs")}>Agent日志</button>
          <button className={view === "videos" ? "active" : ""} onClick={() => setView("videos")}>视频资源</button>
          <span
            className={
              modelStatus?.configured
                ? "model-pill configured"
                : "model-pill"
            }
          >
            {modelStatus?.configured
              ? `${modelStatus.model} 已配置`
              : "模型未配置"}
          </span>
        </nav>
      </header>

      {error && <div className="error-banner">{error}</div>}

      {view === "workspace" && <div className="workspace">
        <aside className="sidebar">
          <UploadPanel uploading={uploading} onUpload={upload} />
          <div className="paper-list">
            <div className="section-heading compact">
              <h2>论文库</h2>
              <span>{papers.length}</span>
            </div>
            {papers.map((item) => (
              <div className="paper-row" key={item.id}>
                <button
                  className={paper?.id === item.id ? "paper-item active" : "paper-item"}
                  onClick={() => {
                    setPaper(item);
                    setGuide(null);
                    setTargetCitation(null);
                  }}
                >
                  <span className="file-icon">PDF</span>
                  <span>
                    <strong>{item.filename}</strong>
                    <small title={item.error ?? item.stage}>
                      {item.status === "ready"
                        ? `${item.page_count}页 · ${item.stage || "已解析"}`
                        : item.status === "failed"
                          ? "解析失败 · 可重新解析"
                          : `${item.stage || "解析中"} · ${item.progress || 0}%`}
                    </small>
                    {item.status === "parsing" && (
                      <span className="parse-progress" aria-label={`解析进度${item.progress || 0}%`}>
                        <i style={{ width: `${item.progress || 0}%` }} />
                      </span>
                    )}
                  </span>
                </button>
                <div className="paper-actions">
                  {item.status === "failed" && (
                    <button
                      className="paper-retry"
                      disabled={retryingPaperId === item.id}
                      onClick={() => void retryPaper(item)}
                    >
                      {retryingPaperId === item.id ? "重试中" : "重试"}
                    </button>
                  )}
                  <button
                    className="paper-delete"
                    title={item.status === "parsing" ? "解析期间不能删除" : "删除论文及相关数据"}
                    disabled={item.status === "parsing" || deletingPaperId === item.id}
                    onClick={() => void deletePaper(item)}
                  >
                    {deletingPaperId === item.id ? "…" : "删除"}
                  </button>
                </div>
              </div>
            ))}
          </div>
          <GuidePanel
            guide={guide}
            loading={guideLoading}
            disabled={!paper || paper.status !== "ready"}
            onGenerate={generateGuide}
          />
          <TranslationPanel paperId={paper?.status === "ready" ? paper.id : undefined} />
        </aside>

        <PaperReader paper={paper} targetCitation={targetCitation} />
        <ChatPanel paperId={paper?.status === "ready" ? paper.id : undefined} onLocate={setTargetCitation} />
      </div>}
      {view === "logs" && <AgentLogView logs={logs} loading={viewLoading} onRefresh={loadLogs} />}
      {view === "videos" && <VideoLibrary videos={videos} loading={viewLoading} />}
      {view === "contents" && (
        <StructuredContentView paper={paper} />
      )}
      <div hidden={view !== "mindmap"}>
        <MindMapView paper={paper} />
      </div>
    </main>
  );
}
