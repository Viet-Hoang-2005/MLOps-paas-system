import { productionPreview } from "@/features/monitoring/productionPreview";
import type { ProductionDataRecord } from "@/features/monitoring/types";
import Papa from "papaparse";
import { describe, expect, it } from "vitest";

describe("Monitoring productionPreview & Papaparse Serialization", () => {
  it("should extract flat columns keeping prediction last without mutating original records", () => {
    const records: ProductionDataRecord[] = [
      {
        id: "r1",
        project_id: "project-1",
        model_version_id: "version-1",
        features: {
          x: 1,
          label: 'comma, quote"',
          prediction: "feature collision",
        },
        prediction: "safe",
        timestamp: "2026-01-01T00:00:00Z",
      },
      {
        id: "r2",
        project_id: "project-1",
        model_version_id: "version-1",
        features: { y: 2, x: null, nested: { score: 1 } },
        prediction: "attack",
        timestamp: "2026-01-01T00:01:00Z",
      },
    ];

    const unchanged = structuredClone(records);
    const result = productionPreview(records);

    expect(result.fields).toEqual(["x", "label", "y", "nested", "prediction"]);
    expect(result.data).toEqual([
      ["1", 'comma, quote"', "", "", "safe"],
      ["", "", "2", '{"score":1}', "attack"],
    ]);

    expect(records).toEqual(unchanged);

    // Verify CSV serialization and round-trip parsing
    const csv = Papa.unparse(result);
    const parsed = Papa.parse<Record<string, string>>(csv, { header: true }).data;

    expect(parsed).toEqual([
      { x: "1", label: 'comma, quote"', y: "", nested: "", prediction: "safe" },
      { x: "", label: "", y: "2", nested: '{"score":1}', prediction: "attack" },
    ]);
  });

  it("should return empty data for empty records", () => {
    expect(productionPreview([]).data).toEqual([]);
    expect(productionPreview([]).fields).toEqual(["prediction"]);
  });
});
