/**
 * QuickChatPage — powerful standalone chat with web search, URL fetching,
 * multi-provider support (Ollama, OpenRouter, any OpenAI-compatible),
 * and tool-use capabilities.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Typography } from "@nous-research/ui";
import { cn } from "@/lib/utils";
import {
  Globe, Loader2, Send, Settings2, Trash2, X, Zap, Link,
  ChevronDown, Search, ExternalLink,
} from "lucide-react";

/* ─── Types ─────────────────────────────────────────────────────────── */
interface Message {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  toolName?: string;
  searching?: boolean;
}

interface Provider {
  id: string;
  name: string;
  endpoint: string;
  needsKey: boolean;
  chatPath: string;
  streamFormat: "ollama" | "openai";
}

interface SearchResult {
  title: string;
  url: string;
  snippet: string;
}

/* ─── Providers ─────────────────────────────────────────────────────── */
const PROVIDERS: Provider[] = [
  { id: "ollama", name: "Ollama (local)", endpoint: "http://localhost:11434", needsKey: false, chatPath: "/api/chat", streamFormat: "ollama" },
  { id: "openrouter", name: "OpenRouter", endpoint: "https://openrouter.ai/api/v1", needsKey: true, chatPath: "/chat/completions", streamFormat: "openai" },
  { id: "openai", name: "OpenAI", endpoint: "https://api.openai.com/v1", needsKey: true, chatPath: "/chat/completions", streamFormat: "openai" },
  { id: "custom", name: "Custom API", endpoint: "", needsKey: false, chatPath: "/chat/completions", streamFormat: "openai" },
];

/* ─── Storage helpers ───────────────────────────────────────────────── */
const S = (k: string, fb: string) => { try { return localStorage.getItem(k) ?? fb; } catch { return fb; } };
const KEYS = { provider: "hc_provider", endpoint: "hc_endpoint", model: "hc_model", apiKey: "hc_apikey", searchEnabled: "hc_search" };

const SYSTEM_PROMPT = `You are Hermes, a powerful AI assistant by Nous Research. You are helpful, fast, and capable.
When the user asks you to search the web or look something up, respond with exactly: [SEARCH: query here]
When the user asks you to read or fetch a URL, respond with exactly: [FETCH: url here]
You can use multiple tool calls in one response. After receiving tool results, synthesize them into a clear answer.`;

/* ─── Tool execution ────────────────────────────────────────────────── */
async function webSearch(query: string): Promise<SearchResult[]> {
  try {
    const r = await fetch(`/proxy/search?q=${encodeURIComponent(query)}`);
    const data = await r.json();
    return data.results ?? [];
  } catch { return []; }
}

async function fetchUrl(url: string): Promise<string> {
  try {
    const r = await fetch(`/proxy/fetch?url=${encodeURIComponent(url)}`);
    const data = await r.json();
    return data.text?.slice(0, 6000) ?? "Failed to fetch";
  } catch (e) { return `Fetch error: ${(e as Error).message}`; }
}

function extractToolCalls(text: string): { type: "search" | "fetch"; arg: string }[] {
  const calls: { type: "search" | "fetch"; arg: string }[] = [];
  const searchRe = /\[SEARCH:\s*(.+?)\]/gi;
  const fetchRe = /\[FETCH:\s*(.+?)\]/gi;
  let m;
  while ((m = searchRe.exec(text)) !== null) calls.push({ type: "search", arg: m[1].trim() });
  while ((m = fetchRe.exec(text)) !== null) calls.push({ type: "fetch", arg: m[1].trim() });
  return calls;
}

