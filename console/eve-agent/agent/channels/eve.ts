import { eveChannel } from "eve/channels/eve";
import { httpBasic, localDev } from "eve/channels/auth";

// the console's /api/chat is the only caller; it holds the same secret
export default eveChannel({
  auth: [httpBasic({ username: "neo", password: process.env.NEO_EVE_SECRET ?? "" }), localDev()],
});
