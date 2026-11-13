# Logger

Streamlit app for wood lamination production and paper glue recipe logging.

## Authentication and ranks

Configure accounts in Streamlit Community Cloud's **App settings → Secrets**, or in a local `.streamlit/secrets.toml` file (do not commit secrets). Each account has a unique username, password, and rank. Supported ranks are `Admin`, `Supervisor`, `Operator`, and `Glue Chef`.

```toml
[users.admin]
password = "replace-with-a-strong-password"
rank = "Admin"

[users.supervisor]
password = "replace-with-a-strong-password"
rank = "Supervisor"

[users.operator]
password = "replace-with-a-strong-password"
rank = "Operator"

[users.glue_chef]
password = "replace-with-a-strong-password"
rank = "Glue Chef"
```

Permissions:

- **Admin:** all pages.
- **Supervisor:** dashboard, production stations, and shift reports.
- **Operator:** Paper ID, Resin Content, and Ovens & Line.
- **Glue Chef:** paper glue recipe library.

Authorization is checked inside each page as well as in the navigation, so hiding a link does not grant or deny access by itself. Configure at least one Admin account before deploying. Passwords must remain in Streamlit secrets, not in source control.

## Production attribution and recipes

New roll creation records the signed-in user as `logged_by`. Each station update records the latest editor and appends an attributed activity entry with the username, rank, station, changed fields, shift, and time; supervisors and admins can review this in **Shift Reports**. Existing database records are retained, but historical authors cannot be inferred and remain blank.

The **Glue Recipes** page lets Admins and Glue Chefs maintain multiple uniquely named recipes, with ingredients/proportions, mixing instructions, and creator/update attribution. The SQLite schema is migrated automatically when the app starts.

Run locally with `streamlit run app.py` after installing `requirements.txt` and configuring `.streamlit/secrets.toml`.
