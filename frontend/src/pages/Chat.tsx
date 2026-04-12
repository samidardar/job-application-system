import { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowUp, Paperclip, Image, ArrowLeft, Wrench } from "lucide-react";
import { Link } from "react-router-dom";
import VideoBackground from "@/components/VideoBackground";
import FloatingP from "@/components/FloatingP";
import BubbleNav from "@/components/BubbleNav";
import logo from "@/assets/logo.png";
import { consultant, ApiError } from "@/lib/api";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  toolEvents?: ToolEvent[];
}

interface ToolEvent {
  type: "tool_start" | "tool_end";
  tool: string;
  input?: Record<string, unknown>;
  result?: string;
}

const SUGGESTIONS = [
  "Guide-moi pour trouver une alternance",
  "Quels secteurs recrutent en 2026 ?",
  "Comment réussir mon entretien ?",
  "Aide-moi à choisir entre deux offres",
];

const Chat = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 160) + "px";
    }
  }, [input]);

  // Ensure a conversation exists before sending
  const ensureConversation = useCallback(async (): Promise<string> => {
    if (conversationId) return conversationId;
    const conv = await consultant.createConversation();
    setConversationId(conv.id);
    return conv.id;
  }, [conversationId]);

  const sendMessage = useCallback(async (text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || isTyping) return;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: msg,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsTyping(true);
    setError(null);

    // Placeholder for the AI response while streaming
    const aiMsgId = crypto.randomUUID();
    const toolEvents: ToolEvent[] = [];
    setMessages((prev) => [
      ...prev,
      { id: aiMsgId, role: "assistant", content: "", timestamp: new Date(), toolEvents },
    ]);

    try {
      const convId = await ensureConversation();
      const reader = await consultant.chatStream(convId, msg);
      const decoder = new TextDecoder();
      let buffer = "";
      let fullContent = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Process complete SSE lines
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;

          try {
            const evt = JSON.parse(raw) as Record<string, unknown>;

            if ("chunk" in evt && typeof evt.chunk === "string") {
              fullContent += evt.chunk;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === aiMsgId ? { ...m, content: fullContent } : m,
                ),
              );
            } else if (evt.event === "tool_start") {
              const te: ToolEvent = {
                type: "tool_start",
                tool: String(evt.tool ?? ""),
                input: evt.input as Record<string, unknown> | undefined,
              };
              toolEvents.push(te);
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === aiMsgId ? { ...m, toolEvents: [...toolEvents] } : m,
                ),
              );
            } else if (evt.event === "tool_end") {
              const te: ToolEvent = {
                type: "tool_end",
                tool: String(evt.tool ?? ""),
                result: String(evt.result ?? ""),
              };
              toolEvents.push(te);
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === aiMsgId ? { ...m, toolEvents: [...toolEvents] } : m,
                ),
              );
            } else if (evt.event === "done") {
              // Stream complete
              break;
            } else if (evt.event === "error") {
              setError(String(evt.message ?? "Une erreur est survenue."));
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === aiMsgId
                    ? { ...m, content: "Je suis désolé, une erreur est survenue. Veuillez réessayer." }
                    : m,
                ),
              );
            }
          } catch {
            // Ignore malformed SSE frames
          }
        }
      }
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Impossible de contacter le serveur.";
      setError(message);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === aiMsgId
            ? { ...m, content: "Je suis désolé, une erreur est survenue. Veuillez réessayer." }
            : m,
        ),
      );
    } finally {
      setIsTyping(false);
    }
  }, [input, isTyping, ensureConversation]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void sendMessage();
    }
  };

  const isEmpty = messages.length === 0;

  return (
    <div className="h-screen flex flex-col relative overflow-hidden">
      <VideoBackground />
      <FloatingP />

      {/* Top bar */}
      <header className="relative z-10 flex items-center justify-between px-5 py-4 border-b border-border/10 backdrop-blur-sm bg-background/20">
        <Link
          to="/"
          className="flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span className="text-xs font-light tracking-widest uppercase">Retour</span>
        </Link>
        <div className="flex items-center gap-2">
          <img src={logo} alt="Postulio" className="w-6 h-6" />
          <span className="text-xs font-medium tracking-[0.15em] uppercase text-foreground/70">
            Consultant IA
          </span>
        </div>
        <Link
          to="/dashboard"
          className="text-xs font-light tracking-widest uppercase text-muted-foreground hover:text-foreground transition-colors"
        >
          Dashboard
        </Link>
      </header>

      {/* Error banner */}
      {error && (
        <div className="relative z-10 px-4 py-2 bg-red-900/30 border-b border-red-500/20 text-xs text-red-400 font-light text-center">
          {error}
        </div>
      )}

      {/* Messages area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto relative z-10">
        {isEmpty ? (
          <div className="h-full flex flex-col items-center justify-center px-6">
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
              className="text-center"
            >
              <img src={logo} alt="" className="w-12 h-12 mx-auto mb-6 opacity-60" />
              <h1 className="text-xl md:text-2xl font-extralight tracking-tight text-foreground/80">
                Ton mentor carrière
              </h1>
              <p className="mt-2 text-xs text-muted-foreground font-light">
                Je te guide, te conseille et t'accompagne à chaque étape
              </p>
            </motion.div>

            {/* Suggestions */}
            <motion.div
              className="mt-8 grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-lg w-full"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.3 }}
            >
              {SUGGESTIONS.map((s, i) => (
                <button
                  key={i}
                  onClick={() => void sendMessage(s)}
                  className="text-left px-4 py-3 rounded-2xl border border-border/20 bg-card/20 backdrop-blur-sm text-xs text-foreground/70 font-light hover:bg-card/40 hover:border-border/40 transition-all duration-300"
                >
                  {s}
                </button>
              ))}
            </motion.div>
          </div>
        ) : (
          <div className="max-w-2xl mx-auto px-4 py-6 space-y-5">
            <AnimatePresence mode="popLayout">
              {messages.map((msg) => (
                <motion.div
                  key={msg.id}
                  initial={{ opacity: 0, y: 12, filter: "blur(4px)" }}
                  animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                  transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                  className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}
                >
                  {/* Tool events (shown for assistant messages) */}
                  {msg.role === "assistant" && msg.toolEvents && msg.toolEvents.length > 0 && (
                    <div className="mb-2 space-y-1 w-full max-w-[85%]">
                      {msg.toolEvents.map((te, idx) => (
                        <div
                          key={idx}
                          className="flex items-center gap-1.5 text-[10px] text-muted-foreground/60 bg-card/20 rounded-lg px-2 py-1"
                        >
                          <Wrench className="w-3 h-3 shrink-0" />
                          <span>
                            {te.type === "tool_start"
                              ? `Outil: ${te.tool}`
                              : `${te.tool} terminé`}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  <div
                    className={`max-w-[85%] px-4 py-3 rounded-2xl text-sm font-light leading-relaxed ${
                      msg.role === "user"
                        ? "bg-primary/90 text-primary-foreground rounded-br-md"
                        : "bg-card/40 backdrop-blur-sm border border-border/20 text-foreground/90 rounded-bl-md"
                    }`}
                  >
                    {msg.content || (msg.role === "assistant" && isTyping ? "…" : "")}
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>

            {isTyping && messages[messages.length - 1]?.role !== "assistant" && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="flex justify-start"
              >
                <div className="px-4 py-3 rounded-2xl rounded-bl-md bg-card/40 backdrop-blur-sm border border-border/20">
                  <div className="flex gap-1.5">
                    {[0, 1, 2].map((i) => (
                      <motion.div
                        key={i}
                        className="w-1.5 h-1.5 rounded-full bg-muted-foreground/50"
                        animate={{ opacity: [0.3, 1, 0.3] }}
                        transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }}
                      />
                    ))}
                  </div>
                </div>
              </motion.div>
            )}
          </div>
        )}
      </div>

      {/* Input area */}
      <div className="relative z-10 px-4 pb-5 pt-2">
        <div className="max-w-2xl mx-auto">
          <div className="flex items-end gap-2 rounded-2xl border border-border/20 bg-card/30 backdrop-blur-md px-3 py-2 focus-within:border-primary/30 transition-colors duration-300">
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept="image/*,.pdf,.doc,.docx"
              className="hidden"
              onChange={(e) => {
                const files = e.target.files;
                if (files?.length) {
                  void sendMessage(`📎 ${Array.from(files).map((f) => f.name).join(", ")}`);
                }
              }}
            />

            <button
              onClick={() => fileInputRef.current?.click()}
              className="p-2 text-muted-foreground hover:text-foreground transition-colors shrink-0"
              title="Joindre un fichier"
            >
              <Paperclip className="w-4 h-4" />
            </button>

            <button
              onClick={() => {
                if (fileInputRef.current) {
                  fileInputRef.current.accept = "image/*";
                  fileInputRef.current.click();
                  fileInputRef.current.accept = "image/*,.pdf,.doc,.docx";
                }
              }}
              className="p-2 text-muted-foreground hover:text-foreground transition-colors shrink-0"
              title="Envoyer une image"
            >
              <Image className="w-4 h-4" />
            </button>

            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Écris ton message..."
              rows={1}
              className="flex-1 bg-transparent text-sm font-light text-foreground placeholder:text-muted-foreground/50 resize-none focus:outline-none py-2 max-h-40"
            />

            <button
              onClick={() => void sendMessage()}
              disabled={!input.trim() || isTyping}
              className="p-2 rounded-full bg-primary text-primary-foreground disabled:opacity-20 transition-all duration-300 hover:brightness-110 active:scale-95 shrink-0"
            >
              <ArrowUp className="w-4 h-4" />
            </button>
          </div>

          <p className="text-center text-[10px] text-muted-foreground/40 mt-2 font-light">
            Postulio IA peut faire des erreurs. Vérifie les informations importantes.
          </p>
        </div>
      </div>
      <BubbleNav />
    </div>
  );
};

export default Chat;
