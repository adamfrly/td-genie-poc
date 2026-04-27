# TD Rahona — Ask Genie

A small TD-branded chat web app that lets you ask questions to a Databricks Genie Space from a clean browser URL. Designed for quick sharing with stakeholders who have a Databricks SSO login.

- **Framework:** Streamlit
- **Hosting:** Databricks Apps (one-command deploy, HTTPS + SSO out of the box)
- **Auth:** On-behalf-of — each user queries Genie under their own identity
- **Branding:** TD green (`#2FBF00`), TD shield logo

---

## 1. What this is

Open a URL → sign in with TD SSO → ask questions in plain English → Genie returns text answers and, when relevant, a SQL result table. No Databricks UI, no tokens to manage.

## 2. Prerequisites

Before you deploy:

- A Databricks workspace login (TD SSO).
- Membership in the Genie Space you want to expose (`CAN VIEW` at minimum).
- A macOS / Linux / Windows machine with a terminal.
- Python 3.11+ — **only needed for local testing**, not for deployment.

## 3. Install the Databricks CLI (one time)

**macOS:**
```bash
brew tap databricks/tap
brew install databricks
```

**Windows (winget):**
```powershell
winget install Databricks.DatabricksCLI
```

**Any OS (curl):**
```bash
curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh
```

Verify:
```bash
databricks --version
```

## 4. Authenticate the CLI (one time)

```bash
databricks auth login --host https://<your-workspace>.cloud.databricks.com
```

A browser window opens. Sign in with TD SSO. The CLI stores credentials in `~/.databrickscfg`.

## 5. Configure the Genie Space ID

1. In your Databricks workspace, open the Genie Space you want to expose.
2. Copy the ID from the URL — it looks like this:
   ```
   https://<workspace>/genie/rooms/01f0abcd1234ef567890abcdef123456
                                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                    this is the Space ID
   ```
3. Open `app.yaml` in this folder and replace `REPLACE_WITH_SPACE_ID` with the ID.

## 6. Deploy

From the `td-us-genie-poc/` folder (one level up from this `app/` folder):

```bash
databricks apps create td-rahona-genie-chat
databricks apps deploy td-rahona-genie-chat --source-code-path $(pwd)/app
```

When the deploy finishes, the CLI prints a URL like `https://td-rahona-genie-chat-<id>.cloud.databricks.com/`. That is the URL you share.

To redeploy after editing code:
```bash
databricks apps deploy td-rahona-genie-chat --source-code-path $(pwd)/app
```

## 7. Grant the app access to Genie (one time)

Databricks Apps runs under a dedicated service principal created for this app. It needs `CAN VIEW` on the Genie Space so the app can look up Space metadata. (Actual queries still run as the logged-in user via OBO — their Unity Catalog grants apply.)

1. Open the Genie Space in Databricks.
2. Click **Share**.
3. Add the service principal named `td-rahona-genie-chat` and give it `CAN VIEW`.

## 8. Share with the stakeholder

Send the URL from step 6. They open it in a browser, sign in with TD SSO, and can start chatting. No further setup on their side.

## 9. Local testing (Adam only, optional)

To run the app on your laptop before deploying:

```bash
cd app
cp .env.example .env
# edit .env: set DATABRICKS_HOST, DATABRICKS_TOKEN (personal PAT), GENIE_SPACE_ID

python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Opens at `http://localhost:8501`.

## 10. Troubleshooting

| Symptom | Fix |
| --- | --- |
| App page shows "Permission denied on Genie Space" | Step 7 — share the Space with the app SP, and confirm the signed-in user has `CAN VIEW` too. |
| App URL loads blank or 500s | `databricks apps logs td-rahona-genie-chat` — shows the Streamlit stderr. |
| "GENIE_SPACE_ID is not set" banner | `app.yaml` still has the placeholder. Fix and redeploy (step 6). |
| Rate-limit errors | Genie free tier is 5 queries per minute. If this is too tight, contact Databricks about the Dedicated tier. |
| Logo not rendering | Confirm `assets/td-logo.png` was included in the deploy — it must sit next to `app.py`. |

## File map

```
app/
├── app.py                   # Streamlit chat UI + Genie Conversation API client
├── app.yaml                 # Databricks Apps manifest (entrypoint + GENIE_SPACE_ID)
├── requirements.txt         # Python deps
├── .streamlit/config.toml   # TD colour theme
├── assets/td-logo.png       # TD shield
├── .env.example             # template for local dev
└── README.md                # this file
```
