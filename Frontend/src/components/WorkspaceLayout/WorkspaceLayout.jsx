export function WorkspaceLayout({ leftPanel, rightPanel }) {
  return (
    <section className="workspace-layout">
      <div className="workspace-pane chat-pane">{leftPanel}</div>
      <div className="workspace-pane graph-pane">{rightPanel}</div>
    </section>
  );
}
