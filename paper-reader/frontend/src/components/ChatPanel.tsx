import {
  FormEvent,
  KeyboardEvent,
  useEffect,
  useRef,
  useState,
} from "react";

import { api } from "../api";
import {
  usePaperChatHistory,
  type ChatMessage,
} from "../hooks/usePaperChatHistory";
import type { ChatResponse, Citation, CitationTarget } from "../types";
import { ConfirmDialog } from "./ConfirmDialog";
import { RichText } from "./RichText";
import { VideoRecommendationCard } from "./VideoRecommendationCard";

interface Props {
  paperId?: string;
  // 外部预填问题（US-02导读思考题一键提问）；nonce变化时写入输入框。
  prefill?: { text: string; nonce: number } | null;
  onPrefillConsumed?: () => void;
  onLocate: (target: CitationTarget) => void;
}

const kindLabels: Record<string, string> = {
  text: "正文",
  image: "图片",
  chart: "图表",
  table: "表格",
  equation: "公式",
  code: "代码",
  list: "列表",
};

const SUGGESTED_QUESTIONS = [
  "这篇论文解决了什么问题？",
  "解释论文中的核心方法",
  "主要实验结果是否支持作者结论？",
];

function newMessage(
  role: ChatMessage["role"],
  text: string,
  state: ChatMessage["state"] = "complete",
): ChatMessage {
  return {
    id: globalThis.crypto?.randomUUID?.()
      ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    text,
    state,
    createdAt: Date.now(),
  };
}

function updateMessage(
  messages: ChatMessage[],
  id: string,
  updater: (message: ChatMessage) => ChatMessage,
): ChatMessage[] {
  return messages.map((message) => (
    message.id === id ? updater(message) : message
  ));
}

function citationExcerpt(citation: Citation): string {
  const withoutPrefix = citation.quote.replace(/^章节：[^。\n]{1,240}(?:\n|$)/, "");
  return withoutPrefix.trim() || "点击查看该证据在论文中的原始位置";
}

function LocateIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 21s6-5.2 6-11a6 6 0 1 0-12 0c0 5.8 6 11 6 11Z" />
      <circle cx="12" cy="10" r="2" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="m4 4 17 8-17 8 3-8-3-8Z" />
      <path d="M7 12h14" />
    </svg>
  );
}

