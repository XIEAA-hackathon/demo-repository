import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = "C:/Users/ADMIN/Videos/demo-repository/outputs/hackathon-simulation-20260825";
await fs.mkdir(outputDir, { recursive: true });

async function saveWorkbook(filename, sheetName, headers, rows, widths) {
  const workbook = Workbook.create();
  const sheet = workbook.worksheets.add(sheetName);
  sheet.showGridLines = false;
  sheet.getRangeByIndexes(0, 0, rows.length + 1, headers.length).values = [headers, ...rows];
  const header = sheet.getRangeByIndexes(0, 0, 1, headers.length);
  header.format = {
    fill: "#35104A",
    font: { bold: true, color: "#FFFFFF" },
    rowHeight: 28,
    verticalAlignment: "center",
  };
  const body = sheet.getRangeByIndexes(1, 0, rows.length, headers.length);
  body.format = {
    font: { color: "#23172B" },
    verticalAlignment: "top",
    borders: { preset: "inside", style: "thin", color: "#E4D9E9" },
  };
  for (let col = 0; col < widths.length; col += 1) {
    sheet.getRangeByIndexes(0, col, rows.length + 1, 1).format.columnWidth = widths[col];
  }
  sheet.freezePanes.freezeRows(1);
  sheet.tables.add(sheet.getRangeByIndexes(0, 0, rows.length + 1, headers.length), true, `${sheetName.replace(/\W/g, "")}Table`);
  const check = await workbook.inspect({ kind: "table", range: `${sheetName}!A1:${String.fromCharCode(64 + headers.length)}${Math.min(rows.length + 1, 8)}`, include: "values,formulas", tableMaxRows: 8, tableMaxCols: 8 });
  console.log(check.ndjson);
  const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 20 }, summary: `${filename} formula scan` });
  console.log(errors.ndjson);
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
  await fs.writeFile(`${outputDir}/${filename.replace(/\.xlsx$/, "-preview.png")}`, new Uint8Array(await preview.arrayBuffer()));
  const xlsx = await SpreadsheetFile.exportXlsx(workbook);
  await xlsx.save(`${outputDir}/${filename}`);
}

const registrationRows = Array.from({ length: 30 }, (_, index) => {
  const number = String(index + 1).padStart(2, "0");
  return [`Team ${number}`, `Leader ${number}`, `leader${number}@example.com`];
});

await saveWorkbook(
  "simulation_registration_30_teams.xlsx",
  "Registrations",
  ["Team Name", "Leader Name", "Leader Email"],
  registrationRows,
  [24, 24, 34],
);

await saveWorkbook(
  "simulation_round1_problems.xlsx",
  "Round 1 Problems",
  ["Problem Number", "Title", "Description"],
  [
    [1, "Adaptive Noise Cancellation", "Develop an AI-assisted system that removes changing environmental noise from field communications."],
    [2, "Tropical Cyclone Prediction", "Forecast cyclone intensity and movement using weather observations and historical tracks."],
    [3, "Emergency Communication", "Build a resilient low-bandwidth communication platform for disaster response teams."],
    [4, "Autonomous Logistics", "Optimize autonomous delivery routes for supplies across disrupted transport networks."],
    [5, "Disaster Mapping", "Generate rapidly updated damage maps from aerial and satellite imagery."],
    [6, "Secure Field Network", "Create a secure peer-to-peer network for teams operating without reliable infrastructure."],
  ],
  [18, 34, 88],
);

await saveWorkbook(
  "simulation_wildcard_problems.xlsx",
  "Wildcard Problems",
  ["Problem Number", "Title", "Description"],
  [
    [1, "Adaptive Relief Routing", "Continuously reroute relief vehicles as roads, priorities, and resource availability change."],
    [2, "Offline Medical Triage", "Support explainable field triage decisions on devices with intermittent connectivity."],
    [3, "Community Signal Mesh", "Coordinate verified emergency updates across a delay-tolerant community mesh network."],
  ],
  [18, 34, 88],
);
