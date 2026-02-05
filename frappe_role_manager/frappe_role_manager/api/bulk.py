"""BULK API - Mass Assignment Operations.

Allows bulk operations:
- Assign roles to multiple users by filters (department, company, etc.)
- Remove roles from multiple users
- Assign user permissions in bulk
- Remove user permissions in bulk
"""

import json

import frappe
from frappe import _

from frappe_role_manager.frappe_role_manager.doctype.bulk_operation_log.bulk_operation_log import (
	create_operation_log,
)


@frappe.whitelist()
def get_users_by_filter(department=None, company=None, user_type=None, role=None, enabled_only=True):
	"""Get users matching the specified filters.

	Args:
	    department: Filter by department
	    company: Filter by default company
	    user_type: Filter by user type (System User, Website User, etc.)
	    role: Filter by existing role
	    enabled_only: Only include enabled users

	Returns:
	    list: Matching users
	"""
	filters = {}

	if _to_bool(enabled_only):
		filters["enabled"] = 1

	if department:
		# Get employees in department, then their users
		employees = frappe.get_all("Employee", filters={"department": department, "user_id": ["is", "set"]}, fields=["user_id"])
		user_ids = [e.user_id for e in employees]
		if not user_ids:
			return []
		filters["name"] = ["in", user_ids]

	if company:
		# Get employees in company, then their users
		employees = frappe.get_all("Employee", filters={"company": company, "user_id": ["is", "set"]}, fields=["user_id"])
		user_ids = [e.user_id for e in employees]
		if not user_ids:
			return []
		if "name" in filters:
			# Intersect with existing filter
			filters["name"] = ["in", list(set(filters["name"][1]) & set(user_ids))]
		else:
			filters["name"] = ["in", user_ids]

	if user_type:
		filters["user_type"] = user_type

	# Exclude system users
	if "name" not in filters:
		filters["name"] = ["not in", ["Administrator", "Guest"]]
	else:
		filters["name"] = ["in", [u for u in filters["name"][1] if u not in ["Administrator", "Guest"]]]

	users = frappe.get_all("User", filters=filters, fields=["name", "full_name", "email", "enabled", "user_type"])

	# Filter by role if specified
	if role:
		users_with_role = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, fields=["parent"])
		users_with_role = [u.parent for u in users_with_role]
		users = [u for u in users if u.name in users_with_role]

	return users


@frappe.whitelist()
def preview_bulk_role_assignment(role, users=None, department=None, company=None, user_type=None, action="add"):
	"""Preview bulk role assignment operation.

	Args:
	    role: Role to assign/remove
	    users: List of specific users (JSON string or list)
	    department: Assign to all users in department
	    company: Assign to all users in company
	    user_type: Assign to all users of type
	    action: 'add' or 'remove'

	Returns:
	    dict: Preview of changes
	"""
	if not frappe.db.exists("Role", role):
		frappe.throw(_("Role {0} does not exist").format(role))

	# Get target users
	if users:
		if isinstance(users, str):
			users = json.loads(users)
		target_users = frappe.get_all("User", filters={"name": ["in", users]}, fields=["name", "full_name", "enabled"])
	else:
		target_users = get_users_by_filter(department=department, company=company, user_type=user_type)

	# Check current state
	users_with_role = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, fields=["parent"])
	users_with_role = set(u.parent for u in users_with_role)

	preview = {"role": role, "action": action, "will_change": [], "already_done": [], "total_users": len(target_users)}

	for user in target_users:
		has_role = user.name in users_with_role

		if action == "add":
			if has_role:
				preview["already_done"].append({"user": user.name, "name": user.full_name, "reason": "Already has role"})
			else:
				preview["will_change"].append({"user": user.name, "name": user.full_name})
		else:  # remove
			if has_role:
				preview["will_change"].append({"user": user.name, "name": user.full_name})
			else:
				preview["already_done"].append({"user": user.name, "name": user.full_name, "reason": "Doesn't have role"})

	preview["summary"] = {"will_change": len(preview["will_change"]), "already_done": len(preview["already_done"])}

	return preview


