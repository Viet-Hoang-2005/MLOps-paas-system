import type { ReactNode } from "react";
import { Plus } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { routes } from "@/app/router/paths";
import { useModelSelection } from "@/features/projects/hooks/useModelSelection";
import { Button } from "@/shared/components/Button";
import { Placeholder } from "@/shared/components/Placeholder";

export interface NoProjectPlaceholderProps {
  title: string;
  description: string;
  icon: ReactNode;
}

export function NoProjectPlaceholder({
  title,
  description,
  icon,
}: NoProjectPlaceholderProps) {
  const navigate = useNavigate();
  const { t } = useTranslation("projects");
  const { t: tCommon } = useTranslation("common");
  const { selectedModel } = useModelSelection();

  return (
    <Placeholder
      title={title}
      description={description}
      icon={icon}
      additional={
        selectedModel ? selectedModel.name : tCommon("modelSelector.empty")
      }
      action={
        <Button
          size="md"
          icon={<Plus className="h-4 w-4" />}
          onClick={() => navigate(routes.newProject)}
        >
          {t("workflow.newProject")}
        </Button>
      }
    />
  );
}
