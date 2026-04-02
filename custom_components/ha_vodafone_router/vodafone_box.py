import random
import json
import requests
import re
import logging
import time

from .sjcl import SJCL

_LOGGER = logging.getLogger(__name__)


class VodafoneBox:
    def __init__(self, host: str):
        _LOGGER.debug("Initializing VodafoneBox for host: %s", host)
        self.host = host
        self.base_url = f"http://{host}"
        _LOGGER.debug("Base URL set to: %s", self.base_url)

        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{self.base_url}/?overview",
                "Origin": self.base_url,
                "User-Agent": "Mozilla/5.0",
            }
        )

        self.session_id = None
        self.nonce = None
        self.csrf_nonce = ""
        self.iv = None
        self.salt = None
        self.key = None

    def _headers(self):
        return {
            "Cookie": f"PHPSESSID={self.session_id}",
            "csrfNonce": self.csrf_nonce,
        }

    def _get(self, endpoint: str, params: str | None = None):
        url = f"{self.base_url}/php/{endpoint}?_n={self.nonce}"
        if params:
            url += f"&{params}"

        _LOGGER.debug(
            "Making GET request to: %s with headers: %s", url, self._headers()
        )
        response = self.session.get(url, headers=self._headers(), timeout=10)
        _LOGGER.debug(
            "GET response status: %s, content length: %s",
            response.status_code,
            len(response.content),
        )
        return response

    def _post(self, endpoint: str, data=None):
        url = f"{self.base_url}/php/{endpoint}?_n={self.nonce}"
        _LOGGER.debug(
            "Making POST request to: %s with data: %s and headers: %s",
            url,
            data,
            self._headers(),
        )
        response = self.session.post(
            url, json=data, headers=self._headers(), timeout=10
        )
        _LOGGER.debug(
            "POST response status: %s, content length: %s",
            response.status_code,
            len(response.content),
        )
        return response

    def _init_crypto_values(self):
        # First, make an initial request to establish session properly
        initial_resp = self.session.get(self.base_url, timeout=10)

        # Get session ID from the initial response
        if initial_resp.cookies.get("PHPSESSID"):
            self.session_id = initial_resp.cookies.get("PHPSESSID")

        # Now make a second request with the session established
        resp = self.session.get(self.base_url, timeout=10)

        # Update session ID if it changed
        if resp.cookies.get("PHPSESSID"):
            self.session_id = resp.cookies.get("PHPSESSID")

        print(f"Response text preview: {resp.text[:500]}...")

        # Extract crypto values with error checking
        iv_match = re.search(r"var myIv = '(.+?)';", resp.text)
        salt_match = re.search(r"var mySalt = '(.+?)';", resp.text)

        if not iv_match or not iv_match.group(1):
            raise ValueError(
                f"Could not extract IV value. Found match: {iv_match.group(0) if iv_match else 'None'}"
            )

        if not salt_match or not salt_match.group(1):
            raise ValueError(
                f"Could not extract salt value. Found match: {salt_match.group(0) if salt_match else 'None'}"
            )

        self.iv = iv_match.group(1)
        self.salt = salt_match.group(1)
        self.nonce = str(random.random())[2:7]

        print(f"Extracted IV: '{self.iv}', Salt: '{self.salt}'")

    def login(self, username: str, password: str):
        _LOGGER.info("Starting login process for user: %s", username)
        _LOGGER.debug("Initializing crypto values")
        self._init_crypto_values()

        js_data = json.dumps(
            {
                "Password": password,
                "Nonce": self.session_id,
            }
        )
        _LOGGER.debug("Prepared login data with session_id: %s", self.session_id)

        _LOGGER.debug(
            "Generating encryption key using PBKDF2 with salt: %s",
            self.salt[:10] + "...",
        )
        self.key = SJCL.pbkdf2(
            password,
            self.salt,
            SJCL.DEFAULT_SJCL_ITERATIONS,
            SJCL.DEFAULT_SJCL_KEYSIZEBITS,
        )
        _LOGGER.debug("Key generated successfully")

        auth_data = "loginPassword"
        _LOGGER.debug("Encrypting login data using IV: %s", self.iv[:10] + "...")
        encrypt_data = SJCL.ccm_encrypt(
            self.key,
            js_data,
            self.iv,
            auth_data,
            SJCL.DEFAULT_SJCL_TAGLENGTH,
        )
        _LOGGER.debug("Data encrypted successfully, length: %s", len(encrypt_data))

        payload = {
            "EncryptData": encrypt_data,
            "Name": username,
            "AuthData": auth_data,
        }
        _LOGGER.debug("Sending login request with payload for user: %s", username)

        resp = self._post("ajaxSet_Password.php", payload)
        _LOGGER.debug(
            "Login response status: %s, content: %s", resp.status_code, resp.text[:200]
        )

        if resp.status_code == 200:
            _LOGGER.info("Login successful for user: %s", username)
        else:
            _LOGGER.error(
                "Login failed for user: %s with status: %s", username, resp.status_code
            )
            raise Exception(f"Login failed with status {resp.status_code}: {resp.text}")

        _LOGGER.debug("Parsing login response JSON")
        data = resp.json()
        _LOGGER.debug("Login response data: %s", data)

        status = data.get("p_status", "")
        _LOGGER.debug("Login status: %s", status)

        if "Fail" in status:
            _LOGGER.error("Login failed: wrong password for user: %s", username)
            raise RuntimeError("Login failed: wrong password")

        if "Lockout" in status:
            wait_time = data.get("p_waitTime")
            _LOGGER.error(
                "Login locked for user: %s, wait time: %s", username, wait_time
            )
            raise RuntimeError(f"Login locked: {wait_time}")

        if "Match" in status:
            _LOGGER.info("Login credentials matched for user: %s", username)
            self.session_id = resp.cookies.get("PHPSESSID")
            _LOGGER.debug("Updated session ID: %s", self.session_id)

            _LOGGER.debug("Decrypting CSRF nonce")
            self.csrf_nonce = SJCL.ccm_decrypt(
                self.key,
                data["encryptData"],
                self.iv,
                "nonce",
                SJCL.DEFAULT_SJCL_TAGLENGTH,
            )
            _LOGGER.debug("CSRF nonce decrypted: %s", self.csrf_nonce[:10] + "...")

            _LOGGER.debug("Setting session")
            self._set_session()

    def _set_session(self):
        _LOGGER.debug("Setting session with CSRF nonce")
        resp = self._post("ajaxSet_Session.php")
        login_status = resp.json().get("LoginStatus", "")
        _LOGGER.debug("Session response: %s", resp.json())

        if "yes" not in login_status:
            _LOGGER.warning(
                "Session not fully established. Login status: %s", login_status
            )
        else:
            _LOGGER.info("Session successfully established")

    def logout(self):
        _LOGGER.info("Starting logout process")
        resp = self._post("logout.php")
        _LOGGER.debug("Logout response status: %s", resp.status_code)

        if resp.status_code == 200:
            _LOGGER.info("Logout successful")
        else:
            _LOGGER.warning("Logout may have failed with status: %s", resp.status_code)

    def get_connected_devices(self):
        max_retries = 3
        retry_delay_in_seconds = 2

        for attempt in range(max_retries):
            _LOGGER.debug("Fetching connected devices (Attempt %s/%s)", attempt + 1, max_retries)
            resp = self._get("overview_data.php")
            text = resp.text

            _LOGGER.debug("Overview data received: %s", text)
            
            if "PAGE_OVERVIEW_SESSION_LOST_POPUP_TEXT" in text or resp.status_code == 400:
                _LOGGER.warning("Vodafone Station session expired. Re-authentication required.")
                raise Exception("Session lost")

            lan_devices = self._safe_extract(text, "json_lanAttachedDevice")
            wireless_devices = self._safe_extract(text, "json_primaryWlanAttachedDevice")

            if lan_devices is not None and wireless_devices is not None:
                total_found = len(lan_devices) + len(wireless_devices)
                
                if total_found > 0:
                    _LOGGER.info("Found %s LAN and %s WLAN devices", len(lan_devices), len(wireless_devices))
                    return {
                        "lanDevices": lan_devices,
                        "wlanDevices": wireless_devices,
                    }
                
                if attempt < max_retries - 1:
                    _LOGGER.debug(
                        "Router reported 0 devices (stale data). Retrying in %ss...", 
                        retry_delay_in_seconds
                    )
                    time.sleep(retry_delay_in_seconds)
                    continue
                else:
                    _LOGGER.warning("Confirmed 0 devices after %s attempts.", max_retries)
                    return {
                        "lanDevices": [],
                        "wlanDevices": [],
                    }
            
            raise ValueError("Parsing failed: Response format has changed or is corrupted.")

    def _safe_extract(self, data, var_name):
        """Extracts property from response safely"""
        try:
            parts = data.split(f"{var_name} = ")
            if len(parts) < 2:
                _LOGGER.error("Variable '%s' not found in response", var_name)
                return None
            
            json_str = parts[1].split(";")[0]
            return json.loads(json_str)
        except (json.JSONDecodeError, IndexError) as e:
            _LOGGER.error("Failed to parse %s: %s", var_name, e)
            return None