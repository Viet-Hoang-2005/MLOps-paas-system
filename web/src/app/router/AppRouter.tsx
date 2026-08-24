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
const CatalogLayout = lazy(
  () => import("@/features/catalog/pages/CatalogLayout"),
);
const ModelProjectPage = lazy(
  () => import("@/features/catalog/pages/ModelProjectPage"),
);
const ModelTestingPage = lazy(
  () => import("@/features/catalog/pages/ModelTestingPage"),
);
const ModelManagementPage = lazy(
  () => import("@/features/deploy/pages/ModelManagementPage"),
);
const UploadModelPage = lazy(
  () => import("@/features/deploy/pages/UploadModelPage"),
);
const MetadataModelPage = lazy(
  () => import("@/features/deploy/pages/MetadataModelPage"),
);
const BuildModelPage = lazy(
  () => import("@/features/deploy/pages/BuildModelPage"),
);
const DeployModelPage = lazy(
  () => import("@/features/deploy/pages/DeployModelPage"),
);
const ModelDetailPage = lazy(
  () => import("@/features/deploy/pages/ModelDetailPage"),
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
const DriftReportPage = lazy(
  () => import("@/features/drift/pages/DriftReportPage"),
);
const SettingsLayout = lazy(
  () => import("@/features/settings/pages/SettingsLayout"),
);
const ProfileSettingPage = lazy(
  () => import("@/features/settings/pages/ProfileSettingPage"),
);
const DeveloperSettingPage = lazy(
  () => import("@/features/settings/pages/DeveloperSettingPage"),
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

      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <DashboardLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="home/models" replace />} />
        <Route path="home" element={<CatalogLayout />}>
          <Route index element={<Navigate to="models" replace />} />
          <Route path="models">
            <Route index element={<ModelProjectPage />} />
            <Route path=":modelId" element={<ModelProjectPage />} />
          </Route>
          <Route path="model-testing">
            <Route index element={<ModelTestingPage />} />
            <Route path=":modelId" element={<ModelTestingPage />} />
          </Route>
        </Route>
        <Route path="drift-monitoring">
          <Route index element={<DriftMonitoringPage />} />
          <Route path=":modelId" element={<DriftMonitoringPage />} />
          <Route path=":modelId/new" element={<CreateDriftMonitoringPage />} />
          <Route path=":modelId/edit" element={<CreateDriftMonitoringPage />} />
          <Route path=":modelId/report/:runId" element={<DriftReportPage />} />
        </Route>
        <Route path="model-training">
          <Route index element={<TrainingModelPage />} />
          <Route path=":modelId" element={<TrainingModelPage />} />
          <Route path="create" element={<CreateTrainingJobPage />}>
            <Route index element={<Navigate to="metadata" replace />} />
            <Route path="metadata" element={<MetadataTrainingJobPage />} />
            <Route path="source" element={<SourceTrainingJobPage />} />
            <Route path="execution" element={<ExecutionTrainingJobPage />} />
          </Route>
          <Route
            path="jobs/:jobId"
            element={<Navigate to="details/overview" replace />}
          />
          <Route path="jobs/:jobId/details" element={<TrainingJobDetailPage />}>
            <Route index element={<Navigate to="overview" replace />} />
            <Route path="overview" element={<TrainingJobOverviewPage />} />
            <Route path="logs" element={<TrainingJobLogsPage />} />
            <Route path="metrics" element={<TrainingJobMetricsPage />} />
            <Route path="artifacts" element={<TrainingJobArtifactsPage />} />
            <Route path="config" element={<TrainingJobConfigPage />} />
            <Route path="*" element={<Navigate to="overview" replace />} />
          </Route>
        </Route>
        <Route path="model-evolution">
          <Route index element={<RegistryPage />} />
          <Route path=":familyId" element={<RegistryPage />} />
        </Route>
        <Route path="management" element={<ModelManagementPage />} />
        <Route path="management/model/upload" element={<UploadModelPage />}>
          <Route index element={<Navigate to="metadata" replace />} />
          <Route path="metadata" element={<MetadataModelPage />} />
          <Route path="build" element={<BuildModelPage />} />
          <Route path="deploy" element={<DeployModelPage />} />
        </Route>
        <Route
          path="management/model/:modelId"
          element={<Navigate to="information" replace />}
        />
        <Route
          path="management/model/:modelId/:tab"
          element={<ModelDetailPage />}
        />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route path="settings" element={<SettingsLayout />}>
          <Route index element={<Navigate to="profile" replace />} />
          <Route path="profile" element={<ProfileSettingPage />} />
          <Route path="developer" element={<DeveloperSettingPage />} />
        </Route>
        <Route
          path="settings/developer/api-keys/create"
          element={<ApiKeyPage />}
        />
        <Route
          path="settings/developer/api-keys/:keyId"
          element={<ApiKeyPage />}
        />
        <Route
          path="*"
          element={<Navigate to="/dashboard/home/models" replace />}
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
