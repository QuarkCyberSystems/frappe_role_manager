"""VIEW API - Consolidated Permission Viewer.

Provides a single view of all permissions for a user, including:
- Assigned Roles
- Effective DocPerms (from all roles combined)
- User Permissions (document-level filters)
- Role Profile
- Module Profile
"""

import frappe
from frappe import _


@frappe.whitelist()
def get_user_permissions_view(user):
	"""Get consolidated permission view for a user.

	Args:
	    user: The user email/ID to get permissions for

	Returns:
	    dict: Consolidated permission data
	"""
	if not frappe.db.exists("User", user):
		frappe.throw(_("User {0} does not exist").format(user))

	user_doc = frappe.get_doc("User", user)

	return {
		"user": user,
		"user_name": user_doc.full_name,
		"enabled": user_doc.enabled,
		"roles": get_user_roles(user),
		"role_profile": get_role_profile(user_doc),
		"module_profile": get_module_profile(user_doc),
		"effective_permissions": get_effective_permissions(user),
		"user_permissions": get_user_permission_filters(user),
		"permission_summary": get_permission_summary(user),
	}


def get_user_roles(user):
	"""Get all roles assigned to a user."""
	roles = frappe.get_all("Has Role", filters={"parent": user, "parenttype": "User"}, fields=["role"], order_by="role")
	return [r.role for r in roles]


def get_role_profile(user_doc):
	"""Get role profile details if assigned."""
	if not user_doc.role_profile_name:
		return None

	profile = frappe.get_doc("Role Profile", user_doc.role_profile_name)
	return {"name": profile.name, "roles": [r.role for r in profile.roles]}


def get_module_profile(user_doc):
	"""Get module profile details if assigned."""
	if not user_doc.module_profile:
		return None

	profile = frappe.get_doc("Module Profile", user_doc.module_profile)
	return {"name": profile.name, "blocked_modules": [m.module for m in profile.block_modules]}


def get_effective_permissions(user):
	"""Get effective permissions for all DocTypes based on user's roles.

	Returns a dict of DocType -> permission flags
	"""
	roles = get_user_roles(user)
	if not roles:
		return {}

	# Get all DocPerms for user's roles
	docperms = frappe.get_all(
		"DocPerm",
		filters={"role": ["in", roles], "permlevel": 0},
		fields=[
			"parent as doctype",
			"role",
			"read",
			"write",
			"create",
			"delete",
			"submit",
			"cancel",
			"amend",
			"report",
			"export",
			"import",
			"share",
			"print",
			"email",
		],
	)

	# Aggregate permissions by DocType (OR logic - if any role has permission, user has it)
	permissions = {}
	for dp in docperms:
		doctype = dp.doctype
		if doctype not in permissions:
			permissions[doctype] = {
				"doctype": doctype,
				"read": 0,
				"write": 0,
				"create": 0,
				"delete": 0,
				"submit": 0,
				"cancel": 0,
				"amend": 0,
				"report": 0,
				"export": 0,
				"import": 0,
				"share": 0,
				"print": 0,
				"email": 0,
				"roles": [],
			}

		# OR the permission flags
		for perm in ["read", "write", "create", "delete", "submit", "cancel", "amend", "report", "export", "import", "share", "print", "email"]:
			if dp.get(perm):
				permissions[doctype][perm] = 1

		if dp.role not in permissions[doctype]["roles"]:
			permissions[doctype]["roles"].append(dp.role)

	return permissions


def get_user_permission_filters(user):
	"""Get all User Permission records for a user."""
	user_perms = frappe.get_all(
		"User Permission",
		filters={"user": user},
		fields=["allow", "for_value", "applicable_for", "apply_to_all_doctypes", "name"],
		order_by="allow",
	)

	# Group by allow DocType
	grouped = {}
	for up in user_perms:
		allow = up.allow
		if allow not in grouped:
			grouped[allow] = []
		grouped[allow].append(
			{
				"for_value": up.for_value,
				"applicable_for": up.applicable_for,
				"apply_to_all_doctypes": up.apply_to_all_doctypes,
				"name": up.name,
			}
		)

	return grouped


