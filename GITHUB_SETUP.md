# Put this repository on GitHub

## Option A — upload through the GitHub website

1. Create a new empty GitHub repository (do not add a README/license because this ZIP already contains them).
2. Extract this ZIP on your computer.
3. Upload the extracted files/folders from the repository root into the GitHub repository. Preserve all relative paths, including `.github/` and `.env.example`.
4. Do **not** upload `.env`, `.venv/`, uploads, passwords, API tokens, or `COMMENTS_LAUNCH_SECRET`.
5. Wait for the **tests** GitHub Actions workflow to finish. Fix any failing tests before deployment.

## Option B — Git commands from the extracted project folder

```powershell
git init
git add .
git status
git commit -m "Initial Task Activity Feed FastAPI app"
git branch -M main
git remote add origin https://github.com/YOUR-ACCOUNT/YOUR-REPOSITORY.git
git push -u origin main
```

Replace the example repository URL with your own. Before `git add`, check `git status` and confirm that `.env` is not listed. The `.gitignore` excludes it, but inspect the status rather than committing a secret accidentally.

## Important separation

This repository contains the Comments backend plus the files needed to integrate identity handoff. It cannot automatically edit your already-existing One Portal backend just by being pushed to GitHub. Follow `one_portal_integration/README.md` to copy the new router into that project and include it in the existing FastAPI app.
