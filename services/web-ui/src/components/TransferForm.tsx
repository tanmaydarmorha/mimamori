import { useState } from "react";
import { postTransfer } from "../api/client";
import type { TransferResponse } from "../api/types";
import { useAuth } from "../auth/Auth";
import { useLang } from "../i18n";

/**
 * The teller keys in a counter transfer (`POST /transfers` on core banking). For a counter transfer
 * Scoring checks it first; on `alert` the money stays pending and a case is returned. The defaults are
 * the synthetic Tanaka demo (¥3,000,000 to the same-bank account 「カ）ミライケンセツ」).
 */
export function TransferForm({ onCreated }: { onCreated: (r: TransferResponse) => void }) {
  const { tr } = useLang();
  const { identity } = useAuth();
  const [customer, setCustomer] = useState("cust-tanaka-0001");
  const [account, setAccount] = useState("acct-tanaka-0001");
  const [amount, setAmount] = useState("3000000");
  const [payee, setPayee] = useState("カ）ミライケンセツ");
  const [payeeAccount, setPayeeAccount] = useState("acct-mule-0001");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TransferResponse | null>(null);
  const [open, setOpen] = useState(false);

  const amt = Number(amount);
  const valid = customer.trim() && account.trim() && payee.trim() && Number.isInteger(amt) && amt >= 1;

  const outcome = result
    ? result.case_id
      ? tr("アラートが出ました。ケースを開きました。", "Alert raised. The case is open.")
      : result.scoring === "unavailable"
        ? tr("確認ができなかったため、通常の手続きで受け付けました。", "The check was unavailable, so the transfer went ahead under existing controls.")
        : tr("問題は見つかりませんでした。振込を受け付けました。", "Nothing unusual. The transfer was accepted.")
    : null;

  return (
    <>
    <details className="transfer-form" data-testid="transfer-form" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>{tr("窓口の振込を入力", "New counter transfer")}</summary>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (!valid || busy) return;
          setBusy(true);
          setError(null);
          try {
            const r = await postTransfer({
              customer_ref: customer.trim(),
              account_id: account.trim(),
              channel: "counter",
              kind: "transfer",
              amount_jpy: amt,
              payee: { name_kana: payee.trim(), relation: "same_bank", account_id: payeeAccount.trim() || null },
              teller_id: identity.user,
            });
            setResult(r);
            setOpen(false);
            onCreated(r);
          } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
          } finally {
            setBusy(false);
          }
        }}
      >
        <label className="field">
          {tr("お客様ID", "Customer ref")}
          <input value={customer} onChange={(e) => setCustomer(e.target.value)} />
        </label>
        <label className="field">
          {tr("口座ID", "Account")}
          <input value={account} onChange={(e) => setAccount(e.target.value)} />
        </label>
        <label className="field">
          {tr("金額(円)", "Amount (JPY)")}
          <input inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value)} aria-label={tr("金額", "Amount")} />
        </label>
        <label className="field">
          {tr("振込先名義(カナ)", "Payee (kana)")}
          <input value={payee} onChange={(e) => setPayee(e.target.value)} />
        </label>
        <label className="field">
          {tr("振込先口座ID(当行内)", "Payee account (same bank)")}
          <input value={payeeAccount} onChange={(e) => setPayeeAccount(e.target.value)} />
        </label>
        <button type="submit" disabled={!valid || busy}>
          {tr("振込を入力", "Submit transfer")}
        </button>
      </form>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </details>
    {outcome && (
      <p className="muted small" data-testid="transfer-result">
        {outcome}
      </p>
    )}
    </>
  );
}
