# Development and Security Rules

1. Keep SQL Server access behind the existing Test/Production PHP CRUD APIs. Do not add direct SQL Server drivers or direct database credentials to this app.
2. Never commit `.env`, API tokens, the shared launch secret, or other private credentials. `.env.example` contains templates only.
3. Production identity must come from a signed One Portal launch ticket and a verified HttpOnly session. Never trust browser-supplied sender email, name, or EmployeeCode.
4. Always resolve launch-ticket EmployeeCode to `VM_EmployeeMaster` and require `Active='Y'`. User tab and @mentions must show active employees only.
5. Sender email is resolved from the verified employee's `OffEmail`; display names are resolved from `EmployeeName` by normalized OffEmail match.
6. Production writes remain disabled unless a deliberate deployment decision enables them. Never use the Production API for development troubleshooting.
7. Validate table names and column identifiers at the API boundary. Use the compact physical schema verified by `sql/001_create_comment_tables.sql`; preserve the SQL API payload contract.
8. The task context key is `TableName + reference value + AppID + StageNo`. Keep the mapping table's `FMSRefId` source column name distinct from the current row value in the URL.
9. Maintain Ask/Reply/Message thread behavior and avoid changing legacy element IDs without updating the corresponding scripts and tests.
10. Do not add the Cases creation form to the UI unless specifically requested; optional backend integration may remain for linked case records.
11. Every bug fix should have a focused regression test. Run `pytest -q` before committing.
12. Use explicit trusted origin allowlists for cross-origin `postMessage`; never use `*` for identity handoff messages.
13. The in-memory replay cache is only for a single-instance deployment. Replace it with shared replay storage before horizontal scaling.
