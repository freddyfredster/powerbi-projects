import logging
import os
import json
import time
import requests
import azure.functions as func
 
# ----- Function App -----
app = func.FunctionApp()
 
# Env Vars:
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
 
def fetch_smokeball_contacts(limit=500, offset=0):
    token = get_valid_access_token()
    headers = {
        "x-api-key": API_KEY,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    params = {"limit": limit, "offset": offset}
    resp = requests.get(API_URL, headers=headers, params=params, timeout=30)
    logging.info(f"Upstream status: {resp.status_code}")
 
    if resp.status_code != 200:
        # Bubble up the body to help debugging
        raise Exception(f"Upstream error {resp.status_code}: {resp.text}")
 
    return resp.json()
 
# ====== HTTP Route ======
@app.route(route="testsmokeballfn", methods=["GET", "POST"], auth_level=func.AuthLevel.ANONYMOUS)
def testsmokeballfn(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Python HTTP trigger function processed a request.")
    try:
        # Safely parse request body
        try:
            body = req.get_json()
        except ValueError:
            body = {}

        # Get limit and offset (default limit = 1000)
        limit = int(req.params.get("limit") or body.get("limit") or 500)
        offset = int(req.params.get("offset") or body.get("offset") or 0)

        data = fetch_smokeball_contacts(limit=limit, offset=offset)
        return func.HttpResponse(
            json.dumps(data),
            mimetype="application/json",
            status_code=200
        )
    except Exception as e:
        logging.exception("testsmokeballfn failed")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500
        )