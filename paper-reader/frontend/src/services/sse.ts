export type StreamPayload = Record<string, unknown>;

export interface StreamHandlers<T> {
  onStatus?: (payload: StreamPayload) => void;
  onProgress?: (payload: StreamPayload) => void;
  onEvidence?: (payload: StreamPayload) => void;
  onDelta?: (payload: StreamPayload) => void;
  onComplete: (payload: T) => void;
}

export async function postEventStream<T>(
  url: string,
  body: unknown,
  handlers: StreamHandlers<T>,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(body),
      signal,
    });
  } catch (reason) {
    if ((reason as Error).name === "AbortError") throw reason;
    throw new Error("网络连接失败，请确认后端服务已启动");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `请求失败：${response.status}`);
  }
  if (!response.body) {
    throw new Error("浏览器未收到流式响应");
  }

  const decoder = new TextDecoder();
  const reader = response.body.getReader();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const lines = block.split("\n");
      const event = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
      const rawData = lines
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim())
        .join("\n");
      if (event && rawData) {
        let payload: unknown;
        try {
          payload = JSON.parse(rawData);
        } catch {
          throw new Error("流式响应格式异常");
        }
        if (event === "error") {
          const message = (payload as StreamPayload).message;
          throw new Error(typeof message === "string" ? message : "生成失败，请稍后重试");
        }
        if (event === "complete") {
          handlers.onComplete(payload as T);
        } else if (event === "delta") {
          handlers.onDelta?.(payload as StreamPayload);
        } else if (event === "status") {
          handlers.onStatus?.(payload as StreamPayload);
        } else if (event === "progress") {
          handlers.onProgress?.(payload as StreamPayload);
        } else if (event === "evidence") {
          handlers.onEvidence?.(payload as StreamPayload);
        }
      }
      boundary = buffer.indexOf("\n\n");
    }
    if (done) break;
  }
}
