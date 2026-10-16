import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { getConfig, getWhoAmI, setIdentity, type Identity } from "../api/client";
import type { RuntimeConfig } from "../api/types";

const STORAGE_KEY = "mimamori.identity";
const DEFAULT_USERS: Record<Identity["role"], string> = { teller: "teller-01", analyst: "analyst-01" };

interface AuthState {
  identity: Identity;
  /** true when IAP (via nginx /whoami) supplied the role; the local switcher is then hidden. */
  locked: boolean;
  config: RuntimeConfig;
  setRole: (role: Identity["role"]) => void;
}

const Ctx = createContext<AuthState | null>(null);

function readStored(): Identity {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const p = JSON.parse(raw);
      if ((p.role === "teller" || p.role === "analyst") && typeof p.user === "string") return p;
    }
  } catch {
    /* ignore */
  }
  return { role: "teller", user: DEFAULT_USERS.teller };
}

export function AuthProvider({
  children,
  initial,
  initialConfig,
}: {
  children: ReactNode;
  /** tests / storybook: skip the network probes */
  initial?: Identity;
  initialConfig?: RuntimeConfig;
}) {
  const [identity, setId] = useState<Identity>(() => initial ?? readStored());
  const [locked, setLocked] = useState(false);
  const [config, setConfig] = useState<RuntimeConfig>(initialConfig ?? { env: "local", speech: "typed" });

  setIdentity(identity); // keep the fetch wrapper in step during render, before children fetch

  useEffect(() => {
    if (initial) return;
    let alive = true;
    getConfig()
      .then((c) => alive && setConfig(c))
      .catch(() => {});
    getWhoAmI()
      .then((w) => {
        if (!alive) return;
        if ((w.role === "teller" || w.role === "analyst") && w.user) {
          setId({ role: w.role, user: w.user });
          setLocked(true);
        }
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [initial]);

  const value = useMemo<AuthState>(
    () => ({
      identity,
      locked,
      config,
      setRole: (role) => {
        const next = { role, user: DEFAULT_USERS[role] };
        setId(next);
        try {
          localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        } catch {
          /* ignore */
        }
      },
    }),
    [identity, locked, config],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
