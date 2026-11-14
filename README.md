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

Authorization is checked inside each page as well as in navigation. The previous single `admin_password` secret remains supported as an Admin account with username `admin` if no `[users.admin]` account is configured. If sign-in fails, verify credentials in the deployed app's Secrets (not repository files), exact password capitalization, and that the app restarted after the secrets were saved. Never put production passwords in source control.

## Production attribution and recipes

New roll creation records the signed-in user as `logged_by`. Each station update records the latest editor and appends an attributed activity entry; Admins and Supervisors can review it in Shift Reports. Admins can edit or delete rolls from the **Edit or delete roll information** section. Deletions are also retained in the activity history. Existing rows are preserved during SQLite schema migration; historical authors cannot be inferred.

The **Glue Recipes** page lets Admins and Glue Chefs maintain multiple uniquely named recipes, with ingredients/proportions, mixing instructions, and creator/update attribution.

The page footer displays **Biashara Masters Sawmill · v1.0.0 · a product of kutswaInc**.

Run locally with `streamlit run app.py` after installing `requirements.txt` and configuring `.streamlit/secrets.toml`.
