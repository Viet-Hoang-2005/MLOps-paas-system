import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

export default function NotFoundPage() {
  const { t } = useTranslation("projects");
  return (
    <section
      role="alert"
      className="space-y-4 rounded-surface border border-border bg-surface p-6"
    >
      <h1 className="text-style-heading">{t("workflow.notFound")}</h1>
      <Link
        className="text-color-primary hover:underline"
        to="/dashboard/projects"
      >
        {t("workflow.projects")}
      </Link>
    </section>
  );
}
