export function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderInlineMarkdown(value) {
  const codeSpans = [];
  let rendered = escapeHtml(value).replace(/`([^`]+)`/g, (_match, code) => {
    const placeholder = `%%CODESPAN${codeSpans.length}%%`;
    codeSpans.push(`<code>${code}</code>`);
    return placeholder;
  });

  rendered = rendered
    .replace(
      /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
      '<a href="$2" target="_blank" rel="noreferrer">$1</a>',
    )
    .replace(/(\*\*|__)(.+?)\1/g, "<strong>$2</strong>")
    .replace(/~~(.+?)~~/g, "<del>$1</del>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/(^|[^_])_([^_\n]+)_/g, "$1<em>$2</em>");

  codeSpans.forEach((code, index) => {
    rendered = rendered.replaceAll(`%%CODESPAN${index}%%`, code);
  });
  return rendered;
}

export function renderMarkdown(value) {
  const lines = String(value || "").replace(/\r\n?/g, "\n").split("\n");
  const html = [];
  let paragraph = [];
  let listType = "";
  let pendingListBreak = false;
  let inCodeBlock = false;
  let codeLines = [];

  const closeParagraph = () => {
    if (!paragraph.length) {
      return;
    }
    html.push(`<p>${paragraph.join("<br>")}</p>`);
    paragraph = [];
  };

  const closeList = () => {
    if (!listType) {
      return;
    }
    html.push(`</${listType}>`);
    listType = "";
    pendingListBreak = false;
  };

  const openList = (nextListType) => {
    closeParagraph();
    if (listType === nextListType) {
      pendingListBreak = false;
      return;
    }
    closeList();
    listType = nextListType;
    pendingListBreak = false;
    html.push(`<${listType}>`);
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();
    if (trimmed.startsWith("```")) {
      if (inCodeBlock) {
        html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
        codeLines = [];
        inCodeBlock = false;
      } else {
        closeParagraph();
        closeList();
        inCodeBlock = true;
      }
      continue;
    }

    if (inCodeBlock) {
      codeLines.push(line);
      continue;
    }

    if (!trimmed) {
      closeParagraph();
      if (listType) {
        pendingListBreak = true;
      }
      continue;
    }

    if (pendingListBreak && !isListItem(trimmed)) {
      closeList();
    }

    if (/^([-*_])(?:\s*\1){2,}$/.test(trimmed)) {
      closeParagraph();
      closeList();
      html.push("<hr>");
      continue;
    }

    if (looksLikeTableStart(lines, index)) {
      closeParagraph();
      closeList();
      const table = collectMarkdownTable(lines, index);
      html.push(renderMarkdownTable(table.headers, table.rows));
      index = table.nextIndex - 1;
      continue;
    }

    const heading = trimmed.match(/^(#{1,6})\s+(.+?)\s*#*$/);
    if (heading) {
      closeParagraph();
      closeList();
      const level = Math.min(heading[1].length + 1, 6);
      html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }

    const quote = trimmed.match(/^>\s?(.+)$/);
    if (quote) {
      closeParagraph();
      closeList();
      html.push(`<blockquote><p>${renderInlineMarkdown(quote[1])}</p></blockquote>`);
      continue;
    }

    const unordered = trimmed.match(/^[-*]\s+(.+)$/);
    if (unordered) {
      openList("ul");
      html.push(`<li>${renderInlineMarkdown(unordered[1])}</li>`);
      continue;
    }

    const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/);
    if (ordered) {
      openList("ol");
      html.push(`<li>${renderInlineMarkdown(ordered[1])}</li>`);
      continue;
    }

    closeList();
    paragraph.push(renderInlineMarkdown(trimmed));
  }

  if (inCodeBlock) {
    html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
  }
  closeParagraph();
  closeList();
  return html.join("");
}

function isListItem(trimmedLine) {
  return /^[-*]\s+(.+)$/.test(trimmedLine) || /^\d+[.)]\s+(.+)$/.test(trimmedLine);
}

function splitMarkdownTableRow(line) {
  let row = line.trim();
  if (row.startsWith("|")) {
    row = row.slice(1);
  }
  if (row.endsWith("|")) {
    row = row.slice(0, -1);
  }
  return row.split("|").map((cell) => cell.trim());
}

function isMarkdownTableSeparator(line) {
  const cells = splitMarkdownTableRow(line);
  return cells.length > 1 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function looksLikeTableStart(lines, index) {
  const current = lines[index] || "";
  const next = lines[index + 1] || "";
  return current.includes("|") && isMarkdownTableSeparator(next);
}

function collectMarkdownTable(lines, startIndex) {
  const headers = splitMarkdownTableRow(lines[startIndex]);
  const rows = [];
  let index = startIndex + 2;
  while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
    rows.push(splitMarkdownTableRow(lines[index]));
    index += 1;
  }
  return { headers, rows, nextIndex: index };
}

function renderMarkdownTable(headers, rows) {
  const headerHtml = headers
    .map((header) => `<th>${renderInlineMarkdown(header)}</th>`)
    .join("");
  const bodyHtml = rows
    .map(
      (row) => `
      <tr>
        ${headers.map((_header, index) => `<td>${renderInlineMarkdown(row[index] || "")}</td>`).join("")}
      </tr>
    `,
    )
    .join("");
  return `
    <div class="markdown-table-wrap">
      <table>
        <thead><tr>${headerHtml}</tr></thead>
        <tbody>${bodyHtml}</tbody>
      </table>
    </div>
  `;
}