def get_permission_summary(user):
	"""Get a summary of user's permission coverage."""
	roles = get_user_roles(user)
	effective_perms = get_effective_permissions(user)
	user_perms = frappe.db.count("User Permission", {"user": user})

	# Count DocTypes by permission type
	can_read = sum(1 for p in effective_perms.values() if p.get("read"))
	can_write = sum(1 for p in effective_perms.values() if p.get("write"))
	can_create = sum(1 for p in effective_perms.values() if p.get("create"))
	can_delete = sum(1 for p in effective_perms.values() if p.get("delete"))

	return {
		"total_roles": len(roles),
		"total_doctypes_accessible": len(effective_perms),
		"can_read": can_read,
		"can_write": can_write,
		"can_create": can_create,
		"can_delete": can_delete,
		"user_permission_count": user_perms,
	}


@frappe.whitelist()
def get_all_roles():
	"""Get list of all roles in the system."""
	roles = frappe.get_all(
		"Role",
		filters={"disabled": 0, "name": ["not in", ["Administrator", "Guest", "All"]]},
		fields=["name", "desk_access", "is_custom"],
		order_by="name",
	)
	return roles


@frappe.whitelist()
def get_all_users(filters=None):
	"""Get list of all users with basic info."""
	user_filters = {"enabled": 1, "name": ["not in", ["Administrator", "Guest"]]}

	if filters:
		if isinstance(filters, str):
			import json

			filters = json.loads(filters)
		user_filters.update(filters)

	users = frappe.get_all(
		"User",
		filters=user_filters,
		fields=["name", "full_name", "email", "role_profile_name", "module_profile", "user_type"],
		order_by="full_name asc, name asc",
	)

	# Add role count for each user and ensure full_name is set
	for user in users:
		user["role_count"] = frappe.db.count("Has Role", {"parent": user.name, "parenttype": "User"})
		# Use name (email) if full_name is empty
		if not user.get("full_name"):
			user["full_name"] = user.name

	return users


@frappe.whitelist()
def get_role_permissions(role):
	"""Get all permissions for a specific role."""
	if not frappe.db.exists("Role", role):
		frappe.throw(_("Role {0} does not exist").format(role))

	docperms = frappe.get_all(
		"DocPerm",
		filters={"role": role, "permlevel": 0},
		fields=[
			"parent as doctype",
			"read",
			"write",
			"create",
			"delete",
			"submit",
			"cancel",
			"amend",
			"report",
			"export",
			"import",
			"share",
			"print",
			"email",
		],
		order_by="parent",
	)

	return docperms


@frappe.whitelist()
def get_doctype_permissions(doctype):
	"""Get all role permissions for a specific DocType."""
	if not frappe.db.exists("DocType", doctype):
		frappe.throw(_("DocType {0} does not exist").format(doctype))

	docperms = frappe.get_all(
		"DocPerm",
		filters={"parent": doctype, "permlevel": 0},
		fields=[
			"role",
			"read",
			"write",
			"create",
			"delete",
			"submit",
			"cancel",
			"amend",
			"report",
			"export",
			"import",
			"share",
			"print",
			"email",
			"if_owner",
		],
		order_by="role",
	)

	return docperms


@frappe.whitelist()
def get_users_with_role(role):
	"""Get all users who have a specific role."""
	if not frappe.db.exists("Role", role):
		frappe.throw(_("Role {0} does not exist").format(role))

	users = frappe.get_all(
		"Has Role",
		filters={"role": role, "parenttype": "User"},
		fields=["parent as user"],
	)

	user_list = [u.user for u in users]

	# Get user details
	if user_list:
		user_details = frappe.get_all(
			"User",
			filters={"name": ["in", user_list]},
			fields=["name", "full_name", "enabled"],
		)
		return user_details

	return []


@frappe.whitelist()
def get_users_with_permission(allow, for_value):
	"""Get all users who have a specific user permission."""
	user_perms = frappe.get_all(
		"User Permission",
		filters={"allow": allow, "for_value": for_value},
		fields=["user"],
	)

	user_list = [u.user for u in user_perms]

	if user_list:
		user_details = frappe.get_all(
			"User",
			filters={"name": ["in", user_list]},
			fields=["name", "full_name", "enabled"],
		)
		return user_details

	return []
