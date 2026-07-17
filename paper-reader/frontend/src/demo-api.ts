import type { StreamHandlers } from "./services/sse";
import type {
  AgentLog,
  BilingualPage,
  ChatResponse,
  ChunkExplanation,
  Guide,
  GuidePromptInfo,
  LearningResourceType,
  LearningSearchResponse,
  MindMap,
  ModelStatus,
  Paper,
  PaperContentsResponse,
  VideoResource,
  VideoUpdatePayload,
} from "./types";

const DEMO_PAPER_ID = "paperpilot-demo-paper";
const DEMO_COVER = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='640' height='360' viewBox='0 0 640 360'%3E%3Cdefs%3E%3ClinearGradient id='g' x2='1' y2='1'%3E%3Cstop stop-color='%23172b50'/%3E%3Cstop offset='1' stop-color='%23365fd1'/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect width='640' height='360' fill='url(%23g)'/%3E%3Ccircle cx='320' cy='165' r='48' fill='%23ffffff' fill-opacity='.18' stroke='%23ffffff' stroke-opacity='.6'/%3E%3Cpath d='M307 137l42 28-42 28z' fill='white'/%3E%3Ctext x='320' y='258' text-anchor='middle' fill='white' font-size='24' font-family='Arial'%3EPaperPilot Demo%3C/text%3E%3C/svg%3E";

const wait = (milliseconds = 220, signal?: AbortSignal) => new Promise<void>((resolve, reject) => {
  const timer = window.setTimeout(resolve, milliseconds);
  signal?.addEventListener("abort", () => {
    window.clearTimeout(timer);
    reject(new DOMException("The operation was aborted", "AbortError"));
  }, { once: true });
});

const demoPaper: Paper = {
  id: DEMO_PAPER_ID,
  filename: "PaperPilot 示例论文：多 Agent 可追溯学术阅读.pdf",
  file_url: "demo://paperpilot-paper",
  file_size: 813_510,
  status: "ready",
  page_count: 12,
  progress: 100,
  stage: "Pages 演示数据 · 已建立索引",
};

const section = (content: string, page: number) => ({
  content,
  citations: [{ section: `第 ${page} 页`, page }],
});

const demoGuide: Guide = {
  paper_id: DEMO_PAPER_ID,
  title: "多 Agent 可追溯学术阅读系统",
  overview: "本文构建了一个面向学术阅读的多 Agent 协作系统，将论文解析、导读、双语阅读、证据问答和学习资源推荐组织为可追踪工作流。",
  one_liner: "让每一次论文问答都能回到原文证据。",
  background: section("论文阅读工具链分散，生成式答案也常缺少清晰的原文依据。", 2),
  research_question: section("如何统一论文理解、翻译与问答，并保留页码和页内位置级证据？", 2),
  method: section("协调 Agent 识别意图，专业 Agent 共享结构化索引，通过混合检索选择证据。", 4),
  experiment: section("使用上传、解析、导读、问答、引用定位和双语阅读组成端到端验证流程。", 8),
  results: section("核心流程能够返回带页码引用的答案，并从引用卡片跳转到原文位置。", 9),
  innovations: section("把 Agent 执行日志、结构化内容和 PDF 原文统一到同一阅读工作区。", 10),
  limitations: section("静态演示不执行真实 MinerU 解析和大模型调用，完整能力仍需部署后端。", 11),
  key_points: [
    "协调 Agent 根据意图路由任务。",
    "结构化索引保存内容类型、页码与位置。",
    "回答限定在检索证据范围内并返回可点击引用。",
  ],
  reading_questions: [
    "多 Agent 拆分相比单次模型调用有什么工程收益？",
    "引用定位如何提升论文问答的可信度？",
  ],
  keywords: ["多 Agent", "RAG", "论文阅读", "证据溯源"],
  generator: "demo",
  agent_trace_id: "demo-guide-7f31c2",
};

const demoMindMap: MindMap = {
  paper_id: DEMO_PAPER_ID,
  title: "PaperPilot 论文知识结构",
  center: "多 Agent 可追溯学术阅读",
  branches: [
    { label: "研究问题", summary: "降低阅读成本并让答案可以回到原文。", children: ["工具链割裂", "答案缺少证据", "多模态内容分散"] },
    {
      label: "系统方法",
      summary: "以任务路由、结构化解析和检索增强生成形成协作链路。",
      children: ["协调 Agent", "统一论文索引", "Trace ID"],
      subbranches: [
        { label: "论文理解 Agent", children: ["智能导读", "要点提取", "思维导图"] },
        { label: "问答 Agent", children: ["证据检索", "回答生成", "引用定位"] },
      ],
    },
    { label: "关键结果", summary: "核心阅读闭环可以在一个工作台中完成。", children: ["双语阅读", "结构化内容", "可追溯问答", "拓展学习"] },
  ],
  agent_trace_id: "demo-map-91ad04",
};

