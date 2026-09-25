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
const ProjectLayout = lazy(() => import("@/app/layouts/ProjectLayout"));
const NotificationsPage = lazy(
  () => import("@/features/notifications/pages/NotificationsPage"),
);
const ModelManagementPage = lazy(
  () => import("@/features/deploy/pages/ModelManagementPage"),
);
const UploadModelPage = lazy(
  () => import("@/features/deploy/pages/UploadModelPage"),
);
const ModelDetailPage = lazy(
  () => import("@/features/deploy/pages/ModelDetailPage"),
);
const ModelTestingPage = lazy(
  () => import("@/features/catalog/pages/ModelTestingPage"),
);
const OverviewRedirector = lazy(
  () => import("@/features/catalog/pages/OverviewRedirector"),
);
const OverviewPresentTab = lazy(
  () => import("@/features/catalog/pages/OverviewPresentTab"),
);
const OverviewDraftTab = lazy(
  () => import("@/features/catalog/pages/OverviewDraftTab"),
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
const RegistryPage = lazy(
  () => import("@/features/registry/pages/RegistryPage"),
);
const DriftMonitoringPage = lazy(
  () => import("@/features/drift/pages/DriftMonitoringPage"),
);
const CreateDriftMonitoringPage = lazy(
  () => import("@/features/drift/pages/CreateDriftMonitoringPage"),
);
const MonitoringBasePage = lazy(() => import("@/features/drift/pages/MonitoringBasePage"));
const DriftReportPage = lazy(
  () => import("@/features/drift/pages/DriftReportPage"),
);
const SettingsLayout = lazy(
  () => import("@/features/settings/pages/SettingsLayout"),
);
const ProfileSettingPage = lazy(
  () => import("@/features/settings/pages/ProfileSettingPage"),
);
const ApiTokensPage = lazy(
  () => import("@/features/settings/pages/ApiTokensPage"),
);
const ApiKeyPage = lazy(() => import("@/features/settings/pages/ApiKeyPage"));

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

        {/* Canonical Model Projects Route */}
        <Route path="projects" element={<ModelManagementPage />} />
        <Route path="projects/new" element={<UploadModelPage />} />

        {/* Project Context & Tabs */}
        <Route path="projects/:projectId" element={<ProjectLayout />}>
          <Route index element={<OverviewRedirector />} />
          <Route path="overview" element={<OverviewRedirector />} />
          <Route path="overview/present" element={<OverviewPresentTab />} />
          <Route path="overview/draft" element={<OverviewDraftTab />} />
          <Route path="deployment" element={<ModelDetailPage />} />
          <Route path="deployment/playground" element={<ModelTestingPage />} />

          {/* Monitoring */}
          <Route path="monitoring" element={<Navigate to="production" replace />} />
          <Route path="monitoring/production" element={<DriftMonitoringPage />} />
          <Route path="monitoring/production/configure" element={<CreateDriftMonitoringPage />} />
          <Route path="monitoring/base" element={<MonitoringBasePage />} />
          <Route path="monitoring/report/:runId" element={<DriftReportPage />} />

          {/* Training */}
          <Route path="training" element={<TrainingModelPage />} />
          <Route path="training/create" element={<CreateTrainingJobPage />}>
            <Route index element={<Navigate to="metadata" replace />} />
            <Route path="metadata" element={<MetadataTrainingJobPage />} />
            <Route path="source" element={<SourceTrainingJobPage />} />
            <Route path="execution" element={<ExecutionTrainingJobPage />} />
          </Route>
          <Route
            path="training/jobs/:jobId"
            element={<Navigate to="details/overview" replace />}
          />
          <Route
            path="training/jobs/:jobId/details"
            element={<TrainingJobDetailPage />}
          >
            <Route index element={<Navigate to="overview" replace />} />
            <Route path="overview" element={<TrainingJobOverviewPage />} />
            <Route path="logs" element={<TrainingJobLogsPage />} />
            <Route path="metrics" element={<TrainingJobMetricsPage />} />
            <Route path="artifacts" element={<TrainingJobArtifactsPage />} />
            <Route path="config" element={<TrainingJobConfigPage />} />
            <Route path="*" element={<Navigate to="overview" replace />} />
          </Route>

          {/* Evolution */}
          <Route path="evolution" element={<RegistryPage />} />
          <Route path="evolution/versions/:versionId" element={<RegistryPage />} />
        </Route>

        {/* First-Class Independent Top-level Pages */}
        <Route path="notifications" element={<NotificationsPage />} />
        <Route path="api-tokens" element={<ApiTokensPage />} />
        <Route
          path="api-tokens/create"
          element={<ApiKeyPage />}
        />
        <Route
          path="api-tokens/:keyId"
          element={<ApiKeyPage />}
        />

        <Route path="settings" element={<SettingsLayout />}>
          <Route index element={<Navigate to="profile" replace />} />
          <Route path="profile" element={<ProfileSettingPage />} />
        </Route>

        {/* Catch-all */}
        <Route
          path="*"
          element={<Navigate to="/dashboard/projects" replace />}
        />
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
