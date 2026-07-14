import { FormEvent, useState } from "react";

import { api } from "../api";
import type { ChatResponse, CitationTarget } from "../types";
import { VideoRecommendationCard } from "./VideoRecommendationCard";

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

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const current = question.trim();
    if (!paperId || !current || loading) return;
    setQuestion("");
    setMessages((items) => [...items, { role: "user", text: current }]);
    setLoading(true);
    try {
      const result = await api.chat(paperId, current);
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

  return (
    <section className="chat-panel">
      <header>
        <div>
          <span className="eyebrow">聊天问答Agent</span>
          <h2>论文对话</h2>
        </div>
        <span className="agent-status">Agent在线</span>
      </header>
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
                <VideoRecommendationCard key={video.id} video={video} />
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
