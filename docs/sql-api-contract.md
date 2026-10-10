# SQL API Contract Checklist

The existing Portal API client and payload model use a CRUD-style JSON contract. The configured endpoints are `https://api.hosexperts.com:85/apiv2.php` for Test and `https://api.hosexperts.com:85/apiv3.php` for Production.

## Request payloads

- SELECT: `{"action":"select","table":"...","filters":{},"fetchAll":true,"orderBy":"..."}`. `columns` is optional.
- INSERT: `{"action":"insert","table":"...","data":{...}}`.
- UPDATE: `{"action":"update","table":"...","data":{...},"where":{...}}`.

## Verify against Test before rollout

- [ ] The Test URL is reachable from the local/deployment environment.
- [ ] Whether an Authorization token/header is required.
- [ ] The API's result envelope and error fields match the adapter.
- [ ] Configured comment, user, pending task, case-map, and label tables/columns exist.
- [ ] The PHP API validates table/column identifiers and parameterizes values server-side.
- [ ] SQL Server datetime fields serialize in a format handled by the app.
- [ ] Update filters are respected by the API and empty `where` values are rejected server-side.

All API-envelope compatibility is centralized in `app/sql_api.py`. The Python application never sends raw SQL to the API.


## Dynamic task identity

Each comment thread is scoped to the exact tuple `TableName`, `[FMS Ref Id]`, `[App ID]`, and `[Stage No]` in `dbo.FMS_Comment_FMS_Stage_Map`. The comment log field remains `[Table Name]`. `Comment ID` is a stable internal key derived from that tuple, while every comment row also stores the four source values for auditing/reporting. The mapping table's composite primary key includes all four fields.

The form table name is dynamically supplied by the launcher URL and sent as the `table` value in a SELECT request. Confirm that the Test SQL API's table allow-list permits the intended FMS tables and that these tables expose `FMS Ref Id`, `App ID`, and `Stage No` (or adjust the field adapter in `ActivityService.get_form_context`).

For an existing mapping table, the DDL upgrades the key by adding `TableName` with an empty value for old rows (renaming the previous `[Table Name]` column if the earlier migration ran). Backfill old mapping rows with the correct table names before expecting them to resolve through the new four-part key. Review this migration on Test first.
