import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import type { Conversation } from "../types";

export function useConversations(paperId?: string) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const loadList = useCallback(async (id: string) => {
    try {
      setConversations(await api.listConversations(id));
    } catch {
      setConversations([]);
    }
  }, []);

  const loadMessages = useCallback(
    async (convId: string) => {
      if (!paperId) return null;
      try {
        return await api.getConversation(paperId, convId);
      } catch {
        setConversations((items) => items.filter((c) => c.id !== convId));
        return null;
      }
    },
    [paperId]
  );

  const startNew = useCallback(() => {
    setActiveId(null);
  }, []);

  const switchTo = useCallback((convId: string) => {
    setActiveId(convId);
  }, []);

  const remove = useCallback(
    async (convId: string) => {
      if (!paperId) return;
      try {
        await api.deleteConversation(paperId, convId);
        setConversations((items) => items.filter((c) => c.id !== convId));
        if (activeId === convId) setActiveId(null);
      } catch {
        // silently ignore
      }
    },
    [paperId, activeId]
  );

  const addToList = useCallback(
    (conv: Conversation) => {
      setConversations((items) => {
        const exists = items.some((c) => c.id === conv.id);
        return exists ? items : [conv, ...items];
      });
    },
    []
  );

  // Reset when paper changes
  useEffect(() => {
    if (!paperId) {
      setConversations([]);
      setActiveId(null);
      return;
    }
    setActiveId(null);
    void loadList(paperId);
  }, [paperId, loadList]);

  return {
    conversations,
    activeId,
    loading,
    loadList,
    loadMessages,
    startNew,
    switchTo,
    remove,
    addToList,
  };
}