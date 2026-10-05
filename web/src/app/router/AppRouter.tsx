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
const SignUpOTPPage = lazy(() => import("@/features/auth/pages/SignUpOTPPage"));
const CompleteProfilePage = lazy(
  () => import("@/features/auth/pages/CompleteProfilePage"),
);
const ForgotPasswordPage = lazy(
  () => import("@/features/auth/pages/ForgotPasswordPage"),
);
const ForgotPasswordOTPPage = lazy(
  () => import("@/features/auth/pages/ForgotPasswordOTPPage"),
);
const ForgotPasswordResetPage = lazy(
  () => import("@/features/auth/pages/ForgotPasswordResetPage"),
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
const CreateDeploymentPage = lazy(
  () => import("@/features/deployments/pages/CreateDeploymentPage"),
);
const TrainingModelPage = lazy(
  () => import("@/features/training/pages/TrainingModelPage"),
);
const TrainingJobDetailPage = lazy(
  () => import("@/features/training/pages/TrainingJobDetailPage"),
);
const TrainingJobOverviewPage = lazy(
  () => import("@/features/training/pages/TrainingJobOverviewPage"),
);
const TrainingJobLogsPage = lazy(
  () => import("@/features/training/pages/TrainingJobLogsPage"),
);
const TrainingJobMetricsPage = lazy(
  () => import("@/features/training/pages/TrainingJobMetricsPage"),
);
const TrainingJobArtifactsPage = lazy(
  () => import("@/features/training/pages/TrainingJobArtifactsPage"),
);
const TrainingJobConfigPage = lazy(
  () => import("@/features/training/pages/TrainingJobConfigPage"),
);
const CreateTrainingJobPage = lazy(
  () => import("@/features/training/pages/CreateTrainingJobPage"),
);
const MetadataTrainingJobPage = lazy(
  () => import("@/features/training/pages/MetadataTrainingJobPage"),
);
const SourceTrainingJobPage = lazy(
  () => import("@/features/training/pages/SourceTrainingJobPage"),
);
const ExecutionTrainingJobPage = lazy(
  () => import("@/features/training/pages/ExecutionTrainingJobPage"),
);
const EvolutionPage = lazy(
  () => import("@/features/evolution/pages/EvolutionPage"),
);
const DriftMonitoringPage = lazy(
  () => import("@/features/monitoring/pages/DriftMonitoringPage"),
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
  () => import("@/features/api-tokens/pages/ApiTokensPage"),
);
const ApiKeyPage = lazy(() => import("@/features/api-tokens/pages/ApiKeyPage"));
const NotFoundPage = lazy(() => import("./NotFoundPage"));
const ProjectRouteBoundary = lazy(() => import("./ProjectRouteBoundary"));

const router = createBrowserRouter(
  createRoutesFromElements(
    <>
      <Route element={<AuthLayout />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignUpPage />} />
        <Route path="/signup/verify-otp" element={<SignUpOTPPage />} />
        <Route
          path="/signup/complete-profile"
          element={<CompleteProfilePage />}
        />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route
          path="/forgot-password/verify-otp"
          element={<ForgotPasswordOTPPage />}
        />
        <Route
          path="/forgot-password/reset"
          element={<ForgotPasswordResetPage />}
        />
        <Route path="/oauth/github/callback" element={<GitHubCallbackPage />} />
      </Route>
      <Route path="/" element={<Navigate to="/dashboard/projects" replace />} />
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
          <Route path="monitoring" element={<DriftMonitoringPage />} />
          <Route
            path="monitoring/report/:runId"
            element={<DriftReportPage />}
          />
          <Route path="training" element={<TrainingModelPage />} />
          <Route path="evolution" element={<EvolutionPage />} />
        </Route>
        <Route path="overview" element={<ProjectOverviewPage />} />
        <Route path="deployment" element={<DeploymentPage />} />
        <Route path="monitoring" element={<DriftMonitoringPage />} />
        <Route path="training" element={<TrainingModelPage />} />
        <Route path="evolution" element={<EvolutionPage />} />
        <Route path="deployments/new" element={<CreateDeploymentPage />} />
        <Route path="monitoring/new" element={<CreateDriftMonitoringPage />} />
        <Route
          path="monitoring/:monitorId/edit"
          element={<CreateDriftMonitoringPage />}
        />
        <Route path="training/new" element={<CreateTrainingJobPage />}>
          <Route index element={<Navigate to="metadata" replace />} />
          <Route path="metadata" element={<MetadataTrainingJobPage />} />
          <Route path="source" element={<SourceTrainingJobPage />} />
          <Route path="execution" element={<ExecutionTrainingJobPage />} />
        </Route>
        <Route path="training/jobs/:jobId" element={<TrainingJobDetailPage />}>
          <Route index element={<Navigate to="overview" replace />} />
          <Route path="overview" element={<TrainingJobOverviewPage />} />
          <Route path="logs" element={<TrainingJobLogsPage />} />
          <Route path="metrics" element={<TrainingJobMetricsPage />} />
          <Route path="artifacts" element={<TrainingJobArtifactsPage />} />
          <Route path="config" element={<TrainingJobConfigPage />} />
        </Route>
        <Route path="notifications" element={<NotificationsPage />} />
        <Route path="settings/profile" element={<ProfileSettingPage />} />
        <Route path="api-tokens" element={<ApiTokensPage />} />
        <Route path="api-tokens/new" element={<ApiKeyPage />} />
        <Route path="api-tokens/:keyId" element={<ApiKeyPage />} />
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
