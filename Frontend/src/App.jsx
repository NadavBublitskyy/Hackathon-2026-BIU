import { BrainCircuit, GitBranch } from "lucide-react";
import { ChatPanel } from "./components/ChatPanel/ChatPanel";
import { GraphNodeDetails } from "./components/GraphNodeDetails/GraphNodeDetails";
import { LoadingOverlay } from "./components/LoadingOverlay/LoadingOverlay";
import { RepoGraphFlow } from "./components/RepoGraph/RepoGraphFlow";
import { RepoUrlForm } from "./components/RepoUrlForm/RepoUrlForm";
import { WorkspaceLayout } from "./components/WorkspaceLayout/WorkspaceLayout";
import { useChatController } from "./hooks/useChatController";
import { useRepoSession } from "./hooks/useRepoSession";

export default function App() {
  const repoSession = useRepoSession();
  const chatController = useChatController({
    repoSessionId: repoSession.repoSessionId,
    selectedNode: repoSession.selectedNode,
  });

  const isBootstrapping = repoSession.status === "validating" || repoSession.status === "ingesting";

  return (
    <main className="app-shell">
      <header className="top-bar">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">
            <BrainCircuit size={22} />
          </span>
          <div>
            <h1>Repo Explorer</h1>
            <p>Context-aware codebase onboarding</p>
          </div>
        </div>
        {repoSession.repoMeta ? (
          <div className="repo-chip">
            <GitBranch size={16} />
            <span>{repoSession.repoMeta.owner}/{repoSession.repoMeta.repo}</span>
          </div>
        ) : null}
      </header>

      {!repoSession.isReady ? (
        <section className="repo-entry-panel">
          <RepoUrlForm
            repoUrl={repoSession.repoUrl}
            status={repoSession.status}
            error={repoSession.error}
            onRepoUrlChange={repoSession.setRepoUrl}
            onSubmit={repoSession.ingestRepo}
          />
        </section>
      ) : (
        <WorkspaceLayout
          leftPanel={
            <ChatPanel
              messages={chatController.messages}
              status={chatController.status}
              error={chatController.error}
              selectedNode={repoSession.selectedNode}
              onAsk={chatController.askQuestion}
              onClear={chatController.clearMessages}
              onClearNode={() => repoSession.setSelectedNode(null)}
            />
          }
          rightPanel={
            <div className="graph-workspace">
              <RepoGraphFlow
                graphData={repoSession.graphData}
                selectedNode={repoSession.selectedNode}
                onSelectNode={repoSession.setSelectedNode}
              />
              <GraphNodeDetails selectedNode={repoSession.selectedNode} onClear={() => repoSession.setSelectedNode(null)} />
            </div>
          }
        />
      )}

      {isBootstrapping ? (
        <LoadingOverlay
          title={repoSession.status === "validating" ? "Checking GitHub repository" : "Indexing repository"}
          detail={repoSession.status === "validating" ? "No GitHub token or OAuth is required for public repos." : "Waiting for structure.json, code_chunks.json, and graph data."}
        />
      ) : null}
    </main>
  );
}
