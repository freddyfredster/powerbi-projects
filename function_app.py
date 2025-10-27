import logging
import os
import json
import time
import requests
import azure.functions as func
 
# ----- Function App -----
app = func.FunctionApp()

 
# If you’ve put them in env vars, use:
TOKEN_URL = os.getenv("TOKEN_URL")
API_URL = os.getenv("API_URL")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN")
API_KEY = os.getenv("API_KEY")
ACCESS_TOKEN_FILE = os.getenv("ACCESS_TOKEN_FILE", "smokeball_access_token.json")
 
# ====== Helpers ======
def get_cached_token():
    if os.path.exists(ACCESS_TOKEN_FILE):
        with open(ACCESS_TOKEN_FILE, "r") as f:
            token_data = json.load(f)
            if token_data.get("expires_at", 0) > time.time():
                logging.info("Using cached token.")
                return token_data["access_token"]
    return None
 
def refresh_access_token():
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    resp = requests.post(TOKEN_URL, data=payload, headers=headers, timeout=30)
 
    if resp.status_code != 200:
        raise Exception(f"Failed to refresh token: {resp.status_code} - {resp.text}")
 
    token_data = resp.json()
    access_token = token_data["access_token"]
    expires_in = token_data.get("expires_in", 3600)
    token_data["expires_at"] = time.time() + expires_in - 60
 
    with open(ACCESS_TOKEN_FILE, "w") as f:
        json.dump(token_data, f)
 
    logging.info("Access token refreshed successfully.")
    return access_token
 
def get_valid_access_token():
    token = get_cached_token()
    if token:
        return token
    logging.info("Refreshing token…")
    return refresh_access_token()
 
def fetch_all_smokeball_contacts(max_per_request=500):
 
    token = get_valid_access_token()
    headers = {
        "x-api-key": API_KEY,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    all_contacts = []
    offset = 0

    while True:
        params = {"limit": max_per_request, "offset": offset}
        resp = requests.get(API_URL, headers=headers, params=params, timeout=30)
        logging.info(f"Fetching contacts: offset={offset}, status={resp.status_code}")

        if resp.status_code != 200:
            raise Exception(f"Upstream error {resp.status_code}: {resp.text}")

        data = resp.json()
        contacts = data.get("value", [])
        all_contacts.extend(contacts)

        # Stop when fewer than max_per_request are returned (last page)
        if len(contacts) < max_per_request:
            break

        offset += max_per_request

    return {"contacts": all_contacts}

 
# ====== HTTP Route ======
@app.route(route="APICallingSmokeball", methods=["GET", "POST"], auth_level=func.AuthLevel.ANONYMOUS)
def APICallingSmokeball(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Python HTTP trigger function processed a request.")
    try:
        data = fetch_all_smokeball_contacts(max_per_request=500)
        return func.HttpResponse(
            json.dumps(data),
            mimetype="application/json",
            status_code=200
        )
    except Exception as e:
        logging.exception("APICallingSmokeball failed")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500
        )