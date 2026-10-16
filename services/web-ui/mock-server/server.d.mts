export function holdWindow(
  placedMs: number,
  opts?: { minimum_hours?: number; extend?: boolean; cap_hours?: number },
): { minimum_ends_at: number; ends_at: number; cap_ends_at: number };

export function startMock(opts?: { port?: number; delayMs?: number; host?: string }): Promise<{
  port: number;
  url: string;
  reset: () => void;
  close: () => Promise<void>;
}>;
