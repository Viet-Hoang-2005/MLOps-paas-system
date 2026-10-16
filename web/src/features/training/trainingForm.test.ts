import {
  buildStoredZip,
  inspectZipFile,
  readZipEntryText,
} from "@/features/training/lib/trainingZip";
import { describe, expect, it } from "vitest";

describe("Training Zip Packaging & Inspection", () => {
  const encoder = new TextEncoder();

  it("should create a valid ZIP and correctly inspect files", async () => {
    const file = buildStoredZip(
      [
        { name: "train.py", data: encoder.encode("print('hello train')") },
        { name: "requirements.txt", data: encoder.encode("scikit-learn\npandas") },
      ],
      "test_source.zip",
    );

    const inspection = await inspectZipFile(file);
    expect(inspection.fileNames).toContain("train.py");
    expect(inspection.fileNames).toContain("requirements.txt");
    expect(inspection.entries.length).toBe(2);
  });

  it("should read entry point text content correctly", async () => {
    const scriptContent = "def train():\n    pass\n";
    const file = buildStoredZip(
      [{ name: "entry.py", data: encoder.encode(scriptContent) }],
      "source.zip",
    );

    const text = await readZipEntryText(file, "entry.py");
    expect(text).toBe(scriptContent);
  });

  it("should throw error when specified entry point does not exist in ZIP", async () => {
    const file = buildStoredZip(
      [{ name: "main.py", data: encoder.encode("print(1)") }],
      "source.zip",
    );

    await expect(readZipEntryText(file, "train.py")).rejects.toThrow(
      "Entry point train.py was not found in source.zip.",
    );
  });
});

