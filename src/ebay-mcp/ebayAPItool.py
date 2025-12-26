import base64
import json
import logging
import os
from datetime import datetime, timedelta

import requests

logger = logging.getLogger("mcp-ebay-server")

DEFAULT_OAUTH_SCOPE = "https://api.ebay.com/oauth/api_scope"
DEFAULT_TOKEN_FILE = "ebay_token.json"

EBAY_ENVIRONMENTS = {
    "production": {
        "oauth_url": "https://api.ebay.com/identity/v1/oauth2/token",
        "api_base_url": "https://api.ebay.com",
    },
    "sandbox": {
        "oauth_url": "https://api.sandbox.ebay.com/identity/v1/oauth2/token",
        "api_base_url": "https://api.sandbox.ebay.com",
    },
}


def get_ebay_environment():
    env_name = os.getenv("EBAY_ENV", "production").strip().lower()
    if env_name not in EBAY_ENVIRONMENTS:
        raise ValueError(
            f"Unsupported EBAY_ENV '{env_name}'. Valid options: {', '.join(EBAY_ENVIRONMENTS)}"
        )
    return env_name, EBAY_ENVIRONMENTS[env_name]

# Function to generate an OAuth2 access token
def get_access_token(CLIENT_ID, CLIENT_SECRET):
    if not CLIENT_ID or not CLIENT_SECRET:
        raise ValueError("Missing CLIENT_ID or CLIENT_SECRET environment variable")

    TOKEN_FILE = os.getenv("EBAY_TOKEN_FILE", DEFAULT_TOKEN_FILE)
    env_name, env_config = get_ebay_environment()
    oauth_url = env_config["oauth_url"]
    api_scope = os.getenv("EBAY_OAUTH_SCOPE", DEFAULT_OAUTH_SCOPE)

    logger.info(
        "Generating eBay token using env=%s oauth_url=%s client_id_set=%s client_secret_set=%s",
        env_name,
        oauth_url,
        bool(CLIENT_ID),
        bool(CLIENT_SECRET),
    )
    # Check if the token already exists and is valid
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as file:
            token_data = json.load(file)
            expiration_time = datetime.fromisoformat(token_data["expires_at"])
            if expiration_time > datetime.now():
                return token_data["access_token"]

    # If the token is expired or doesn't exist, generate a new one
    auth = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded_auth = base64.b64encode(auth.encode()).decode()

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded_auth}",
    }

    data = {
        "grant_type": "client_credentials",
        "scope": api_scope,
    }

    response = requests.post(oauth_url, headers=headers, data=data, timeout=30)
    if response.status_code == 200:
        token_response = response.json()
        access_token = token_response["access_token"]
        expires_in = token_response["expires_in"]

        # Store the token and expiration time locally
        token_data = {
            "access_token": access_token,
            "expires_at": (datetime.now() + timedelta(seconds=expires_in)).isoformat(),
        }
        with open(TOKEN_FILE, "w") as file:
            json.dump(token_data, file)

        return access_token
    error_detail = response.text
    raise RuntimeError(f"Error generating token: {response.status_code} {error_detail}")

# Function to make an authenticated eBay API request
def make_ebay_api_request(
    access_token,
    query=str,
    ammount=int,
    buying_options=None,
    category_ids=None,
):
    env_name, env_config = get_ebay_environment()
    api_base_url = env_config["api_base_url"]

    # Define the eBay Browse API endpoint
    url = f"{api_base_url}/buy/browse/v1/item_summary/search"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    if not buying_options:
        buying_options = ["AUCTION", "FIXED_PRICE"]
    params = {
        "q": query,
        "filter": f"buyingOptions:{{{'|'.join(buying_options)}}}",
        "limit": ammount,
    }
    if category_ids:
        normalized_categories = "|".join(str(category_id) for category_id in category_ids)
        params["filter"] += f",categoryIds:{{{normalized_categories}}}"

    response = requests.get(url, headers=headers, params=params, timeout=30)
    ebay_search_results = []

    if response.status_code == 200:
        results = response.json().get("itemSummaries", [])
        if not results:
            return "No auctions found"

        # Format and display the results
        for item in results:
            title = item.get("title", "N/A")
            price =  item.get("currentBidPrice", {}).get("value")
            currency = item.get("currentBidPrice", {}).get("currency", "N/A")
            end_date = item.get("itemEndDate", "N/A")
            
            # Parse and format the auction end time
            if end_date != "N/A":
                end_time = datetime.fromisoformat(end_date[:-1]).strftime("%Y-%m-%d %H:%M:%S")
            else:
                end_time = "N/A"

            ebay_search_results.append([title, price, currency, end_date, item.get('itemWebUrl', 'N/A')])

        return ebay_search_results

    error_detail = response.text
    raise RuntimeError(
        f"eBay Browse API error: {response.status_code} {error_detail} (env={env_name})"
    )


def make_ebay_rest_request(
    access_token,
    method,
    path,
    params=None,
    json_body=None,
):
    env_name, env_config = get_ebay_environment()
    api_base_url = env_config["api_base_url"]
    normalized_path = path if path.startswith("/") else f"/{path}"
    url = f"{api_base_url}{normalized_path}"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    response = requests.request(
        method=method.upper(),
        url=url,
        headers=headers,
        params=params,
        json=json_body,
        timeout=30,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"eBay REST API error: {response.status_code} {response.text} (env={env_name})"
        )

    if response.text:
        try:
            return response.json()
        except json.JSONDecodeError:
            return response.text

    return None
