# Embed the Task Comments launcher in an FMS form

The launcher displays a floating comments icon. Clicking it requests a signed task launch ticket from the logged-in One Portal session, opens Comments in a modal, and offers an **Open in new tab** action.

## Static context example

```html
<script defer src="https://YOUR-COMMENTS-HOST/embed.js?tableName=Z_SalesOrder&fmsRefId=8&appId=APP000001&stageNo=1"></script>
```

`fmsRefId=8` is the current row value, not the source column name. The mapping table's `FMSRefId` value should contain the column name, e.g. `Pick ID`.

## Read values dynamically from the form

Use selectors matching the actual form's input IDs/names. The selected element's `.value`, text, or `data-value` is read at click time:

```html
<script defer src="https://YOUR-COMMENTS-HOST/embed.js?tableSelector=%23table-name&fmsRefSelector=%23pick-id&appSelector=%23app-id&stageSelector=%23stage-no&portalOrigin=https%3A%2F%2Fportal.example.com"></script>
```

Replace all sample hosts/selectors with real values. For a cross-origin iframe, include the trusted One Portal origin and install the bridge as documented in `portal-identity-handoff.md`.

The comments app receives `TableName`, reference value, `AppID`, and `StageNo` from the signed task context. It generates its stable internal `CTX-...` CommentID. Do not pass an email or CommentID as a security credential.
