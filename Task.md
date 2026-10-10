# Task Tracker

## Established
- [x] FastAPI app with legacy Apps Script callback bridge.
- [x] Test/Production SQL API adapter; no direct SQL Server connection.
- [x] SQL API Test endpoint uses `apiv2.php`; Production uses `apiv3.php`.
- [x] Production writes blocked by default.
- [x] Compact comment-log column adapter matching the verified Test database schema.
- [x] Mapping table context: `TableName`, `FMSRefId`, `AppID`, `StageNo`.
- [x] No caller-provided CommentID required; internal task-scoped ID is derived from URL context.
- [x] Application Name shown in the header instead of physical table name when available.
- [x] User tab lists `EmployeeName`, `OffEmail`, and Rights.
- [x] @mentions and User tab filter to `Active='Y'` users.
- [x] Comment sender is set server-side from verified identity.
- [x] Signed One Portal launch ticket + Comments HttpOnly session handoff.
- [x] Vertical layout: task details above full-width activity and comment composer.
- [x] Remove Cases creation input form from the UI.
- [x] Local mock gateway and automated tests.

## Must complete in the target environment
- [ ] Apply `one_portal_integration/app/routers/comments_launch.py` and include its router in the actual One Portal backend.
- [ ] Configure the same secret on both backend services using private environment settings.
- [ ] Add embed launcher to each real FMS form with correct dynamic selectors/context.
- [ ] Verify active EmployeeCode resolves to `EmployeeName` and `OffEmail` via Test API.
- [ ] Test new Message, Ask, Reply, attachment and read-status behavior against Test_OperationsDB only.
- [ ] Confirm external Case System/upload settings if those backend integrations remain needed.
- [ ] Test iframe cookies and allowed origins in the actual HTTPS domains.
- [ ] Move one-use ticket replay tracking to a shared store before running multiple backend instances.
- [ ] Approve a production rollout after Test DB acceptance.

## Known constraints
- Mock mode is in-memory and does not persist after restarts.
- Test API calls can write to Test_OperationsDB; use test records.
- A GitHub push does not modify the existing One Portal service; that service requires the provided router integration too.
