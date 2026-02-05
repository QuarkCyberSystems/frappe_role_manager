"""COMPARE API - Compare Permissions Between Users/Roles.

Allows comparing:
- Two users (roles, user permissions, effective access)
- Two roles (DocType permissions)
- User vs Role (what would change if user gets the role)
"""

import frappe
from frappe import _


@frappe.whitelist()
def compare_users(user_a, user_b):
	"""Compare permissions between two users.

	Args:
	    user_a: First user
	    user_b: Second user

	Returns:
	    dict: Detailed comparison
	"""
	if not frappe.db.exists("User", user_a):
		frappe.throw(_("User {0} does not exist").format(user_a))
	if not frappe.db.exists("User", user_b):
		frappe.throw(_("User {0} does not exist").format(user_b))

	user_a_doc = frappe.get_doc("User", user_a)
	user_b_doc = frappe.get_doc("User", user_b)

	comparison = {
		"user_a": {"name": user_a, "full_name": user_a_doc.full_name},
		"user_b": {"name": user_b, "full_name": user_b_doc.full_name},
		"roles": _compare_roles(user_a, user_b),
		"user_permissions": _compare_user_permissions(user_a, user_b),
		"effective_permissions": _compare_effective_permissions(user_a, user_b),
		"profiles": _compare_profiles(user_a_doc, user_b_doc),
	}

	# Summary
	comparison["summary"] = {
		"roles_only_a": len(comparison["roles"]["only_a"]),
		"roles_only_b": len(comparison["roles"]["only_b"]),
		"roles_common": len(comparison["roles"]["common"]),
		"user_perms_only_a": len(comparison["user_permissions"]["only_a"]),
		"user_perms_only_b": len(comparison["user_permissions"]["only_b"]),
		"user_perms_common": len(comparison["user_permissions"]["common"]),
		"effective_perms_only_a": len(comparison["effective_permissions"]["only_a"]),
		"effective_perms_only_b": len(comparison["effective_permissions"]["only_b"]),
		"effective_perms_different": len(comparison["effective_permissions"]["different"]),
	}

	comparison["similarity_score"] = _calculate_similarity(comparison)

	return comparison


@frappe.whitelist()
def compare_roles(role_a, role_b):
	"""Compare permissions between two roles.

	Args:
	    role_a: First role
	    role_b: Second role

	Returns:
	    dict: Detailed comparison
	"""
	if not frappe.db.exists("Role", role_a):
		frappe.throw(_("Role {0} does not exist").format(role_a))
	if not frappe.db.exists("Role", role_b):
		frappe.throw(_("Role {0} does not exist").format(role_b))

	# Get permissions for both roles
	perms_a = _get_role_docperms(role_a)
	perms_b = _get_role_docperms(role_b)

	doctypes_a = set(perms_a.keys())
	doctypes_b = set(perms_b.keys())

	comparison = {
		"role_a": role_a,
		"role_b": role_b,
		"doctypes": {
			"only_a": list(doctypes_a - doctypes_b),
			"only_b": list(doctypes_b - doctypes_a),
			"common": list(doctypes_a & doctypes_b),
		},
		"permission_differences": [],
	}

	# Compare permissions for common DocTypes
	for doctype in doctypes_a & doctypes_b:
		perm_a = perms_a[doctype]
		perm_b = perms_b[doctype]

		differences = []
		for field in ["read", "write", "create", "delete", "submit", "cancel", "amend", "report", "export", "import", "share", "print", "email"]:
			if perm_a.get(field) != perm_b.get(field):
				differences.append({"field": field, "role_a": perm_a.get(field), "role_b": perm_b.get(field)})

		if differences:
			comparison["permission_differences"].append({"doctype": doctype, "differences": differences})

	# Summary
	comparison["summary"] = {
		"doctypes_only_a": len(comparison["doctypes"]["only_a"]),
		"doctypes_only_b": len(comparison["doctypes"]["only_b"]),
		"doctypes_common": len(comparison["doctypes"]["common"]),
		"doctypes_with_differences": len(comparison["permission_differences"]),
	}

	return comparison


