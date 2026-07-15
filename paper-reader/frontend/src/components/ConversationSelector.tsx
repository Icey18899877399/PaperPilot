import type { Conversation } from "../types";

interface Props {
  conversations: Conversation[];
  activeId: string | null;
  onNew: () => void;
  onSwitch: (convId: string) => void;
  onDelete: (convId: string) => void;
}

export function ConversationSelector({
  conversations,
  activeId,
  onNew,
  onSwitch,
  onDelete,
}: Props) {
  return (
    <div className="conversation-selector">
      <button
        className={!activeId ? "conv-item active" : "conv-item"}
        onClick={onNew}
      >
        + 新对话
      </button>
      {conversations.map((conv) => (
        <div
          className={
            activeId === conv.id ? "conv-item active" : "conv-item"
          }
          key={conv.id}
        >
          <button
            className="conv-label"
            title={conv.title}
            onClick={() => onSwitch(conv.id)}
          >
            {conv.title || "未命名对话"}
          </button>
          <button
            className="conv-delete"
            title="删除此对话"
            onClick={(e) => {
              e.stopPropagation();
              if (window.confirm("确定删除此对话？")) onDelete(conv.id);
            }}
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}