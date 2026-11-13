import { routes } from "@/app/router/paths";
import { Button } from "@/shared/components/Button";
import { Placeholder } from "@/shared/components/Placeholder";
import { FileQuestion } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

export default function NotFoundPage() {
  const { t } = useTranslation("projects");
  const navigate = useNavigate();

  return (
    <Placeholder
      role="alert"
      icon={<FileQuestion className="h-6 w-6" />}
      title={t("workflow.notFoundTitle")}
      description={t("workflow.notFound")}
      action={
        <Button
          size="md"
          variant="primary"
          onClick={() => navigate(routes.projects)}
        >
          {t("workflow.projects")}
        </Button>
      }
    />
  );
}
