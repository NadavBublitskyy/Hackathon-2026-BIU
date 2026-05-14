import { useMemo, useState } from "react";
import { githubService } from "../services/githubService";
import { ingestionService } from "../services/ingestionService";

export const useRepoSession = () => {
  const [repoUrl, setRepoUrl] = useState("");
  const [repoMeta, setRepoMeta] = useState(null);
  const [structureJson, setStructureJson] = useState(null);
  const [codeChunksJson, setCodeChunksJson] = useState(null);
  const [graphData, setGraphData] = useState({ nodes: [], edges: [] });
  const [selectedNode, setSelectedNode] = useState(null);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");

  const isReady = useMemo(() => Boolean(structureJson && codeChunksJson), [structureJson, codeChunksJson]);

  const resetRepo = () => {
    setRepoMeta(null);
    setStructureJson(null);
    setCodeChunksJson(null);
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

      setStructureJson(result.structureJson);
      setCodeChunksJson(result.codeChunksJson);
      setGraphData(result.graphData);
      setStatus("ready");
    } catch (caughtError) {
      setError(caughtError.message || "Failed to ingest repository.");
      setStatus("error");
    }
  };

  return {
    repoUrl,
    repoMeta,
    structureJson,
    codeChunksJson,
    graphData,
    selectedNode,
    status,
    error,
    isReady,
    setRepoUrl,
    setSelectedNode,
    ingestRepo,
    resetRepo,
  };
};
