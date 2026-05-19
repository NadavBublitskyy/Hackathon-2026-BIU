import { useMemo, useState } from "react";
import { githubService } from "../services/githubService";
import { graphService } from "../services/graphService";
import { ingestionService } from "../services/ingestionService";

export const useRepoSession = () => {
  const [repoUrl, setRepoUrl] = useState("");
  const [repoMeta, setRepoMeta] = useState(null);
  const [repoSessionId, setRepoSessionId] = useState(null);
  const [graphData, setGraphData] = useState({ nodes: [], edges: [] });
  const [selectedNode, setSelectedNode] = useState(null);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");

  const isReady = useMemo(() => Boolean(repoSessionId), [repoSessionId]);

  const resetRepo = () => {
    setRepoMeta(null);
    setRepoSessionId(null);
    setGraphData({ nodes: [], edges: [] });
    setSelectedNode(null);
    setStatus("idle");
    setError("");
  };

  const ingestRepo = async (url) => {
    setError("");
    setStatus("validating");

    try {
      const validation = await githubService.validatePublicRepo(url);

      if (!validation.isValid) {
        setError(validation.error);
        setStatus("error");
        return;
      }

      setRepoUrl(validation.normalizedUrl);
      setRepoMeta(validation);
      setStatus("ingesting");

      const result = await ingestionService.ingestRepo(validation.normalizedUrl);

      setRepoSessionId(result.repoSessionId);
      setGraphData(result.graphData);
      setStatus("ready");
    } catch (caughtError) {
      setError(caughtError.message || "Failed to ingest repository.");
      setStatus("error");
    }
  };

  const selectGraphNode = async (node) => {
    if (!node) {
      setSelectedNode(null);
      return;
    }

    const basicNode = { ...node, isLoadingDetails: Boolean(repoSessionId) };
    setSelectedNode(basicNode);

    if (!repoSessionId || !node.id) {
      return;
    }

    try {
      const details = await graphService.getNodeDetails({ repoSessionId, nodeId: node.id });
      setSelectedNode((currentNode) => {
        if (currentNode?.id !== node.id) {
          return currentNode;
        }

        return { ...currentNode, ...details, isLoadingDetails: false };
      });
    } catch (caughtError) {
      setSelectedNode((currentNode) => {
        if (currentNode?.id !== node.id) {
          return currentNode;
        }

        return {
          ...currentNode,
          isLoadingDetails: false,
          detailError: caughtError.message || "Could not load file details.",
        };
      });
    }
  };

  return {
    repoUrl,
    repoMeta,
    repoSessionId,
    graphData,
    selectedNode,
    status,
    error,
    isReady,
    setRepoUrl,
    setSelectedNode: selectGraphNode,
    ingestRepo,
    resetRepo,
  };
};
