export type PaperStatus = "uploaded" | "parsing" | "ready" | "failed";

export interface Paper {
  id: string;
  filename: string;
  file_url: string;
  file_sha256?: string | null;
  file_size?: number;
  status: PaperStatus;
  page_count: number;
  progress: number;
  stage: string;
  error?: string | null;
}

export interface Citation {
  chunk_id: string;
  page: number;
  quote: string;
  kind: string;
  resource_url?: string | null;
  bbox?: number[] | null;
}

export interface CitationTarget {
  page: number;
  bbox?: number[] | null;
}

export interface PaperChunk {
  chunk_id: string;
  paper_id: string;
  page: number;
  kind: string;
  content: string;
  resource_url?: string | null;
  bbox?: number[] | null;
  metadata: Record<string, unknown>;
}

export interface PaperContentsResponse {
  paper_id: string;
  total: number;
  counts: Record<string, number>;
  items: PaperChunk[];
}

export interface ChunkExplanation {
  paper_id: string;
  chunk_id: string;
  page: number;
  explanation: string;
  agent_trace_id: string;
}

export interface BilingualBlock {
  chunk_id: string;
  page: number;
  kind: string;
  source_text: string;
  translated_text: string;
  resource_url?: string | null;
  bbox?: number[] | null;
  metadata: Record<string, unknown>;
}

export interface BilingualPage {
  paper_id: string;
  page: number;
  target_language: string;
  blocks: BilingualBlock[];
  agent_trace_id: string;
}

export interface VideoResource {
  id: string;
  title: string;
  description: string;
  cover_url: string;
  source: string;
  keywords: string[];
  tags: string[];
  knowledge_points: string[];
  file_url: string;
  local_path: string;
  file_sha256?: string | null;
  recommendation_reason?: string | null;
}

export interface VideoUpdatePayload {
  title?: string;
  description?: string;
  source?: string;
  keywords?: string[];
  tags?: string[];
  knowledge_points?: string[];
}

export type LearningResourceType =
  | "paper"
  | "video"
  | "article"
  | "course"
  | "documentation"
  | "local";

export interface LearningResource {
  id: string;
  resource_type: LearningResourceType;
  title: string;
  description: string;
  source: string;
  url: string;
  authors: string[];
  published_year?: number | null;
  thumbnail_url?: string | null;
  tags: string[];
  relevance_reason: string;
  local: boolean;
}

export interface LearningProviderStatus {
  provider: string;
  enabled: boolean;
  success: boolean;
  message: string;
}

export interface LearningSearchResponse {
  query: string;
  interpreted_query: string;
  summary: string;
  learning_path: string[];
  resources: LearningResource[];
  providers: LearningProviderStatus[];
  agent_trace_id: string;
}

export interface Guide {
  paper_id: string;
  title: string;
  overview: string;
  key_points: string[];
  reading_questions: string[];
  agent_trace_id: string;
}

export interface MindMapBranch {
  label: string;
  summary: string;
  children: string[];
  subbranches?: MindMapSubBranch[];
}

export interface MindMapSubBranch {
  label: string;
  children: string[];
}

export interface MindMap {
  paper_id: string;
  title: string;
  center: string;
  branches: MindMapBranch[];
  agent_trace_id: string;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  videos: VideoResource[];
  agent_trace_id: string;
  conversation_id: string;
  evidence_sufficient: boolean;
}

export interface MessageRecord {
  id: string;
  role: "user" | "assistant";
  text: string;
  citations: Citation[];
  videos: VideoResource[];
  evidence_sufficient: boolean;
  created_at: string;
}

export interface Conversation {
  id: string;
  paper_id: string;
  title: string;
  messages: MessageRecord[];
  created_at: string;
  updated_at: string;
}

export interface ModelStatus {
  provider: string;
  configured: boolean;
  base_url: string;
  model: string;
  thinking: boolean;
  warning?: string | null;
}

export interface AgentLog {
  trace_id: string;
  agent: string;
  action: string;
  detail: string;
  created_at: string;
}