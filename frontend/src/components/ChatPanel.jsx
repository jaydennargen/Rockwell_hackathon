import { useEffect, useRef, useState } from "react";
import * as api from "../api/client.js";

function suggestions(report, role) {
  if (role === "specialist")
    return ["Why was this escalated?", "How often does this product family come back within 6 months?"];
  if (report.predicted) return ["What should the technician check first?", "Which parts usually get replaced?"];
  return ["What happens next with this order?"];
}

export default function ChatPanel({ report, role }) {
  const id = report.order_id;
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const endRef = useRef(null);
  const processing = report.status === "PROCESSING";

  useEffect(() => {
    api.getChat(id).then((d) => setMessages(d.messages)).catch((e) => setError(e.message));
  }, [id]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages, sending]);

  async function send(msg) {
    const body = msg.trim();
    if (!body || sending) return;
    setError(null);
    setSending(true);
    const temp = { id: `tmp-${Date.now()}`, role: "user", content: body };
    setMessages((m) => [...m, temp]);
    setText("");
    try {
      const { reply } = await api.sendChat(id, body);
      setMessages((m) => [...m, reply]);
    } catch (e) {
      setMessages((m) => m.filter((x) => x.id !== temp.id));
      setText(body);
      setError(e.message);
    } finally {
      setSending(false);
    }
  }

  return (
    <section className="chat" aria-label="Ask about this order">
      <header className="chat-head">
        <h2>Ask about this order</h2>
        <p className="muted">
          {role === "specialist"
            ? "Answers can draw on this report and the full repair history."
            : "Answers are based on this order's report."}
        </p>
      </header>

      <div className="chat-log" aria-live="polite">
        {messages.length === 0 && !processing && (
          <div className="chat-empty">
            <p className="muted">Try asking</p>
            {suggestions(report, role).map((s) => (
              <button key={s} className="chip" onClick={() => send(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`msg msg-${m.role}`}>
            <p className="msg-who">{m.role === "user" ? "You" : "Triage assistant"}</p>
            <p className="msg-text">{m.content}</p>
            {m.sql && (
              <details className="msg-sql">
                <summary>Query used</summary>
                <pre>
                  <code>{m.sql}</code>
                </pre>
              </details>
            )}
            {m.sources?.length > 0 && (
              <p className="msg-src">Based on {m.sources.map((s) => s.label).join("; ")}</p>
            )}
          </div>
        ))}
        {sending && (
          <div className="msg msg-assistant">
            <p className="msg-who">Triage assistant</p>
            <p className="msg-text typing" aria-label="Writing a reply">
              <span />
              <span />
              <span />
            </p>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {error && <p className="form-error" role="alert">{error}</p>}
      <form
        className="chat-input"
        onSubmit={(e) => {
          e.preventDefault();
          send(text);
        }}
      >
        <label htmlFor="chat-text" className="sr-only">
          Your question
        </label>
        <textarea
          id="chat-text"
          rows={2}
          value={text}
          disabled={processing}
          placeholder={processing ? "Available once triage finishes" : "Ask a question"}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(text);
            }
          }}
        />
        <button className="btn" type="submit" disabled={processing || sending || !text.trim()}>
          Send
        </button>
      </form>
    </section>
  );
}
