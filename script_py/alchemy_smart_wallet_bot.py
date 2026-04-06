import os
import time
from typing import Any, Dict, List, Optional

import requests
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_abi import encode as abi_encode
from eth_utils import keccak


def build_rpc_url(api_key: str) -> str:
    # Wallet JSON-RPC methods are served on Alchemy API host.
    return f"https://api.g.alchemy.com/v2/{api_key}"


def load_dotenv(dotenv_path: str = ".env") -> None:
    if not os.path.exists(dotenv_path):
        return
    with open(dotenv_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = value


def normalize_account(value: str) -> str:
    # Accept either an address or a private key and always return a checksummed address.
    if not value:
        return value
    candidate = value.strip()
    if candidate.startswith("0x") and len(candidate) == 66:
        return Account.from_key(candidate).address
    return Account.from_key(candidate).address if len(candidate) == 64 else candidate


def normalize_private_key(value: str) -> str:
    if not value:
        return value
    key = value.strip()
    return key if key.startswith("0x") else "0x" + key


class AlchemyRpcClient:
    def __init__(self, rpc_url: str) -> None:
        self.rpc_url = rpc_url
        self.session = requests.Session()

    def call(self, method: str, params: List[Any]) -> Dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),
            "method": method,
            "params": params,
        }
        response = self.session.post(self.rpc_url, json=payload, timeout=30)
        if response.status_code >= 400:
            body = response.text.strip()
            raise RuntimeError(
                f"HTTP {response.status_code} for {method} on {self.rpc_url}. "
                f"Response body: {body}"
            )
        data = response.json()
        if "error" in data:
            raise RuntimeError(f"RPC error for {method}: {data['error']}")
        return data["result"]


def function_selector(signature: str) -> bytes:
    return keccak(text=signature)[:4]


def encode_set_uint256(value: int) -> str:
    # Equivalent to viem encodeFunctionData for set(uint256)
    selector = function_selector("set(uint256)")
    encoded_args = abi_encode(["uint256"], [value])
    return "0x" + (selector + encoded_args).hex()


def _sign_raw_hash(raw_payload: str, private_key: str) -> Any:
    raw = raw_payload[2:] if raw_payload.startswith("0x") else raw_payload
    msg_hash = bytes.fromhex(raw)
    return Account._sign_hash(message_hash=msg_hash, private_key=private_key)


def _sign_eip7702_auth(raw_payload: str, private_key: str) -> str:
    # Match SDK behavior: serialize as r || s || yParity (0/1).
    signed = _sign_raw_hash(raw_payload, private_key)
    y_parity = signed.v - 27 if signed.v >= 27 else signed.v
    return (
        "0x"
        + signed.r.to_bytes(32, "big").hex()
        + signed.s.to_bytes(32, "big").hex()
        + y_parity.to_bytes(1, "big").hex()
    )


def create_session(
    rpc: AlchemyRpcClient,
    owner_account: str,
    owner_private_key: str,
    delegate_public_key: str,
    contract_address: str,
    chain_id: str,
    method_name: str = "wallet_createSession",
) -> Dict[str, Any]:
    params = [
        {
            "account": owner_account,
            "chainId": chain_id,
            # "expirySec": int(time.time()) + 86400,
            "permissions": [
                {
                    "type": "contract-access",
                    "data": {
                        "address": contract_address,
                        # To scope to one function, uncomment and use:
                        # "functions": ["0x60fe47b1"],  # set(uint256)
                    },
                }
            ],
            "key": {
                "publicKey": delegate_public_key,
                "type": "secp256k1",
            },
        }
    ]
    result = rpc.call(method_name, params)
    session_id = result.get("sessionId")
    sig_req = result.get("signatureRequest", {})
    raw_payload = sig_req.get("rawPayload")
    if not session_id or not raw_payload:
        raise RuntimeError(f"wallet_createSession missing fields: {result}")

    # Sign EIP-712 hash directly (no message prefix), matching Alchemy docs flow.
    msg_hash = bytes.fromhex(raw_payload[2:]) if raw_payload.startswith("0x") else bytes.fromhex(raw_payload)
    signed = Account._sign_hash(message_hash=msg_hash, private_key=owner_private_key)
    session_signature = "0x" + signed.signature.hex()

    # Mirror @alchemy/wallet-apis grantPermissions() context packing:
    # context = 0x00 ++ sessionId ++ ownerSignature
    context = "0x00" + session_id[2:] + session_signature[2:]
    print("context:", context)
    print("session_id:", session_id)
    print("session_signature:", session_signature)
    return {
        "context": context,
        # Raw Wallet API capability shape for wallet_prepareCalls/sendPreparedCalls
        "sessionId": session_id,
        "signature": session_signature,
    }


