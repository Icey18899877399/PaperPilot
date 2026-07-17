import { useEffect, useState } from "react";

import type { ChatResponse } from "../types";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  result?: ChatResponse;
  state?: "streaming" | "complete" | "error";
  createdAt: number;
}

const STORAGE_VERSION = 1;
const MAX_MESSAGES = 40;

function storageKey(paperId: string): string {
  return `paperpilot:chat-history:v${STORAGE_VERSION}:${paperId}`;
}

function readHistory(paperId?: string): ChatMessage[] {
  if (!paperId) return [];
  try {
    const parsed = JSON.parse(localStorage.getItem(storageKey(paperId)) ?? "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(
        (item): item is ChatMessage =>
          Boolean(item)
          && typeof item.id === "string"
          && (item.role === "user" || item.role === "assistant")
          && typeof item.text === "string",
      )
      .slice(-MAX_MESSAGES)
      .map((item) => (
        item.state === "streaming"
          ? {
              ...item,
              text: item.text
                ? `${item.text}\n\n上次回答因页面关闭而中断，可重新提问。`
                : "上次回答因页面关闭而中断，可重新提问。",
              state: "error" as const,
            }
          : item
      ));
  } catch {
    return [];
  }
}

export function usePaperChatHistory(paperId?: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [hydratedPaperId, setHydratedPaperId] = useState<string>();

  useEffect(() => {
    setMessages(readHistory(paperId));
    setHydratedPaperId(paperId);
  }, [paperId]);

  useEffect(() => {
    if (!paperId || hydratedPaperId !== paperId) return;
    const timer = window.setTimeout(() => {
      try {
        localStorage.setItem(
          storageKey(paperId),
          JSON.stringify(messages.slice(-MAX_MESSAGES)),
        );
      } catch {
        // 隐私模式或存储空间不足时仅关闭持久化，不影响当前对话。
      }
    }, 240);
    return () => window.clearTimeout(timer);
  }, [hydratedPaperId, messages, paperId]);

  const clearHistory = () => {
    if (paperId) localStorage.removeItem(storageKey(paperId));
    setMessages([]);
  };

  return { messages, setMessages, clearHistory };
}
