import { describe, expect, it } from "vitest";
import { cn, formatPrice, formatDate, formatEta } from "./utils";

describe("cn", () => {
  it("merges class names and drops falsy values", () => {
    expect(cn("a", false, "b", undefined, "c")).toBe("a b c");
  });
});

describe("formatPrice", () => {
  it("formats a numeric amount as XOF currency", () => {
    const result = formatPrice(6000);
    expect(result).toContain("6");
    expect(result).toMatch(/XOF|CFA/);
  });

  it("parses a string amount the same way as a number", () => {
    expect(formatPrice("6000")).toBe(formatPrice(6000));
  });

  it("has no decimal places (whole XOF amounts)", () => {
    const result = formatPrice(1234.5);
    expect(result).not.toContain(".5");
    expect(result).not.toContain(",5");
  });
});

describe("formatDate", () => {
  it("formats an ISO date string without throwing", () => {
    expect(() => formatDate("2026-07-19T10:30:00Z")).not.toThrow();
  });

  it("produces a non-empty, human-readable string", () => {
    const result = formatDate("2026-07-19T10:30:00Z");
    expect(result.length).toBeGreaterThan(0);
  });
});

describe("formatEta", () => {
  it("returns null when the ETA is missing", () => {
    expect(formatEta(null)).toBeNull();
    expect(formatEta(undefined)).toBeNull();
  });

  it("announces an imminent arrival for zero or negative", () => {
    expect(formatEta(0)).toBe("Arrivée imminente");
    expect(formatEta(-5)).toBe("Arrivée imminente");
  });

  it("rounds up to whole minutes", () => {
    expect(formatEta(30)).toBe("~1 min");
    expect(formatEta(120)).toBe("~2 min");
    expect(formatEta(749)).toBe("~13 min");
  });
});
