# Project Memory

## Current purpose
Python/FastAPI port of the Apps Script comment/activity feed to embed in FMS/One Portal forms. The physical application table is identified dynamically by the form context.

## Current architecture
- FastAPI + Jinja2/vanilla JavaScript.
- Existing PHP CRUD APIs only: `https://api.hosexperts.com:85/apiv2.php` for Test and `https://api.hosexperts.com:85/apiv3.php` for Production.
- `SQL_API_MODE=mock|test|production`; Production writes blocked unless deliberately enabled.
- Identity from One Portal signed launch ticket; EmployeeCode is authoritative; Comments backend resolves name/email through `VM_EmployeeMaster` and requires `Active='Y'`.

## SQL schema confirmed in SSMS
`dbo.FMS_Comment_Log` columns: `RecordID`, `CommentID`, `FMSRefId`, `TaskID`, `StageName`, `AppID`, `AppName`, `Text`, `AttachmentURL`, `Timestamp`, `Sender`, `Receiver`, `AttachmentFilename`, `Type`, `AskID`, `Status`, `NotificationMessage`, `OpenThread`, `CompleteStatus`, `UniqueID`, `ThreadID`, `ThreadColor`, `Unique`, `ExtractedText`, `TimestampInText`.

`dbo.FMS_Comment_FMS_Stage_Map` columns: `FMSRefId`, `AppID`, `StageNo`, `TableName`. In this table `FMSRefId` stores the reference column name such as `Pick ID`; URL `fmsRefId=8` stores the live record value.

## Identity details
- One Portal login uses EmployeeCode + existing One Portal password check.
- One Portal's validated middleware sets `request.state.user`; the added route signs a short-lived launch ticket using EmployeeCode from this trusted context.
- Comments `/auth/launch` consumes a single-use ticket and issues an HttpOnly cookie.
- `Sender` must never come from browser request values; backend uses authenticated `OffEmail`.
- Local `DEV_USER_EMAIL` is only a local preview fallback. Set it to an Active='Y' email for testing locally; disable fallback in production.

## Employee rules
- Name: `VM_EmployeeMaster.EmployeeName`.
- Email: `VM_EmployeeMaster.OffEmail`.
- Only `Active='Y'` employees appear in the User tab and @mentions.
- Admin rule: RoleID 1, 2 or 3 OR Department token Management/MDO.

## UI decisions
- Vertical layout: application/task information at top; activity and comment threads below full width.
- Application name is shown when present; do not display physical table name as application title unless no display name exists.
- No visible internal CommentID key and no requirement to put CommentID in URL.
- Cases creation input form is removed from the UI; optional backend linked-case support may remain.

## Do not forget
- Keep `.env` out of GitHub; only commit `.env.example`.
- Keep `COMMENTS_LAUNCH_SECRET` in secret storage and use the same value on both servers.
- Add One Portal router integration separately; deploying this repo alone is not enough for true portal SSO.
- The `jti` replay cache is in memory; use shared storage before horizontal scaling.
