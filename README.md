# EIP-7702 Permissioned Execution

Example project showing how to execute contract calls on behalf of a user account using:

- `@alchemy/wallet-apis` (TypeScript flow)
- Raw Wallet API RPC calls (Python flow)
- Session-style permissions for delegated execution

This repo demonstrates the "user grants permission once, bot executes later" model.

## Project layout

- `script/client.ts` - creates user and bot smart wallet clients
- `script/delegatePermission.ts` - grants scoped permissions
- `script/sencCalls.ts` - sends a call using stored permission
- `script/testConteactAbi.json` - sample ABI (`set(uint256)`)
- `script_py/alchemy_smart_wallet_bot.py` - Python end-to-end session + send flow

## Prerequisites

- Node.js 18+ (Node 20+ recommended)
- npm
- Python 3.9+
- Alchemy API key and wallet API access

## Environment variables

Create `.env` in repo root:

```bash
ALCHEMY_API_KEY=your_api_key
OWNER_PRIVATE_KEY=0x...
OWNER_ACCOUNT=0x...                # owner/smart account address
DELEGATE_PRIVATE_KEY=0x...         # bot/session key private key
DELEGATE_PUBLIC_KEY=0x...          # bot/session key address
SMART_WALLET_ACCOUNT=0x...         # account used for sending calls
TARGET_CONTRACT=0x...              # target contract
# Optional:
# ALCHEMY_POLICY_ID=...
# CHAIN_ID=0xaa36a7
```

## Install

```bash
npm install
python3 -m pip install requests eth-account eth-abi eth-utils
```

## Run TypeScript flow

Use `tsx` so `.ts` files run cleanly in ESM:

```bash
npx tsx script/sencCalls.ts
```

What this does:
1. Loads env from `.env` (via `dotenv/config`)
2. Grants permission (`grantPermissions`)
3. Sends a call (`sendCalls`) using returned permission
4. Waits for call status

## Run Python flow

```bash
python3 script_py/alchemy_smart_wallet_bot.py
```

What this does:
1. Creates session (`wallet_createSession`)
2. Signs session authorization
3. Prepares calls (`wallet_prepareCalls`)
4. Signs prepared call as delegate key
5. Sends (`wallet_sendPreparedCalls`)
6. Polls status (`wallet_getCallsStatus`)

## Common issues

- `fetch is not defined`:
  - Use Node 18+ (prefer Node 20+)
- `Unknown file extension ".ts"`:
  - Run with `npx tsx ...` instead of `node ...`
- `Address already has a permission`:
  - Do not add duplicate permission entries for the same contract
- `Permission denied (publickey)` when cloning:
  - Ensure SSH key mapping is correct in `~/.ssh/config`
