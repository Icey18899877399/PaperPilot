import { FormEvent, useCallback, useEffect, useState } from "react";

import { api } from "../api";
import type { ChatResponse, CitationTarget, Conversation } from "../types";
import { VideoPlayer } from "./VideoPlayer";

interface Message {
  role: "user" | "assistant";
  text: string;
  result?: ChatResponse;
}

interface Props {
  paperId?: string;
  onLocate: (target: CitationTarget) => void;
}

const kindLabels: Record<string, string> = {
  text: "正文",
  image: "图片",
  chart: "图表",
  table: "表格",
  equation: "公式",
  code: "代码",
  list: "列表"
};

export function ChatPanel({ paperId, onLocate }: Props) {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [switchLoading, setSwitchLoading] = useState(false);

  // ── load conversation list when paper changes ───────────────────
  const loadConversations = useCallback(async (paperId: string) => {
    try {
      const list = await api.listConversations(paperId);
      setConversations(list);
      return list;
    } catch {
      setConversations([]);
      return [];
    }
  }, []);

  useEffect(() => {
    if (!paperId) {
      setMessages([]);
      setConversations([]);
      setConversationId(null);
      return;
    }
    // reset state for new paper
    setMessages([]);
    setConversationId(null);
    void loadConversations(paperId);
  }, [paperId, loadConversations]);

  // ── load conversation messages when switching conversations ─────
  const loadConversation = useCallback(
    async (convId: string) => {
      if (!paperId) return;
      setSwitchLoading(true);
      try {
        const conv = await api.getConversation(paperId, convId);
        setMessages(
          conv.messages.map((msg) => ({
            role: msg.role as "user" | "assistant",
            text: msg.text,
            result:
              msg.role === "assistant"
                ? {
                    answer: msg.text,
                    citations: msg.citations ?? [],
                    videos: msg.videos ?? [],
                    agent_trace_id: "",
                    conversation_id: convId,
                    evidence_sufficient: msg.evidence_sufficient ?? true,
                  }
                : undefined,
          }))
        );
      } catch {
        // conversation not found → remove from list, start fresh
        setConversations((items) => items.filter((c) => c.id !== convId));
        setConversationId(null);
        setMessages([]);
      } finally {
        setSwitchLoading(false);
      }
    },
    [paperId]
  );

  // ── send message ────────────────────────────────────────────────
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const current = question.trim();
    if (!paperId || !current || loading) return;
    setQuestion("");
    setMessages((items) => [...items, { role: "user", text: current }]);
    setLoading(true);
    try {
      const result = await api.chat(paperId, current, conversationId ?? undefined);
      // persist conversation id
      if (result.conversation_id && !conversationId) {
        setConversationId(result.conversation_id);
        // refresh conversation list
        void loadConversations(paperId);
      }
      setMessages((items) => [
        ...items,
        { role: "assistant", text: result.answer, result }
      ]);
    } catch (error) {
      setMessages((items) => [
        ...items,
        { role: "assistant", text: (error as Error).message }
      ]);
    } finally {
      setLoading(false);
    }
  };

  // ── conversation management ─────────────────────────────────────
  const startNewConversation = () => {
    setConversationId(null);
    setMessages([]);
  };

  const switchConversation = (convId: string) => {
    setConversationId(convId);
    void loadConversation(convId);
  };

  const deleteConversation = async (convId: string, event: React.MouseEvent) => {
    event.stopPropagation();
    if (!paperId) return;
    if (!window.confirm("确定删除此对话？")) return;
    try {
      await api.deleteConversation(paperId, convId);
      setConversations((items) => items.filter((c) => c.id !== convId));
      if (conversationId === convId) {
        setConversationId(null);
        setMessages([]);
      }
    } catch {
      // silently ignore — may already be deleted
    }
  };

  return (
    <section className="chat-panel">
      <header>
        <div>
          <span className="eyebrow">聊天问答Agent</span>
          <h2>论文对话</h2>
        </div>
        <span className="agent-status">Agent在线</span>
      </header>

      {/* ── conversation selector ────────────────────────────────── */}
      {paperId && conversations.length > 0 && (
        <div className="conversation-selector">
          <button
            className={!conversationId ? "conv-item active" : "conv-item"}
            onClick={startNewConversation}
          >
            + 新对话
          </button>
          {conversations.map((conv) => (
            <div
              className={
                conversationId === conv.id
                  ? "conv-item active"
                  : "conv-item"
              }
              key={conv.id}
            >
              <button
                className="conv-label"
                title={conv.title}
                onClick={() => switchConversation(conv.id)}
              >
                {conv.title || "未命名对话"}
              </button>
              <button
                className="conv-delete"
                title="删除此对话"
                onClick={(e) => void deleteConversation(conv.id, e)}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="messages">
        {!messages.length && (
          <div className="chat-welcome">
            <strong>可以这样提问</strong>
            <button onClick={() => setQuestion("这篇论文解决了什么问题？")}>
              这篇论文解决了什么问题？
            </button>
            <button onClick={() => setQuestion("解释论文中的核心方法")}>
              解释论文中的核心方法
            </button>
            <button onClick={() => setQuestion("推荐相关的学习视频")}>
              推荐相关的学习视频
            </button>
          </div>
        )}
        {messages.map((message, index) => (
          <article className={`message ${message.role}`} key={index}>
            <span>{message.role === "user" ? "你" : "AI"}</span>
            <div>
              {message.result && !message.result.evidence_sufficient && (
                <span className="evidence-warning">⚠ 证据不足</span>
              )}
              <p>{message.text}</p>
              {message.result?.citations.map((citation) => (
                <div className={`citation-card ${citation.kind}`} key={citation.chunk_id}>
                  {citation.resource_url && (
                    <img src={citation.resource_url} alt={`第${citation.page}页${kindLabels[citation.kind] ?? "内容"}`} />
                  )}
                  <button
                    className="citation"
                    onClick={() => onLocate({ page: citation.page, bbox: citation.bbox })}
                  >
                    <strong>{kindLabels[citation.kind] ?? citation.kind}</strong>
                    <span>第{citation.page}页 · {citation.quote}</span>
                  </button>
                </div>
              ))}
              {message.result?.videos.map((video) => (
                <VideoPlayer key={video.id} video={video} />
              ))}
            </div>
          </article>
        ))}
        {loading && <p className="thinking">协调Agent正在调用知识库与聊天Agent…</p>}
      </div>
      <form onSubmit={submit}>
        <textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={paperId ? "围绕当前论文提问…" : "请先上传或选择论文"}
          disabled={!paperId}
          rows={3}
        />
        <button type="submit" disabled={!paperId || !question.trim() || loading}>
          发送
        </button>
      </form>
    </section>
  );
}