def send_and_wait(
    rpc: AlchemyRpcClient,
    smart_wallet_account: str,
    delegate_private_key: str,
    to: str,
    value: str,
    data_hex: str,
    permission_obj: Optional[Dict[str, Any]],
    chain_id: str,
    paymaster_policy_id: Optional[str],
    prepare_method_name: str = "wallet_prepareCalls",
    send_prepared_method_name: str = "wallet_sendPreparedCalls",
    status_method_name: str = "wallet_getCallsStatus",
) -> Dict[str, Any]:
    call_id = prepare_and_send_calls(
        rpc=rpc,
        smart_wallet_account=smart_wallet_account,
        delegate_private_key=delegate_private_key,
        to=to,
        value=value,
        data_hex=data_hex,
        permission_obj=permission_obj,
        chain_id=chain_id,
        paymaster_policy_id=paymaster_policy_id or None,
        prepare_method_name=prepare_method_name,
        send_prepared_method_name=send_prepared_method_name,
    )
    print("call id:", call_id)

    status = wait_for_calls_status(
        rpc=rpc,
        call_id=call_id,
        method_name=status_method_name,
    )
    print("final status:", status)
    return {"id": call_id, "status": status}


def prepare_and_send_calls(
    rpc: AlchemyRpcClient,
    smart_wallet_account: str,
    delegate_private_key: str,
    to: str,
    value: str,
    data_hex: str,
    permission_obj: Optional[Dict[str, Any]],
    chain_id: str,
    paymaster_policy_id: Optional[str],
    prepare_method_name: str = "wallet_prepareCalls",
    send_prepared_method_name: str = "wallet_sendPreparedCalls",
) -> str:
    capabilities: Dict[str, Any] = {}
    if permission_obj and permission_obj.get("sessionId") and permission_obj.get("signature"):
        capabilities["permissions"] = {
            "sessionId": permission_obj["sessionId"],
            "signature": permission_obj["signature"],
        }

    prepare_body: Dict[str, Any] = {
        "chainId": chain_id,
        "from": smart_wallet_account,
        "calls": [{"to": to, "value": value, "data": data_hex}],
    }

    if paymaster_policy_id:
        capabilities["paymasterService"] = {"policyId": paymaster_policy_id}

    if capabilities:
        prepare_body["capabilities"] = capabilities

    prepared = rpc.call(prepare_method_name, [prepare_body])

    prepared_type = prepared.get("type")
    if prepared_type == "array":
        signed_items: List[Dict[str, Any]] = []
        for item in prepared.get("data", []):
            sig_req = item.get("signatureRequest", {})
            sig_type = sig_req.get("type")
            if sig_type == "eip7702Auth":
                raw_payload = sig_req.get("rawPayload")
                if not raw_payload:
                    raise RuntimeError(f"eip7702Auth missing rawPayload: {sig_req}")
                signature = _sign_eip7702_auth(raw_payload, delegate_private_key)
            elif sig_type == "personal_sign":
                raw = (sig_req.get("data") or {}).get("raw")
                if not raw:
                    raise RuntimeError(f"personal_sign missing data.raw: {sig_req}")
                signed = Account.sign_message(
                    encode_defunct(hexstr=raw),
                    private_key=delegate_private_key,
                )
                signature = "0x" + signed.signature.hex()
            else:
                raise RuntimeError(f"Unsupported signatureRequest.type for array item: {sig_type}")

            signed_item = {
                k: v
                for k, v in item.items()
                if k not in ("signatureRequest", "feePayment")
            }
            signed_item["signature"] = {"type": "secp256k1", "data": signature}
            signed_items.append(signed_item)

        send_prepared_body = {"type": "array", "data": signed_items}
        if capabilities:
            send_prepared_body["capabilities"] = capabilities
    else:
        sig_req = prepared.get("signatureRequest", {})
        sig_type = sig_req.get("type")
        if sig_type != "personal_sign":
            raise RuntimeError(f"Unsupported signatureRequest.type for prepared calls: {sig_type}")
        raw = (sig_req.get("data") or {}).get("raw")
        if not raw:
            raise RuntimeError(f"personal_sign missing data.raw: {sig_req}")
        signed = Account.sign_message(
            encode_defunct(hexstr=raw),
            private_key=delegate_private_key,
        )
        userop_signature = "0x" + signed.signature.hex()

        send_prepared_body = {
            "type": prepared_type,
            "data": prepared.get("data"),
            "chainId": prepared.get("chainId", chain_id),
            "signature": {"type": "secp256k1", "data": userop_signature},
        }
        if capabilities:
            send_prepared_body["capabilities"] = capabilities

    result = rpc.call(send_prepared_method_name, [send_prepared_body])
    call_id = result.get("id")
    if not call_id:
        raise RuntimeError(f"wallet_sendPreparedCalls returned no id: {result}")
    return call_id


