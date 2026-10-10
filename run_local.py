"""Run the app locally, honoring the selected mode from the project's .env file.

Without a .env file the launcher stays in safe mock mode. To load actual employees
from VM_EmployeeMaster, copy .env.example to .env and set SQL_API_MODE=test.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent

def main() -> None:
    # Load user configuration BEFORE setting defaults. Previously SQL_API_MODE=mock
    # was set first, overriding the Test API mode declared in .env.
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    os.environ.setdefault("APP_ENV", "local")
    os.environ.setdefault("SQL_API_MODE", "mock")
    mode = os.getenv("SQL_API_MODE", "mock").strip().lower()
    print(f"Task Activity Feed starting with SQL_API_MODE={mode!r}.")
    if mode == "mock":
        print("Mock mode is enabled: real VM_EmployeeMaster users will not load. Copy .env.example to .env and set SQL_API_MODE=test to use apiv2.php.")
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.getenv("PORT", "8000")), reload=True)

if __name__ == "__main__":
    main()
