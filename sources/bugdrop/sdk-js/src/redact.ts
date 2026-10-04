// Client-side PII redaction (the BugDrop service redacts again server-side).
const EMAIL = /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g;
const JWT = /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g;
const SECRET = /\b(bearer|token|api[_-]?key|secret|password|authorization)\b(["']?\s*[:=]\s*["']?|\s+)([A-Za-z0-9._~+/=-]{8,})/gi;
const PHONE = /(?<![\w.])(?:\+\d{1,3}[\s.-]?\(?\d{1,4}\)?(?:[\s.-]?\d{2,4}){2,3}|\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}|\d{10})(?![\w.])/g;
const CARD = /\b\d(?:[ -]?\d){12,18}\b/g;

function luhn(digits: string): boolean {
  let sum = 0;
  let alt = false;
  for (let i = digits.length - 1; i >= 0; i--) {
    let d = Number(digits[i]);
    if (alt) {
      d *= 2;
      if (d > 9) d -= 9;
    }
    sum += d;
    alt = !alt;
  }
  return sum % 10 === 0;
}

export function redactText(s: string): string {
  return s
    .replace(JWT, "[token]")
    .replace(SECRET, (_m, k: string, sep: string) => `${k}${sep}[token]`)
    .replace(EMAIL, "[email]")
    .replace(CARD, (m) => (luhn(m.replace(/\D/g, "")) ? "[card]" : m))
    .replace(PHONE, "[phone]");
}

export function redactDeep<T>(v: T): T {
  if (typeof v === "string") return redactText(v) as T;
  if (Array.isArray(v)) return v.map((x) => redactDeep(x)) as T;
  if (v && typeof v === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, x] of Object.entries(v as Record<string, unknown>)) {
      out[k] = ["lat", "lng", "latitude", "longitude"].includes(k) && typeof x === "number" ? Math.round(x * 100) / 100 : redactDeep(x);
    }
    return out as T;
  }
  return v;
}