def wait_for_calls_status(
    rpc: AlchemyRpcClient,
    call_id: str,
    method_name: str = "wallet_getCallsStatus",
    timeout_sec: int = 120,
    poll_every_sec: int = 3,
) -> Dict[str, Any]:
    start = time.time()
    while time.time() - start < timeout_sec:
        status = rpc.call(method_name, [call_id])
        state = status.get("status")
        # EIP-5792 numeric statuses: 200+ are terminal.
        if isinstance(state, int) and state >= 200:
            return status
        state_str = str(state).lower()
        if state_str in {"confirmed", "success", "mined", "failed", "reverted"}:
            return status
        time.sleep(poll_every_sec)
    raise TimeoutError(f"Timed out waiting for call status for id={call_id}")


def main() -> None:
    load_dotenv()

    api_key = os.getenv("ALCHEMY_API_KEY", "")
    rpc_url_override = os.getenv("ALCHEMY_RPC_URL", "").strip()
    owner_account = normalize_account(os.getenv("OWNER_ACCOUNT", ""))
    owner_private_key = normalize_private_key(
        os.getenv("OWNER_PRIVATE_KEY", os.getenv("OWNER_ACCOUNT", ""))
    )
    delegate_private_key = normalize_private_key(os.getenv("DELEGATE_PRIVATE_KEY", ""))
    delegate_public_key_env = os.getenv("DELEGATE_PUBLIC_KEY", "")
    delegate_public_key = (
        Account.from_key(delegate_private_key).address if delegate_private_key else delegate_public_key_env
    )
    contract_address = os.getenv("TARGET_CONTRACT", "")
    paymaster_policy_id = os.getenv("POLICY_ID", "")

    # Override if your endpoint uses different method names.
    grant_method = os.getenv("ALCHEMY_GRANT_METHOD", "wallet_createSession")
    prepare_method = os.getenv("ALCHEMY_PREPARE_METHOD", "wallet_prepareCalls")
    send_method = os.getenv("ALCHEMY_SEND_METHOD", "wallet_sendPreparedCalls")
    status_method = os.getenv("ALCHEMY_STATUS_METHOD", "wallet_getCallsStatus")
    chain_id = os.getenv("CHAIN_ID", "0x14a34")

    missing = [
        name
        for name, value in [
            ("ALCHEMY_API_KEY", api_key),
            ("OWNER_ACCOUNT", owner_account),
            ("OWNER_PRIVATE_KEY", owner_private_key),
            ("DELEGATE_PRIVATE_KEY", delegate_private_key),
            ("SMART_WALLET_ACCOUNT", owner_account),
            ("DELEGATE_PUBLIC_KEY", delegate_public_key),
            ("TARGET_CONTRACT", contract_address),
        ]
        if not value
    ]
    if missing:
        raise ValueError(f"Missing required env vars: {', '.join(missing)}")

    if delegate_public_key_env and delegate_private_key:
        derived_delegate = Account.from_key(delegate_private_key).address
        if delegate_public_key_env.lower() != derived_delegate.lower():
            print(
                "warning: DELEGATE_PUBLIC_KEY does not match DELEGATE_PRIVATE_KEY; "
                f"using derived address {derived_delegate}"
            )

    rpc = AlchemyRpcClient(rpc_url_override or build_rpc_url(api_key))

    send_and_wait(
        rpc=rpc,
        smart_wallet_account=owner_account,
        delegate_private_key=owner_private_key,
        to="0x0000000000000000000000000000000000000000",
        value="0x0",
        data_hex="0x",
        permission_obj=None,
        chain_id=chain_id,
        paymaster_policy_id=paymaster_policy_id or None,
        prepare_method_name=prepare_method,
        send_prepared_method_name=send_method,
        status_method_name=status_method,
    )

    permission = create_session(
        rpc=rpc,
        owner_account=owner_account,
        owner_private_key=owner_private_key,
        delegate_public_key=delegate_public_key,
        contract_address=contract_address,
        chain_id=chain_id,
        method_name=grant_method,
    )
    print("permission:", permission)

    data_hex = encode_set_uint256(46)
    send_and_wait(
        rpc=rpc,
        smart_wallet_account=owner_account,
        delegate_private_key=delegate_private_key,
        to=contract_address,
        value="0x0",
        data_hex=data_hex,
        permission_obj=permission,
        chain_id=chain_id,
        paymaster_policy_id=paymaster_policy_id or None,
        prepare_method_name=prepare_method,
        send_prepared_method_name=send_method,
        status_method_name=status_method,
    )


if __name__ == "__main__":
    main()
