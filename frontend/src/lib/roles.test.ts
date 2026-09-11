import { describe, expect, it } from "vitest";
import { roleHomePath, roleNotificationsPath } from "./roles";

describe("roleHomePath", () => {
  it("sends an admin to /admin regardless of other roles", () => {
    expect(roleHomePath(["client", "admin"])).toBe("/admin");
  });

  it("sends any specialized admin role to /admin", () => {
    expect(roleHomePath(["admin_kyc"])).toBe("/admin");
    expect(roleHomePath(["admin_support"])).toBe("/admin");
    expect(roleHomePath(["admin_finance"])).toBe("/admin");
    expect(roleHomePath(["admin_marketplace"])).toBe("/admin");
    expect(roleHomePath(["admin_delivery"])).toBe("/admin");
    expect(roleHomePath(["super_admin"])).toBe("/admin");
  });

  it("sends a merchant to /merchant", () => {
    expect(roleHomePath(["merchant"])).toBe("/merchant");
  });

  it("sends a driver to /driver-dashboard", () => {
    expect(roleHomePath(["driver"])).toBe("/driver-dashboard");
  });

  it("prioritizes admin over merchant and driver", () => {
    expect(roleHomePath(["driver", "merchant", "admin"])).toBe("/admin");
  });

  it("prioritizes merchant over driver", () => {
    expect(roleHomePath(["driver", "merchant"])).toBe("/merchant");
  });

  it("defaults a plain client (or no roles) to /home", () => {
    expect(roleHomePath(["client"])).toBe("/home");
    expect(roleHomePath([])).toBe("/home");
  });
});

describe("roleNotificationsPath", () => {
  it("sends an admin to /admin-notifications regardless of other roles", () => {
    expect(roleNotificationsPath(["driver", "merchant", "admin"])).toBe("/admin-notifications");
  });

  it("sends a specialized admin to /admin-notifications", () => {
    expect(roleNotificationsPath(["admin_finance"])).toBe("/admin-notifications");
    expect(roleNotificationsPath(["admin_kyc"])).toBe("/admin-notifications");
  });

  it("sends a merchant to /merchant-notifications", () => {
    expect(roleNotificationsPath(["merchant"])).toBe("/merchant-notifications");
  });

  it("sends a driver to /driver-notifications", () => {
    expect(roleNotificationsPath(["driver"])).toBe("/driver-notifications");
  });

  it("defaults a plain client (or no roles) to /notifications", () => {
    expect(roleNotificationsPath(["client"])).toBe("/notifications");
    expect(roleNotificationsPath([])).toBe("/notifications");
  });
});
