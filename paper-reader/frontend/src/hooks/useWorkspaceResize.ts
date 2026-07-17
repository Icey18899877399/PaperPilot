import { useEffect, useRef, useState } from "react";
import type {
  CSSProperties,
  PointerEvent as ReactPointerEvent,
} from "react";

interface ResizeSession {
  side: "left" | "right";
  startX: number;
  startLeft: number;
  startRight: number;
}

export function useWorkspaceResize() {
  const [leftPaneWidth, setLeftPaneWidth] = useState(250);
  const [rightPaneWidth, setRightPaneWidth] = useState(440);
  const resizeSession = useRef<ResizeSession | null>(null);

  useEffect(() => {
    const move = (event: PointerEvent) => {
      const session = resizeSession.current;
      if (!session) return;
      const delta = event.clientX - session.startX;
      if (session.side === "left") {
        const maxLeft = Math.max(
          240,
          Math.min(420, window.innerWidth - session.startRight - 440),
        );
        setLeftPaneWidth(Math.min(maxLeft, Math.max(180, session.startLeft + delta)));
      } else {
        const maxRight = Math.max(
          380,
          Math.min(720, window.innerWidth - session.startLeft - 440),
        );
        setRightPaneWidth(Math.min(maxRight, Math.max(320, session.startRight - delta)));
      }
    };
    const stop = () => {
      resizeSession.current = null;
      document.body.classList.remove("is-resizing-workspace");
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
      document.body.classList.remove("is-resizing-workspace");
    };
  }, []);

  const startResize = (
    side: ResizeSession["side"],
    event: ReactPointerEvent<HTMLDivElement>,
  ) => {
    event.preventDefault();
    resizeSession.current = {
      side,
      startX: event.clientX,
      startLeft: leftPaneWidth,
      startRight: rightPaneWidth,
    };
    document.body.classList.add("is-resizing-workspace");
  };

  const workspaceStyle = {
    "--library-width": `${leftPaneWidth}px`,
    "--assistant-width": `${rightPaneWidth}px`,
  } as CSSProperties;

  return { startResize, workspaceStyle };
}
