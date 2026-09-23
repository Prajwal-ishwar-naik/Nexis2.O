/**
 * Client-Side Privacy Redaction Guardrails
 * Redacts 12-digit Indian Aadhaar numbers, Korean Resident Registration Numbers (RRN),
 * and Japanese MyNumber / Generic National IDs into standardized privacy placeholders.
 */
export function redactSensitiveIdentifiers(text) {
  if (!text || typeof text !== 'string') return text || '';

  // 1. 12-digit Indian Aadhaar (e.g., "1234 5678 9012" or "123456789012")
  let sanitized = text.replace(/\b\d{4}\s?\d{4}\s?\d{4}\b/g, '[Aadhaar Redacted]');

  // 2. Korean RRN (6 digits - 7 digits, e.g., "880101-1234567")
  sanitized = sanitized.replace(/\b\d{6}-[1-4]\d{6}\b/g, '[ID Redacted]');

  // 3. Japanese MyNumber / generic national ID (e.g., "MyNumber: 123456789012")
  sanitized = sanitized.replace(/\b(MyNumber|National ID)[:\s]*\d{12}\b/gi, '$1: [ID Redacted]');

  return sanitized;
}
