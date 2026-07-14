import { useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";

import { api } from "./api";
import { AgentLogView } from "./components/AgentLogView";
import { BilingualReader } from "./components/BilingualReader";
import { ChatPanel } from "./components/ChatPanel";
import { GuidePanel } from "./components/GuidePanel";
import { MindMapView } from "./components/MindMapView";
import { PaperReader } from "./components/PaperReader";
import { StructuredContentView } from "./components/StructuredContentView";
import { UploadPanel } from "./components/UploadPanel";
import { VideoLibrary } from "./components/VideoLibrary";
import type { AgentLog, CitationTarget, Guide, ModelStatus, Paper, VideoResource } from "./types";

type View = "workspace" | "mindmap" | "logs" | "videos";
type AssistantTab = "guide" | "chat" | "bilingual" | "contents";

interface ResizeSession {
  side: "left" | "right";
  startX: number;
  startLeft: number;
  startRight: number;
}

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
  const [assistantTab, setAssistantTab] = useState<AssistantTab>("guide");
  const [readerPage, setReaderPage] = useState(1);
  const [leftPaneWidth, setLeftPaneWidth] = useState(250);
  const [rightPaneWidth, setRightPaneWidth] = useState(440);
  const [sourceSelection, setSourceSelection] = useState("");
  const [pairedSourceText, setPairedSourceText] = useState("");
  const [logs, setLogs] = useState<AgentLog[]>([]);
  const [videos, setVideos] = useState<VideoResource[]>([]);
  const [viewLoading, setViewLoading] = useState(false);
  const [deletingPaperId, setDeletingPaperId] = useState<string | null>(null);
  const [retryingPaperId, setRetryingPaperId] = useState<string | null>(null);
  const monitoringPapers = useRef(new Set<string>());
  const resizeSession = useRef<ResizeSession | null>(null);

  useEffect(() => {
    const move = (event: PointerEvent) => {
      const session = resizeSession.current;
      if (!session) return;
      const delta = event.clientX - session.startX;
      if (session.side === "left") {
        const maxLeft = Math.max(
          240,
          Math.min(420, window.innerWidth - session.startRight - 440),
        );
        setLeftPaneWidth(Math.min(maxLeft, Math.max(180, session.startLeft + delta)));
      } else {
        const maxRight = Math.max(
          380,
          Math.min(720, window.innerWidth - session.startLeft - 440),
        );
        setRightPaneWidth(Math.min(maxRight, Math.max(320, session.startRight - delta)));
      }
    };
    const stop = () => {
      resizeSession.current = null;
      document.body.classList.remove("is-resizing-workspace");
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
      document.body.classList.remove("is-resizing-workspace");
    };
  }, []);

  const startResize = (
    side: ResizeSession["side"],
    event: ReactPointerEvent<HTMLDivElement>,
  ) => {
    event.preventDefault();
    resizeSession.current = {
      side,
      startX: event.clientX,
      startLeft: leftPaneWidth,
      startRight: rightPaneWidth,
    };
    document.body.classList.add("is-resizing-workspace");
  };

  const workspaceStyle = {
    "--library-width": `${leftPaneWidth}px`,
    "--assistant-width": `${rightPaneWidth}px`,
  } as CSSProperties;

  const handleReaderPageChange = useCallback((nextPage: number) => {
    setReaderPage(nextPage);
    setSourceSelection("");
    setPairedSourceText("");
  }, []);

  const updatePaper = (updated: Paper) => {
    setPapers((items) => items.map((item) => item.id === updated.id ? updated : item));
    setPaper((current) => current?.id === updated.id ? updated : current);
  };

  const openView = (next: View) => {
    if (next === "mindmap" && !paper) {
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

  const loadVideos = async () => {
    setViewLoading(true);
    setError("");
    try {
      setVideos(await api.listVideos());
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setViewLoading(false);
    }
  };

  useEffect(() => {
    if (view === "logs") void loadLogs();
    if (view === "videos") void loadVideos();
  }, [view]);

  const upload = async (file: File) => {
    setUploading(true);
    setError("");
    try {
      const created = await api.uploadPaper(file);
      setPapers((items) => [created, ...items]);
      setPaper(created);
      setReaderPage(1);
      setSourceSelection("");
      setPairedSourceText("");
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
      setReaderPage(1);
      setSourceSelection("");
      setPairedSourceText("");
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

      {view === "workspace" && <div className="workspace" style={workspaceStyle}>
        <aside className="sidebar paper-library-sidebar">
          <div className="paper-list">
            <div className="paper-library-heading">
              <div className="section-heading compact">
                <h2>论文库</h2>
                <span>{papers.length}</span>
              </div>
              <UploadPanel compact uploading={uploading} onUpload={upload} />
            </div>
            {papers.map((item) => (
              <div className="paper-row" key={item.id}>
                <button
                  className={paper?.id === item.id ? "paper-item active" : "paper-item"}
                  onClick={() => {
                    setPaper(item);
                    setReaderPage(1);
                    setSourceSelection("");
                    setPairedSourceText("");
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
        </aside>

        <div
          className="workspace-resizer workspace-resizer-left"
          role="separator"
          aria-label="拖动调整论文库宽度"
          aria-orientation="vertical"
          onPointerDown={(event) => startResize("left", event)}
        />

        <PaperReader
          paper={paper}
          targetCitation={targetCitation}
          pairedSourceText={pairedSourceText}
          onSourceSelection={setSourceSelection}
          onPageChange={handleReaderPageChange}
        />
        <div
          className="workspace-resizer workspace-resizer-right"
          role="separator"
          aria-label="拖动调整右侧功能栏宽度"
          aria-orientation="vertical"
          onPointerDown={(event) => startResize("right", event)}
        />
        <section className="workspace-assistant">
          <nav className="assistant-tabs" aria-label="论文辅助功能">
            <button
              className={assistantTab === "guide" ? "active" : ""}
              onClick={() => setAssistantTab("guide")}
            >智能导读</button>
            <button
              className={assistantTab === "chat" ? "active" : ""}
              onClick={() => setAssistantTab("chat")}
            >论文对话</button>
            <button
              className={assistantTab === "bilingual" ? "active" : ""}
              onClick={() => setAssistantTab("bilingual")}
            >中英对照</button>
            <button
              className={assistantTab === "contents" ? "active" : ""}
              onClick={() => setAssistantTab("contents")}
            >结构化切片</button>
          </nav>
          <div className="assistant-panel-body">
            {assistantTab === "guide" && (
              <GuidePanel
                guide={guide}
                loading={guideLoading}
                disabled={!paper || paper.status !== "ready"}
                onGenerate={generateGuide}
              />
            )}
            {assistantTab === "chat" && (
              <ChatPanel
                paperId={paper?.status === "ready" ? paper.id : undefined}
                onLocate={(target) => {
                  setTargetCitation({ page: target.page, bbox: null });
                  setReaderPage(target.page);
                }}
              />
            )}
            {assistantTab === "bilingual" && (
              <BilingualReader
                paper={paper}
                compact
                activePage={readerPage}
                sourceSelection={sourceSelection}
                onPairSelect={setPairedSourceText}
              />
            )}
            {assistantTab === "contents" && (
              <StructuredContentView
                paper={paper}
                compact
                onLocate={(target) => {
                  setTargetCitation({ page: target.page, bbox: null });
                  setReaderPage(target.page);
                }}
              />
            )}
          </div>
        </section>
      </div>}
      {view === "logs" && <AgentLogView logs={logs} loading={viewLoading} onRefresh={loadLogs} />}
      {view === "videos" && <VideoLibrary videos={videos} loading={viewLoading} onChanged={loadVideos} />}
      <div hidden={view !== "mindmap"}>
        <MindMapView paper={paper} />
      </div>
    </main>
  );
}
