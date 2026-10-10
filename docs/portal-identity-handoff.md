# One Portal identity handoff

The Comments app does not trust `user`, `email`, `EmployeeCode`, or `sender` query/body values to establish identity.

## Flow

1. A user signs in to One Portal with EmployeeCode + the existing One Portal password flow.
2. Existing One Portal JWT/session middleware validates the live session and populates `request.state.user`.
3. The form's Comments launcher sends only form context (`tableName`, `fmsRefId`, `appId`, `stageNo`) to `/api/comments/launch-ticket`.
4. The One Portal route obtains EmployeeCode from `request.state.user`, signs a 45-second ticket with the shared secret, and returns it.
5. The browser POSTs the ticket to Comments `/auth/launch` in a modal iframe or new tab.
6. The Comments app validates signature, audience, issuer, expiry and a one-use `jti`, then resolves EmployeeCode through `VM_EmployeeMaster` and requires `Active='Y'`.
7. The Comments app sets an HttpOnly session cookie; every RPC derives the current sender email from that verified session.

The ticket does not contain email, name, role, or password supplied by the browser. Those fields are resolved by the Comments backend from the employee master after verifying EmployeeCode.

## Required settings on both servers

`COMMENTS_LAUNCH_SECRET` must be the same strong random value (48+ characters) on both backends. Store it only in server-side environment settings. Never commit it, place it in frontend JavaScript, or add it to a URL.

Comments production settings:

- `APP_ENV=production`
- `LOCAL_DEV_IDENTITY_ENABLED=false`
- `COMMENTS_COOKIE_SAMESITE=none` if cross-site iframes are required; HTTPS is mandatory in production.
- Use HTTPS and preferably a same-site host or reverse proxy to avoid third-party-cookie blocking.

## One Portal router

Copy `one_portal_integration/app/routers/comments_launch.py` to the existing One Portal repo and include its router using `one_portal_integration/integration/MAIN_INCLUDE_SNIPPET.txt`. Do not remove the existing JWT/session middleware.

For a form embedded from a different origin, configure `window.ONEPORTAL_COMMENTS_ALLOWED_ORIGINS` to a list of exact origins and add the `comments-launch-bridge.js` script. Never accept messages from wildcard origins.

## Deployment limitation

The single-use ticket `jti` cache is in process memory for local/single-instance use. Multi-instance deployments should use a shared replay store (Redis or SQL) before scaling horizontally.
