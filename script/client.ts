import type { Hex } from "viem";
import { sepolia } from "viem/chains";
import { privateKeyToAccount } from "viem/accounts";
import { createSmartWalletClient, alchemyWalletTransport } from "@alchemy/wallet-apis";
import "dotenv/config";
 
export const client = createSmartWalletClient({
  transport: alchemyWalletTransport({
    apiKey: process.env.ALCHEMY_API_KEY,
  }),
  chain: sepolia,
  signer: privateKeyToAccount(process.env.OWNER_PRIVATE_KEY as Hex),
  // Optional: sponsor gas for your users (see "Sponsor gas" guide)
  // paymaster: { policyId: process.env.POLICY_ID },
});

// Minimal bootstrap call to trigger first 7702 delegation.
// Uses a no-op style call (zero-address, zero value, empty data).
const { id } = await client.sendCalls({
  calls: [
    {
      to: "0x0000000000000000000000000000000000000000",
      value: 0n,
      data: "0x",
    },
  ],
});

console.log("delegate call id:", id);
const status = await client.waitForCallsStatus({ id });
console.log("delegate status:", status);

export const botClient = createSmartWalletClient({
  transport: alchemyWalletTransport({
    apiKey: process.env.ALCHEMY_API_KEY,
  }),
  chain: sepolia,
  signer: privateKeyToAccount(process.env.DELEGATE_PRIVATE_KEY as Hex),
  account: process.env.OWNER_ACCOUNT as `0x${string}`,
  // Optional: sponsor gas for your users (see "Sponsor gas" guide)
  // paymaster: { policyId: process.env.POLICY_ID },
});