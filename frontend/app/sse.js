export async function readSseStream(response, onEvent) {
  if (!response.body) {
    throw new Error("Streaming response body is unavailable");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    frames.forEach((frame) => {
      const event = parseSseFrame(frame);
      if (event) {
        onEvent(event);
      }
    });
  }

  const tail = buffer.trim();
  if (tail) {
    const event = parseSseFrame(tail);
    if (event) {
      onEvent(event);
    }
  }
}

function parseSseFrame(frame) {
  let type = "message";
  const dataLines = [];
  frame.split("\n").forEach((line) => {
    if (line.startsWith("event:")) {
      type = line.slice("event:".length).trim();
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  });
  if (!dataLines.length) {
    return null;
  }
  return { type, data: JSON.parse(dataLines.join("\n")) };
}