const counts = { text: 8, image: 2, chart: 1, table: 1, equation: 1 };
const contentItems: Record<string, PaperContentsResponse["items"]> = {
  text: [
    { chunk_id: "demo-text-1", paper_id: DEMO_PAPER_ID, page: 2, kind: "text", content: "PaperPilot 将论文阅读拆分为解析、理解、翻译与问答等可追踪任务。", bbox: [84, 208, 522, 282], metadata: {} },
    { chunk_id: "demo-text-2", paper_id: DEMO_PAPER_ID, page: 7, kind: "text", content: "检索结果携带页码、内容类型和页内坐标，供前端完成引用定位。", bbox: [84, 300, 522, 370], metadata: {} },
  ],
  table: [
    { chunk_id: "demo-table-1", paper_id: DEMO_PAPER_ID, page: 8, kind: "table", content: "协调 Agent：意图识别与任务路由；问答 Agent：证据检索、答案生成与引用回传。", bbox: [88, 182, 510, 378], metadata: { table_text: "模块 | 主要职责 | 输出" } },
  ],
  equation: [
    { chunk_id: "demo-equation-1", paper_id: DEMO_PAPER_ID, page: 6, kind: "equation", content: "score(q,c)=alpha*semantic(q,c)+beta*keyword(q,c)", bbox: [116, 320, 492, 365], metadata: { latex: "s(q,c)=\\alpha s_{semantic}+\\beta s_{keyword}" } },
  ],
  chart: [
    { chunk_id: "demo-chart-1", paper_id: DEMO_PAPER_ID, page: 9, kind: "chart", content: "核心流程验证：上传、解析、导读、问答和引用定位均完成。", bbox: [102, 160, 516, 410], metadata: {} },
  ],
  image: [
    { chunk_id: "demo-image-1", paper_id: DEMO_PAPER_ID, page: 3, kind: "image", content: "系统架构：前端、统一 API、协调 Agent、专业 Agent 与知识库。", bbox: [76, 146, 532, 432], metadata: {} },
    { chunk_id: "demo-image-2", paper_id: DEMO_PAPER_ID, page: 5, kind: "image", content: "从用户问题到可追溯答案的 Agent 协作时序。", bbox: [90, 194, 518, 438], metadata: {} },
  ],
};

const makeVideo = (id: string, title: string, description: string): VideoResource => ({
  id,
  title,
  description,
  cover_url: DEMO_COVER,
  source: "PaperPilot Pages 演示",
  keywords: ["RAG", "Agent"],
  tags: ["学术阅读", "演示资源"],
  knowledge_points: ["向量检索", "任务编排"],
  file_url: `demo://video/${id}`,
  local_path: "Pages 演示资源（未加载本地 MP4）",
  recommendation_reason: "帮助理解论文中的检索与 Agent 协作流程。",
});

let papers: Paper[] = [demoPaper];
let videos: VideoResource[] = [
  makeVideo("demo-rag", "RAG 与证据检索入门", "理解论文问答中的检索、证据选择和引用生成。"),
  makeVideo("demo-agent", "多 Agent 任务编排基础", "了解协调 Agent 如何把复杂任务分派给专业 Agent。"),
];
let logs: AgentLog[] = [
  { trace_id: "demo-upload-a81b2e", agent: "coordinator-agent", action: "route.paper.parse", detail: "已将示例论文交给结构化解析服务", created_at: "2026-07-18T09:00:00+08:00" },
  { trace_id: "demo-guide-7f31c2", agent: "paper-understanding-agent", action: "paper.guide", detail: "已生成九项结构化导读", created_at: "2026-07-18T09:00:02+08:00" },
  { trace_id: "demo-chat-d2104f", agent: "chat-agent", action: "paper.answer", detail: "已生成带页码引用的回答", created_at: "2026-07-18T09:00:04+08:00" },
];

function addLog(agent: string, action: string, detail: string) {
  logs = [...logs, { trace_id: `demo-${Date.now().toString(16)}`, agent, action, detail, created_at: new Date().toISOString() }];
}

