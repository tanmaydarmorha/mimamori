# Infra (not created)

No GCP project, Artifact Registry or Workload Identity Federation exists yet, and `gcloud` isn't
installed on the build machine. **Nothing here creates cloud resources.** This is the list of what a
deploy needs, taken from `docs/architecture/c4-containers.md`.

## Project and region
- A GCP project in the bank's organisation. Prototype region `asia-south1` (`MIMAMORI_REGION`);
  production for a Japanese bank is `asia-northeast1`.
- Open item: Gemma GPU quota, streaming ja-JP Chirp STT and Gemini availability in `asia-south1`.
  Anything missing may use another region for this synthetic-data prototype (stated in the brief):
  set `MIMAMORI_GEMINI_LOCATION`, the STT region, or the Vertex endpoint region accordingly.

## APIs to enable
Cloud Run, Artifact Registry, Firestore, Vertex AI, Speech-to-Text, Text-to-Speech, IAP, Cloud
Scheduler, Secret Manager (only if a secret appears; none is needed now), Cloud Logging.

## Firestore (Native mode), three databases, one project
`case-db`, `intel-db`, `ref-db`. The store layer sorts client-side, so **no composite indexes** are
needed. IAM **conditions on each database** (Firestore has no per-collection IAM for server access):

| Principal (service account) | `case-db` | `intel-db` | `ref-db` |
|---|---|---|---|
| scoring | read/write | none | read |
| case-svc | read/write | read; write approved playbooks (analyst approval path) | none |
| conversation-svc, core-bank-mock, web-ui | **none** | none | none |
| intel-job | **none** | write (pending only) | none |
| watchlist-loader | **none** | none | write |
| sim-job | **none** | none | none |

The Vertex Gemma endpoint's service identity has no grant on any database.

## Cloud Run
One service per `services/*`, one job per `jobs/*`, one service account each (least privilege per
the table above). Images: `<region>-docker.pkg.dev/<project>/<repo>/<name>:<sha>`. Services:
`--no-allow-unauthenticated`, min instances 1 for `scoring`. Env per container: `MIMAMORI_ENV=cloud`,
`MIMAMORI_REGION`, `MIMAMORI_PROJECT_ID`, `MIMAMORI_SERVICE=<name>`, the service URLs,
`VERTEX_GEMMA_ENDPOINT_ID`, `GEMINI_MODEL`. `web-ui` sits behind IAP (roles `teller`, `analyst`
mapped to `X-Mimamori-Role`). Scheduler triggers `watchlist-loader` and `intel-job`.

## web-ui to private services
nginx cannot attach Cloud Run ID tokens when proxying to `--no-allow-unauthenticated` services.
Decide before deploying: put the services behind the same IAP / an internal load balancer, or add a
token-injecting sidecar to `web-ui`. Not solved in the prototype (local compose has no auth).

## Vertex AI
A Gemma endpoint with constrained decoding (the case service sends a JSON schema). Fixed GPU floor:
at least one replica runs all the time, so **undeploy between sessions**. Check latency against the
~3 s per turn target (spike criterion 4 is still untested).

## GitHub Actions deploy (Workload Identity Federation)
`.github/workflows/_build-deploy.yml` builds and tests on every run, and **deploys only on `main`
when the repository variable `GCP_WORKLOAD_IDENTITY_PROVIDER` is set**. Needed repository variables:
`GCP_PROJECT_ID`, `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`, `GCP_ARTIFACT_REPO`,
optionally `MIMAMORI_REGION`. No service-account keys, ever.

## Designed, not built
Append-only audit sink (Cloud Logging to BigQuery or GCS with a retention lock), the ATM / app path,
cross-bank fan-in, the learning loop, voice onboarding, real telephony.
