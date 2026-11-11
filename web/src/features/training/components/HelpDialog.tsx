import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Copy } from "lucide-react";
import BaseDialog from "@/shared/components/BaseDialog";
import { Button } from "@/shared/components/Button";
import { toast } from "@/shared/lib/toastStore";

export interface HelpDialogProps {
  onClose: () => void;
}

function getHelpPythonSnippet(isVi: boolean): string {
  if (isVi) {
    return `import os
import json
import joblib
import pandas as pd
from pathlib import Path

# Environment và Secret đã khai báo trên giao diện
batch_size = int(os.environ.get("BATCH_SIZE", "32"))
api_token = os.environ["API_TOKEN"]  # Không print Secret

# Đọc Input, giữ nguyên cấu trúc thư mục
input_dir = Path(os.environ["SM_CHANNEL_TRAIN"])
df = pd.read_csv(input_dir / "data" / "train.csv")

# Ghi dữ liệu trung gian
work_dir = Path(os.environ["MLOPS_WORK_DIR"])
df.head().to_csv(work_dir / "sample.csv", index=False)

# Sau khi huấn luyện, lưu model chính thức
model_dir = Path(os.environ["SM_MODEL_DIR"])
joblib.dump(model, model_dir / "model.joblib")

# Xuất metrics
output_dir = Path(os.environ["SM_OUTPUT_DIR"])
(output_dir / "metrics.json").write_text(
    json.dumps({"accuracy": 0.95}),
    encoding="utf-8",
)
`;
  }

  return `import os
import json
import joblib
import pandas as pd
from pathlib import Path

# Environment and Secret declared in the UI
batch_size = int(os.environ.get("BATCH_SIZE", "32"))
api_token = os.environ["API_TOKEN"]  # Do not print Secret

# Read Input, preserving folder structure
input_dir = Path(os.environ["SM_CHANNEL_TRAIN"])
df = pd.read_csv(input_dir / "data" / "train.csv")

# Write intermediate working data
work_dir = Path(os.environ["MLOPS_WORK_DIR"])
df.head().to_csv(work_dir / "sample.csv", index=False)

# After training, save official model
model_dir = Path(os.environ["SM_MODEL_DIR"])
joblib.dump(model, model_dir / "model.joblib")

# Export metrics
output_dir = Path(os.environ["SM_OUTPUT_DIR"])
(output_dir / "metrics.json").write_text(
    json.dumps({"accuracy": 0.95}),
    encoding="utf-8",
)
`;
}

