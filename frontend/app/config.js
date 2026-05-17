export const MODES = {
  v1: {
    endpoint: "/v1/search",
    kicker: "v1 Search",
    title: "Search the SOPs",
    subtitle: "关键词匹配，适合 OOM、CDN、P0 这类明确线索。",
    placeholder: "OOM / CDN / P0",
    resultTitle: "Keyword matches",
  },
  v2: {
    endpoint: "/v2/search",
    kicker: "v2 RAG",
    title: "Ask for evidence",
    subtitle: "语义检索相关 SOP 片段，不生成最终处置结论。",
    placeholder: "服务器挂了，先查什么？",
    resultTitle: "Retrieved evidence",
  },
  v3: {
    kind: "interview",
    endpoint: "/interview/chat",
    streamEndpoint: "/interview/chat/stream",
    kicker: "v3 Interview Agent",
    title: "Mock interview",
    subtitle: "一个可自由对话的 AI Agent 面试助手；只有明确开始面试时才进入模拟面试流程。",
    placeholder: "直接聊天，或输入“开始面试”“采集面经”“讲 RAG 召回失败”",
    resultTitle: "Interview transcript",
  },
  interview: {
    kind: "interview",
    baseMode: "v3",
    endpoint: "/interview/chat",
    streamEndpoint: "/interview/chat/stream",
    kicker: "v3 Interview Agent",
    title: "Mock interview",
    subtitle: "一个可自由对话的 AI Agent 面试助手；只有明确开始面试时才进入模拟面试流程。",
    placeholder: "直接聊天，或输入“开始面试”“采集面经”“讲 RAG 召回失败”",
    resultTitle: "Interview transcript",
  },
};

export const PRODUCT_PAGES = {
  interview: {
    label: "面试",
    path: "/v3",
  },
  questions: {
    label: "题库",
    path: "/v3/questions",
  },
  sources: {
    label: "来源",
    path: "/v3/sources",
  },
  review: {
    label: "复盘",
    path: "/v3/review",
  },
};

export const MAX_HISTORY_ENTRIES = 24;
export const MAX_CHAT_CONTEXT_TURNS = 12;

export function modeFromPath(pathname) {
  if (pathname === "/v1") {
    return "v1";
  }
  if (pathname === "/v2") {
    return "v2";
  }
  return "v3";
}

export function productPageFromPath(pathname) {
  if (pathname === "/v3/questions") {
    return "questions";
  }
  if (pathname === "/v3/sources") {
    return "sources";
  }
  if (pathname === "/v3/review") {
    return "review";
  }
  return "interview";
}
