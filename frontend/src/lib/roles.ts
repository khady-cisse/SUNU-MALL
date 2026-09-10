import type { Role } from "@/store/authStore";

export function roleHomePath(roles: Role[]): string {
  if (roles.includes("admin")) return "/admin";
  if (roles.includes("merchant")) return "/merchant";
  if (roles.includes("driver")) return "/driver-dashboard";
  if (roles.includes("partner")) return "/partner";
  return "/home";
}

export function roleNotificationsPath(roles: Role[]): string {
  if (roles.includes("admin")) return "/admin-notifications";
  if (roles.includes("merchant")) return "/merchant-notifications";
  if (roles.includes("driver")) return "/driver-notifications";
  if (roles.includes("partner")) return "/partner-notifications";
  return "/notifications";
}
