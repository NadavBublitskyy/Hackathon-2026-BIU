import { Boxes, FileCode2, MessageCircleQuestion, Sparkles } from "lucide-react";
import { questionCategories } from "../../utils/questionClassifier";

const routeIcon = {
  [questionCategories.PENDING]: Sparkles,
  [questionCategories.GENERAL]: MessageCircleQuestion,
  [questionCategories.SPECIFIC_CODE]: FileCode2,
  [questionCategories.REPO_WIDE]: Boxes,
};

const routeLabel = {
  [questionCategories.PENDING]: "LLM route",
  [questionCategories.GENERAL]: "General",
  [questionCategories.SPECIFIC_CODE]: "Specific code",
  [questionCategories.REPO_WIDE]: "Repo-wide",
};

export function RouteBadge({ route }) {
  if (!route) {
    return null;
  }

  const Icon = routeIcon[route.category] || MessageCircleQuestion;

  return (
    <span className={`route-badge ${route.category}`}>
      <Icon size={14} />
      {route.label || routeLabel[route.category] || "General"}
    </span>
  );
}
