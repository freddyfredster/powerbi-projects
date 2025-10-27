import logging, os, json, time, requests, azure.functions as func
from azure.storage.blob import BlobClient

app = func.FunctionApp()

# ----- Config from env -----
TOKEN_URL     = os.getenv("TOKEN_URL")
API_URL       = os.getenv("API_URL")
CLIENT_ID     = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
API_KEY       = os.getenv("API_KEY")

# Storage for token state + lock
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
STATE_CONTAINER = os.getenv("STATE_CONTAINER", "tokens")
STATE_BLOB_NAME = os.getenv("STATE_BLOB_NAME", "smokeball-token-state.json")
LOCK_CONTAINER  = os.getenv("LOCK_CONTAINER",  "locks")
LOCK_BLOB_NAME  = os.getenv("LOCK_BLOB_NAME",  "smokeball-token.lock")

state_blob = BlobClient.from_connection_string(
    AZURE_STORAGE_CONNECTION_STRING, STATE_CONTAINER, STATE_BLOB_NAME
)
lock_blob = BlobClient.from_connection_string(
    AZURE_STORAGE_CONNECTION_STRING, LOCK_CONTAINER, LOCK_BLOB_NAME
)

# ----- Helpers -----
def _load_state():
    try:
        data = state_blob.download_blob().readall()
        return json.loads(data)
    except Exception:
        return {}  # first run

def _save_state(state: dict):
    state_blob.upload_blob(json.dumps(state), overwrite=True)

def _acquire_lock(timeout_seconds=15):
    try:
        return lock_blob.acquire_lease(timeout=timeout_seconds)
    except Exception:
        return None

def _release_lock(lease):
    if lease:
        try:
            lease.release()
        except Exception:
            pass

def _now(): return time.time()

def _exchange_refresh_for_access(refresh_token: str):
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    resp = requests.post(TOKEN_URL, data=payload, headers=headers, timeout=60)
    if resp.status_code >= 400:
        logging.error(f"Failed to refresh token: {resp.status_code} - {resp.text}")
        resp.raise_for_status()
    js = resp.json()
    return js["access_token"], js.get("refresh_token"), js.get("expires_in", 3600)

def _get_valid_access_token():
    st = _load_state()
    access = st.get("access_token")
    exp    = st.get("expires_at", 0)
    if access and exp > _now():
        logging.info("Using cached access token from blob.")
        return access

    lease = _acquire_lock()
    try:
        st = _load_state()
        access = st.get("access_token")
        exp    = st.get("expires_at", 0)
        if access and exp > _now():
            logging.info("Another instance refreshed; using cached token.")
            return access

        refresh = st.get("refresh_token") or os.getenv("REFRESH_TOKEN")
        if not refresh:
            raise Exception("No refresh token found (state or env).")

        access, new_refresh, expires_in = _exchange_refresh_for_access(refresh)
        st["access_token"]  = access
        st["expires_at"]    = _now() + int(expires_in) - 60
        if new_refresh:
            st["refresh_token"] = new_refresh
        _save_state(st)
        logging.info("Access token refreshed and persisted.")
        return access
    finally:
        _release_lock(lease)

def _call_smokeball(access_token: str, limit=500):
    headers = {
        "x-api-key": API_KEY,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    all_contacts = []
    offset = 0
    while True:
        params = {"limit": limit, "offset": offset}
        resp = requests.get(API_URL, headers=headers, params=params, timeout=240)
        if resp.status_code == 401:
            raise PermissionError("ACCESS_EXPIRED")
        if resp.status_code >= 400:
            logging.error(f"Upstream error {resp.status_code}: {resp.text}")
            resp.raise_for_status()

        data = resp.json()
        contacts = data.get("value", [])
        all_contacts.extend(contacts)
        if len(contacts) < limit:
            break
        offset += limit

    return {"contacts": all_contacts}

 
# ====== HTTP Route ======
@app.route(route="APICallingSmokeball", methods=["GET", "POST"], auth_level=func.AuthLevel.ANONYMOUS)
def APICallingSmokeball(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("APICallingSmokeball invoked.")
    try:
        access = _get_valid_access_token()
        try:
            data = _call_smokeball(access, limit=500)
        except PermissionError:
            access = _get_valid_access_token()
            data = _call_smokeball(access, limit=500)

        return func.HttpResponse(json.dumps(data), mimetype="application/json", status_code=200)
    except Exception as e:
        logging.exception("APICallingSmokeball failed")
        return func.HttpResponse(json.dumps({"error": str(e)}), mimetype="application/json", status_code=502)
