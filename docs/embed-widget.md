# Embed the Task Comments launcher in an FMS form

The launcher adds an inline Comments icon beside an existing Lead Time Extension icon. If that stage has no Lead Time Extension control, it places the Comments icon in the stage heading. Clicking it opens a compact modal showing the conversation and comment/reply controls. The modal provides **Open in new tab**, which opens the same context with the complete task information.

The launcher asks the logged-in One Portal backend for a short-lived signed ticket. It does not accept a sender name, email or role from the URL. The Comments app resolves the employee from the verified ticket and shows the signed-in employee name and Role ID.

## Static context example

```html
<script defer src="https://YOUR-COMMENTS-HOST/embed.js?tableName=Z_SalesOrder&fmsRefId=8&appId=APP000001&stageNo=1"></script>
```

`fmsRefId=8` is the current value of the configured reference column, not its column name. The mapping table's `FMSRefId` value should contain that column name, for example `Pick ID`.

## FMS Portal context

The FMS Portal integration passes `tableName`, `fmsRefId`, `rowId`, `primaryKey`, `taskId`, `appId`, and `stageNo`. If the physical row primary key and mapped reference value are different, Comments first resolves the physical row by `primaryKey` + `rowId`, then uses the mapped `FMSRefId` column value as the canonical conversation key. This ensures separate applications and stages do not share a conversation by accident.

For an iframe opened from One Portal, `portalOrigin` must be set to the exact One Portal origin and the FMS origin must be in `COMMENTS_BRIDGE_ALLOWED_ORIGINS`. Configure the same `COMMENTS_LAUNCH_SECRET` (at least 32 characters) in One Portal and Comments App, and set the Comments app's URL/SSO settings in One Portal's Application Master as described in `docs/portal-identity-handoff.md`.
