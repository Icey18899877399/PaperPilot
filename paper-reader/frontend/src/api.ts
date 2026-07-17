import type {
  AgentLog,
  BilingualPage,
  ChunkExplanation,
  ChatResponse,
  Guide,
  GuidePromptInfo,
  LearningResourceType,
  LearningSearchResponse,
  MindMap,
  ModelStatus,
  Paper,
  PaperContentsResponse,
  VideoResource,
  VideoUpdatePayload
} from "./types";
import { postEventStream, type StreamHandlers } from "./services/sse";

// 默认120秒超时：覆盖导读/解析等长耗时LLM请求，同时避免请求悬挂无反馈
const REQUEST_TIMEOUT_MS = 120_000;

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(url, { ...options, signal: controller.signal });
  } catch (reason) {
    if ((reason as Error).name === "AbortError") {
      throw new Error("请求超时，请检查后端服务后重试");
    }
    throw new Error("网络请求失败，请确认后端服务已启动");
  } finally {
    window.clearTimeout(timer);
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `请求失败：${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  modelStatus: () => request<ModelStatus>("/api/models/status"),

  listPapers: () => request<Paper[]>("/api/papers"),

  getPaper: (paperId: string) => request<Paper>(`/api/papers/${paperId}`),

  uploadPaper: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<Paper>("/api/papers?background=true", { method: "POST", body });
  },

  cachedGuide: async (paperId: string) => {
    const response = await fetch(`/api/papers/${paperId}/guide`);
    if (response.status === 404) return null;
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      throw new Error(payload?.detail ?? `请求失败：${response.status}`);
    }
    return response.json() as Promise<Guide>;
  },

  createGuide: (paperId: string, refresh = false, promptKey?: string) =>
    request<Guide>(
      `/api/papers/${paperId}/guide?refresh=${refresh}` +
        (promptKey ? `&prompt_key=${encodeURIComponent(promptKey)}` : ""),
      { method: "POST" },
    ),

  streamGuide: (
    paperId: string,
    refresh: boolean,
    promptKey: string | undefined,
    handlers: StreamHandlers<Guide>,
    signal?: AbortSignal,
  ) => postEventStream<Guide>(
    `/api/papers/${paperId}/guide/stream?refresh=${refresh}`
      + (promptKey ? `&prompt_key=${encodeURIComponent(promptKey)}` : ""),
    {},
    handlers,
    signal,
  ),

  guidePrompts: () => request<GuidePromptInfo[]>("/api/models/guide-prompts"),

  retryPaper: (paperId: string) =>
    request<Paper>(`/api/papers/${paperId}/retry?background=true`, { method: "POST" }),

  cachedMindMap: async (paperId: string) => {
    const response = await fetch(`/api/papers/${paperId}/mind-map`);
    if (response.status === 404) return null;
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      throw new Error(payload?.detail ?? `请求失败：${response.status}`);
    }
    return response.json() as Promise<MindMap>;
  },

  createMindMap: (paperId: string, refresh = false) =>
    request<MindMap>(
      `/api/papers/${paperId}/mind-map?refresh=${refresh}`,
      { method: "POST" }
    ),

  deletePaper: async (paperId: string) => {
    const response = await fetch(`/api/papers/${paperId}`, { method: "DELETE" });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      throw new Error(payload?.detail ?? `删除失败：${response.status}`);
    }
  },

  paperContents: (paperId: string, kind: string, includeAll = false) =>
    request<PaperContentsResponse>(
      `/api/papers/${paperId}/contents?kind=${encodeURIComponent(kind)}&include_all=${includeAll}`
    ),

  explainChunk: (paperId: string, chunkId: string) =>
    request<ChunkExplanation>(
      `/api/papers/${paperId}/chunks/${encodeURIComponent(chunkId)}/explanation`,
      { method: "POST" }
    ),

  chat: (paperId: string, question: string) =>
    request<ChatResponse>("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paper_id: paperId, question })
    }),

  streamChat: (
    paperId: string,
    question: string,
    handlers: StreamHandlers<ChatResponse>,
    signal?: AbortSignal,
  ) => postEventStream<ChatResponse>(
    "/api/chat/stream",
    { paper_id: paperId, question },
    handlers,
    signal,
  ),

  translate: (paperId: string, text: string) =>
    request<{ translated_text: string }>(`/api/papers/${paperId}/translate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, target_language: "中文" })
    }),

  cachedBilingual: async (paperId: string, page: number) => {
    const response = await fetch(`/api/papers/${paperId}/bilingual/${page}`);
    if (response.status === 404) return null;
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      throw new Error(payload?.detail ?? `请求失败：${response.status}`);
    }
    return response.json() as Promise<BilingualPage>;
  },

  createBilingual: (paperId: string, page: number, refresh = false) =>
    request<BilingualPage>(
      `/api/papers/${paperId}/bilingual/${page}?refresh=${refresh}`,
      { method: "POST" }
    ),

  listVideos: () => request<VideoResource[]>("/api/videos"),

  createVideo: (body: FormData) =>
    request<VideoResource>("/api/videos", { method: "POST", body }),

  updateVideo: (videoId: string, payload: VideoUpdatePayload) =>
    request<VideoResource>(`/api/videos/${videoId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),

  deleteVideo: async (videoId: string, deleteFile = false) => {
    const response = await fetch(`/api/videos/${videoId}?delete_file=${deleteFile}`, { method: "DELETE" });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      throw new Error(payload?.detail ?? `删除失败：${response.status}`);
    }
  },

  searchLearning: (
    query: string,
    paperId: string | null,
    resourceTypes: LearningResourceType[]
  ) => request<LearningSearchResponse>("/api/learning/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      paper_id: paperId || null,
      resource_types: resourceTypes
    })
  }),

  agentLogs: (limit = 100) =>
    request<AgentLog[]>(`/api/agents/logs?limit=${limit}`)
};
