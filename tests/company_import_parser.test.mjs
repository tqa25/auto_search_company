import assert from "node:assert/strict";
import { parseCompanyImportText } from "../dashboard/frontend/assets/companyImportParser.js";

const fullName = "CÔNG TY TNHH THIẾT BỊ DẠY HỌC, DẠY NGHỀ LB";

assert.deepEqual(
  parseCompanyImportText(`${fullName}\n`, "company_list_20260610-idp-list.txt"),
  [fullName],
);

assert.deepEqual(
  parseCompanyImportText(`"Tên công ty"\n"${fullName}"\n`, "companies.csv"),
  [fullName],
);

assert.deepEqual(
  parseCompanyImportText(`company name\nABC COMPANY\n`, "companies.txt"),
  ["ABC COMPANY"],
);

console.log("company import parser tests passed");