function bilingualPage(page: number): BilingualPage {
  return {
    paper_id: DEMO_PAPER_ID,
    page,
    target_language: "中文",
    blocks: [
      { chunk_id: `demo-bilingual-${page}-title`, page, kind: "text", source_text: "Traceable Multi-Agent Academic Reading", translated_text: "可追溯的多 Agent 学术阅读", metadata: { text_level: 1 } },
      { chunk_id: `demo-bilingual-${page}-body`, page, kind: "text", source_text: "PaperPilot coordinates specialized agents over a shared structured paper index.", translated_text: "PaperPilot 基于共享的结构化论文索引协调多个专业 Agent。", metadata: {} },
    ],
    agent_trace_id: `demo-bilingual-${page}`,
  };
}

const demoChatAnswer = "这篇论文解决了学术阅读工具链割裂和答案难以溯源的问题。系统使用协调 Agent 完成任务路由，并让专业 Agent 结合结构化论文索引生成导读、翻译和带原文定位的回答。";
const demoChatResult = (): ChatResponse => ({
  answer: demoChatAnswer,
  citations: [
    { chunk_id: "demo-citation-1", page: 2, quote: "将论文阅读拆分为解析、理解、翻译和问答等可追踪任务。", kind: "text", section: "研究背景", bbox: [84, 208, 522, 282] },
    { chunk_id: "demo-citation-2", page: 7, quote: "检索结果保留页码与页内坐标，用于答案溯源和原文定位。", kind: "text", section: "可追溯问答", bbox: [84, 300, 522, 370] },
  ],
  videos: [videos[0]],
  agent_trace_id: `demo-chat-${Date.now().toString(16)}`,
});

