# TD Rahona — Ask Genie

A small TD-branded chat web app that lets you ask questions to a Databricks Genie Space from a clean browser URL.

- **Framework:** Streamlit
- **Branding:** TD green (`#2FBF00`), TD shield logo
- **Deployment:** Local (default) → Azure → Databricks Apps (optional)

---

## 1. What this is

Open a URL → ask questions in plain English → Genie returns text answers and, when relevant, a SQL result table.

The app reads a single config value (`GENIE_SPACE_ID`) and authenticates to Databricks via the SDK. Anywhere `WorkspaceClient()` can find credentials — env vars, `~/.databrickscfg`, or platform-injected — the app will run.

## 2. Prerequisites

**Shared (any deployment target):**
- A Databricks workspace.
- A Genie Space, plus the ID of that Space (see section 3).
- The identity that the app runs as must have `CAN VIEW` on the Genie Space, plus the relevant Unity Catalog grants on the underlying tables.

**Local only:** Python 3.11+, a terminal, and a personal access token (PAT) on the workspace.

**Azure only:** Azure CLI (`az login`), an Azure subscription + resource group, and a Databricks **service principal** with an OAuth secret. See section 5 for how to create one.

**Databricks Apps only:** the Databricks CLI (see section 6).

> **Auth note:** outside Databricks Apps there is no on-behalf-of (OBO). Local and Azure deployments query Genie under a single shared identity (your PAT, or the Azure-side service principal) — not under each end-user. Make sure that identity has the grants it needs.

## 3. Get your Genie Space ID

1. In your Databricks workspace, open the Genie Space you want to expose.
2. Copy the ID from the URL:
   ```
   https://<workspace>/genie/rooms/01f0abcd1234ef567890abcdef123456
                                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                   this is the Space ID
   ```

You'll use this ID in every deployment path below.

---

## 4. Run locally (default)

The fastest way to try the app.

```bash
cp .env.example .env
# edit .env: set DATABRICKS_HOST, DATABRICKS_TOKEN (your PAT), GENIE_SPACE_ID

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Opens at `http://localhost:8501`. All Genie queries run as the PAT's owner.

---

## 5. Deploy to Azure

Two paths. Start with **5a (App Service)** for a POC — no Dockerfile needed. Use **5b (Container Apps)** if you prefer containers, scale-to-zero, or already have a container pipeline.

### One-time: create a Databricks service principal

