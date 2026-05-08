const TWSE_MIS_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp";
const MAX_BATCH_SIZE = 80;

const corsHeaders = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET,POST,OPTIONS",
  "access-control-allow-headers": "content-type",
  "access-control-max-age": "86400",
};

export default {
  async fetch(request) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders });
    }

    const url = new URL(request.url);
    if (url.pathname === "/health") {
      return json({ ok: true, service: "twse-realtime-proxy" });
    }
    if (url.pathname !== "/quotes") {
      return json({ error: "not_found" }, 404);
    }
    if (request.method !== "POST") {
      return json({ error: "method_not_allowed" }, 405);
    }

    let body;
    try {
      body = await request.json();
    } catch (_error) {
      return json({ error: "invalid_json" }, 400);
    }

    const channels = normalizeChannels(body.symbols || body.channels || []);
    if (!channels.length) {
      return json({ generated_at: new Date().toISOString(), quotes: [] });
    }

    const quotes = [];
    for (const batch of chunks(channels, Number(body.batchSize) || MAX_BATCH_SIZE)) {
      const payload = await fetchTwseBatch(batch);
      quotes.push(...payload);
    }

    return json({
      generated_at: new Date().toISOString(),
      quote_count: quotes.length,
      quotes,
    });
  },
};

async function fetchTwseBatch(channels) {
  const url = new URL(TWSE_MIS_URL);
  url.searchParams.set("ex_ch", channels.join("|"));
  url.searchParams.set("json", "1");
  url.searchParams.set("delay", "0");
  url.searchParams.set("_", String(Date.now()));

  const response = await fetch(url.toString(), {
    headers: {
      "accept": "application/json, text/javascript, */*; q=0.01",
      "accept-language": "zh-TW,zh;q=0.9,en-US;q=0.8",
      "referer": "https://mis.twse.com.tw/stock/fibest.jsp?lang=zh_tw",
      "user-agent": "Mozilla/5.0 Cloudflare-Worker TWSE realtime proxy",
      "x-requested-with": "XMLHttpRequest",
    },
    cf: { cacheTtl: 3, cacheEverything: false },
  });

  const text = await response.text();
  const jsonText = text.slice(text.indexOf("{"));
  const data = JSON.parse(jsonText);
  return (data.msgArray || []).map(parseQuote).filter(Boolean);
}

function parseQuote(row) {
  const symbol = String(row.c || "").trim();
  if (!symbol) return null;
  const market = String(row.ex || "").trim().toLowerCase();
  const price = firstNumber(row.z, row.a, row.b, row.y);
  const previousClose = toNumber(row.y);
  return {
    symbol,
    market,
    name: String(row.n || "").trim(),
    timestamp: parseTimestamp(row.d, row.t),
    open: toNumber(row.o),
    high: toNumber(row.h),
    low: toNumber(row.l),
    price,
    previous_close: previousClose,
    volume: toNumber(row.v),
    change_pct: price != null && previousClose ? price / previousClose - 1 : null,
    raw_channel: String(row.ch || row["@"] || "").trim(),
  };
}

function normalizeChannels(items) {
  const channels = [];
  for (const item of items) {
    if (typeof item === "string") {
      channels.push(normalizeChannel(item));
      continue;
    }
    const symbol = String(item.symbol || "").trim();
    const market = String(item.market || "tse").trim().toLowerCase();
    if (/^[1-9][0-9]{3}$/.test(symbol)) {
      channels.push(`${market === "otc" ? "otc" : "tse"}_${symbol}.tw`);
    }
  }
  return [...new Set(channels)].filter(Boolean);
}

function normalizeChannel(value) {
  const text = String(value || "").trim().toLowerCase();
  if (!text) return "";
  if (text.includes("_") && text.endsWith(".tw")) return text;
  if (text.includes(":")) {
    const [market, symbol] = text.split(":", 2);
    return `${market}_${symbol}.tw`;
  }
  if (text.includes(".")) {
    const [symbol, market] = text.split(".", 2);
    return `${market === "two" || market === "otc" ? "otc" : "tse"}_${symbol}.tw`;
  }
  return `tse_${text}.tw`;
}

function parseTimestamp(dateText, timeText) {
  const d = String(dateText || "").trim();
  const t = String(timeText || "").trim();
  if (/^[0-9]{8}$/.test(d) && /^[0-9]{2}:[0-9]{2}:[0-9]{2}/.test(t)) {
    return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)} ${t.slice(0, 8)}`;
  }
  return new Date().toISOString();
}

function firstNumber(...values) {
  for (const value of values) {
    const number = toNumber(value);
    if (number) return number;
  }
  return null;
}

function toNumber(value) {
  const text = String(value ?? "").replace(/,/g, "").trim();
  if (!text || text === "-" || text === "--" || text === "N/A") return null;
  const first = text.split("_", 1)[0];
  const number = Number(first);
  return Number.isFinite(number) ? number : null;
}

function chunks(items, size) {
  const output = [];
  const capped = Math.min(Math.max(size, 1), MAX_BATCH_SIZE);
  for (let index = 0; index < items.length; index += capped) {
    output.push(items.slice(index, index + capped));
  }
  return output;
}

function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      ...corsHeaders,
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}
