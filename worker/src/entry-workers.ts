import type { Env } from "./core/types";
import { handleFetch, handleScheduled } from "./core/app";

export default {
  fetch: (request: Request, env: Env) => handleFetch(request, env),
  scheduled: (_event: ScheduledEvent, env: Env, ctx: ExecutionContext) => {
    ctx.waitUntil(handleScheduled(env));
  },
};