/* ─── Component ─────────────────────────────────────────────────────── */
export default function QuickChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [providerId, setProviderId] = useState(() => S(KEYS.provider, "ollama"));
  const [customEndpoint, setCustomEndpoint] = useState(() => S(KEYS.endpoint, ""));
  const [model, setModel] = useState(() => S(KEYS.model, "hermes3:latest"));
  const [apiKey, setApiKey] = useState(() => S(KEYS.apiKey, ""));
  const [searchEnabled, setSearchEnabled] = useState(() => S(KEYS.searchEnabled, "true") === "true");
  const [showSettings, setShowSettings] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const provider = PROVIDERS.find(p => p.id === providerId) ?? PROVIDERS[0];

  // Fetch Ollama models
  useEffect(() => {
    if (providerId !== "ollama") return;
    fetch("http://localhost:11434/api/tags")
      .then(r => r.json())
      .then(data => {
        const names = (data.models ?? []).map((m: { name: string }) => m.name);
        setModels(names);
      })
      .catch(() => setModels([]));
  }, [providerId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const saveSettings = () => {
    try {
      localStorage.setItem(KEYS.provider, providerId);
      localStorage.setItem(KEYS.endpoint, customEndpoint);
      localStorage.setItem(KEYS.model, model);
      localStorage.setItem(KEYS.apiKey, apiKey);
      localStorage.setItem(KEYS.searchEnabled, String(searchEnabled));
    } catch { /* */ }
    setShowSettings(false);
  };

  const getEndpoint = () => {
    if (providerId === "custom") return customEndpoint;
    return provider.endpoint;
  };

  /* ─── Streaming chat call ─────────────────────────────────────────── */
  const chatStream = useCallback(async (
    history: { role: string; content: string }[],
    onDelta: (text: string) => void,
    signal: AbortSignal,
  ): Promise<string> => {
    const ep = getEndpoint();
    const url = `${ep}${provider.chatPath}`;
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

    const body: Record<string, unknown> = { model, messages: history, stream: true };

    const res = await fetch(url, { method: "POST", headers, body: JSON.stringify(body), signal });
    if (!res.ok) {
      const errBody = await res.text();
      throw new Error(`API ${res.status}: ${errBody.slice(0, 200)}`);
    }

    const reader = res.body?.getReader();
    if (!reader) throw new Error("No stream");
    const decoder = new TextDecoder();
    let acc = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });

      if (provider.streamFormat === "ollama") {
        for (const line of chunk.split("\n").filter(l => l.trim())) {
          try {
            const p = JSON.parse(line);
            const c = p.message?.content;
            if (c) { acc += c; onDelta(acc); }
          } catch { /* skip */ }
        }
      } else {
        for (const line of chunk.split("\n")) {
          const t = line.trim();
          if (!t.startsWith("data: ")) continue;
          const d = t.slice(6);
          if (d === "[DONE]") continue;
          try {
            const p = JSON.parse(d);
            const c = p.choices?.[0]?.delta?.content;
            if (c) { acc += c; onDelta(acc); }
          } catch { /* skip */ }
        }
      }
    }
    return acc;
  }, [model, apiKey, providerId, customEndpoint, provider]);

  /* ─── Send message with tool loop ─────────────────────────────────── */
  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || streaming) return;
    setError(null);

    const userMsg: Message = { role: "user", content: text };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput("");
    setStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      // Build history for API
      const apiHistory = [
        { role: "system", content: searchEnabled ? SYSTEM_PROMPT : SYSTEM_PROMPT.split("\n")[0] },
        ...newMessages.filter(m => m.role !== "tool").map(m => ({ role: m.role, content: m.content })),
      ];

      // First response
      const assistantMsg: Message = { role: "assistant", content: "" };
      setMessages([...newMessages, assistantMsg]);

      const fullResponse = await chatStream(apiHistory, (acc) => {
        setMessages(prev => {
          const u = [...prev];
          u[u.length - 1] = { role: "assistant", content: acc };
          return u;
        });
      }, controller.signal);

      // Check for tool calls in the response
      if (searchEnabled) {
        const calls = extractToolCalls(fullResponse);
        if (calls.length > 0) {
          let toolContext = "";

          for (const call of calls) {
            if (call.type === "search") {
              // Show searching indicator
              setMessages(prev => [...prev, { role: "tool", content: `Searching: ${call.arg}`, toolName: "web_search", searching: true }]);

              const results = await webSearch(call.arg);
              const resultText = results.length > 0
                ? results.map((r, i) => `${i + 1}. **${r.title}**\n   ${r.url}\n   ${r.snippet}`).join("\n\n")
                : "No results found.";

              toolContext += `\n\n[Web Search Results for "${call.arg}"]\n${resultText}\n`;

              // Update tool message with results
              setMessages(prev => {
                const u = [...prev];
                const idx = u.findLastIndex(m => m.toolName === "web_search" && m.searching);
                if (idx >= 0) u[idx] = { role: "tool", content: resultText, toolName: "web_search" };
                return u;
              });
            } else if (call.type === "fetch") {
              setMessages(prev => [...prev, { role: "tool", content: `Fetching: ${call.arg}`, toolName: "url_fetch", searching: true }]);
              const pageText = await fetchUrl(call.arg);
              toolContext += `\n\n[Fetched content from ${call.arg}]\n${pageText.slice(0, 4000)}\n`;
              setMessages(prev => {
                const u = [...prev];
                const idx = u.findLastIndex(m => m.toolName === "url_fetch" && m.searching);
                if (idx >= 0) u[idx] = { role: "tool", content: pageText.slice(0, 500) + "...", toolName: "url_fetch" };
                return u;
              });
            }
          }

          // Second pass — model synthesizes with tool results
          const synthesisHistory = [
            ...apiHistory,
            { role: "assistant", content: fullResponse },
            { role: "user", content: `Here are the results from the tools you requested:\n${toolContext}\n\nNow please provide a comprehensive answer based on these results.` },
          ];

          const synthMsg: Message = { role: "assistant", content: "" };
          setMessages(prev => [...prev, synthMsg]);

          await chatStream(synthesisHistory, (acc) => {
            setMessages(prev => {
              const u = [...prev];
              u[u.length - 1] = { role: "assistant", content: acc };
              return u;
            });
          }, controller.signal);
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        const msg = (err as Error).message;
        if (msg.includes("Failed to fetch") || msg.includes("ECONNREFUSED")) {
          setError(providerId === "ollama"
            ? "Can't connect to Ollama. Run: ollama serve"
            : `Can't connect to ${getEndpoint()}`);
        } else {
          setError(msg);
        }
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }, [input, streaming, messages, chatStream, searchEnabled, providerId]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };

  /* ─── Quick actions ───────────────────────────────────────────────── */
  const quickSearch = (q: string) => { setInput(`Search the web for: ${q}`); setTimeout(() => inputRef.current?.focus(), 50); };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 normal-case">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Typography className="font-bold text-[1.125rem] leading-[0.95] tracking-[0.04em] text-midground"
            style={{ mixBlendMode: "plus-lighter" }}>
            Quick Chat
          </Typography>
          <span className="rounded border border-current/15 bg-midground/5 px-1.5 py-0.5 text-[0.55rem] font-semibold tracking-wider text-midground/40">
            {model.split(":")[0]}
          </span>
          {searchEnabled && (
            <span className="flex items-center gap-1 rounded border border-success/20 bg-success/5 px-1.5 py-0.5 text-[0.5rem] font-semibold tracking-wider text-success/60">
              <Globe className="h-2.5 w-2.5" /> WEB
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <Button ghost size="icon" onClick={() => { setMessages([]); setError(null); }} title="Clear"
            className="text-midground/50 hover:text-midground"><Trash2 className="h-3.5 w-3.5" /></Button>
          <Button ghost size="icon" onClick={() => setShowSettings(!showSettings)} title="Settings"
            className={cn("text-midground/50 hover:text-midground", showSettings && "text-midground")}>
            <Settings2 className="h-3.5 w-3.5" /></Button>
        </div>
      </div>

      {/* Settings */}
      {showSettings && (
        <div className="rounded-lg border border-current/20 bg-card p-4 space-y-3">
          <span className="text-xs font-semibold tracking-wider text-midground/60 uppercase">Configuration</span>

          {/* Provider */}
          <div className="space-y-1.5">
            <label className="text-[0.7rem] font-medium text-midground/50 tracking-wider uppercase">Provider</label>
            <div className="relative">
              <select value={providerId} onChange={e => setProviderId(e.target.value)}
                className="w-full appearance-none rounded border border-current/15 bg-black/20 px-3 py-2 pr-8 text-sm text-midground outline-none focus:border-current/30">
                {PROVIDERS.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              <ChevronDown className="absolute right-2.5 top-2.5 h-4 w-4 text-midground/30 pointer-events-none" />
            </div>
          </div>

          {/* Custom endpoint */}
          {providerId === "custom" && (
            <div className="space-y-1.5">
              <label className="text-[0.7rem] font-medium text-midground/50 tracking-wider uppercase">Endpoint URL</label>
              <input value={customEndpoint} onChange={e => setCustomEndpoint(e.target.value)}
                placeholder="http://localhost:8080/v1"
                className="w-full rounded border border-current/15 bg-black/20 px-3 py-2 text-sm text-midground placeholder:text-midground/25 outline-none focus:border-current/30" />
            </div>
          )}

          {/* API Key */}
          {provider.needsKey && (
            <div className="space-y-1.5">
              <label className="text-[0.7rem] font-medium text-midground/50 tracking-wider uppercase">API Key</label>
              <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)}
                placeholder="sk-..."
                className="w-full rounded border border-current/15 bg-black/20 px-3 py-2 text-sm text-midground placeholder:text-midground/25 outline-none focus:border-current/30" />
            </div>
          )}

          {/* Model */}
          <div className="space-y-1.5">
            <label className="text-[0.7rem] font-medium text-midground/50 tracking-wider uppercase">Model</label>
            {providerId === "ollama" && models.length > 0 ? (
              <select value={model} onChange={e => setModel(e.target.value)}
                className="w-full appearance-none rounded border border-current/15 bg-black/20 px-3 py-2 pr-8 text-sm text-midground outline-none focus:border-current/30">
                {models.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            ) : (
              <input value={model} onChange={e => setModel(e.target.value)}
                placeholder={providerId === "openrouter" ? "anthropic/claude-3.5-sonnet" : "gpt-4o"}
                className="w-full rounded border border-current/15 bg-black/20 px-3 py-2 text-sm text-midground placeholder:text-midground/25 outline-none focus:border-current/30" />
            )}
          </div>

          {/* Web search toggle */}
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={searchEnabled} onChange={e => setSearchEnabled(e.target.checked)}
              className="accent-[var(--midground)]" />
            <span className="text-[0.7rem] font-medium text-midground/50 tracking-wider uppercase flex items-center gap-1">
              <Globe className="h-3 w-3" /> Web Search & URL Fetch
            </span>
          </label>

          <Button onClick={saveSettings}
            className="w-full rounded border border-current/20 bg-midground/10 py-2 text-xs font-bold tracking-wider text-midground hover:bg-midground/20">
            Save
          </Button>
        </div>
      )}

      {error && (
        <div className="rounded border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive normal-case">{error}</div>
      )}

      {/* Messages */}
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto space-y-2.5 pr-1"
        style={{ scrollbarWidth: "thin", scrollbarColor: "rgba(240,230,210,0.1) transparent" }}>

        {messages.length === 0 && !showSettings && (
          <div className="flex flex-col items-center justify-center h-full pt-12 gap-6">
            <div className="text-center space-y-2">
              <p className="text-lg font-bold text-midground/20 tracking-wider">What can I help with?</p>
              <p className="text-xs text-midground/15 normal-case">Chat, search the web, fetch URLs — powered by {model.split(":")[0]}</p>
            </div>
            {searchEnabled && (
              <div className="flex flex-wrap gap-2 justify-center max-w-md">
                {["latest AI news 2026", "Hermes Agent features", "best local LLM models"].map(q => (
                  <button key={q} onClick={() => quickSearch(q)}
                    className={cn("rounded-lg border border-current/10 bg-midground/5 px-3 py-1.5",
                      "text-[0.65rem] text-midground/40 hover:text-midground/60 hover:bg-midground/10",
                      "transition-colors flex items-center gap-1.5")}>
                    <Search className="h-2.5 w-2.5" /> {q}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {messages.map((m, i) => {
          if (m.role === "tool") {
            return (
              <div key={i} className="mx-8 rounded-lg border border-current/8 bg-midground/3 px-3 py-2 text-[0.7rem] text-midground/40 space-y-1">
                <div className="flex items-center gap-1.5 font-semibold tracking-wider uppercase text-[0.6rem]">
                  {m.searching ? <Loader2 className="h-3 w-3 animate-spin" /> : m.toolName === "web_search" ? <Search className="h-3 w-3" /> : <Link className="h-3 w-3" />}
                  {m.toolName === "web_search" ? "Web Search" : "URL Fetch"}
                </div>
                <div className="normal-case leading-relaxed" style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>
              </div>
            );
          }
          return (
            <div key={i} className={cn("flex gap-2.5", m.role === "user" ? "justify-end" : "justify-start")}>
              {m.role === "assistant" && (
                <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-midground/10 text-[0.55rem] font-bold text-midground/60">H</div>
              )}
              <div className={cn("max-w-[85%] rounded-lg px-3.5 py-2.5 text-sm leading-relaxed",
                m.role === "user" ? "bg-midground/10 border border-midground/15 text-midground/90"
                  : "bg-card border border-current/10 text-midground/75",
              )} style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                {m.content || (streaming && i === messages.length - 1 ? "..." : "")}
              </div>
            </div>
          );
        })}
      </div>

      {/* Input */}
      <div className="flex gap-2 items-end">
        <textarea ref={inputRef} value={input} onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown} placeholder={searchEnabled ? "Chat or search the web..." : "Message Hermes..."}
          rows={1}
          className={cn("flex-1 resize-none rounded-lg border border-current/15 bg-black/20",
            "px-3.5 py-2.5 text-sm text-midground placeholder:text-midground/25",
            "outline-none focus:border-current/30 max-h-32 normal-case")}
          style={{ scrollbarWidth: "thin" }} />
        <Button onClick={streaming ? () => abortRef.current?.abort() : send}
          className={cn("shrink-0 rounded-lg border px-3 py-2.5",
            streaming ? "border-destructive/30 bg-destructive/10 text-destructive hover:bg-destructive/20"
              : "border-current/20 bg-midground/10 text-midground hover:bg-midground/20")}>
          {streaming ? <X className="h-4 w-4" /> : <Send className="h-4 w-4" />}
        </Button>
      </div>
    </div>
  );
}
