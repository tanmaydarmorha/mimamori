/**
 * Demo sample lines and their English glosses. The glosses are hand-written: no machine translation
 * and no model call, so speech never takes a new path to a model. English appears beside the
 * Japanese, never instead of it.
 */
export interface DemoLine {
  id: string;
  who: "customer" | "contact";
  /** The language the line is said in: the case language. */
  language: "ja" | "en";
  /** What is said, in `language`. */
  text: string;
  /** English gloss (equal to `text` for an English line). */
  en: string;
  label_ja: string;
  label_en: string;
}

export const DEMO_LINES: DemoLine[] = [
  { id: "cust-renovation", who: "customer", language: "ja", text: "リフォーム代なんです", en: "It's for my renovation.", label_ja: "お客様: リフォーム代", label_en: "Customer: it's for renovation" },
  {
    id: "cust-police",
    who: "customer",
    language: "ja",
    text: "警察の人から電話があってね、誰にも言うなって言われてるの",
    en: "The police called me and told me not to tell anyone.",
    label_ja: "お客様: 警察から電話",
    label_en: "Customer: police called, keep it secret",
  },
  {
    id: "cust-contractor",
    who: "customer",
    language: "ja",
    text: "業者さんとは先月から何度も会って、見積もりももらっています",
    en: "I've met the contractor several times since last month and have a written quote.",
    label_ja: "お客様: 業者と面談済み",
    label_en: "Customer: met the contractor, have a quote",
  },
  {
    id: "cust-grandson",
    who: "customer",
    language: "ja",
    text: "孫の入学金なんです。娘と一緒に学校で手続きしました",
    en: "It's my grandson's school entrance fee. I did the paperwork with my daughter at the school.",
    label_ja: "お客様: 孫の入学金",
    label_en: "Customer: grandson's entrance fee",
  },
  { id: "contact-what", who: "contact", language: "ja", text: "何があったんですか？", en: "What happened?", label_ja: "娘: 何があった?", label_en: "Daughter: what happened?" },
  { id: "contact-safe", who: "contact", language: "ja", text: "母は大丈夫ですか？", en: "Is my mother safe?", label_ja: "娘: 母は大丈夫?", label_en: "Daughter: is my mother safe?" },
  { id: "contact-amount", who: "contact", language: "ja", text: "いくらの振込ですか？", en: "How much is the transfer?", label_ja: "娘: 金額は?", label_en: "Daughter: how much?" },
  { id: "contact-what-do", who: "contact", language: "ja", text: "どうすればいいですか？", en: "What should I do?", label_ja: "娘: どうすれば?", label_en: "Daughter: what should I do?" },
  { id: "contact-account", who: "contact", language: "ja", text: "口座番号を教えてください", en: "Tell me the account number.", label_ja: "娘: 口座番号は?", label_en: "Daughter: account number?" },
  {
    id: "contact-on-way",
    who: "contact",
    language: "ja",
    text: "今から向かいます。20分くらいで着きます",
    en: "I'm on my way, about 20 minutes.",
    label_ja: "娘: 今から向かう",
    label_en: "Daughter: on my way",
  },
  { id: "contact-branch", who: "contact", language: "ja", text: "すぐ支店に行きます", en: "I'm coming to the branch right away.", label_ja: "娘: すぐ支店へ", label_en: "Daughter: coming to the branch" },
  { id: "en-cust-renovation", who: "customer", language: "en", text: "It's for my home renovation.", en: "It's for my home renovation.", label_ja: "お客様: リフォーム", label_en: "Customer: home renovation" },
  {
    id: "en-cust-police",
    who: "customer",
    language: "en",
    text: "The police called me and told me not to tell anyone, not even my family.",
    en: "The police called me and told me not to tell anyone, not even my family.",
    label_ja: "お客様: 警察から電話",
    label_en: "Customer: police called, keep it secret",
  },
  {
    id: "en-cust-contractor",
    who: "customer",
    language: "en",
    text: "I've met the contractor several times since last month and I have a written quote.",
    en: "I've met the contractor several times since last month and I have a written quote.",
    label_ja: "お客様: 業者と面談済み",
    label_en: "Customer: met the contractor, have a quote",
  },
  {
    id: "en-cust-grandson",
    who: "customer",
    language: "en",
    text: "It's my grandson's school entrance fee. My daughter and I did the paperwork at the school.",
    en: "It's my grandson's school entrance fee. My daughter and I did the paperwork at the school.",
    label_ja: "お客様: 孫の入学金",
    label_en: "Customer: grandson's entrance fee",
  },
  { id: "en-contact-what", who: "contact", language: "en", text: "What happened?", en: "What happened?", label_ja: "娘: 何があった?", label_en: "Daughter: what happened?" },
  { id: "en-contact-safe", who: "contact", language: "en", text: "Is my mother safe?", en: "Is my mother safe?", label_ja: "娘: 母は大丈夫?", label_en: "Daughter: is my mother safe?" },
  { id: "en-contact-amount", who: "contact", language: "en", text: "How much is the transfer?", en: "How much is the transfer?", label_ja: "娘: 金額は?", label_en: "Daughter: how much?" },
  { id: "en-contact-what-do", who: "contact", language: "en", text: "What should I do?", en: "What should I do?", label_ja: "娘: どうすれば?", label_en: "Daughter: what should I do?" },
  { id: "en-contact-account", who: "contact", language: "en", text: "Tell me the account number.", en: "Tell me the account number.", label_ja: "娘: 口座番号は?", label_en: "Daughter: account number?" },
  { id: "en-contact-on-way", who: "contact", language: "en", text: "I'm on my way, about twenty minutes.", en: "I'm on my way, about twenty minutes.", label_ja: "娘: 今から向かう", label_en: "Daughter: on my way" },
  { id: "en-contact-branch", who: "contact", language: "en", text: "I'm coming to the branch right away.", en: "I'm coming to the branch right away.", label_ja: "娘: すぐ支店へ", label_en: "Daughter: coming to the branch" },
];

/** English for `text` when it equals a demo line, or is a substring of exactly one (card quotes are substrings). */
export function glossFor(text: string): string | undefined {
  const t = text.trim();
  if (t.length < 2) return undefined;
  const japanese = DEMO_LINES.filter((l) => l.language === "ja"); // an English line needs no gloss
  const exact = japanese.find((l) => l.text === t);
  if (exact) return exact.en;
  const hits = japanese.filter((l) => l.text.includes(t));
  return hits.length === 1 ? hits[0].en : undefined;
}
