import { describe, expect, it } from "vitest";
import {
  daysUntil,
  findPlanForSubscription,
  formatDateOnly,
  isActiveStatus,
  periodSuffix,
  PLAN_BLURB,
  PLAN_LABEL,
  planLabel,
  productLimitLabel,
  productsRemaining,
} from "./subscriptions";
import type { SubscriptionPlan } from "@/types";

describe("planLabel", () => {
  it("maps the three known codes", () => {
    expect(planLabel("STARTER")).toBe("Starter");
    expect(planLabel("PRO")).toBe("Pro");
    expect(planLabel("BUSINESS")).toBe("Business");
  });

  it("falls back to the raw name for unknown codes", () => {
    expect(planLabel("GOLD")).toBe("GOLD");
  });

  it("labels all three plans", () => {
    expect(Object.keys(PLAN_LABEL)).toEqual(["STARTER", "PRO", "BUSINESS"]);
  });
});

describe("PLAN_BLURB", () => {
  it("covers the three plans", () => {
    expect(Object.keys(PLAN_BLURB)).toEqual(["STARTER", "PRO", "BUSINESS"]);
  });
});

describe("productLimitLabel", () => {
  it("shows unlimited for null", () => {
    expect(productLimitLabel(null)).toBe("Produits illimités");
    expect(productLimitLabel(undefined)).toBe("Produits illimités");
  });

  it("shows the count for finite limits", () => {
    expect(productLimitLabel(20)).toBe("20 produits");
    expect(productLimitLabel(100)).toBe("100 produits");
  });
});

describe("isActiveStatus", () => {
  it("only returns true for an active status", () => {
    expect(isActiveStatus("active")).toBe(true);
    expect(isActiveStatus("pending")).toBe(false);
    expect(isActiveStatus("expired")).toBe(false);
    expect(isActiveStatus("suspended")).toBe(false);
    expect(isActiveStatus(undefined)).toBe(false);
  });
});

describe("daysUntil", () => {
  it("returns 0 for null/undefined/expired", () => {
    expect(daysUntil(null)).toBe(0);
    expect(daysUntil(undefined)).toBe(0);
  });

  it("returns a positive count for a future date", () => {
    const future = new Date();
    future.setDate(future.getDate() + 3);
    const d = daysUntil(future.toISOString());
    expect(d).toBeGreaterThanOrEqual(2);
    expect(d).toBeLessThanOrEqual(4);
  });
});

describe("formatDateOnly", () => {
  it("formats a date in long French form", () => {
    const s = formatDateOnly("2026-10-15");
    expect(s).toContain("octobre");
    expect(s).toContain("2026");
  });
});

describe("periodSuffix", () => {
  it("returns the monthly and yearly suffixes", () => {
    expect(periodSuffix("yearly")).toBe("/ an");
    expect(periodSuffix("monthly")).toBe(" / mois");
    expect(periodSuffix(undefined)).toBe(" / mois");
  });
});

describe("findPlanForSubscription", () => {
  const plans: SubscriptionPlan[] = [
    {
      id: "p1", code: "STARTER", name: "STARTER", price: "2500", billing_cycle: "monthly",
      features: {}, max_products: 20, commission_rate: "0.00", duration_days: 30, is_active: true, created_at: "",
    },
    {
      id: "p2", code: "PRO", name: "PRO", price: "5000", billing_cycle: "monthly",
      features: {}, max_products: 100, commission_rate: "0.00", duration_days: 30, is_active: true, created_at: "",
    },
  ];

  it("finds the plan matching the subscription", () => {
    expect(findPlanForSubscription(plans, "p2")?.name).toBe("PRO");
  });

  it("returns null when nothing matches", () => {
    expect(findPlanForSubscription(plans, "unknown")).toBeNull();
    expect(findPlanForSubscription(undefined, "p1")).toBeNull();
  });
});

describe("productsRemaining", () => {
  it("returns null for unlimited plans", () => {
    expect(productsRemaining(50, null)).toBeNull();
  });

  it("computes remaining products", () => {
    expect(productsRemaining(87, 100)).toBe(13);
  });

  it("never goes negative", () => {
    expect(productsRemaining(120, 100)).toBe(0);
  });
});
