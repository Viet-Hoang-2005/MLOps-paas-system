import {
  FileSpreadsheet,
  Play,
  Pause,
  Download,
  Trash2,
  SendHorizontal,
  X,
  Check,
  Percent,
} from "lucide-react";
import { useRef, useState, useMemo, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useBlocker } from "react-router-dom";
import { ConfirmModal } from "@/shared/components/ConfirmModal";
import { TerminalViewer } from "@/shared/components/TerminalViewer";
import { Button } from "@/shared/components/Button";
import { useModelSelection } from "@/features/catalog/hooks/useModelSelection";
import { predictWithModelProject } from "@/features/catalog/api/catalogApi";
import { getApiErrorMessage } from "@/shared/api/errors";
import { toast } from "@/shared/components/toastStore";
import { FileDropzone } from "@/shared/components/FileDropzone";
import { CSVEditor } from "@/shared/components/CSVEditor";
import { CardSummary } from "@/shared/components/Card";
import { PageBody } from "@/shared/components/PageBody";

const TARGET_COLUMN_NAMES = new Set([
  "label",
  "target",
  "y",
  "class",
  "output",
  "result",
  "category",
]);

type TestSummary = {
  total: number;
  success: number;
  failed: number;
  withExpected: number;
  correct: number;
  mismatch: number;
};

type TestLogEntry = {
  id: string;
  time: string;
  level: "info" | "success" | "warning" | "error";
  message: string;
  detail?: string;
};

type PredictionErrorPayload = {
  error?: string;
  message?: string;
  hint?: string;
  received_features?: string[];
  detail?: PredictionErrorPayload | string;
};

const isTargetColumn = (name: string) =>
  TARGET_COLUMN_NAMES.has(name.toLowerCase());

const parseCSV = (text: string) => {
  const lines = text.trim().split(/\r?\n/).filter(Boolean);
  const headers =
    lines[0]?.split(",").map((header) => header.trim().replace(/^"|"$/g, "")) ??
    [];
  return lines.slice(1).map((line) => {
    const values = line
      .split(",")
      .map((value) => value.trim().replace(/^"|"$/g, ""));
    return headers.reduce<Record<string, unknown>>((record, header, index) => {
      const rawValue = values[index] ?? "";
      const numericValue = Number(rawValue);
      record[header] =
        rawValue !== "" && Number.isFinite(numericValue)
          ? numericValue
          : rawValue;
      return record;
    }, {});
  });
};

const splitRow = (row: Record<string, unknown>) => {
  const features: Record<string, unknown> = {};
  let expectedLabel: string | undefined;

  for (const [key, value] of Object.entries(row)) {
    if (isTargetColumn(key)) {
      if (expectedLabel === undefined) expectedLabel = String(value);
      continue;
    }
    features[key] = value;
  }

  return { features, expectedLabel };
};

const makeLog = (
  level: TestLogEntry["level"],
  message: string,
  detail?: string,
): TestLogEntry => ({
  id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
  time: new Date().toLocaleTimeString(),
  level,
  message,
  detail,
});

const formatPrediction = (value: unknown) => {
  if (value === null || value === undefined) return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
};

const extractPredictionError = (
  error: unknown,
  copy: { fallback: string; hint: (value: string) => string; received: (value: string) => string },
) => {
  const response = (
    error as { response?: { status?: number; data?: PredictionErrorPayload } }
  )?.response;
  const rawPayload = response?.data;
  const payload =
    typeof rawPayload?.detail === "object" ? rawPayload.detail : rawPayload;
  const message =
    payload?.message ||
    payload?.error ||
    getApiErrorMessage(error, copy.fallback);
  const hint = payload?.hint ? copy.hint(payload.hint) : "";
  const received = payload?.received_features?.length
    ? copy.received(payload.received_features.join(", "))
    : "";

  return {
    status: response?.status,
    title: payload?.error || getApiErrorMessage(error, copy.fallback),
    detail: [message, received, hint].filter(Boolean).join("\n"),
  };
};

