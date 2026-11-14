# Logger

Streamlit app for Biashara Masters Sawmill production and paper glue recipe logging.

## Authentication and ranks

No working usernames or passwords are committed to this repository. Configure real accounts in Streamlit Community Cloud's **App settings → Secrets** (then save/restart the app), or locally in `.streamlit/secrets.toml`. Do not commit credentials. Usernames are case-insensitive; passwords are case-sensitive.

```toml
[users.admin]
password = "choose-a-real-strong-password"
rank = "Admin"

[users.supervisor]
password = "choose-a-different-password"
rank = "Supervisor"

[users.operator]
password = "choose-a-different-password"
rank = "Operator"

[users.glue_chef]
password = "choose-a-different-password"
rank = "Glue Chef"
```

Permissions:

- **Admin:** all pages, including roll editing and deletion.
- **Supervisor:** dashboard, production stations, and shift reports.
- **Operator:** Paper ID, Resin Content, and Ovens & Line.
- **Glue Chef:** paper glue recipe library.

Authorization is checked inside each page as well as in navigation. The previous single `admin_password` secret remains supported as an Admin account with username `admin` if no `[users.admin]` account is configured. If sign-in fails, verify credentials in the deployed app's Secrets and that the app restarted after secrets were saved. Login inputs clear after each attempt. Never put production passwords in source control.

## Production attribution, recipes, and audit files

New roll creation records the signed-in user as `logged_by`. Each station update appends an attributed activity entry with shift date/name; Admins and Supervisors can review it in Shift Reports. Admins can edit or delete rolls, and those actions are also retained in the activity history. Existing rows are preserved during SQLite schema migration; historical authors cannot be inferred.

The **Glue Recipes** page lets Admins and Glue Chefs maintain multiple uniquely named recipes, with ingredients/proportions, mixing instructions, and creator/update attribution.

Successful sign-ins are appended to a separate `login_activity.csv` file with username, rank, and East Africa Time timestamp (never passwords). Admins can download the CSV from Shift Reports. On Streamlit Cloud this file is stored on the app's local filesystem and may not survive a rebuild/restart; use durable external storage if long-term retention is required.

The page footer displays **Biashara Masters Sawmill · v1.0.0 · a product of kutswaInc**.

Run locally with `streamlit run app.py` after installing `requirements.txt` and configuring `.streamlit/secrets.toml`.
