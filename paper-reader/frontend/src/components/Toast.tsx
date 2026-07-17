export interface ToastItem {
  id: number;
  type: "error" | "success" | "info";
  message: string;
}

interface Props {
  toasts: ToastItem[];
  onClose: (id: number) => void;
}

const TYPE_LABEL: Record<ToastItem["type"], string> = {
  error: "出错了",
  success: "已完成",
  info: "提示",
};

/** 轻量Toast栈：替代全局错误横幅，支持多条并存、自动消失、手动关闭。 */
export function ToastStack({ toasts, onClose }: Props) {
  if (!toasts.length) return null;
  return (
    <div className="toast-stack" role="status" aria-live="polite">
      {toasts.map((toast) => (
        <div className={`toast toast-${toast.type}`} key={toast.id}>
          <div className="toast-body">
            <strong>{TYPE_LABEL[toast.type]}</strong>
            <span>{toast.message}</span>
          </div>
          <button
            type="button"
            aria-label="关闭提示"
            onClick={() => onClose(toast.id)}
          >×</button>
        </div>
      ))}
    </div>
  );
}