Both Azure paths authenticate to Databricks with M2M OAuth (not a PAT — PATs are bound to a human user and shouldn't live in cloud config).

1. In the Databricks **Account Console** → **Service Principals**, create one named e.g. `td-rahona-genie-azure`. Save its **Application ID** (this is `DATABRICKS_CLIENT_ID`).
2. Generate an **OAuth secret** for the SP. Save it (this is `DATABRICKS_CLIENT_SECRET`).
3. Add the SP to your workspace.
4. In the Genie Space → **Share** → add the SP with `CAN VIEW`.
5. Grant the SP the necessary Unity Catalog access on tables Genie reads.

Docs: <https://docs.databricks.com/aws/en/dev-tools/auth/oauth-m2m>.

### 5a. Azure App Service (Python runtime) — primary

```bash
RG=<your-resource-group>
APP=td-rahona-genie-chat

# Create the web app from this folder.
az webapp up \
  --name "$APP" \
  --resource-group "$RG" \
  --runtime "PYTHON:3.11" \
  --sku B1

# App Service runs gunicorn by default — override with the Streamlit command.
az webapp config set \
  --name "$APP" --resource-group "$RG" \
  --startup-file "streamlit run app.py --server.port 8000 --server.address 0.0.0.0"

# Inject config + auth.
az webapp config appsettings set \
  --name "$APP" --resource-group "$RG" \
  --settings \
    GENIE_SPACE_ID=<space-id> \
    DATABRICKS_HOST=https://<workspace>.azuredatabricks.net \
    DATABRICKS_CLIENT_ID=<sp-application-id> \
    DATABRICKS_CLIENT_SECRET=<sp-oauth-secret>
```

Browse `https://<APP>.azurewebsites.net`.

**Recommended:** store `DATABRICKS_CLIENT_SECRET` in Azure Key Vault and use a Key Vault reference (`@Microsoft.KeyVault(SecretUri=https://<vault>.vault.azure.net/secrets/<name>/)`) instead of putting the raw secret in app settings.

To redeploy after editing code:
```bash
az webapp up --name "$APP" --resource-group "$RG"
```

### 5b. Azure Container Apps (Docker) — alternative

A `Dockerfile` is included at the repo root.

```bash
RG=<your-resource-group>
ACR=<your-acr-name>
CAE=<your-container-apps-environment>
APP=td-rahona-genie-chat

# Build the image in ACR (no local Docker required).
az acr build --registry "$ACR" --image "$APP:latest" .

# Create the Container App with the same four env vars as 5a.
az containerapp create \
  --name "$APP" \
  --resource-group "$RG" \
  --environment "$CAE" \
  --image "$ACR.azurecr.io/$APP:latest" \
  --target-port 8000 \
  --ingress external \
  --secrets databricks-client-secret=<sp-oauth-secret> \
  --env-vars \
    GENIE_SPACE_ID=<space-id> \
    DATABRICKS_HOST=https://<workspace>.azuredatabricks.net \
    DATABRICKS_CLIENT_ID=<sp-application-id> \
    DATABRICKS_CLIENT_SECRET=secretref:databricks-client-secret
```

The CLI prints the public FQDN.

To redeploy after editing code:
```bash
az acr build --registry "$ACR" --image "$APP:latest" .
az containerapp update --name "$APP" --resource-group "$RG" --image "$ACR.azurecr.io/$APP:latest"
```

---

## 6. (Optional) Deploy as a Databricks App

If you already operate inside Databricks, this is the simplest path — it handles HTTPS, SSO, and OBO automatically (each user queries Genie under their own identity).

```bash
# One-time: install + auth the CLI.
brew install databricks/tap/databricks                                 # macOS
# winget install Databricks.DatabricksCLI                              # Windows
# curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh   # any OS
databricks auth login --host https://<workspace>.cloud.databricks.com
```

Then, edit `app.yaml` and replace `REPLACE_WITH_SPACE_ID` with the Space ID from section 3, and deploy:

```bash
databricks apps create td-rahona-genie-chat
databricks apps deploy td-rahona-genie-chat --source-code-path "$(pwd)"
```

Grant the auto-created service principal `td-rahona-genie-chat` `CAN VIEW` on the Genie Space (Share → add SP). The CLI prints the HTTPS URL to share.

---

## 7. Auth model summary

| Target | Auth | Required env vars | Identity that hits Genie |
| --- | --- | --- | --- |
| Local | Personal access token | `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `GENIE_SPACE_ID` | The PAT's owner (you) |
| Azure (App Service or Container Apps) | Service principal (M2M OAuth) | `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`, `GENIE_SPACE_ID` | The service principal |
| Databricks Apps | On-behalf-of (handled by platform) | `GENIE_SPACE_ID` (in `app.yaml`) | The signed-in end user |

## 8. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `GENIE_SPACE_ID is not set` banner | Local: edit `.env`. App Service: re-run the `az webapp config appsettings set` command. Container Apps: `az containerapp update --set-env-vars …`. Databricks Apps: edit `app.yaml` and redeploy. |
| `Permission denied` on the Genie Space | The identity from section 7 is missing `CAN VIEW` on the Space and/or UC grants on the underlying tables. |
| Local: `default auth: cannot configure default credentials` | `DATABRICKS_HOST` or `DATABRICKS_TOKEN` is missing/blank in `.env`. |
| Azure App Service serves the default landing page | The startup command wasn't applied — re-run `az webapp config set --startup-file …` and restart the app. |
| Azure Container App returns 502 | The container is binding to a different port. Confirm `--target-port 8000` matches the `Dockerfile` `CMD` port. |
| Rate-limit errors | Genie free tier is 5 queries per minute. Contact Databricks about the Dedicated tier if needed. |
| Logo not rendering | `assets/td-logo.png` must be present in the deploy. App Service / Container Apps include the whole folder; Databricks Apps include everything under the `--source-code-path`. |

## 9. File map

```
.
├── app.py                   # Streamlit chat UI + Genie Conversation API client
├── app.yaml                 # Databricks Apps manifest (used only in section 6)
├── Dockerfile               # Container image (used only in section 5b)
├── requirements.txt         # Python deps
├── .streamlit/config.toml   # TD colour theme
├── assets/td-logo.png       # TD shield
├── .env.example             # template for local dev (and SP vars for Azure)
└── README.md                # this file
```
