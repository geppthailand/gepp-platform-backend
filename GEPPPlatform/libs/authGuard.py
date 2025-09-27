import base64
import hmac
import hashlib
import json
from datetime import datetime, timedelta, timezone

def base64url_decode(input_str):
    padded = input_str + '=' * (-len(input_str) % 4)
    return base64.urlsafe_b64decode(padded.encode())

def base64url_encode(input_bytes):
    return base64.urlsafe_b64encode(input_bytes).decode().rstrip('=')

def verify_jwt(token, secret_key):
    try:
        token = token.replace("Bearer ", "")
        header_b64, payload_b64, signature_b64 = token.split('.')

        signature_check = hmac.new(
            key=secret_key.encode(),
            msg=f"{header_b64}.{payload_b64}".encode(),
            digestmod=hashlib.sha256
        ).digest()

        signature_check_b64 = base64url_encode(signature_check)

        if signature_check_b64 != signature_b64:
            raise Exception("Invalid signature")

        payload = json.loads(base64url_decode(payload_b64))
        
        if datetime.now(timezone.utc).timestamp() > payload.get("exp", 0):
            raise Exception("Token expired")
        
        return payload

    except Exception as e:
        print("Token verify error:", e)
        return None
