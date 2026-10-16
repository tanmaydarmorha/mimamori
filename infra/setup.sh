#!/usr/bin/env bash
# One-time GCP setup for the prototype (safe to re-run: every step skips what already exists).
# Creates no keys. Prints the GitHub repository variables at the end.
#
#   PROJECT=mimamori-proto-2026 GITHUB_REPO=tanmaydarmorha/mimamori infra/setup.sh
set -euo pipefail

PROJECT="${PROJECT:?set PROJECT}"
GITHUB_REPO="${GITHUB_REPO:?set GITHUB_REPO (owner/name)}"
REGION="${REGION:-asia-south1}"
REPO="${REPO:-mimamori}"
NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
g() { echo "+ gcloud $*" >&2; gcloud --project "$PROJECT" --quiet "$@"; }
exists() { gcloud --project "$PROJECT" "$@" >/dev/null 2>&1; }

echo "== APIs"
g services enable run.googleapis.com artifactregistry.googleapis.com firestore.googleapis.com \
  aiplatform.googleapis.com compute.googleapis.com iam.googleapis.com iamcredentials.googleapis.com \
  sts.googleapis.com logging.googleapis.com texttospeech.googleapis.com

echo "== Artifact Registry"
exists artifacts repositories describe "$REPO" --location "$REGION" ||
  g artifacts repositories create "$REPO" --repository-format docker --location "$REGION"

echo "== Network: default VPC, Private Google Access in $REGION (Direct VPC egress reaches Google APIs)"
exists compute networks describe default || g compute networks create default --subnet-mode auto
g compute networks subnets update default --region "$REGION" --enable-private-ip-google-access

echo "== Firestore (Native) databases"
for db in case-db intel-db ref-db; do
  exists firestore databases describe --database "$db" ||
    g firestore databases create --database "$db" --location "$REGION" --type firestore-native
done

echo "== One service account per deployable"
SAS=(core-bank-mock scoring case-svc conversation-svc web-ui intel-job watchlist-loader sim-job)
for sa in "${SAS[@]}"; do
  exists iam service-accounts describe "$sa@$PROJECT.iam.gserviceaccount.com" ||
    g iam service-accounts create "$sa" --display-name "Mimamori $sa"
done

# Database grants, conditioned on the database (infra/README.md table). No one else gets any.
db_grant() {  # sa role db
  g projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$1@$PROJECT.iam.gserviceaccount.com" \
    --role "$2" --condition "title=$1-$3,expression=resource.name==\"projects/$PROJECT/databases/$3\"" >/dev/null
}
echo "== Firestore IAM (per database)"
db_grant scoring roles/datastore.user case-db
db_grant scoring roles/datastore.viewer ref-db
db_grant case-svc roles/datastore.user case-db
db_grant case-svc roles/datastore.user intel-db
db_grant intel-job roles/datastore.user intel-db
db_grant watchlist-loader roles/datastore.user ref-db

echo "== Vertex AI (Gemini) for the model callers"
for sa in case-svc conversation-svc intel-job sim-job; do
  g projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$sa@$PROJECT.iam.gserviceaccount.com" \
    --role roles/aiplatform.user --condition None >/dev/null
done

echo "== Cloud Text-to-Speech for the call voice (needs only API use on the project)"
g projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:conversation-svc@$PROJECT.iam.gserviceaccount.com" \
  --role roles/serviceusage.serviceUsageConsumer --condition None >/dev/null

echo "== Deployer for GitHub Actions (Workload Identity Federation, main branch of $GITHUB_REPO only)"
DEPLOYER="gh-deployer@$PROJECT.iam.gserviceaccount.com"
exists iam service-accounts describe "$DEPLOYER" || g iam service-accounts create gh-deployer --display-name "GitHub deploy"
for role in roles/run.admin roles/artifactregistry.writer roles/iam.serviceAccountUser; do
  g projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$DEPLOYER" --role "$role" --condition None >/dev/null
done
exists iam workload-identity-pools describe github --location global ||
  g iam workload-identity-pools create github --location global --display-name "GitHub"
exists iam workload-identity-pools providers describe github --location global --workload-identity-pool github ||
  g iam workload-identity-pools providers create-oidc github --location global --workload-identity-pool github \
    --issuer-uri https://token.actions.githubusercontent.com \
    --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
    --attribute-condition "assertion.repository=='$GITHUB_REPO' && assertion.ref=='refs/heads/main'"
g iam service-accounts add-iam-policy-binding "$DEPLOYER" --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/$NUMBER/locations/global/workloadIdentityPools/github/attribute.repository/$GITHUB_REPO" >/dev/null

cat <<EOF

Done. GitHub repository variables (gh variable set NAME --body VALUE):
  GCP_PROJECT_ID                  $PROJECT
  GCP_PROJECT_NUMBER              $NUMBER
  GCP_ARTIFACT_REPO               $REPO
  GCP_SERVICE_ACCOUNT             $DEPLOYER
  GCP_WORKLOAD_IDENTITY_PROVIDER  projects/$NUMBER/locations/global/workloadIdentityPools/github/providers/github
EOF
