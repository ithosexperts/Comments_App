# Architecture

## Runtime flow

1. One Portal's login flow validates EmployeeCode + One Portal password using `VM_EmployeeMaster` and establishes its JWT/session.
2. A form loads `/embed.js` with task context. The launcher requests a signed short-lived ticket from the authenticated One Portal backend.
3. One Portal's `comments_launch` router takes EmployeeCode from its verified `request.state.user` and signs a one-use ticket; browser-supplied email/name are ignored.
4. Comments `/auth/launch` validates the ticket and resolves EmployeeCode against `VM_EmployeeMaster`, requiring `Active='Y'`. The resolved `EmployeeName`, `OffEmail`, RoleID, and Department are stored in a signed HttpOnly Comments session cookie.
5. FastAPI serves the vertical page: task/form details at the top, Activity & Comments/User tabs beneath, threads above the composer.
6. The legacy `google.script.run` callback calls are bridged to `/api/rpc/{method}`. Business logic is in `ActivityService`/`CaseService` and data access is behind `HttpSqlGateway`.
7. SQL Server access goes only through the existing CRUD PHP API: Test `apiv2.php`, Production `apiv3.php`. There is no direct pyodbc connection.

## Code layout

- `app/main.py`: FastAPI routes, template rendering, signed launch exchange, RPC bridge, uploads, stage map.
- `app/identity.py`: JWT helpers for Portal launch tickets and Comments session cookies.
- `app/config.py`: environment and table names; `.env` is loaded locally.
- `app/services.py`: comment/thread/task/employee/name mapping logic.
- `app/sql_api.py`: SQL API HTTP adapter and in-memory test gateway; maps legacy spaced keys to verified compact comment/mapping fields.
- `app/templates/`: vertical HTML layout and browser behavior for comments, mentions, user list, uploads and UI.
- `tests/`: mock-gateway tests, auth handoff tests and employee-name mapping tests.
- `one_portal_integration/`: router and bridge which must be copied/included in the existing One Portal backend.
- `sql/`: reviewed schema creation and upgrade scripts.

## Current SQL schema

`FMS_Comment_Log` uses compact column names. `TableName` and `StageNo` are not comment-log columns: they live in `FMS_Comment_FMS_Stage_Map`, whose natural key is `TableName + FMSRefId + AppID + StageNo`. For the mapping table, `FMSRefId` contains a *source column name* (e.g. `Pick ID`); the URL's `fmsRefId` carries that row's actual value (e.g. `8`). The UI obtains the application display name from the FMS row or falls back to `TM_Application_Master` by AppID.

## Identity and authorization

- Production identity is exclusively derived from a signed One Portal ticket and an Active `VM_EmployeeMaster` row.
- The current sender's `OffEmail` is imposed server-side when a comment is saved. The browser cannot override it.
- @mentions and User tab are limited to `Active='Y'` employees and use `EmployeeName` + `OffEmail`.
- Admin UI rule: `RoleID` in `{1,2,3}` OR Department token `Management`/`MDO`. Privileged operations must independently enforce authorization server-side.
- Local developer fallback is available only for `APP_ENV=local` and must be disabled in production.

## Deployment constraints

The One Portal and Comments services require the same server-only `COMMENTS_LAUNCH_SECRET`. SameSite=None cookies require HTTPS in production. Multi-instance deployments must replace the in-process one-time-ticket replay cache with shared storage.
