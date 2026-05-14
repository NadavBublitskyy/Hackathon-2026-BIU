import { FileCode2, X } from "lucide-react";

const renderList = (label, values = []) => {
  if (!values.length) {
    return null;
  }

  return (
    <div className="definition-row">
      <span>{label}</span>
      <div>
        {values.map((value) => (
          <code key={value}>{value}</code>
        ))}
      </div>
    </div>
  );
};

export function GraphNodeDetails({ selectedNode, onClear }) {
  if (!selectedNode) {
    return (
      <aside className="node-details empty">
        <FileCode2 size={18} />
        <span>Select a graph node to focus code-file questions on that file.</span>
      </aside>
    );
  }

  const definitions = selectedNode.definitions || {};

  return (
    <aside className="node-details">
      <div className="node-details-header">
        <div>
          <span>{selectedNode.group || "root"}</span>
          <h3>{selectedNode.label}</h3>
        </div>
        <button type="button" aria-label="Clear selected file" onClick={onClear}>
          <X size={16} />
        </button>
      </div>
      <p>{selectedNode.id}</p>
      {renderList("Classes", definitions.classes)}
      {renderList("Functions", definitions.functions)}
      {renderList("Variables", definitions.variables)}
    </aside>
  );
}
