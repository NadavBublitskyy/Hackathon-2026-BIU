export class ApiError extends Error {
  constructor(message, status, details) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

const parseResponse = async (response) => {
  const contentType = response.headers.get("content-type") || "";

  if (contentType.includes("application/json")) {
    return response.json();
  }

  return response.text();
};

export const requestJson = async (url, options = {}) => {
  const response = await fetch(url, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(options.headers || {}),
    },
  });

  const payload = await parseResponse(response);

  if (!response.ok) {
    const message = typeof payload === "string" ? payload : payload?.detail || payload?.error || "Request failed";
    throw new ApiError(message, response.status, payload);
  }

  return payload;
};

export const streamSse = async function* (url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      Accept: "text/event-stream",
      ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(options.headers || {}),
    },
  });

  if (!response.ok) {
    const payload = await parseResponse(response);
    const message = typeof payload === "string" ? payload : payload?.detail || payload?.error || "Request failed";
    throw new ApiError(message, response.status, payload);
  }

  if (!response.body) {
    throw new ApiError("Streaming is not supported by this browser.", response.status, null);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  const parseFrame = (frame) => {
    let event = "message";
    const dataLines = [];

    frame.split(/\r?\n/).forEach((line) => {
      if (line.startsWith("event:")) {
        event = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trimStart());
      }
    });

    if (!dataLines.length) {
      return null;
    }

    return { event, data: JSON.parse(dataLines.join("\n")) };
  };

  while (true) {
    const { done, value } = await reader.read();

    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() || "";

    for (const frame of frames) {
      if (!frame.trim()) {
        continue;
      }

      const parsedFrame = parseFrame(frame);

      if (parsedFrame) {
        yield parsedFrame;
      }
    }
  }

  buffer += decoder.decode();

  if (buffer.trim()) {
    const parsedFrame = parseFrame(buffer);

    if (parsedFrame) {
      yield parsedFrame;
    }
  }
};
