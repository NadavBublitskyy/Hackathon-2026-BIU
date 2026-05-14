import { Eraser, Loader2 } from "lucide-react";
import { ChatMessage } from "../ChatMessage/ChatMessage";
import { PromptComposer } from "../PromptComposer/PromptComposer";

export function ChatPanel({ messages, status, error, selectedNode, onAsk, onClear }) {
  const isAnswering = status === "answering";

  return (
    <section className="chat-panel">
      <div className="panel-header">
        <div>
          <h2>Ask the repo</h2>
          <p>Questions are routed to general chat, Viki context retrieval, or repo-wide Brain context.</p>
        </div>
        <button className="icon-text-button" type="button" onClick={onClear} disabled={!messages.length}>
          <Eraser size={16} />
          Clear
        </button>
      </div>

      <div className="message-list">
        {messages.length ? (
          messages.map((message) => <ChatMessage key={message.id} message={message} />)
        ) : (
          <div className="empty-chat">
            <span>Ready</span>
            <p>Ask about a file, a feature location, or the repository architecture.</p>
          </div>
        )}
        {isAnswering ? (
          <div className="answering-row">
            <Loader2 size={16} className="spin" />
            Routing request and waiting for the model
          </div>
        ) : null}
      </div>

      {error ? <div className="chat-error">{error}</div> : null}

      <PromptComposer disabled={isAnswering} selectedNode={selectedNode} onAsk={onAsk} />
    </section>
  );
}
