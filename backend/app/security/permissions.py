"""Role → permission mapping and the authenticated `Principal`.

Permissions are coarse strings `<resource>:<verb>`. Plugin actions declare the permission
they need; the Plugin Manager checks it against the caller's principal on every call.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.enums import Role

ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.CUSTOMER: frozenset(
        {
            "catalog:read",
            "cart:write",
            "order:own",
            "payment:own",
            "return:own",
            "shipment:own",
            "support:use",
            "notify:self",
        }
    ),
    Role.SUPPORT_AGENT: frozenset(
        {
            "catalog:read",
            "order:own",
            "order:read_all",
            "return:own",
            "return:manage",
            "shipment:own",
            "shipment:read_all",
            "support:use",
            "support:manage",
            "notify:self",
            "notify:any",
            "payment:read_all",
        }
    ),
    Role.INVENTORY_MANAGER: frozenset(
        {
            "catalog:read",
            "catalog:write",
            "inventory:read",
            "inventory:write",
            "analytics:inventory",
        }
    ),
    Role.ADMIN: frozenset({"*"}),
    Role.SYSTEM: frozenset({"*"}),
}


@dataclass(frozen=True)
class Principal:
    user_id: int | None
    email: str
    roles: frozenset[Role] = field(default_factory=frozenset)
    name: str = ""

    @property
    def permissions(self) -> frozenset[str]:
        perms: set[str] = set()
        for r in self.roles:
            perms |= ROLE_PERMISSIONS.get(r, frozenset())
        return frozenset(perms)

    def has(self, permission: str) -> bool:
        perms = self.permissions
        if "*" in perms or permission in perms:
            return True
        resource = permission.split(":", 1)[0]
        return f"{resource}:*" in perms

    def has_any_role(self, *roles: Role) -> bool:
        return bool(self.roles & set(roles))

    @property
    def is_staff(self) -> bool:
        return self.has_any_role(Role.ADMIN, Role.SUPPORT_AGENT, Role.INVENTORY_MANAGER, Role.SYSTEM)

    def can_access_user_resource(self, owner_id: int | None, read_all_permission: str) -> bool:
        return (owner_id is not None and owner_id == self.user_id) or self.has(read_all_permission)


SYSTEM_PRINCIPAL = Principal(user_id=None, email="system@nextbot.local", roles=frozenset({Role.SYSTEM}), name="system")
