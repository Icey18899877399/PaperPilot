import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { api } from "./api";
import { BilingualReader } from "./components/BilingualReader";
import { ChatPanel } from "./components/ChatPanel";
import { ConfirmDialog } from "./components/ConfirmDialog";
import { GuidePanel } from "./components/GuidePanel";
import { PaperReader } from "./components/PaperReader";
import { StructuredContentView } from "./components/StructuredContentView";
import { ToastStack } from "./components/Toast";
import { UploadPanel } from "./components/UploadPanel";
import { useToast } from "./hooks/useToast";
import { useWorkspaceResize } from "./hooks/useWorkspaceResize";
import type { AgentLog, CitationTarget, Guide, ModelStatus, Paper, VideoResource } from "./types";

type View = "workspace" | "mindmap" | "logs" | "learning";
type AssistantTab = "guide" | "chat" | "bilingual" | "contents";
type NavIconName =
  | "workspace"
  | "mindmap"
  | "logs"
  | "learning"
  | "guide"
  | "chat"
  | "bilingual"
  | "contents";

function NavIcon({ name }: { name: NavIconName }) {
  const paths: Record<NavIconName, ReactNode> = {
    workspace: (
      <>
        <rect x="3" y="4" width="7" height="16" rx="2" />
        <rect x="14" y="4" width="7" height="16" rx="2" />
      </>
    ),
    mindmap: (
      <>
        <circle cx="12" cy="5" r="2" />
        <circle cx="5" cy="18" r="2" />
        <circle cx="19" cy="18" r="2" />
        <path d="M12 7v4M5 16v-3h14v3" />
      </>
    ),
    logs: (
      <>
        <path d="M5 4h14v16H5z" />
        <path d="M8 8h8M8 12h8M8 16h5" />
      </>
    ),
    learning: (
      <>
        <path d="m3 7 9-4 9 4-9 4-9-4Z" />
        <path d="M6 9.5V15c3 2.4 9 2.4 12 0V9.5" />
      </>
    ),
    guide: (
      <>
        <path d="M5 4h10a4 4 0 0 1 4 4v12H8a3 3 0 0 1-3-3V4Z" />
        <path d="M8 8h7M8 12h5" />
        <path d="m18 3 .6 1.5L20 5l-1.4.5L18 7l-.6-1.5L16 5l1.4-.5L18 3Z" />
      </>
    ),
    chat: (
      <>
        <path d="M4 5h16v11H9l-5 4V5Z" />
        <path d="M8 9h8M8 12h5" />
      </>
    ),
    bilingual: (
      <>
        <path d="M4 5h7v14H4zM13 5h7v14h-7z" />
        <path d="M6.5 9h2M15.5 9h2M6.5 13h2M15.5 13h2" />
      </>
    ),
    contents: (
      <>
        <rect x="3" y="4" width="7" height="7" rx="1.5" />
        <rect x="14" y="4" width="7" height="7" rx="1.5" />
        <rect x="3" y="15" width="7" height="5" rx="1.5" />
        <rect x="14" y="15" width="7" height="5" rx="1.5" />
      </>
    ),
  };
  return (
    <svg className="nav-label-icon" viewBox="0 0 24 24" aria-hidden="true">
      {paths[name]}
    </svg>
  );
}

function BrandIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3.5 6.2c3.2-.75 6.05.05 8.5 2.15V19.5c-2.45-2.1-5.3-2.9-8.5-2.15V6.2Z" />
      <path d="M20.5 6.2c-3.2-.75-6.05.05-8.5 2.15V19.5c2.45-2.1 5.3-2.9 8.5-2.15V6.2Z" />
      <path d="M12 8.35V19.5" />
    </svg>
  );
}

// 第四批工程化：非首屏模块按需加载，避免Markmap与学习模块挤入阅读工作台首包。
const AgentLogView = lazy(() => import("./components/AgentLogView").then(
  (module) => ({ default: module.AgentLogView }),
));
const ExtendedLearning = lazy(() => import("./components/ExtendedLearning").then(
  (module) => ({ default: module.ExtendedLearning }),
));
const MindMapView = lazy(() => import("./components/MindMapView").then(
  (module) => ({ default: module.MindMapView }),
));

function ViewFallback() {
  return (
    <div className="view-loading" role="status">
      <span />
      正在载入功能模块…
    </div>
  );
}

