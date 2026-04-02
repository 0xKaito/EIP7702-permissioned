
import { toFunctionSelector} from "viem";
import "dotenv/config";


import { client } from "./client.ts";



export const permission = await client.grantPermissions({
    permissions: [
      {
        type: "functions-on-contract",
        data: {
          address: process.env.TARGET_CONTRACT as `0x${string}`,  // only this contract
          functions: [toFunctionSelector("set(uint256)")],      // only these functions
        },
      },
    ],
    expirySec: Math.floor(Date.now() / 1000) + 86400, // 24h expiry
    key: {
        publicKey: process.env.DELEGATE_PUBLIC_KEY as `0x${string}`,
        type: "secp256k1",
    },
  });

  console.log("permission", permission);