@frappe.whitelist()
def compare_user_to_role(user, role):
	"""Compare user's current access to what they would have with a role.

	Args:
	    user: User to compare
	    role: Role to compare against

	Returns:
	    dict: What would change if user gets the role
	"""
	if not frappe.db.exists("User", user):
		frappe.throw(_("User {0} does not exist").format(user))
	if not frappe.db.exists("Role", role):
		frappe.throw(_("Role {0} does not exist").format(role))

	# Check if user already has the role
	has_role = frappe.db.exists("Has Role", {"parent": user, "parenttype": "User", "role": role})

	# Get user's current effective permissions
	current_perms = _get_user_effective_permissions(user)

	# Get role's permissions
	role_perms = _get_role_docperms(role)

	comparison = {
		"user": user,
		"role": role,
		"already_has_role": bool(has_role),
		"new_access": [],
		"enhanced_access": [],
		"no_change": [],
	}

	for doctype, role_perm in role_perms.items():
		current_perm = current_perms.get(doctype, {})

		new_permissions = []
		enhanced_permissions = []

		for field in ["read", "write", "create", "delete", "submit", "cancel", "amend", "report", "export", "import", "share", "print", "email"]:
			role_has = role_perm.get(field, 0)
			user_has = current_perm.get(field, 0)

			if role_has and not user_has:
				if doctype not in current_perms:
					new_permissions.append(field)
				else:
					enhanced_permissions.append(field)

		if new_permissions:
			comparison["new_access"].append({"doctype": doctype, "permissions": new_permissions})
		elif enhanced_permissions:
			comparison["enhanced_access"].append({"doctype": doctype, "permissions": enhanced_permissions})
		elif doctype in current_perms:
			comparison["no_change"].append(doctype)

	# Summary
	comparison["summary"] = {
		"new_doctypes": len(comparison["new_access"]),
		"enhanced_doctypes": len(comparison["enhanced_access"]),
		"no_change_doctypes": len(comparison["no_change"]),
	}

	return comparison


@frappe.whitelist()
def find_similar_users(user, threshold=70):
	"""Find users with similar permissions to the given user.

	Args:
	    user: User to find similar users for
	    threshold: Minimum similarity percentage (0-100)

	Returns:
	    list: Similar users with similarity scores
	"""
	if not frappe.db.exists("User", user):
		frappe.throw(_("User {0} does not exist").format(user))

	threshold = int(threshold)

	# Get all other users
	all_users = frappe.get_all(
		"User",
		filters={"enabled": 1, "name": ["not in", [user, "Administrator", "Guest"]]},
		fields=["name", "full_name"],
	)

	similar_users = []

	for other_user in all_users:
		try:
			comparison = compare_users(user, other_user.name)
			similarity = comparison.get("similarity_score", 0)

			if similarity >= threshold:
				similar_users.append({
					"user": other_user.name,
					"full_name": other_user.full_name,
					"similarity": similarity,
					"common_roles": comparison["roles"]["common"],
					"different_roles": {
						"only_in_source": comparison["roles"]["only_a"],
						"only_in_target": comparison["roles"]["only_b"],
					},
				})
		except Exception:
			continue

	# Sort by similarity (descending)
	similar_users.sort(key=lambda x: x["similarity"], reverse=True)

	return similar_users


@frappe.whitelist()
def find_users_with_same_roles(user):
	"""Find users with exactly the same roles as the given user.

	Args:
	    user: User to match

	Returns:
	    list: Users with identical role sets
	"""
	if not frappe.db.exists("User", user):
		frappe.throw(_("User {0} does not exist").format(user))

	# Get user's roles
	user_roles = set(
		r.role
		for r in frappe.get_all("Has Role", filters={"parent": user, "parenttype": "User"}, fields=["role"])
	)

	if not user_roles:
		return []

	# Get all other users
	all_users = frappe.get_all(
		"User",
		filters={"enabled": 1, "name": ["not in", [user, "Administrator", "Guest"]]},
		fields=["name", "full_name"],
	)

	matching_users = []

	for other_user in all_users:
		other_roles = set(
			r.role
			for r in frappe.get_all(
				"Has Role", filters={"parent": other_user.name, "parenttype": "User"}, fields=["role"]
			)
		)

		if user_roles == other_roles:
			matching_users.append({"user": other_user.name, "full_name": other_user.full_name, "roles": list(user_roles)})

	return matching_users


def _compare_roles(user_a, user_b):
	"""Compare roles between two users."""
	roles_a = set(
		r.role
		for r in frappe.get_all("Has Role", filters={"parent": user_a, "parenttype": "User"}, fields=["role"])
	)
	roles_b = set(
		r.role
		for r in frappe.get_all("Has Role", filters={"parent": user_b, "parenttype": "User"}, fields=["role"])
	)

	return {"only_a": list(roles_a - roles_b), "only_b": list(roles_b - roles_a), "common": list(roles_a & roles_b)}


