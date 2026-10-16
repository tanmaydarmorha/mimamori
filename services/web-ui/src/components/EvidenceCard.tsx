import type { EvidenceCard as Card, Language, PlaybookHoldLine } from "../api/types";
import { AskNext } from "./AskNext";
import { RiskBand } from "./RiskBand";
import { Why } from "./Why";

/**
 * The evidence card as one block (band, ask next, why), for screens that do not lay the parts out
 * themselves: the analyst console (until WI-008). The teller's `CaseView` composes the three parts.
 */
export function EvidenceCard({
  card,
  holdLine,
  onDismiss,
  language = "ja",
  onSay,
  name,
}: {
  card: Card;
  holdLine?: PlaybookHoldLine | null;
  language?: Language;
  onSay?: (text: string) => void;
  onDismiss?: (claimId: string, reason: string) => Promise<void> | void;
  name?: string | null;
}) {
  return (
    <div data-testid="evidence-card">
      <RiskBand card={card} holdLine={holdLine} language={language} name={name} />
      <AskNext card={card} language={language} onSay={onSay} />
      <Why card={card} onDismiss={onDismiss} />
    </div>
  );
}