export function HelpDialog({ onClose }: HelpDialogProps) {
  const { t, i18n } = useTranslation("training");
  const isVi = i18n.language.startsWith("vi");
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(getHelpPythonSnippet(isVi));
      setCopied(true);
      toast.success(t("studio.copied"));
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
    }
  }

  return (
    <BaseDialog
      title={t("studio.helpDialogTitle")}
      className="w-[min(94vw,48rem)]"
      onClose={onClose}
    >
      <div className="space-y-5">
        <div className="relative overflow-hidden rounded-surface border border-terminal-border bg-terminal">
          <pre className="custom-scrollbar overflow-x-auto p-4 font-mono text-style-code text-color-terminal-foreground">
            <span className="text-color-syntax-keyword">import</span>{" "}
            <span className="text-color-syntax-variable">os</span>
            {"\n"}
            <span className="text-color-syntax-keyword">import</span>{" "}
            <span className="text-color-syntax-variable">json</span>
            {"\n"}
            <span className="text-color-syntax-keyword">import</span>{" "}
            <span className="text-color-syntax-variable">joblib</span>
            {"\n"}
            <span className="text-color-syntax-keyword">import</span>{" "}
            <span className="text-color-syntax-variable">pandas</span>{" "}
            <span className="text-color-syntax-keyword">as</span>{" "}
            <span className="text-color-syntax-variable">pd</span>
            {"\n"}
            <span className="text-color-syntax-keyword">from</span>{" "}
            <span className="text-color-syntax-variable">pathlib</span>{" "}
            <span className="text-color-syntax-keyword">import</span>{" "}
            <span className="text-color-syntax-type">Path</span>
            {"\n\n"}
            <span className="text-color-syntax-comment">
              {isVi
                ? "# Environment và Secret đã khai báo trên giao diện"
                : "# Environment and Secret declared in the UI"}
            </span>
            {"\n"}
            <span className="text-color-syntax-variable">batch_size</span> ={" "}
            <span className="text-color-syntax-function">int</span>(
            <span className="text-color-syntax-variable">os</span>.
            <span className="text-color-syntax-property">environ</span>.
            <span className="text-color-syntax-function">get</span>(
            <span className="text-color-syntax-string">"BATCH_SIZE"</span>,{" "}
            <span className="text-color-syntax-string">"32"</span>))
            {"\n"}
            <span className="text-color-syntax-variable">api_token</span> ={" "}
            <span className="text-color-syntax-variable">os</span>.
            <span className="text-color-syntax-property">environ</span>[
            <span className="text-color-syntax-string">"API_TOKEN"</span>]{"  "}
            <span className="text-color-syntax-comment">
              {isVi ? "# Không print Secret" : "# Do not print Secret"}
            </span>
            {"\n\n"}
            <span className="text-color-syntax-comment">
              {isVi
                ? "# Đọc Input, giữ nguyên cấu trúc thư mục"
                : "# Read Input, preserving folder structure"}
            </span>
            {"\n"}
            <span className="text-color-syntax-variable">input_dir</span> ={" "}
            <span className="text-color-syntax-type">Path</span>(
            <span className="text-color-syntax-variable">os</span>.
            <span className="text-color-syntax-property">environ</span>[
            <span className="text-color-syntax-string">"SM_CHANNEL_TRAIN"</span>
            ])
            {"\n"}
            <span className="text-color-syntax-variable">df</span> ={" "}
            <span className="text-color-syntax-variable">pd</span>.
            <span className="text-color-syntax-function">read_csv</span>(
            <span className="text-color-syntax-variable">input_dir</span> /{" "}
            <span className="text-color-syntax-string">"data"</span> /{" "}
            <span className="text-color-syntax-string">"train.csv"</span>)
            {"\n\n"}
            <span className="text-color-syntax-comment">
              {isVi
                ? "# Ghi dữ liệu trung gian"
                : "# Write intermediate working data"}
            </span>
            {"\n"}
            <span className="text-color-syntax-variable">work_dir</span> ={" "}
            <span className="text-color-syntax-type">Path</span>(
            <span className="text-color-syntax-variable">os</span>.
            <span className="text-color-syntax-property">environ</span>[
            <span className="text-color-syntax-string">"MLOPS_WORK_DIR"</span>])
            {"\n"}
            <span className="text-color-syntax-variable">df</span>.
            <span className="text-color-syntax-function">head</span>().
            <span className="text-color-syntax-function">to_csv</span>(
            <span className="text-color-syntax-variable">work_dir</span> /{" "}
            <span className="text-color-syntax-string">"sample.csv"</span>,{" "}
            <span className="text-color-syntax-property">index</span>=
            <span className="text-color-syntax-keyword">False</span>)
            {"\n\n"}
            <span className="text-color-syntax-comment">
              {isVi
                ? "# Sau khi huấn luyện, lưu model chính thức"
                : "# After training, save official model"}
            </span>
            {"\n"}
            <span className="text-color-syntax-variable">model_dir</span> ={" "}
            <span className="text-color-syntax-type">Path</span>(
            <span className="text-color-syntax-variable">os</span>.
            <span className="text-color-syntax-property">environ</span>[
            <span className="text-color-syntax-string">"SM_MODEL_DIR"</span>])
            {"\n"}
            <span className="text-color-syntax-variable">joblib</span>.
            <span className="text-color-syntax-function">dump</span>(
            <span className="text-color-syntax-variable">model</span>,{" "}
            <span className="text-color-syntax-variable">model_dir</span> /{" "}
            <span className="text-color-syntax-string">"model.joblib"</span>)
            {"\n\n"}
            <span className="text-color-syntax-comment">
              {isVi ? "# Xuất metrics" : "# Export metrics"}
            </span>
            {"\n"}
            <span className="text-color-syntax-variable">output_dir</span> ={" "}
            <span className="text-color-syntax-type">Path</span>(
            <span className="text-color-syntax-variable">os</span>.
            <span className="text-color-syntax-property">environ</span>[
            <span className="text-color-syntax-string">"SM_OUTPUT_DIR"</span>])
            {"\n"}
            (<span className="text-color-syntax-variable">output_dir</span> /{" "}
            <span className="text-color-syntax-string">"metrics.json"</span>
            ).
            <span className="text-color-syntax-function">write_text</span>(
            {"\n    "}
            <span className="text-color-syntax-variable">json</span>.
            <span className="text-color-syntax-function">dumps</span>({"{"}
            <span className="text-color-syntax-string">"accuracy"</span>:{" "}
            <span className="text-color-syntax-number">0.95</span>
            {"}"}),
            {"\n    "}
            <span className="text-color-syntax-property">encoding</span>=
            <span className="text-color-syntax-string">"utf-8"</span>,
            {"\n"}
            )
          </pre>
          <button
            type="button"
            onClick={() => void handleCopy()}
            className="absolute right-3 top-3 rounded-compact bg-terminal-header p-2 text-color-terminal-muted shadow-sm ring-1 ring-terminal-border transition-colors hover:bg-terminal-border hover:text-color-terminal-foreground active:bg-terminal-muted"
            title={t("studio.copyCode")}
          >
            {copied ? (
              <Check className="h-4 w-4 text-color-success" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
          </button>
        </div>

        <div className="flex justify-end pt-2">
          <Button variant="secondary" onClick={onClose}>
            {t("studio.close")}
          </Button>
        </div>
      </div>
    </BaseDialog>
  );
}

export default HelpDialog;
