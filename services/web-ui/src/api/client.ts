import type {
  AuditEntry,
  Case,
  CaseSummary,
  Customer,
  DecisionRequest,
  DecisionResponse,
  DismissIndicatorBody,
  FreezeDecisionBody,
  FreezeDecisionResponse,
  FreezeRequest,
  FreezeRequestBody,
  Notice,
  OutreachItem,
  Playbook,
  PlaybookPatch,
  PoliceSummaryRequest,
  PoliceSummaryResponse,
  RuntimeConfig,
  TransferRequest,
  TransferResponse,
  TurnRequest,
  TurnResponse,
  WhoAmI,
  Language,
} from "./types";

/** Browser-side base: nginx (or the Vite dev proxy) maps /api/<svc>/ to the service. */
let apiBase = "/api";
export function setApiBase(base: string) {
  apiBase = base.replace(/\/$/, "");
}
export const svc = {
  core: () => `${apiBase}/core`,
  scoring: () => `${apiBase}/scoring`,
  case: () => `${apiBase}/case`,
  conversation: () => `${apiBase}/conversation`,
};

/** Who the console acts as. Locally the role switcher sets it; in the cloud IAP supplies the headers. */
export interface Identity {
  role: "teller" | "analyst";
  user: string;
}
let identity: Identity = { role: "teller", user: "teller-01" };
export function setIdentity(i: Identity) {
  identity = i;
}
export function getIdentity(): Identity {
  return identity;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public error: string,
    public detail?: string | null,
  ) {
    super(detail ? `${error}: ${detail}` : error);
  }
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {
    "X-Mimamori-Role": identity.role,
    "X-Mimamori-User": identity.user,
  };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!res.ok) {
    let err: { error?: string; detail?: unknown } = {};
    try {
      err = await res.json();
    } catch {
      /* not JSON */
    }
    const detail = typeof err.detail === "string" ? err.detail : err.detail ? JSON.stringify(err.detail) : null;
    throw new ApiError(res.status, err.error ?? res.statusText, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
const get = <T>(url: string) => request<T>("GET", url);
const post = <T>(url: string, body?: unknown) => request<T>("POST", url, body ?? {});

// -------- nginx-local
export const getConfig = () => get<RuntimeConfig>("/config.json");
/** Plain fetch, no identity headers: /whoami must only echo what IAP supplied, not what this page set. */
export const getWhoAmI = async (): Promise<WhoAmI> => {
  const res = await fetch("/whoami", { cache: "no-store" });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return res.json();
};

// -------- core banking
export const postTransfer = (b: TransferRequest) => post<TransferResponse>(`${svc.core()}/transfers`, b);
export const getCustomer = (ref: string) => get<Customer>(`${svc.core()}/customers/${encodeURIComponent(ref)}`);

// -------- case service
export const listCases = (status?: string) =>
  get<CaseSummary[]>(`${svc.case()}/cases${status ? `?status=${encodeURIComponent(status)}` : ""}`);
export const getCase = (id: string) => get<Case>(`${svc.case()}/cases/${id}`);
export const patchLanguage = (id: string, language: Language, actor: string) =>
  request<Case>("PATCH", `${svc.case()}/cases/${id}/language`, { language, actor });
export const getAudit = (id: string) => get<AuditEntry[]>(`${svc.case()}/cases/${id}/audit`);
export const postTurn = (id: string, b: TurnRequest) => post<TurnResponse>(`${svc.case()}/cases/${id}/turns`, b);
export const postDecision = (id: string, b: DecisionRequest) =>
  post<DecisionResponse>(`${svc.case()}/cases/${id}/decision`, b);
export const dismissClaim = (id: string, claimId: string, b: DismissIndicatorBody) =>
  post<Case>(`${svc.case()}/cases/${id}/claims/${claimId}/dismiss`, b);
export const postPoliceSummary = (id: string, b: PoliceSummaryRequest) =>
  post<PoliceSummaryResponse>(`${svc.case()}/cases/${id}/police-summary`, b);
export const postContactCall = (id: string) => post<Case>(`${svc.case()}/cases/${id}/contact-call`);
export const postFreezeRequest = (id: string, b: FreezeRequestBody) =>
  post<FreezeRequest>(`${svc.case()}/cases/${id}/freeze-request`, b);
export const listFreezeRequests = (status?: string) =>
  get<FreezeRequest[]>(`${svc.case()}/freeze-requests${status ? `?status=${encodeURIComponent(status)}` : ""}`);
export const postFreezeDecision = (id: string, b: FreezeDecisionBody) =>
  post<FreezeDecisionResponse>(`${svc.case()}/cases/${id}/freeze-decision`, b);
export const getOutreach = (id: string) => get<OutreachItem[]>(`${svc.case()}/cases/${id}/outreach`);
export const listPlaybooks = (status?: string) =>
  get<Playbook[]>(`${svc.case()}/playbooks${status ? `?status=${encodeURIComponent(status)}` : ""}`);
export const patchPlaybook = (id: string, b: PlaybookPatch) =>
  request<Playbook>("PATCH", `${svc.case()}/playbooks/${id}`, b);

// -------- conversation service
export const listNotices = (to: string) => get<Notice[]>(`${svc.conversation()}/notices?to=${encodeURIComponent(to)}`);

/** ws:// or wss:// URL for a path under an /api/<svc>/ prefix (works behind nginx and the Vite proxy). */
export function wsUrl(path: string): string {
  const abs = path.startsWith("http") ? path : `${window.location.origin}${path}`;
  return abs.replace(/^http/, "ws");
}
export const phoneSocketUrl = () => wsUrl(`${svc.conversation()}/phone`);
export const audioSocketUrl = (caseId: string) => wsUrl(`${svc.case()}/cases/${caseId}/audio`);
export const eventsUrl = (caseId: string) => `${svc.case()}/cases/${caseId}/events`;