export default function ModelTestingPage() {
  const { t } = useTranslation("catalog");
  const { selectedModel } = useModelSelection();
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [csvText, setCsvText] = useState("");
  const [fileName, setFileName] = useState("");
  const [logs, setLogs] = useState<TestLogEntry[]>([]);

  const stringLogs = useMemo(() => {
    return logs.map(
      (log) =>
        `[${log.time}] [${log.level.toUpperCase()}] ${log.message}${log.detail ? `\n${log.detail}` : ""}`,
    );
  }, [logs]);
  const [predictions, setPredictions] = useState<string[]>([]);
  const [summary, setSummary] = useState<TestSummary>({
    total: 0,
    success: 0,
    failed: 0,
    withExpected: 0,
    correct: 0,
    mismatch: 0,
  });
  const [running, setRunning] = useState(false);
  const [testFinished, setTestFinished] = useState(false);
  const isRunningRef = useRef(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [currentRowIndex, setCurrentRowIndex] = useState(0);

  const isDirty = rows.length > 0;

  const blocker = useBlocker(({ currentLocation, nextLocation }) => {
    return isDirty && currentLocation.pathname !== nextLocation.pathname;
  });

  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!isDirty) return;
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [isDirty]);

  const pushLog = (entry: TestLogEntry) =>
    setLogs((current) => [...current, entry]);

  const handleFileChange = async (file?: File) => {
    if (!file) return;
    const text = await file.text();
    const parsedRows = parseCSV(text);
    const parsedTargetColumns = Object.keys(parsedRows[0] ?? {}).filter(
      isTargetColumn,
    );

    setCsvText(text);
    setRows(parsedRows);
    setFileName(file.name);
    setSummary({
      total: 0,
      success: 0,
      failed: 0,
      withExpected: 0,
      correct: 0,
      mismatch: 0,
    });
    setPredictions([]);
    setTestFinished(false);
    setCurrentRowIndex(0);
    setLogs([
      makeLog("info", t("testingPage.loaded", { fileName: file.name, count: parsedRows.length })),
      makeLog(
        parsedTargetColumns.length > 0 ? "warning" : "info",
        parsedTargetColumns.length > 0
          ? t("testingPage.targetsExcluded", { columns: parsedTargetColumns.join(", ") })
          : t("testingPage.noTargetColumns"),
      ),
    ]);
  };

  const handleRemoveFile = () => {
    setRows([]);
    setFileName("");
    setCsvText("");
    setLogs([]);
    setPredictions([]);
    setTestFinished(false);
    setCurrentRowIndex(0);
  };

  const runTesting = async () => {
    if (!selectedModel) {
      toast.warning(t("testingPage.modelRequired"));
      return;
    }
    if (!rows.length) {
      toast.warning(t("testingPage.csvRequired"));
      return;
    }
    if (!selectedModel.endpoint_url) {
      toast.error(t("testingPage.endpointRequired"));
      return;
    }

    if (running) {
      isRunningRef.current = false;
      setRunning(false);
      pushLog(makeLog("info", t("testingPage.paused")));
      return;
    }

    setRunning(true);
    isRunningRef.current = true;

    const isStartingFresh = currentRowIndex === 0 || testFinished;

    let currentSummary: TestSummary;
    let currentPredictions: string[];

    if (isStartingFresh) {
      setCurrentRowIndex(0);
      setTestFinished(false);
      setPredictions([]);
      setSummary({
        total: 0,
        success: 0,
        failed: 0,
        withExpected: 0,
        correct: 0,
        mismatch: 0,
      });
      setLogs([
        makeLog(
          "info",
          t("testingPage.selectedModel", {
            name: selectedModel.name,
            version: selectedModel.version || "v1",
          }),
        ),
        makeLog("info", t("testingPage.endpointLog", { endpoint: selectedModel.endpoint_url })),
        makeLog("info", t("testingPage.running", { count: rows.length })),
      ]);

      currentSummary = {
        total: 0,
        success: 0,
        failed: 0,
        withExpected: 0,
        correct: 0,
        mismatch: 0,
      };
      currentPredictions = [];
    } else {
      pushLog(
        makeLog(
          "info",
          t("testingPage.resuming", { row: currentRowIndex + 1 }),
        ),
      );
      currentSummary = { ...summary };
      currentPredictions = [...predictions];
    }

    let i = isStartingFresh ? 0 : currentRowIndex;

    for (; i < rows.length; i++) {
      if (!isRunningRef.current) break;

      const row = rows[i];
      const { features, expectedLabel } = splitRow(row);
      const rowNumber = i + 1;

      currentSummary.total += 1;
      if (expectedLabel !== undefined) currentSummary.withExpected += 1;

      try {
        const response = await predictWithModelProject(
          selectedModel.endpoint_url,
          features,
        );
        const prediction = formatPrediction(response.prediction);
        const confidence =
          response.confidence == null
            ? ""
            : ` | ${t("testingPage.confidence", { confidence: response.confidence })}`;
        const isCorrect =
          expectedLabel !== undefined &&
          prediction.toLowerCase() === expectedLabel.toLowerCase();

        currentSummary.success += 1;
        if (expectedLabel !== undefined) {
          if (isCorrect) currentSummary.correct += 1;
          else currentSummary.mismatch += 1;
        }

        currentPredictions.push(prediction);

        pushLog(
          makeLog(
            expectedLabel === undefined || isCorrect ? "success" : "warning",
            t("testingPage.rowResult", {
              row: rowNumber,
              prediction,
              expected:
                expectedLabel !== undefined
                  ? t("testingPage.expected", { expected: expectedLabel })
                  : "",
              confidence,
            }),
            expectedLabel !== undefined
              ? isCorrect
                ? t("testingPage.resultCorrect")
                : t("testingPage.resultMismatch")
              : undefined,
          ),
        );
      } catch (error) {
        const parsedError = extractPredictionError(error, {
          fallback: t("testingPage.predictionFailed"),
          hint: (value) => t("testingPage.hint", { hint: value }),
          received: (value) => t("testingPage.receivedFeatures", { features: value }),
        });
        currentSummary.failed += 1;
        currentPredictions.push("ERROR");
        pushLog(
          makeLog(
            "error",
            t("testingPage.requestFailed", {
              row: rowNumber,
              status: parsedError.status
                ? t("testingPage.httpStatus", { status: parsedError.status })
                : "",
              error: parsedError.title,
            }),
            parsedError.detail,
          ),
        );
      }

      setSummary({ ...currentSummary });
      setPredictions([...currentPredictions]);
      setCurrentRowIndex(i + 1);
    }

    if (isRunningRef.current) {
      pushLog(
        makeLog(
          currentSummary.failed > 0 ? "warning" : "success",
          t("testingPage.finished", {
            success: currentSummary.success,
            total: currentSummary.total,
            failed: currentSummary.failed,
          }),
          currentSummary.withExpected > 0
            ? t("testingPage.comparison", {
                correct: currentSummary.correct,
                total: currentSummary.withExpected,
                mismatch: currentSummary.mismatch,
              })
            : undefined,
        ),
      );
      setRunning(false);
      isRunningRef.current = false;
      setTestFinished(true);
      setCurrentRowIndex(0);
    }
  };

  const handleDownloadCSV = () => {
    if (rows.length === 0 || predictions.length === 0) return;

    const headers = Object.keys(rows[0]);
    const newHeaders = [...headers, "Prediction"];

    const csvContent = [
      newHeaders.join(","),
      ...rows.slice(0, predictions.length).map((row, index) => {
        const values = headers.map((h) => row[h]);
        values.push(predictions[index] || "");
        return values.join(",");
      }),
    ].join("\n");

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `tested_${fileName}`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const accuracy =
    summary.withExpected > 0
      ? Math.round((summary.correct / summary.withExpected) * 100)
      : null;

  return (
    <>
      <ConfirmModal
        open={blocker.state === "blocked"}
        title={t("testingPage.leaveTitle")}
        description={t("testingPage.leaveDescription")}
        tone="danger"
        confirmText={t("testingPage.leaveConfirm")}
        onConfirm={() => {
          blocker.proceed?.();
        }}
        onCancel={() => {
          blocker.reset?.();
        }}
      />
      <PageBody className="p-6 h-full">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between mb-6">
          <div>
            <h2 className="text-style-section-title font-bold text-color-foreground">{t("testingPage.title")}</h2>
            <p className="mt-1 text-style-body text-color-muted-foreground">
              {t("testingPage.description", {
                model: selectedModel?.name ?? t("testingPage.selectedModelFallback"),
              })}
            </p>
          </div>
          <div className="flex gap-3">
            {rows.length > 0 && (
              <>
                <Button
                  size="md"
                  variant="danger"
                  icon={<Trash2 className="h-4 w-4" />}
                  onClick={handleRemoveFile}
                >
                  {t("testingPage.remove")}
                </Button>
                <Button
                  size="md"
                  variant="secondary"
                  icon={<FileSpreadsheet className="h-4 w-4" />}
                  onClick={() => fileInputRef.current?.click()}
                >
                  {t("testingPage.uploadCsv")}
                </Button>
                <input
                  type="file"
                  accept=".csv,text/csv"
                  className="hidden"
                  ref={fileInputRef}
                  onChange={(event) => {
                    void handleFileChange(event.target.files?.[0]);
                    event.target.value = "";
                  }}
                />
              </>
            )}
          </div>
        </div>

        {rows.length === 0 ? (
          <div className="flex-1 flex flex-col [&>label]:flex-1">
            <FileDropzone
              accept=".csv,text/csv"
              title={t("testingPage.dropzoneTitle")}
              subtitle={t("testingPage.dropzoneSubtitle")}
              onChange={(file) => void handleFileChange(file || undefined)}
            />
          </div>
        ) : (
          <div className="flex flex-col space-y-6">
            <div>
              <p className="mb-4 text-style-body-strong text-color-foreground">
                {t("testingPage.rowsLoaded", { fileName, count: rows.length })}
              </p>
              <div className="overflow-hidden rounded-surface border border-border h-125">
                <CSVEditor initialCsvText={csvText} readOnly={true} />
              </div>
            </div>

            <div className="border-t border-border pt-6 space-y-6">
              <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div>
                  <h3 className="text-style-section-title font-bold text-color-foreground">
                    {t("testingPage.runTitle")}
                  </h3>
                  <p className="mt-1 text-style-body text-color-muted-foreground">
                    {t("testingPage.runDescription", {
                      model: selectedModel?.name ?? t("testingPage.selectedModelFallback"),
                    })}
                  </p>
                </div>
                <div className="flex gap-3">
                  <Button
                    size="md"
                    variant="secondary"
                    icon={<Download className="h-4 w-4" />}
                    disabled={running || predictions.length === 0}
                    onClick={handleDownloadCSV}
                  >
                    {t("testingPage.download")}
                  </Button>
                  <Button
                    size="md"
                    icon={
                      running ? (
                        <Pause className="h-4 w-4" />
                      ) : (
                        <Play className="h-4 w-4" />
                      )
                    }
                    variant={running ? "danger" : "primary"}
                    onClick={runTesting}
                  >
                    {running ? t("testingPage.pause") : t("testingPage.run")}
                  </Button>
                </div>
              </div>

              <div className="grid gap-3 md:grid-cols-4">
                <CardSummary
                  label={t("testingPage.processed")}
                  value={`${summary.success + summary.failed}/${rows.length}`}
                  helper={t("testingPage.processedHelper")}
                  tone={testFinished && rows.length > 0 ? "info" : "default"}
                  icon={<SendHorizontal className="h-4 w-4" />}
                />
                <CardSummary
                  label={t("testingPage.failed")}
                  value={String(summary.failed)}
                  tone={summary.failed ? "error" : "default"}
                  helper={t("testingPage.failedHelper")}
                  icon={<X className="h-4 w-4" />}
                />
                <CardSummary
                  label={t("testingPage.successful")}
                  value={String(summary.success)}
                  tone={summary.success > 0 ? "success" : "default"}
                  helper={t("testingPage.successfulHelper")}
                  icon={<Check className="h-4 w-4" />}
                />
                <CardSummary
                  label={t("testingPage.accuracy")}
                  value={accuracy === null ? "-" : `${accuracy}%`}
                  tone={
                    accuracy === null
                      ? "default"
                      : summary.mismatch > 0
                        ? "warning"
                        : "success"
                  }
                  helper={
                    summary.withExpected
                      ? t("testingPage.correctHelper", {
                          correct: summary.correct,
                          total: summary.withExpected,
                        })
                      : t("testingPage.noLabels")
                  }
                  icon={<Percent className="h-4 w-4" />}
                />
              </div>

              <div className="mt-6">
                <TerminalViewer
                  title={t("testingPage.consoleTitle")}
                  placeholder={t("testingPage.consolePlaceholder")}
                  logs={stringLogs}
                />
              </div>
            </div>
          </div>
        )}
      </PageBody>
    </>
  );
}
