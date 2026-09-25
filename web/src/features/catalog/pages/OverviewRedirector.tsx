import { Navigate } from "react-router-dom";
import { useProjectContext } from "@/features/catalog/hooks/useProjectContext";

export default function OverviewRedirector() {
  const { overview } = useProjectContext();

  if (overview.present.has_production) {
    return <Navigate to="present" replace />;
  }

  return <Navigate to="draft" replace />;
}
