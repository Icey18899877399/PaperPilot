import { ReactNode, useEffect } from "react";

interface Props {
  open: boolean;
  title: string;
  body?: ReactNode;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** 自绘确认弹窗：替代 window.confirm，视觉与全站一致，支持危险色与忙碌态。 */
export function ConfirmDialog({
  open,
  title,
  body,
  confirmText = "确定",
  cancelText = "取消",
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
}: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onCancel]);

  if (!open) return null;
  return (
    <div className="dialog-backdrop" onClick={() => { if (!busy) onCancel(); }}>
      <div
        className="dialog-card"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        <h3>{title}</h3>
        {body && <div className="dialog-body">{body}</div>}
        <div className="dialog-actions">
          <button type="button" disabled={busy} onClick={onCancel}>{cancelText}</button>
          <button
            type="button"
            className={danger ? "dialog-confirm danger" : "dialog-confirm"}
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? "处理中…" : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
