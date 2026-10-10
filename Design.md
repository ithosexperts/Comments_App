# Design Guide

## Layout

- Vertical full-page layout.
- Task/application summary appears across the top.
- Activity & Comments and User tabs appear below the summary.
- Threads stack vertically across the available width; the composer sits below history.
- Preserve the existing task information and Ask/Reply/Message visual distinctions.
- Keep modal/new-tab launch behavior for embedding in forms.

## Existing visual language

- Light gray workspace background, white content surfaces, subtle borders and shadows.
- Indigo/blue is the primary action and active-tab color.
- Thread background colors are selected from the existing palette in `app/services.py`.
- Keep typography compact, readable, and responsive for desktop/tablet widths.

## Reusable UI areas

- `#task-summary`: full-width task/app details.
- `#conversation-workspace`: Activity/User tabs, message feed and composer.
- `#activity-tab-button`, `#users-tab-button`: tabs.
- `#comments-container`: thread cards.
- User directory uses `EmployeeName`, `OffEmail`, and computed Rights.

## Behavior rules

- Mention options are filtered to `Active='Y'` employees.
- Comment cards resolve sender display name by sender OffEmail; if no active employee matches, show the stored email rather than guessing.
- Keep internal `CTX-...` CommentID out of the visible header.
- Status, Ask, Message, Reply and Thread colors must remain distinguishable without relying on color alone.
