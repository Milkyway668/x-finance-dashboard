/**
 * Cloudflare Worker：按需生成短评
 * 环境变量（在 Cloudflare 后台配置，不会暴露给前端）：
 *   DEEPSEEK_API_KEY
 *   ALLOWED_ORIGIN  例如 https://yourname.github.io
 */

const SYSTEM = `你是买方研究编辑。给定一组推特材料，写一段中文短评：

1. 只使用材料中的事实与数字，绝不编造，不引入外部行情。
2. 数字必须原样来自材料。
3. 2-4 段，每段 60-120 字，专业克制，先事实后判断。
4. 每段末尾给出该段来源的推文 ID 列表。
5. 不做投资建议，不出现"建议买入/卖出/目标价"；引用他人观点须写明是谁说的。
6. 材料很少时不要硬凑，可以只写 1-2 段。

只输出 JSON：{"intro":"一句话导语","paragraphs":[{"text":"段落","refs":["推文ID"]}]}`;

function cors(env) {
  return {
    "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN || "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
  };
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors(env) });
    }
    if (request.method !== "POST") {
      return json({ error: "POST only" }, 405, env);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: "invalid json" }, 400, env);
    }

    const label = String(body.label || "所选范围").slice(0, 40);
    const items = Array.isArray(body.items) ? body.items.slice(0, 60) : [];
    if (!items.length) return json({ error: "no items" }, 400, env);

    const materials = items.map((it) => {
      const text = String(it.text || "").slice(0, 800);
      return `推文ID ${it.id}｜@${it.account}｜${it.date}\n${text}\n`;
    }).join("\n");

    const payload = {
      model: "deepseek-chat",
      messages: [
        { role: "system", content: SYSTEM },
        { role: "user", content: `以下是「${label}」范围内的材料：\n\n${materials}\n\n请写这段短评。` },
      ],
      temperature: 0.3,
      response_format: { type: "json_object" },
    };

    let upstream;
    try {
      upstream = await fetch("https://api.deepseek.com/chat/completions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${env.DEEPSEEK_API_KEY}`,
        },
        body: JSON.stringify(payload),
      });
    } catch (e) {
      return json({ error: "upstream failed", detail: String(e).slice(0, 200) }, 502, env);
    }

    if (!upstream.ok) {
      const t = await upstream.text();
      return json({ error: "deepseek error", status: upstream.status, detail: t.slice(0, 300) }, 502, env);
    }

    const data = await upstream.json();
    let parsed;
    try {
      parsed = JSON.parse(data.choices[0].message.content);
    } catch {
      return json({ error: "bad model output" }, 502, env);
    }

    return json({
      intro: parsed.intro || "",
      paragraphs: (parsed.paragraphs || []).map((p) => ({
        text: String(p.text || ""),
        refs: Array.isArray(p.refs) ? p.refs : [],
      })),
      generated: true,
    }, 200, env);
  },
};

function json(obj, status, env) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...cors(env) },
  });
}
