"use client";

import { useChat } from "@ai-sdk/react";
import { useEffect, useRef } from "react";

const SUGGESTED = [
  "What did the swarm find, and how was it confirmed?",
  "How do we know the fix actually worked?",
  "Why can a human trust the merge?",
];

export default function Chat() {
  const { messages, input, handleInputChange, handleSubmit, append, status } = useChat({
    api: "/api/chat",
  });
  const boxRef = useRef<HTMLDivElement>(null);
  const busy = status === "submitted" || status === "streaming";

  useEffect(() => {
    if (boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight;
  }, [messages]);

  return (
    <section className="view">
      <h1 className="title">Ask NEO</h1>
      <div className="chat">
        <div className="chat-log" ref={boxRef}>
          {messages.length === 0 && (
            <div className="chat-empty">
              <p className="dim">Ask about this run. NEO answers from the run artifact.</p>
              <div className="chat-suggest">
                {SUGGESTED.map((s) => (
                  <button
                    key={s}
                    className="suggest"
                    disabled={busy}
                    onClick={() => append({ role: "user", content: s })}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((msg) => (
            <div className={`msg msg-${msg.role}`} key={msg.id}>
              <span className="msg-who faint mono">{msg.role === "user" ? "you" : "neo"}</span>
              <div className="msg-body">{msg.content}</div>
            </div>
          ))}
          {busy && messages[messages.length - 1]?.role === "user" && (
            <div className="msg msg-assistant">
              <span className="msg-who faint mono">neo</span>
              <div className="msg-body dim live-caret" />
            </div>
          )}
        </div>
        <form className="chat-form" onSubmit={handleSubmit}>
          <input
            className="chat-input"
            value={input}
            onChange={handleInputChange}
            placeholder="Ask about the exploit, the fix, the proof…"
            autoComplete="off"
          />
          <button className="chat-send" type="submit" disabled={busy || !input.trim()}>
            ask
          </button>
        </form>
      </div>
    </section>
  );
}
