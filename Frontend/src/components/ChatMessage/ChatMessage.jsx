import { CheckCircle2, RotateCcw, ShieldAlert } from "lucide-react";
import { RouteBadge } from "../RouteBadge/RouteBadge";
import ReactMarkdown from "react-markdown";

export function ChatMessage({ message }) {
  const isAssistant = message.role === "assistant";

  return (
    <article className={`chat-message ${message.role} ${message.metadata?.isError ? "error" : ""}`}>
      <div className="message-header">
        <span>{isAssistant ? "Brain" : "You"}</span>
        <RouteBadge route={message.metadata?.route} />
      </div>
      <div className="message-body">
        <ReactMarkdown>{message.content}</ReactMarkdown>
      </div>
      {isAssistant ? (
        <div className="message-meta">
          {message.metadata?.model ? <span>{message.metadata.model}</span> : null}
          {typeof message.metadata?.pathsVerified === "boolean" ? (
            <span className={message.metadata.pathsVerified ? "meta-ok" : "meta-warn"}>
              {message.metadata.pathsVerified ? <CheckCircle2 size={14} /> : <ShieldAlert size={14} />}
              {message.metadata.pathsVerified ? "Paths verified" : "Paths need review"}
            </span>
          ) : null}
          {message.metadata?.fallbackUsed ? (
            <span>
              <RotateCcw size={14} />
              Fallback used
            </span>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
