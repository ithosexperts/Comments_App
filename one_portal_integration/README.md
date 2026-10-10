# One Portal integration patch

These files are installed into the *existing* One Portal backend; they are not imported by the Comments app.

1. Copy `app/routers/comments_launch.py` to the One Portal project at `app/routers/comments_launch.py`.
2. Apply the import and `app.include_router(comments_launch.router)` lines in `integration/MAIN_INCLUDE_SNIPPET.txt` to the existing One Portal `app/main.py`.
3. Keep the existing JWT/session middleware protecting the endpoint. The route trusts only the middleware-populated `request.state.user`.
4. Set the same `COMMENTS_LAUNCH_SECRET` server-side in One Portal and the Comments app. Never put it in JS or a URL.
5. Copy `app/static/js/comments-launch-bridge.js` into the One Portal static assets and include it only if a cross-origin embedded form needs the bridge. Set exact allowed origins before script load.

Do not replace the One Portal project's current main.py, config, login, or middleware with this patch; only add the router and its include line.