def _compare_user_permissions(user_a, user_b):
	"""Compare user permissions between two users."""
	perms_a = frappe.get_all(
		"User Permission", filters={"user": user_a}, fields=["allow", "for_value"]
	)
	perms_b = frappe.get_all(
		"User Permission", filters={"user": user_b}, fields=["allow", "for_value"]
	)

	set_a = set((p.allow, p.for_value) for p in perms_a)
	set_b = set((p.allow, p.for_value) for p in perms_b)

	return {
		"only_a": [{"allow": p[0], "for_value": p[1]} for p in (set_a - set_b)],
		"only_b": [{"allow": p[0], "for_value": p[1]} for p in (set_b - set_a)],
		"common": [{"allow": p[0], "for_value": p[1]} for p in (set_a & set_b)],
	}


def _compare_effective_permissions(user_a, user_b):
	"""Compare effective permissions (from roles) between two users."""
	perms_a = _get_user_effective_permissions(user_a)
	perms_b = _get_user_effective_permissions(user_b)

	doctypes_a = set(perms_a.keys())
	doctypes_b = set(perms_b.keys())

	result = {
		"only_a": list(doctypes_a - doctypes_b),
		"only_b": list(doctypes_b - doctypes_a),
		"common": list(doctypes_a & doctypes_b),
		"different": [],
	}

	# Check for differences in common DocTypes
	for doctype in doctypes_a & doctypes_b:
		perm_a = perms_a[doctype]
		perm_b = perms_b[doctype]

		differences = []
		for field in ["read", "write", "create", "delete", "submit", "cancel", "amend"]:
			if perm_a.get(field) != perm_b.get(field):
				differences.append({"field": field, "user_a": perm_a.get(field), "user_b": perm_b.get(field)})

		if differences:
			result["different"].append({"doctype": doctype, "differences": differences})

	return result


def _compare_profiles(user_a_doc, user_b_doc):
	"""Compare role and module profiles between two users."""
	return {
		"role_profile": {
			"user_a": user_a_doc.role_profile_name,
			"user_b": user_b_doc.role_profile_name,
			"same": user_a_doc.role_profile_name == user_b_doc.role_profile_name,
		},
		"module_profile": {
			"user_a": user_a_doc.module_profile,
			"user_b": user_b_doc.module_profile,
			"same": user_a_doc.module_profile == user_b_doc.module_profile,
		},
	}


def _get_user_effective_permissions(user):
	"""Get effective permissions for a user based on their roles."""
	roles = [
		r.role
		for r in frappe.get_all("Has Role", filters={"parent": user, "parenttype": "User"}, fields=["role"])
	]

	if not roles:
		return {}

	docperms = frappe.get_all(
		"DocPerm",
		filters={"role": ["in", roles], "permlevel": 0},
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
	)

	# Aggregate by DocType (OR logic)
	permissions = {}
	for dp in docperms:
		doctype = dp.doctype
		if doctype not in permissions:
			permissions[doctype] = {}

		for perm in ["read", "write", "create", "delete", "submit", "cancel", "amend", "report", "export", "import", "share", "print", "email"]:
			if dp.get(perm):
				permissions[doctype][perm] = 1

	return permissions


def _get_role_docperms(role):
	"""Get all DocPerms for a role."""
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
	)

	return {dp.doctype: dp for dp in docperms}


def _calculate_similarity(comparison):
	"""Calculate overall similarity percentage between two users."""
	# Weight different aspects
	role_weight = 0.5
	user_perm_weight = 0.3
	effective_perm_weight = 0.2

	# Role similarity
	roles_common = len(comparison["roles"]["common"])
	roles_total = roles_common + len(comparison["roles"]["only_a"]) + len(comparison["roles"]["only_b"])
	role_sim = (roles_common / roles_total * 100) if roles_total > 0 else 100

	# User permission similarity
	up_common = len(comparison["user_permissions"]["common"])
	up_total = up_common + len(comparison["user_permissions"]["only_a"]) + len(comparison["user_permissions"]["only_b"])
	up_sim = (up_common / up_total * 100) if up_total > 0 else 100

	# Effective permission similarity
	ep_common = len(comparison["effective_permissions"]["common"])
	ep_different = len(comparison["effective_permissions"]["different"])
	ep_only_a = len(comparison["effective_permissions"]["only_a"])
	ep_only_b = len(comparison["effective_permissions"]["only_b"])
	ep_total = ep_common + ep_only_a + ep_only_b
	# Penalize for differences in common DocTypes
	ep_sim = ((ep_common - ep_different) / ep_total * 100) if ep_total > 0 else 100
	ep_sim = max(0, ep_sim)

	# Weighted average
	similarity = role_weight * role_sim + user_perm_weight * up_sim + effective_perm_weight * ep_sim

	return round(similarity, 1)
