import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const outputDir = "C:/Users/ADMIN/Videos/demo-repository/outputs/hackathon-simulation-20260825";
const files = [
  ["simulation_registration_credentials.xlsx", "Registrations", "A1:E8"],
  ["simulation_final_registration_export.xlsx", "Participant Assignments", "A1:M8"],
];

for (const [filename, sheetName, range] of files) {
  const blob = await FileBlob.load(`${outputDir}/${filename}`);
  const workbook = await SpreadsheetFile.importXlsx(blob);
  const table = await workbook.inspect({
    kind: "table",
    range: `${sheetName}!${range}`,
    include: "values,formulas",
    tableMaxRows: 8,
    tableMaxCols: 13,
  });
  const parsed = String(table.ndjson).split("\n").map((line) => {
    try { return JSON.parse(line); } catch { return null; }
  }).find((item) => item?.kind === "table");
  if (!parsed || parsed.rows !== 8) throw new Error(`${filename}: expected inspected rows`);
  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 30 },
    summary: `${filename} formula scan`,
  });
  if (!String(errors.ndjson).includes("matched 0")) throw new Error(`${filename}: formula error detected`);
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 0.8, format: "png" });
  await fs.writeFile(`${outputDir}/${filename.replace(/\.xlsx$/, "-preview.png")}`, new Uint8Array(await preview.arrayBuffer()));
  console.log(JSON.stringify({ filename, rows: parsed.rows, columns: parsed.cols, formulaErrors: 0 }));
}
