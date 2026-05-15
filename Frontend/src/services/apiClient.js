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

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let currentEvent = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("event: ")) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        const dataStr = line.slice(6).trim();
        if (dataStr) {
          try {
            const parsedData = JSON.parse(dataStr);
            yield { event: currentEvent, data: parsedData };
          } catch (e) {
            // Skip invalid JSON
          }
        }
        currentEvent = null;
      }
    }
  }
};
