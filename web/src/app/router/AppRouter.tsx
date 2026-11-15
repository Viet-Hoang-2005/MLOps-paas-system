import { lazy, Suspense } from "react";
import {
  createBrowserRouter,
  createRoutesFromElements,
  Navigate,
  Route,
  RouterProvider,
} from "react-router-dom";
import { RouteFallback } from "./RouteFallback";

const AuthLayout = lazy(() => import("@/features/auth/pages/AuthLayout"));
const LoginPage = lazy(() => import("@/features/auth/pages/LoginPage"));
const SignUpPage = lazy(() => import("@/features/auth/pages/SignUpPage"));
const ForgotPasswordPage = lazy(
  () => import("@/features/auth/pages/ForgotPasswordPage"),
);
const GitHubCallbackPage = lazy(
  () => import("@/features/auth/pages/GitHubCallbackPage"),
);
const ProtectedRoute = lazy(() =>
  import("./ProtectedRoute").then((module) => ({
    default: module.ProtectedRoute,
  })),
);
const DashboardLayout = lazy(() => import("@/app/layouts/DashboardLayout"));

const NotificationsPage = lazy(
  () => import("@/features/notifications/pages/NotificationsPage"),
);
const ModelProjectPage = lazy(
  () => import("@/features/projects/pages/ModelProjectPage"),
);
const NewModelProjectPage = lazy(
  () => import("@/features/projects/pages/NewModelProjectPage"),
);
const ProjectOverviewPage = lazy(
  () => import("@/features/overview/pages/ProjectOverviewPage"),
);
const DeploymentPage = lazy(
  () => import("@/features/deployments/pages/DeploymentPage"),
);
const BuildDeploymentPage = lazy(
  () => import("@/features/deployments/pages/BuildDeploymentPage"),
);
const RunDeploymentPage = lazy(
  () => import("@/features/deployments/pages/RunDeploymentPage"),
);
const TrainingModelPage = lazy(
  () => import("@/features/training/pages/TrainingModelPage"),
);
const TrainingWorkspacePage = lazy(
  () => import("@/features/training/pages/TrainingWorkspacePage"),
);
const TrainingJobProjectPage = lazy(
  () => import("@/features/training/pages/TrainingJobProjectPage"),
);
const EvolutionPage = lazy(
  () => import("@/features/evolution/pages/EvolutionPage"),
);
const DriftMonitoringPage = lazy(
  () => import("@/features/monitoring/pages/DriftMonitoringPage"),
);
const DriftMonitoringDetailPage = lazy(
  () => import("@/features/monitoring/pages/DriftMonitoringDetailPage"),
);
const CreateDriftMonitoringPage = lazy(
  () => import("@/features/monitoring/pages/CreateDriftMonitoringPage"),
);
const DriftReportPage = lazy(
  () => import("@/features/monitoring/pages/DriftReportPage"),
);
const ProfileSettingPage = lazy(
  () => import("@/features/settings/pages/ProfileSettingPage"),
);
const ApiTokensPage = lazy(
  () => import("@/features/api-keys/pages/ApiKeyPage"),
);
const ApiKeyPage = lazy(
  () => import("@/features/api-keys/pages/CreateApiKeyPage"),
);
const NotFoundPage = lazy(() => import("./NotFoundPage"));
const ProjectRouteBoundary = lazy(() => import("./ProjectRouteBoundary"));

const router = createBrowserRouter(
  createRoutesFromElements(
    <>
      <Route element={<AuthLayout />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignUpPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/oauth/github/callback" element={<GitHubCallbackPage />} />
      </Route>
      <Route path="/" element={<Navigate to="/dashboard/projects" replace />} />
      <Route
        path="/projects"
        element={<Navigate to="/dashboard/projects" replace />}
      />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <DashboardLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="projects" replace />} />
        <Route path="projects" element={<ModelProjectPage />} />
        <Route path="projects/new" element={<NewModelProjectPage />} />
        <Route path="projects/:modelId" element={<ProjectRouteBoundary />}>
          <Route path="edit" element={<NewModelProjectPage />} />
          <Route path="overview" element={<ProjectOverviewPage />} />
          <Route path="deployment" element={<DeploymentPage />} />
          <Route
            path="deployments"
            element={<Navigate to="deployment" replace />}
          />
          <Route path="monitoring" element={<DriftMonitoringPage />} />
          <Route
            path="monitoring/:monitorId"
            element={<DriftMonitoringDetailPage />}
          />
          <Route
            path="monitoring/report/:runId"
            element={<DriftReportPage />}
          />
          <Route path="training" element={<TrainingModelPage />} />
          <Route path="evolution" element={<EvolutionPage />} />
        </Route>
        <Route path="overview" element={<ProjectOverviewPage />} />
        <Route path="deployment" element={<DeploymentPage />} />
        <Route
          path="deployments"
          element={<Navigate to="deployment" replace />}
        />
        <Route path="monitoring" element={<DriftMonitoringPage />} />
        <Route path="training" element={<TrainingModelPage />} />
        <Route path="evolution" element={<EvolutionPage />} />
        <Route path="deployment/build/new" element={<BuildDeploymentPage />} />
        <Route
          path="deployment/run/:projectId/:buildId"
          element={<RunDeploymentPage />}
        />
        <Route path="monitoring/new" element={<CreateDriftMonitoringPage />} />
        <Route
          path="monitoring/:monitorId/edit"
          element={<CreateDriftMonitoringPage />}
        />
        <Route
          path="monitoring/:monitorId"
          element={<DriftMonitoringDetailPage />}
        />
        <Route
          path="training/workspaces/:workspaceId"
          element={<TrainingWorkspacePage />}
        />
        <Route
          path="training/workspaces/:workspaceId/job/:jobId"
          element={<TrainingWorkspacePage />}
        />
        <Route
          path="training/workspaces/:workspaceId/job/:jobId/project"
          element={<TrainingJobProjectPage />}
        />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route path="settings/profile" element={<ProfileSettingPage />} />
        <Route path="api-keys" element={<ApiTokensPage />} />
        <Route path="api-keys/new" element={<ApiKeyPage />} />
        <Route path="api-keys/:keyId" element={<ApiKeyPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/login" replace />} />
    </>,
  ),
);
export function AppRouter() {
  return (
    <Suspense fallback={<RouteFallback />}>
      <RouterProvider router={router} />
    </Suspense>
  );
}