@frappe.whitelist()
def execute_bulk_role_assignment(role, users=None, department=None, company=None, user_type=None, action="add"):
	"""Execute bulk role assignment operation.

	Args:
	    role: Role to assign/remove
	    users: List of specific users (JSON string or list)
	    department: Assign to all users in department
	    company: Assign to all users in company
	    user_type: Assign to all users of type
	    action: 'add' or 'remove'

	Returns:
	    dict: Results of the operation
	"""
	if not frappe.db.exists("Role", role):
		frappe.throw(_("Role {0} does not exist").format(role))

	# Get target users
	if users:
		if isinstance(users, str):
			users = json.loads(users)
		target_users = users
	else:
		target_users_data = get_users_by_filter(department=department, company=company, user_type=user_type)
		target_users = [u.name for u in target_users_data]

	# Create operation log
	log = create_operation_log(
		"Bulk Role Assignment" if action == "add" else "Bulk Role Removal",
		{"role": role, "users": target_users, "department": department, "company": company, "action": action},
	)
	log.mark_started()

	results = {"success": 0, "skipped": 0, "failed": 0, "errors": [], "details": []}

	try:
		for user in target_users:
			try:
				if action == "add":
					result = _add_role_to_user(user, role)
				else:
					result = _remove_role_from_user(user, role)

				if result == "success":
					results["success"] += 1
					results["details"].append({"user": user, "status": "success"})
				else:
					results["skipped"] += 1
					results["details"].append({"user": user, "status": "skipped", "reason": result})

			except Exception as e:
				results["failed"] += 1
				error_msg = f"{user}: {e!s}"
				results["errors"].append(error_msg)
				results["details"].append({"user": user, "status": "failed", "error": str(e)})

		frappe.db.commit()

		log.mark_completed(
			success_count=results["success"],
			failure_count=results["failed"],
			skipped_count=results["skipped"],
			details=results,
		)

		return {"status": "success", "results": results, "log": log.name}

	except Exception as e:
		frappe.db.rollback()
		error_msg = str(e)
		log.mark_failed(error_msg)
		return {"status": "error", "message": error_msg, "results": results, "log": log.name}


@frappe.whitelist()
def preview_bulk_user_permission(allow, for_value, users=None, department=None, company=None, action="add"):
	"""Preview bulk user permission operation.

	Args:
	    allow: The DocType to create permission for
	    for_value: The specific value to allow
	    users: List of specific users (JSON string or list)
	    department: Assign to all users in department
	    company: Assign to all users in company
	    action: 'add' or 'remove'

	Returns:
	    dict: Preview of changes
	"""
	if not frappe.db.exists("DocType", allow):
		frappe.throw(_("DocType {0} does not exist").format(allow))

	# Get target users
	if users:
		if isinstance(users, str):
			users = json.loads(users)
		target_users = frappe.get_all("User", filters={"name": ["in", users]}, fields=["name", "full_name", "enabled"])
	else:
		target_users = get_users_by_filter(department=department, company=company)

	# Check current state
	existing_perms = frappe.get_all(
		"User Permission", filters={"allow": allow, "for_value": for_value}, fields=["user"]
	)
	users_with_perm = set(p.user for p in existing_perms)

	preview = {
		"allow": allow,
		"for_value": for_value,
		"action": action,
		"will_change": [],
		"already_done": [],
		"total_users": len(target_users),
	}

	for user in target_users:
		has_perm = user.name in users_with_perm

		if action == "add":
			if has_perm:
				preview["already_done"].append({"user": user.name, "name": user.full_name, "reason": "Already has permission"})
			else:
				preview["will_change"].append({"user": user.name, "name": user.full_name})
		else:  # remove
			if has_perm:
				preview["will_change"].append({"user": user.name, "name": user.full_name})
			else:
				preview["already_done"].append({"user": user.name, "name": user.full_name, "reason": "Doesn't have permission"})

	preview["summary"] = {"will_change": len(preview["will_change"]), "already_done": len(preview["already_done"])}

	return preview


