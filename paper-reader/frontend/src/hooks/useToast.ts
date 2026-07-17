import { useCallback, useRef, useState } from "react";

import type { ToastItem } from "../components/Toast";

export function useToast() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const toastId = useRef(0);

  const dismissToast = useCallback((id: number) => {
    setToasts((items) => items.filter((item) => item.id !== id));
  }, []);

  const notify = useCallback(
    (type: ToastItem["type"], message: string) => {
      const id = ++toastId.current;
      setToasts((items) => [...items.slice(-3), { id, type, message }]);
      window.setTimeout(() => dismissToast(id), 5000);
    },
    [dismissToast],
  );

  return { toasts, notify, dismissToast };
}