export default function App() {
  const [papers, setPapers] = useState<Paper[]>([]);
  const [paper, setPaper] = useState<Paper | null>(null);
  const [guide, setGuide] = useState<Guide | null>(null);
  const [uploading, setUploading] = useState(false);
  const [guideLoading, setGuideLoading] = useState(false);
  const [guideStreamStatus, setGuideStreamStatus] = useState("");
  const [targetCitation, setTargetCitation] = useState<CitationTarget | null>(null);
  const [chatPrefill, setChatPrefill] = useState<{ text: string; nonce: number } | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Paper | null>(null);
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null);
  const [view, setView] = useState<View>("workspace");
  const [assistantTab, setAssistantTab] = useState<AssistantTab>("guide");
  const [readerPage, setReaderPage] = useState(1);
  const [sourceSelection, setSourceSelection] = useState("");
  const [pairedSourceText, setPairedSourceText] = useState("");
  const [logs, setLogs] = useState<AgentLog[]>([]);
  const [videos, setVideos] = useState<VideoResource[]>([]);
  const [viewLoading, setViewLoading] = useState(false);
  const [deletingPaperId, setDeletingPaperId] = useState<string | null>(null);
  const [retryingPaperId, setRetryingPaperId] = useState<string | null>(null);
  const monitoringPapers = useRef(new Set<string>());
  const guideRequest = useRef<AbortController | null>(null);
  const { toasts, notify, dismissToast } = useToast();
  const { startResize, workspaceStyle } = useWorkspaceResize();

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
    window.scrollTo({ top: 0, behavior: "auto" });
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
            notify("error", updated.error || `「${updated.filename}」解析失败，可在列表中重试`);
          }
          return;
        }
      }
      notify("error", "论文解析时间过长，请稍后刷新论文状态");
    } catch (reason) {
      notify("error", (reason as Error).message);
    } finally {
      monitoringPapers.current.delete(paperId);
    }
  }

  useEffect(() => {
    api.listPapers().then((items) => {
      setPapers(items);
      items.filter((item) => item.status === "parsing")
        .forEach((item) => void monitorPaper(item.id));
    }).catch(() => {
      notify("error", "无法连接后端服务（8000端口），请先启动后端再刷新页面");
    });
    api.modelStatus().then(setModelStatus).catch(() => undefined);
  }, []);

  useEffect(() => {
    guideRequest.current?.abort();
    guideRequest.current = null;
    setGuideStreamStatus("");
    setGuide(null);
    if (!paper || paper.status !== "ready") return;
    let cancelled = false;
    setGuideLoading(true);
    api.cachedGuide(paper.id)
      .then((cached) => {
        if (!cancelled) setGuide(cached);
      })
      .catch((reason) => {
        if (!cancelled) notify("error", (reason as Error).message);
      })
      .finally(() => {
        if (!cancelled) setGuideLoading(false);
      });
    return () => { cancelled = true; };
  }, [paper?.id, paper?.status]);

  const loadLogs = async () => {
    setViewLoading(true);
    try {
      setLogs(await api.agentLogs());
    } catch (reason) {
      notify("error", (reason as Error).message);
    } finally {
      setViewLoading(false);
    }
  };

  const loadVideos = async () => {
    setViewLoading(true);
    try {
      setVideos(await api.listVideos());
    } catch (reason) {
      notify("error", (reason as Error).message);
    } finally {
      setViewLoading(false);
    }
  };

  useEffect(() => {
    if (view === "logs") void loadLogs();
    if (view === "learning") void loadVideos();
  }, [view]);

  const upload = async (file: File) => {
    setUploading(true);
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
      notify("error", (reason as Error).message);
    } finally {
      setUploading(false);
    }
  };

  const generateGuide = async (promptKey?: string) => {
    if (!paper) return;
    guideRequest.current?.abort();
    const controller = new AbortController();
    guideRequest.current = controller;
    setGuideLoading(true);
    setGuideStreamStatus("正在连接论文理解 Agent");
    try {
      await api.streamGuide(
        paper.id,
        Boolean(guide),
        promptKey,
        {
          onStatus: (payload) => {
            if (typeof payload.message === "string") setGuideStreamStatus(payload.message);
          },
          onProgress: (payload) => {
            if (typeof payload.message === "string") setGuideStreamStatus(payload.message);
          },
          onComplete: setGuide,
        },
        controller.signal,
      );
    } catch (reason) {
      if ((reason as Error).name === "AbortError") return;
      notify("error", (reason as Error).message);
    } finally {
      if (guideRequest.current === controller) guideRequest.current = null;
      setGuideLoading(false);
      setGuideStreamStatus("");
    }
  };

  const retryPaper = async (item: Paper) => {
    if (item.status !== "failed" || retryingPaperId) return;
    setRetryingPaperId(item.id);
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
      notify("error", (reason as Error).message);
    } finally {
      setRetryingPaperId(null);
    }
  };

  const requestDeletePaper = (item: Paper) => {
    if (item.status === "parsing" || deletingPaperId) return;
    setPendingDelete(item);
  };

  const confirmDeletePaper = async () => {
    const item = pendingDelete;
    if (!item) return;
    setDeletingPaperId(item.id);
    try {
      await api.deletePaper(item.id);
      setPapers((items) => items.filter((value) => value.id !== item.id));
      if (paper?.id === item.id) {
        setPaper(null);
        setGuide(null);
        setTargetCitation(null);
      }
      notify("success", `已删除「${item.filename}」及其解析数据`);
      setPendingDelete(null);
    } catch (reason) {
      notify("error", (reason as Error).message);
    } finally {
      setDeletingPaperId(null);
    }
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-mark"><BrandIcon /></div>
        <div className="brand-copy">
          <strong>PaperPilot</strong>
          <span>多 Agent 论文智能阅读系统</span>
        </div>
        <nav aria-label="主功能导航">
          <div className="topnav-segmented" role="group" aria-label="页面视图切换">
            <button
              className={`topnav-item ${view === "workspace" ? "active" : ""}`}
              aria-current={view === "workspace" ? "page" : undefined}
              aria-label="阅读工作台"
              title="阅读工作台"
              onClick={() => openView("workspace")}
            ><NavIcon name="workspace" /><span>阅读工作台</span></button>
            <button
              className={`topnav-item ${view === "mindmap" ? "active" : ""}`}
              aria-current={view === "mindmap" ? "page" : undefined}
              aria-label="思维导图"
              title="思维导图"
              onClick={() => openView("mindmap")}
            ><NavIcon name="mindmap" /><span>思维导图</span></button>
            <button
              className={`topnav-item ${view === "logs" ? "active" : ""}`}
              aria-current={view === "logs" ? "page" : undefined}
              aria-label="Agent 日志"
              title="Agent 日志"
              onClick={() => openView("logs")}
            ><NavIcon name="logs" /><span>Agent 日志</span></button>
            <button
              className={`topnav-item ${view === "learning" ? "active" : ""}`}
              aria-current={view === "learning" ? "page" : undefined}
              aria-label="拓展学习"
              title="拓展学习"
              onClick={() => openView("learning")}
            ><NavIcon name="learning" /><span>拓展学习</span></button>
          </div>
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

      <ToastStack toasts={toasts} onClose={dismissToast} />

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
                    <strong title={item.filename}>{item.filename}</strong>
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
                    onClick={() => requestDeletePaper(item)}
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
              className={`assistant-tab assistant-tab-guide ${assistantTab === "guide" ? "active" : ""}`}
              aria-current={assistantTab === "guide" ? "page" : undefined}
              onClick={() => setAssistantTab("guide")}
            ><NavIcon name="guide" /><span>智能导读</span></button>
            <button
              className={`assistant-tab assistant-tab-chat ${assistantTab === "chat" ? "active" : ""}`}
              aria-current={assistantTab === "chat" ? "page" : undefined}
              onClick={() => setAssistantTab("chat")}
            ><NavIcon name="chat" /><span>论文对话</span></button>
            <button
              className={`assistant-tab assistant-tab-bilingual ${assistantTab === "bilingual" ? "active" : ""}`}
              aria-current={assistantTab === "bilingual" ? "page" : undefined}
              onClick={() => setAssistantTab("bilingual")}
            ><NavIcon name="bilingual" /><span>中英对照</span></button>
            <button
              className={`assistant-tab assistant-tab-contents ${assistantTab === "contents" ? "active" : ""}`}
              aria-current={assistantTab === "contents" ? "page" : undefined}
              onClick={() => setAssistantTab("contents")}
            ><NavIcon name="contents" /><span>结构化切片</span></button>
          </nav>
          <div className="assistant-panel-body">
            {assistantTab === "guide" && (
              <GuidePanel
                guide={guide}
                loading={guideLoading}
                streamStatus={guideStreamStatus}
                disabled={!paper || paper.status !== "ready"}
                onGenerate={generateGuide}
                onLocate={(page) => {
                  // US-02：点击导读引用页码跳转到PDF对应页
                  setTargetCitation({ page, bbox: null });
                }}
                onAsk={(question) => {
                  // US-02：导读思考题一键转入论文对话（US-05入口）
                  setChatPrefill({ text: question, nonce: Date.now() });
                  setAssistantTab("chat");
                }}
              />
            )}
            {assistantTab === "chat" && (
              <ChatPanel
                paperId={paper?.status === "ready" ? paper.id : undefined}
                prefill={chatPrefill}
                onPrefillConsumed={() => setChatPrefill(null)}
                onLocate={(target) => {
                  setTargetCitation({ page: target.page, bbox: target.bbox ?? null });
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
      <Suspense fallback={<ViewFallback />}>
        {view === "logs" && (
          <AgentLogView logs={logs} loading={viewLoading} onRefresh={loadLogs} />
        )}
        {view === "learning" && (
          <ExtendedLearning
            papers={papers}
            activePaper={paper}
            videos={videos}
            loading={viewLoading}
            onVideosChanged={loadVideos}
          />
        )}
        {view === "mindmap" && <MindMapView paper={paper} />}
      </Suspense>
      <ConfirmDialog
        open={pendingDelete !== null}
        title={`删除「${pendingDelete?.filename ?? ""}」？`}
        body="将同时删除原始PDF、解析资源、检索索引、导读与思维导图，且不可恢复。"
        confirmText="删除"
        danger
        busy={deletingPaperId !== null}
        onConfirm={() => void confirmDeletePaper()}
        onCancel={() => setPendingDelete(null)}
      />
    </main>
  );
}
