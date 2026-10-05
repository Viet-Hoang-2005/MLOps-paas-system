import type { ProductionDataRecord } from "@/features/monitoring/types";

// Preserve feature columns across rows and keep prediction last, without
// changing values in the stored telemetry or interpreting technical content.
export function productionPreview(records: ProductionDataRecord[]) {
  const fields = [
    ...new Set(records.flatMap((record) => Object.keys(record.features))),
  ].filter((name) => name !== "prediction");
  fields.push("prediction");
  const cell = (value: unknown): string =>
    value == null
      ? ""
      : typeof value === "object"
        ? JSON.stringify(value)
        : String(value);
  return {
    fields,
    data: records.map((record) => [
      ...fields.slice(0, -1).map((field) => cell(record.features[field])),
      cell(record.prediction),
    ]),
  };
}
