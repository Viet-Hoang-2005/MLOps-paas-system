import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import * as Popover from "@radix-ui/react-popover";
import { useQuery } from "@tanstack/react-query";
import {
  Bell,
  Check,
  ChevronDown,
  ChevronUp,
  createLucideIcon,
  Laptop,
  LogOut,
  Menu,
  Moon,
  Plus,
  Settings,
  Sun,
  UserCircle,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import AdaptMLLogo from "@/assets/icons/AdaptML.png";
import type { ThemeMode } from "@/app/theme/theme";
import { routes } from "@/app/router/paths";
import { useTheme } from "@/app/theme/useTheme";
import { useAuth } from "@/features/auth/hooks/useAuth";
import { useModelSelection } from "@/features/projects/hooks/useModelSelection";
import { getProfile } from "@/features/settings/api/profileApi";
import { settingsQueryKeys } from "@/features/settings/queryKeys";
import type { UserProfile } from "@/features/settings/types";
import { Button } from "@/shared/components/Button";
import { Search } from "@/shared/components/Search";

const getInitials = (profile: UserProfile | null, fallback: string) => {
  const source = profile?.full_name || profile?.email || fallback;
  return source
    .split(/\s|@/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
};

const themeOptions: Array<{ value: ThemeMode; icon: typeof Sun }> = [
  { value: "light", icon: Sun },
  { value: "dark", icon: Moon },
  { value: "system", icon: Laptop },
];

const VnIcon = createLucideIcon("vn", [
  ["path", { d: "m3 6 4 12 4-12", key: "v" }],
  ["path", { d: "M14 18V6l7 12V6", key: "n" }],
]);

const EnIcon = createLucideIcon("en", [
  ["path", { d: "M10.5 6H3v12h7.5", key: "e-body" }],
  ["path", { d: "M3 12h6.5", key: "e-mid" }],
  ["path", { d: "M14 18V6l7 12V6", key: "n" }],
]);

export default function Header({
  onOpenNavigation,
}: {
  onOpenNavigation: () => void;
}) {
  const navigate = useNavigate();
  const { t, i18n } = useTranslation("common");
  const { logout } = useAuth();
  const { models, selectedModel, selectModel } = useModelSelection();
  const { mode, resolvedTheme, setMode } = useTheme();
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [search, setSearch] = useState("");

  const { data: profile = null } = useQuery({
    queryKey: settingsQueryKeys.profile(),
    queryFn: getProfile,
  });
  const initials = useMemo(
    () => getInitials(profile, t("profile.initialsFallback")),
    [profile, t],
  );
  const visibleModels = useMemo(() => {
    const term = search.trim().toLowerCase();
    return term
      ? models.filter((model) => model.name.toLowerCase().includes(term))
      : models;
  }, [models, search]);

  return (
    <header className="relative z-30 flex h-16 shrink-0 items-center justify-between border-b border-border bg-surface px-3 md:px-4 xl:px-5">
      <Button
        size="icon"
        variant="ghost"
        icon={<Menu className="h-5 w-5" />}
        onClick={onOpenNavigation}
        className="md:hidden"
        aria-label={t("actions.openNavigation")}
      />

      <button
        type="button"
        onClick={() => navigate("/dashboard/projects")}
        className="hidden min-w-40 shrink-0 items-center gap-3 rounded-surface focus-visible:ring-2 focus-visible:ring-ring sm:flex xl:min-w-48"
      >
        <img src={AdaptMLLogo} alt="" className="h-7 w-7" />
        <span className="text-style-section-title font-semibold text-color-foreground">
          {/* i18n-ignore: AdaptML is the product brand. */}
          Adapt<span className="text-color-info italic">ML</span>
        </span>
      </button>

      <div className="mx-1 min-w-0 flex-1 sm:mx-3 sm:max-w-md lg:absolute lg:left-1/2 lg:top-1/2 lg:w-[min(420px,42vw)] lg:-translate-x-1/2 lg:-translate-y-1/2">
        <Popover.Root open={modelMenuOpen} onOpenChange={setModelMenuOpen}>
          <Popover.Trigger asChild>
            <Button
              variant="secondary"
              size="md"
              fullWidth
              className="min-w-0 justify-between rounded-surface px-2 text-left text-style-body-strong shadow-sm sm:px-4"
              aria-label={t("modelSelector.label")}
            >
              <span className="truncate">
                {selectedModel?.name || t("modelSelector.empty")}
              </span>
              {modelMenuOpen ? (
                <ChevronUp className="h-4 w-4 shrink-0 text-color-muted-foreground" />
              ) : (
                <ChevronDown className="h-4 w-4 shrink-0 text-color-muted-foreground" />
              )}
            </Button>
          </Popover.Trigger>
          <Popover.Portal>
            <Popover.Content
              align="start"
              sideOffset={8}
              className="z-50 w-(--radix-popover-trigger-width) rounded-surface border border-border bg-surface p-2 shadow-(--shadow-overlay) animate-fade-in"
            >
              <Search
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                onClear={() => setSearch("")}
                placeholder={t("modelSelector.search")}
                clearAriaLabel={t("modelSelector.clearSearch")}
                wrapperClassName="mb-2"
                autoFocus
              />
              <div className="max-h-72 overflow-y-auto">
                {visibleModels.length ? (
                  visibleModels.map((model) => (
                    <button
                      key={model.id}
                      type="button"
                      onClick={() => {
                        selectModel(model.id);
                        setModelMenuOpen(false);
                        setSearch("");
                      }}
                      className="flex min-h-10 w-full items-center justify-between gap-3 rounded-compact px-3 py-2 text-left hover:bg-muted"
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-style-body-strong text-color-foreground">
                          {model.name}
                        </span>
                        <span className="block truncate text-style-caption capitalize text-color-muted-foreground">
                          {t(
                            `statuses.${model.lifecycle_status || "registered"}`,
                          )}{" "}
                          · {model.flavor || t("statuses.registered")}
                        </span>
                      </span>
                      {selectedModel?.id === model.id && (
                        <Check className="h-4 w-4 shrink-0 text-color-primary" />
                      )}
                    </button>
                  ))
                ) : (
                  <p className="px-3 py-8 text-center text-style-body text-color-muted-foreground">
                    {t("modelSelector.noMatches")}
                  </p>
                )}
              </div>
              <div className="mt-2 border-t border-border pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setModelMenuOpen(false);
                    navigate(routes.newProject);
                  }}
                  className="flex h-10 w-full items-center gap-2 rounded-surface px-3 text-style-body-strong text-color-muted-foreground hover:bg-muted hover:text-color-foreground"
                >
                  <Plus className="h-4 w-4" /> {t("actions.uploadModel")}
                </button>
              </div>
            </Popover.Content>
          </Popover.Portal>
        </Popover.Root>
      </div>

      <div className="flex min-w-0 shrink-0 items-center justify-end gap-1 sm:min-w-40 sm:gap-2 xl:min-w-48">
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <Button
              size="icon"
              variant="secondary"
              icon={
                (i18n.resolvedLanguage ?? "en").startsWith("vi") ? (
                  <VnIcon className="h-5 w-5" />
                ) : (
                  <EnIcon className="h-5 w-5" />
                )
              }
              aria-label={t("language.current", {
                language: t(`language.${i18n.resolvedLanguage ?? "en"}`),
              })}
              title={t("language.current", {
                language: t(`language.${i18n.resolvedLanguage ?? "en"}`),
              })}
            />
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              align="end"
              sideOffset={8}
              className="z-50 min-w-44 rounded-surface border border-border bg-surface p-1.5 shadow-(--shadow-overlay) animate-fade-in"
            >
              <DropdownMenu.Label className="px-2 py-1.5 text-style-overline uppercase text-color-muted-foreground">
                {t("language.label")}
              </DropdownMenu.Label>
              <DropdownMenu.RadioGroup
                value={i18n.resolvedLanguage ?? "en"}
                onValueChange={(value) => {
                  void i18n.changeLanguage(value);
                }}
              >
                {(["vi", "en"] as const).map((language) => (
                  <DropdownMenu.RadioItem
                    key={language}
                    value={language}
                    className="flex h-9 items-center gap-2 rounded-compact px-2 text-style-body text-color-foreground outline-none hover:bg-muted focus:bg-muted"
                  >
                    <span className="flex-1">{t(`language.${language}`)}</span>
                    <DropdownMenu.ItemIndicator>
                      <Check className="h-4 w-4 text-color-primary" />
                    </DropdownMenu.ItemIndicator>
                  </DropdownMenu.RadioItem>
                ))}
              </DropdownMenu.RadioGroup>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>

        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <Button
              size="icon"
              variant="secondary"
              icon={
                resolvedTheme === "dark" ? (
                  <Moon className="h-5 w-5" />
                ) : (
                  <Sun className="h-5 w-5" />
                )
              }
              aria-label={t("theme.current", { mode: t(`theme.${mode}`) })}
              title={t("theme.current", { mode: t(`theme.${mode}`) })}
            />
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              align="end"
              sideOffset={8}
              className="z-50 min-w-44 rounded-surface border border-border bg-surface p-1.5 shadow-(--shadow-overlay) animate-fade-in"
            >
              <DropdownMenu.Label className="px-2 py-1.5 text-style-overline uppercase text-color-muted-foreground">
                {t("theme.appearance")}
              </DropdownMenu.Label>
              {themeOptions.map((option) => {
                const Icon = option.icon;
                return (
                  <DropdownMenu.Item
                    key={option.value}
                    onSelect={() => setMode(option.value)}
                    className="flex h-9 items-center gap-2 rounded-compact px-2 text-style-body text-color-foreground outline-none hover:bg-muted focus:bg-muted"
                  >
                    <Icon className="h-4 w-4 text-color-muted-foreground" />
                    <span className="flex-1">{t(`theme.${option.value}`)}</span>
                    {mode === option.value && (
                      <Check className="h-4 w-4 text-color-primary" />
                    )}
                  </DropdownMenu.Item>
                );
              })}
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>

        <Button
          size="icon"
          aria-label={t("navigation.notification")}
          title={t("navigation.notification")}
          icon={<Bell className="h-5 w-5" />}
          variant="secondary"
          onClick={() => navigate("/dashboard/notifications")}
        />

        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <Button
              size="icon"
              variant="secondary"
              className="group relative overflow-hidden rounded-full border border-border bg-surface text-style-body-strong text-color-primary-foreground shadow-sm sm:ml-2"
              aria-label={t("userMenu.open")}
            >
              {profile?.avatar ? (
                <img
                  src={profile.avatar}
                  alt=""
                  className="h-full w-full rounded-full object-cover"
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center rounded-full bg-primary">
                  {initials || <UserCircle className="h-5 w-5" />}
                </div>
              )}
              <div className="pointer-events-none absolute inset-0 rounded-full bg-surface-hover opacity-0 transition-opacity group-hover:opacity-40 group-active:opacity-60" />
            </Button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              align="end"
              sideOffset={8}
              className="z-50 w-56 rounded-surface border border-border bg-surface p-2 shadow-(--shadow-overlay) animate-fade-in"
            >
              <DropdownMenu.Label className="border-b border-border px-3 py-2">
                <p className="truncate text-style-body-strong text-color-foreground">
                  {profile?.full_name || t("profile.fallbackName")}
                </p>
                <p className="truncate text-style-caption text-color-muted-foreground">
                  {profile?.email || t("profile.signedIn")}
                </p>
              </DropdownMenu.Label>
              <DropdownMenu.Item
                onSelect={() => navigate("/dashboard/settings/profile")}
                className="mt-2 flex h-10 items-center gap-2 rounded-compact px-2 text-style-body text-color-foreground outline-none hover:bg-muted focus:bg-muted"
              >
                <Settings className="h-4 w-4 text-color-muted-foreground" />{" "}
                {t("navigation.setting")}
              </DropdownMenu.Item>
              <DropdownMenu.Item
                onSelect={logout}
                className="flex h-10 items-center gap-2 rounded-compact px-2 text-style-body text-color-danger outline-none hover:bg-danger-subtle focus:bg-danger-subtle"
              >
                <LogOut className="h-4 w-4" /> {t("actions.logout")}
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      </div>
    </header>
  );
}