export const demoApi = {
  modelStatus: async (): Promise<ModelStatus> => ({ provider: "demo", configured: true, base_url: "static-demo", model: "Pages 演示模型", thinking: false, warning: "当前为静态演示模式" }),
  listPapers: async () => { await wait(80); return [...papers]; },
  getPaper: async (paperId: string) => papers.find((paper) => paper.id === paperId) ?? demoPaper,
  uploadPaper: async (file: File) => {
    await wait(420);
    const created = { ...demoPaper, id: `demo-upload-${Date.now()}`, filename: `${file.name}（浏览器演示）`, stage: "演示模式 · 未上传服务器" };
    papers = [created, ...papers];
    addLog("coordinator-agent", "demo.paper.upload", `已在演示模式载入 ${file.name}`);
    return created;
  },
  cachedGuide: async () => { await wait(); return demoGuide; },
  createGuide: async () => { await wait(420); addLog("paper-understanding-agent", "paper.guide", "已重新生成演示导读"); return demoGuide; },
  streamGuide: async (_paperId: string, _refresh: boolean, _promptKey: string | undefined, handlers: StreamHandlers<Guide>, signal?: AbortSignal) => {
    handlers.onStatus?.({ message: "正在读取论文结构" });
    await wait(180, signal);
    handlers.onProgress?.({ message: "正在组织九项结构化导读", progress: 65 });
    await wait(220, signal);
    handlers.onComplete(demoGuide);
    addLog("paper-understanding-agent", "paper.guide.stream", "已完成演示流式导读");
  },
  guidePrompts: async (): Promise<GuidePromptInfo[]> => [
    { key: "general", name: "通用学术导读", domain: "通用", audience: "大学生与研究入门者", description: "突出研究问题、方法、结果与局限", is_default: true },
    { key: "method", name: "方法精读", domain: "计算机科学", audience: "复现与工程实践者", description: "重点解释系统架构和方法流程", is_default: false },
  ],
  retryPaper: async (paperId: string) => papers.find((paper) => paper.id === paperId) ?? demoPaper,
  cachedMindMap: async () => { await wait(); return demoMindMap; },
  createMindMap: async () => { await wait(360); addLog("paper-understanding-agent", "paper.mind_map", "已生成演示思维导图"); return demoMindMap; },
  deletePaper: async (paperId: string) => { await wait(120); papers = papers.filter((paper) => paper.id !== paperId); },
  paperContents: async (_paperId: string, kind: string, includeAll = false): Promise<PaperContentsResponse> => {
    await wait();
    const items = contentItems[kind] ?? [];
    return { paper_id: DEMO_PAPER_ID, total: items.length, counts, items, hidden: includeAll ? 0 : Math.max(0, (counts[kind as keyof typeof counts] ?? items.length) - items.length) };
  },
  explainChunk: async (_paperId: string, chunkId: string): Promise<ChunkExplanation> => ({ paper_id: DEMO_PAPER_ID, chunk_id: chunkId, page: 7, explanation: "该切片说明了 PaperPilot 如何保留证据位置，并把检索结果连接到 PDF 原文。", agent_trace_id: `demo-explain-${Date.now().toString(16)}` }),
  chat: async () => { await wait(420); return demoChatResult(); },
  streamChat: async (_paperId: string, question: string, handlers: StreamHandlers<ChatResponse>, signal?: AbortSignal) => {
    handlers.onStatus?.({ message: "正在检索论文知识库" });
    await wait(150, signal);
    handlers.onEvidence?.({ count: 2 });
    handlers.onStatus?.({ message: "已找到 2 条原文证据，正在组织回答" });
    for (const text of ["这篇论文解决了学术阅读工具链割裂", "和答案难以溯源的问题。", "系统通过协调 Agent、结构化索引与证据引用形成完整阅读闭环。"]) {
      await wait(110, signal);
      handlers.onDelta?.({ text });
    }
    handlers.onComplete(demoChatResult());
    addLog("chat-agent", "paper.answer.stream", `演示问答：${question.slice(0, 30)}`);
  },
  translate: async (_paperId: string, text: string) => {
    await wait(320);
    addLog("translation-agent", "paper.translate", "已完成演示段落翻译");
    return { translated_text: `演示译文：本文提出一个多 Agent 论文阅读框架，用于协调整体理解、证据检索与可追溯问答。\n\n原文片段：${text.slice(0, 80)}${text.length > 80 ? "…" : ""}` };
  },
  cachedBilingual: async (_paperId: string, page: number) => { await wait(); return bilingualPage(page); },
  createBilingual: async (_paperId: string, page: number) => { await wait(360); addLog("translation-agent", "paper.bilingual", `已生成第 ${page} 页演示译文`); return bilingualPage(page); },
  listVideos: async () => { await wait(); return [...videos]; },
  createVideo: async (body: FormData) => {
    await wait(220);
    const created = makeVideo(`demo-${Date.now()}`, String(body.get("title") || "新演示视频"), String(body.get("description") || "浏览器内演示资源"));
    videos = [created, ...videos];
    return created;
  },
  updateVideo: async (videoId: string, payload: VideoUpdatePayload) => {
    await wait(180);
    videos = videos.map((video) => video.id === videoId ? { ...video, ...payload } : video);
    return videos.find((video) => video.id === videoId) ?? videos[0];
  },
  deleteVideo: async (videoId: string) => { await wait(120); videos = videos.filter((video) => video.id !== videoId); },
  searchLearning: async (query: string, _paperId: string | null, resourceTypes: LearningResourceType[]): Promise<LearningSearchResponse> => {
    await wait(420);
    const allResources: LearningSearchResponse["resources"] = [
      { id: "demo-learning-paper", resource_type: "paper", title: "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks", description: "RAG 的代表性研究，用于理解检索与生成的结合。", source: "PaperPilot 演示目录", url: "https://arxiv.org/abs/2005.11401", authors: ["Patrick Lewis et al."], published_year: 2020, tags: ["RAG", "检索"], relevance_reason: "解释论文问答中的证据检索基础。", local: false },
      { id: "demo-learning-doc", resource_type: "documentation", title: "PaperPilot 项目源码", description: "查看系统架构、接口和部署方式。", source: "GitHub", url: "https://github.com/Icey18899877399/PaperPilot", authors: ["PaperPilot Team"], tags: ["Agent", "学术阅读"], relevance_reason: "可进一步阅读真实实现。", local: false },
      { id: "demo-learning-video", resource_type: "video", title: videos[0].title, description: videos[0].description, source: "本地演示资源", url: "#", authors: [], tags: videos[0].tags, relevance_reason: "补充理解检索和证据引用。", local: true },
    ];
    const resources = allResources.filter((item) => !resourceTypes.length || resourceTypes.includes(item.resource_type));
    return { query, interpreted_query: `围绕“${query}”检索论文、文档与学习资源`, summary: "建议先理解 RAG 证据检索，再阅读多 Agent 编排和可观测性材料。", learning_path: ["理解 RAG 基本流程", "阅读 PaperPilot 系统架构", "结合示例论文体验引用定位"], resources, providers: [{ provider: "Pages 演示目录", enabled: true, success: true, message: "已返回浏览器内置演示资源" }], agent_trace_id: `demo-learning-${Date.now().toString(16)}` };
  },
  agentLogs: async (limit = 100) => { await wait(100); return logs.slice(-limit); },
};
