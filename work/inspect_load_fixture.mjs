import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";
import fs from "node:fs/promises";
import crypto from "node:crypto";

const source = "../load_test/bid_to_build_registration_accounts_2026.xlsx";
const input = await FileBlob.load(source);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheetSummary = await workbook.inspect({
  kind: "sheet",
  include: "id,name",
  maxChars: 3000,
});
console.log(sheetSummary.ndjson);

const sheet = workbook.worksheets.getItemAt(0);
const used = sheet.getUsedRange(true);
const rows = used?.values ?? [];
const headers = rows[0] ?? [];
const normalizedHeaders = headers.map((value) => String(value ?? "").trim());
const emailIndex = normalizedHeaders.findIndex((value) => /email|login/i.test(value));
const passwordIndex = normalizedHeaders.findIndex((value) => /password/i.test(value));
const dataRows = rows.slice(1).filter((row) => row.some((value) => value !== null && String(value ?? "").trim() !== ""));
const emailValues = emailIndex >= 0
  ? dataRows.map((row) => String(row[emailIndex] ?? "").trim().toLowerCase()).filter(Boolean)
  : [];
const passwordCount = passwordIndex >= 0
  ? dataRows.filter((row) => String(row[passwordIndex] ?? "").length > 0).length
  : 0;

console.log(JSON.stringify({
  firstSheetHeaders: normalizedHeaders,
  populatedRows: dataRows.length,
  emailColumnFound: emailIndex >= 0,
  uniqueEmailCount: new Set(emailValues).size,
  passwordColumnFound: passwordIndex >= 0,
  populatedPasswordCount: passwordCount,
}));

const emailDigests = [...new Set(emailValues)].map((value) =>
  crypto.createHash("sha256").update(value).digest("hex"),
);
await fs.writeFile(
  "authoritative-email-digests.json",
  JSON.stringify({ emailDigests }),
  { encoding: "utf8", mode: 0o600 },
);