export function ChatPanel({
  paperId,
  prefill,
  onPrefillConsumed,
  onLocate,
}: Props) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [streamStatus, setStreamStatus] = useState("");
  const [evidenceCount, setEvidenceCount] = useState(0);
  const [confirmClear, setConfirmClear] = useState(false);
  const { messages, setMessages, clearHistory } = usePaperChatHistory(paperId);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const formRef = useRef<HTMLFormElement | null>(null);
  const requestRef = useRef<AbortController | null>(null);

  // US-05边界兜底：切换论文或离开页面时取消仍在生成的上游请求。
  useEffect(() => {
    requestRef.current?.abort();
    requestRef.current = null;
    setLoading(false);
    setStreamStatus("");
    setEvidenceCount(0);
    setQuestion("");
    return () => requestRef.current?.abort();
  }, [paperId]);

  // 导读“建议思考”跳转后预填输入框，并立即消费，避免再次进入聊天时重复出现。
  useEffect(() => {
    if (!prefill?.text) return;
    setQuestion(prefill.text);
    onPrefillConsumed?.();
  }, [onPrefillConsumed, prefill?.nonce, prefill?.text]);

  const latestLength = messages.at(-1)?.text.length ?? 0;
  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: loading ? "auto" : "smooth",
      block: "end",
    });
  }, [latestLength, loading, messages.length]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const current = question.trim();
    if (!paperId || !current || loading) return;

    const userMessage = newMessage("user", current);
    const assistantMessage = newMessage("assistant", "", "streaming");
    setMessages((items) => [...items, userMessage, assistantMessage]);
    setQuestion("");
    setLoading(true);
    setEvidenceCount(0);
    setStreamStatus("正在连接论文知识库");

    const controller = new AbortController();
    requestRef.current = controller;
    try {
      await api.streamChat(
        paperId,
        current,
        {
          onStatus: (payload) => {
            if (typeof payload.message === "string") setStreamStatus(payload.message);
          },
          onEvidence: (payload) => {
            if (typeof payload.count === "number") setEvidenceCount(payload.count);
          },
          onDelta: (payload) => {
            if (typeof payload.text !== "string") return;
            setMessages((items) => updateMessage(
              items,
              assistantMessage.id,
              (message) => ({ ...message, text: message.text + payload.text }),
            ));
          },
          onComplete: (result: ChatResponse) => {
            setMessages((items) => updateMessage(
              items,
              assistantMessage.id,
              (message) => ({
                ...message,
                text: result.answer || message.text,
                result,
                state: "complete",
              }),
            ));
          },
        },
        controller.signal,
      );
    } catch (error) {
      if ((error as Error).name === "AbortError") return;
      setMessages((items) => updateMessage(
        items,
        assistantMessage.id,
        (message) => ({
          ...message,
          text: message.text
            ? `${message.text}\n\n回答意外中断：${(error as Error).message}`
            : (error as Error).message,
          state: "error",
        }),
      ));
    } finally {
      if (requestRef.current === controller) requestRef.current = null;
      setLoading(false);
      setStreamStatus("");
      setEvidenceCount(0);
    }
  };

  const handleComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      formRef.current?.requestSubmit();
    }
  };

  const confirmClearHistory = () => {
    requestRef.current?.abort();
    clearHistory();
    setLoading(false);
    setStreamStatus("");
    setConfirmClear(false);
  };

  return (
    <section className="chat-panel">
      <header className="chat-header">
        <div>
          <span className="eyebrow">聊天问答 Agent</span>
          <h2>论文对话</h2>
          <small>回答仅依据当前论文，并附可跳转的原文证据</small>
        </div>
        <div className="chat-header-actions">
          {messages.length > 0 && (
            <button
              type="button"
              className="chat-clear-button"
              disabled={loading}
              onClick={() => setConfirmClear(true)}
              title="清空当前论文的问答历史"
            >
              清空记录
            </button>
          )}
          <span className="agent-status"><i /> Agent 在线</span>
        </div>
      </header>

      <div className="messages" aria-live="polite">
        {!messages.length && (
          <div className="chat-welcome">
            <div className="chat-welcome-icon">AI</div>
            <strong>从论文中获得有依据的回答</strong>
            <p>选择一个问题开始，或在下方输入你真正关心的内容。</p>
            <div className="chat-suggestions">
              {SUGGESTED_QUESTIONS.map((item, index) => (
                <button type="button" onClick={() => setQuestion(item)} key={item}>
                  <span>{index + 1}</span>
                  {item}
                  <b aria-hidden="true">→</b>
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((message) => (
          <article className={`message ${message.role} ${message.state ?? ""}`} key={message.id}>
            <span className="message-avatar">{message.role === "user" ? "你" : "AI"}</span>
            <div className="message-body">
              {message.text ? (
                <RichText text={message.text} />
              ) : (
                <div className="streaming-placeholder" aria-label="AI正在生成回答">
                  <i /><i /><i />
                </div>
              )}

              {(message.result?.citations.length ?? 0) > 0 && (
                <section className="citation-evidence-list" aria-label="回答的原文依据">
                  <header>
                    <strong>原文依据</strong>
                    <span>{message.result!.citations.length} 条 · 点击定位</span>
                  </header>
                  {message.result!.citations.map((citation, index) => (
                    <article
                      className={`citation-card ${citation.kind}`}
                      key={`${citation.chunk_id}-${index}`}
                    >
                      {citation.resource_url && (
                        <img
                          src={citation.resource_url}
                          alt={`证据${index + 1}：第${citation.page}页${kindLabels[citation.kind] ?? "内容"}`}
                          loading="lazy"
                        />
                      )}
                      <button
                        type="button"
                        className="citation"
                        title={`定位到第${citation.page}页${citation.section ? ` · ${citation.section}` : ""}`}
                        onClick={() => onLocate({ page: citation.page, bbox: citation.bbox })}
                      >
                        <span className="citation-meta">
                          <b className="citation-index">证据 {index + 1}</b>
                          <b className="citation-kind">
                            {kindLabels[citation.kind] ?? citation.kind}
                          </b>
                          <b className="citation-page">第 {citation.page} 页</b>
                          <LocateIcon />
                        </span>
                        {citation.section && (
                          <span className="citation-section">
                            <b>章节</b>
                            <span>{citation.section}</span>
                          </span>
                        )}
                        <span className="citation-quote">{citationExcerpt(citation)}</span>
                      </button>
                    </article>
                  ))}
                </section>
              )}

              {message.result?.videos.map((video) => (
                <VideoRecommendationCard key={video.id} video={video} />
              ))}
            </div>
          </article>
        ))}

        {loading && (
          <div className="chat-stream-status">
            <span className="chat-status-spinner" />
            <span>{streamStatus || "正在生成回答"}</span>
            {evidenceCount > 0 && <b>已找到 {evidenceCount} 条依据</b>}
          </div>
        )}
        <div ref={bottomRef} aria-hidden="true" />
      </div>

      <form className="chat-composer" ref={formRef} onSubmit={submit}>
        <div className="chat-composer-box">
          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={handleComposerKeyDown}
            placeholder={paperId ? "围绕当前论文提问…" : "请先上传或选择论文"}
            disabled={!paperId}
            rows={2}
            maxLength={1200}
            aria-label="论文对话问题"
          />
          <button
            type="submit"
            className="chat-send-button"
            disabled={!paperId || !question.trim() || loading}
            aria-label={loading ? "回答生成中" : "发送问题"}
          >
            <SendIcon />
            <span>{loading ? "生成中" : "发送"}</span>
          </button>
        </div>
        <small>Enter 发送 · Shift + Enter 换行 · 对话自动保存在本机</small>
      </form>

      <ConfirmDialog
        open={confirmClear}
        title="清空当前论文的问答记录？"
        body="只会删除当前论文保存在本机浏览器中的对话，不会删除论文或知识库。"
        confirmText="清空"
        danger
        onConfirm={confirmClearHistory}
        onCancel={() => setConfirmClear(false)}
      />
    </section>
  );
}
