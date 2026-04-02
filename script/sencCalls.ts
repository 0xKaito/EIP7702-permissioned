import testContractAbi from "./testConteactAbi.json" with { type: "json" };
import { encodeFunctionData } from "viem";

import { permission } from "./delegatePermission.ts";
import { botClient } from "./client.ts";
import "dotenv/config";

// Send the transaction
const { id } = await botClient.sendCalls({
  calls: [
    {
      to: process.env.TARGET_CONTRACT as `0x${string}`,    // target contract address
      value: BigInt(0),
      data: encodeFunctionData({
        abi: testContractAbi,
        functionName: "set",
        args: [BigInt(45)], // replace 45 with whatever value you want to set
      }),
    },
  ],
  capabilities: {
    permissions: permission,
  },
});
 
console.log({ id }); // the Call ID
 
// Wait for the transaction to be confirmed
const result = await botClient.waitForCallsStatus({ id });
 
console.log(result);
