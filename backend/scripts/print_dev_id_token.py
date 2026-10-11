"""Sign in to Firebase Auth and print a short-lived development ID token.

This script uses the Firebase Web API key plus an interactively entered
email/password. It never reads, prints, or logs service-account credentials.
"""

from __future__ import annotations

import getpass
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main() -> int:
    api_key = os.environ.get("FIREBASE_WEB_API_KEY", "").strip()
    if not api_key:
        print("Set FIREBASE_WEB_API_KEY to the Firebase project's Web API key.", file=sys.stderr)
        return 2

    email = input("Firebase demo-user email: ").strip()
    password = getpass.getpass("Firebase demo-user password: ")
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
    payload = json.dumps({"email": email, "password": password, "returnSecureToken": True}).encode()
    request = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")

    try:
        with urlopen(request, timeout=20) as response:
            result = json.load(response)
    except (HTTPError, URLError, TimeoutError):
        print("Firebase sign-in failed. Check the API key and demo-user credentials.", file=sys.stderr)
        return 1

    token = result.get("idToken")
    if not token:
        print("Firebase sign-in did not return an ID token.", file=sys.stderr)
        return 1
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())