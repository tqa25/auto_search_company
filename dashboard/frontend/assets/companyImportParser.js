function isCompanyHeader(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return [
    "company name",
    "company name (english)",
    "tên công ty",
    "ten cong ty",
    "name",
  ].includes(normalized);
}

function isTaxCodeHeader(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return [
    "tax code",
    "tax_code",
    "mã số thuế",
    "ma so thue",
    "mst",
  ].includes(normalized);
}

function parseCsvRows(text) {
  const rows = [];
  let row = [];
  let field = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];

    if (char === "\"") {
      if (inQuotes && next === "\"") {
        field += "\"";
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }

    if (char === "," && !inQuotes) {
      row.push(field);
      field = "";
      continue;
    }

    if ((char === "\n" || char === "\r") && !inQuotes) {
      if (char === "\r" && next === "\n") i += 1;
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
      continue;
    }

    field += char;
  }

  if (field || row.length) {
    row.push(field);
    rows.push(row);
  }

  return rows;
}

export function parseCompanyImportText(text, fileName = "") {
  const normalizedText = String(text || "").replace(/^\uFEFF/, "");
  const isCsv = String(fileName || "").toLowerCase().endsWith(".csv");

  if (!isCsv) {
    return normalizedText
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .filter((line, index) => index !== 0 || !isCompanyHeader(line));
  }

  const rows = parseCsvRows(normalizedText).filter((row) => row.some((cell) => String(cell || "").trim()));
  if (!rows.length) return [];

  const header = rows[0];
  const nameIndex = header.findIndex(isCompanyHeader);
  const taxCodeIndex = header.findIndex(isTaxCodeHeader);
  const hasHeader = nameIndex >= 0 || taxCodeIndex >= 0;
  const resolvedNameIndex = nameIndex >= 0 ? nameIndex : 0;
  const dataRows = hasHeader ? rows.slice(1) : rows;

  return dataRows
    .map((row) => {
      const name = String(row[resolvedNameIndex] || "").trim();
      const taxCode = taxCodeIndex >= 0 ? String(row[taxCodeIndex] || "").trim() : "";
      return taxCode ? { name, tax_code: taxCode } : name;
    })
    .filter((item) => typeof item === "string" ? item : item.name);
}
