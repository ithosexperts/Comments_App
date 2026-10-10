# Product Requirements Document — Task Activity Feed

## Overview

A reusable comments/activity application embedded in FMS forms and other One Portal workflows. It replaces the Apps Script execution layer with Python FastAPI while preserving the current comments, Ask/Reply/Message, attachment, @mention and thread behaviors.

## Problem statement

Task conversations are difficult to keep connected to the correct FMS form, reference record, app and stage if each form has separate comment logic or asks users to identify themselves again. Sender names also need to be consistently resolved from the central Employee Master.

## Goals

- Use the authenticated One Portal employee across embedded forms without repeat login.
- Keep every comment scoped to the correct physical table, reference-column value, App ID and Stage No.
- Load active user display names and recipient emails from `VM_EmployeeMaster`.
- Preserve Message, Ask, Reply, attachments, read-status behavior and stable thread IDs.
- Keep the two existing SQL API environments separate and block Production writes by default.
- Provide an accessible vertical UI: task context first, then conversation history.

## Target users

Employees, doers, process owners, managers and authorized portal administrators working in FMS forms and other One Portal workflows.

## Core features

- Signed One Portal identity handoff using EmployeeCode.
- Server-side resolution of `EmployeeName`, `OffEmail`, `RoleID`, and `Department` with `Active='Y'` required.
- FMS/App/Stage mapping table with `TableName`, `FMSRefId`, `AppID`, and `StageNo`.
- Stable internally generated CommentID derived from the task context.
- Message, Ask, Reply, @mentions, attachments and read statuses.
- User tab and active-only employee search.
- Optional Cases API endpoints remain backend integrations; the Cases creation input form is not displayed.
- Local mock mode and API-backed Test/Production modes.

## Acceptance criteria

- Direct request parameters cannot impersonate another sender.
- An Active='N' employee cannot be selected for @mentions or launch Comments through One Portal.
- Comment log and map payloads use the actual compact SQL column names.
- The form URL does not require a CommentID parameter.
- Automated tests run without touching live SQL APIs.