@frappe.whitelist()
def execute_bulk_user_permission(allow, for_value, users=None, department=None, company=None, action="add", apply_to_all_doctypes=True):
	"""Execute bulk user permission operation.

	Args:
	    allow: The DocType to create permission for
	    for_value: The specific value to allow
	    users: List of specific users (JSON string or list)
	    department: Assign to all users in department
	    company: Assign to all users in company
	    action: 'add' or 'remove'
	    apply_to_all_doctypes: Whether to apply to all DocTypes

	Returns:
	    dict: Results of the operation
	"""
	if not frappe.db.exists("DocType", allow):
		frappe.throw(_("DocType {0} does not exist").format(allow))

	apply_to_all_doctypes = _to_bool(apply_to_all_doctypes)

	# Get target users
	if users:
		if isinstance(users, str):
			users = json.loads(users)
		target_users = users
	else:
		target_users_data = get_users_by_filter(department=department, company=company)
		target_users = [u.name for u in target_users_data]

	# Create operation log
	log = create_operation_log(
		"Bulk User Permission Assignment",
		{"allow": allow, "for_value": for_value, "users": target_users, "action": action},
	)
	log.mark_started()

	results = {"success": 0, "skipped": 0, "failed": 0, "errors": [], "details": []}

	try:
		for user in target_users:
			try:
				if action == "add":
					result = _add_user_permission(user, allow, for_value, apply_to_all_doctypes)
				else:
					result = _remove_user_permission(user, allow, for_value)

				if result == "success":
					results["success"] += 1
					results["details"].append({"user": user, "status": "success"})
				else:
					results["skipped"] += 1
					results["details"].append({"user": user, "status": "skipped", "reason": result})

			except Exception as e:
				results["failed"] += 1
				error_msg = f"{user}: {e!s}"
				results["errors"].append(error_msg)
				results["details"].append({"user": user, "status": "failed", "error": str(e)})

		frappe.db.commit()

		log.mark_completed(
			success_count=results["success"],
			failure_count=results["failed"],
			skipped_count=results["skipped"],
			details=results,
		)

		return {"status": "success", "results": results, "log": log.name}

	except Exception as e:
		frappe.db.rollback()
		error_msg = str(e)
		log.mark_failed(error_msg)
		return {"status": "error", "message": error_msg, "results": results, "log": log.name}


@frappe.whitelist()
def get_filter_options():
	"""Get available filter options for bulk operations.

	Returns:
	    dict: Available departments, companies, user types, and roles
	"""
	departments = frappe.get_all("Department", filters={"disabled": 0}, fields=["name"], order_by="name")
	companies = frappe.get_all("Company", fields=["name"], order_by="name")
	user_types = frappe.get_all(
		"User",
		filters={"enabled": 1},
		fields=["user_type"],
		distinct=True,
	)
	roles = frappe.get_all(
		"Role", filters={"disabled": 0, "name": ["not in", ["Administrator", "Guest", "All"]]}, fields=["name"], order_by="name"
	)

	return {
		"departments": [d.name for d in departments],
		"companies": [c.name for c in companies],
		"user_types": list(set(u.user_type for u in user_types if u.user_type)),
		"roles": [r.name for r in roles],
	}


def _add_role_to_user(user, role):
	"""Add a role to a user."""
	exists = frappe.db.exists("Has Role", {"parent": user, "parenttype": "User", "role": role})

	if exists:
		return "already_exists"

	user_doc = frappe.get_doc("User", user)
	user_doc.append("roles", {"role": role})
	user_doc.save(ignore_permissions=True)
	return "success"


def _remove_role_from_user(user, role):
	"""Remove a role from a user."""
	exists = frappe.db.exists("Has Role", {"parent": user, "parenttype": "User", "role": role})

	if not exists:
		return "not_exists"

	user_doc = frappe.get_doc("User", user)
	user_doc.roles = [r for r in user_doc.roles if r.role != role]
	user_doc.save(ignore_permissions=True)
	return "success"


def _add_user_permission(user, allow, for_value, apply_to_all_doctypes=True):
	"""Add a user permission."""
	exists = frappe.db.exists("User Permission", {"user": user, "allow": allow, "for_value": for_value})

	if exists:
		return "already_exists"

	doc = frappe.new_doc("User Permission")
	doc.user = user
	doc.allow = allow
	doc.for_value = for_value
	doc.apply_to_all_doctypes = apply_to_all_doctypes
	doc.insert(ignore_permissions=True)
	return "success"


def _remove_user_permission(user, allow, for_value):
	"""Remove a user permission."""
	existing = frappe.db.exists("User Permission", {"user": user, "allow": allow, "for_value": for_value})

	if not existing:
		return "not_exists"

	frappe.delete_doc("User Permission", existing, ignore_permissions=True)
	return "success"


def _to_bool(value):
	"""Convert various truthy values to boolean."""
	if isinstance(value, bool):
		return value
	if isinstance(value, str):
		return value.lower() in ("true", "1", "yes")
	return bool(value)
