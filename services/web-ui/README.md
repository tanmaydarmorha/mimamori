# web-ui

React + TypeScript + Vite SPA served by nginx. Teller console (`/teller`), analyst console (`/analyst`),
simulated phone for the trusted contact (`/phone`). Builds against `docs/architecture/api-contracts.md`;
types in `src/api/types.ts` are hand-written mirrors of `mimamori_common.models.api` and `schemas/`.

## Run
```bash
npm ci
npm run dev:mock        # mock server (:8090, replays the Tanaka flow) + Vite (:5173)
npm test                # vitest: components, phone, and the full flow against the mock
npm run build
```
Demo: open `/teller`, expand "Key in a counter transfer", submit (defaults are the Tanaka transfer), type the
customer turns (`リフォーム代なんです`, then `警察の人から電話があってね、誰にも言うなって言われてるの`), pause
with basis + rationale, open `/phone` (notice, call back, menu 1, then the case code: 4821 on the mock server; with real services, the code shown in the notice, new for each case), switch the role to `analyst` for
freeze approval. `POST /__mock/reset` restarts the mock demo.

Against real services: `CORE_BANK_URL=... SCORING_URL=... CASE_SVC_URL=... CONVERSATION_SVC_URL=... npm run dev`.

## Container
`docker build -f services/web-ui/Dockerfile .` (repo root context; copies only `services/web-ui/`).
nginx envsubst template: `PORT` (8080), `CORE_BANK_URL`, `SCORING_URL`, `CASE_SVC_URL`,
`CONVERSATION_SVC_URL` (no trailing slash), `MIMAMORI_ENV` (`local|cloud`), `MIMAMORI_SPEECH` (`typed|cloud`,
enables the mic buttons). nginx answers `/healthz`, `/config.json` and `/whoami` (echoes the IAP-supplied
`X-Mimamori-Role` / `X-Mimamori-User`; when empty the SPA shows the local role switcher).
