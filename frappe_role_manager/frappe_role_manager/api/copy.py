"""COPY API - Copy User Permissions.

Allows copying permissions from one user to another:
- Copy Roles
- Copy User Permissions
- Copy Role Profile
- Copy Module Profile
"""

import frappe
from frappe import _

from frappe_role_manager.frappe_role_manager.doctype.bulk_operation_log.bulk_operation_log import (
	create_operation_log,
)


@frappe.whitelist()
def preview_copy(source_user, target_user, copy_roles=True, copy_user_permissions=True, copy_role_profile=True, copy_module_profile=True):
	"""Preview what will be copied from source to target user.

	Args:
	    source_user: User to copy from
	    target_user: User to copy to
	    copy_roles: Whether to copy role assignments
	    copy_user_permissions: Whether to copy user permission records
	    copy_role_profile: Whether to copy role profile
	    copy_module_profile: Whether to copy module profile

	Returns:
	    dict: Preview of changes that will be made
	"""
	# Validate users exist
	if not frappe.db.exists("User", source_user):
		frappe.throw(_("Source user {0} does not exist").format(source_user))
	if not frappe.db.exists("User", target_user):
		frappe.throw(_("Target user {0} does not exist").format(target_user))

	# Convert string booleans to actual booleans
	copy_roles = _to_bool(copy_roles)
	copy_user_permissions = _to_bool(copy_user_permissions)
	copy_role_profile = _to_bool(copy_role_profile)
	copy_module_profile = _to_bool(copy_module_profile)

	source_doc = frappe.get_doc("User", source_user)
	target_doc = frappe.get_doc("User", target_user)

	preview = {
		"source_user": source_user,
		"source_user_name": source_doc.full_name,
		"target_user": target_user,
		"target_user_name": target_doc.full_name,
		"roles": {"add": [], "existing": []},
		"user_permissions": {"add": [], "existing": []},
		"role_profile": {"change": None},
		"module_profile": {"change": None},
	}

	# Preview role changes
	if copy_roles:
		source_roles = set(r.role for r in source_doc.roles)
		target_roles = set(r.role for r in target_doc.roles)

		preview["roles"]["add"] = list(source_roles - target_roles)
		preview["roles"]["existing"] = list(source_roles & target_roles)

	# Preview user permission changes
	if copy_user_permissions:
		source_perms = frappe.get_all(
			"User Permission",
			filters={"user": source_user},
			fields=["allow", "for_value", "applicable_for", "apply_to_all_doctypes"],
		)

		target_perms = frappe.get_all(
			"User Permission",
			filters={"user": target_user},
			fields=["allow", "for_value"],
		)
		target_perm_set = set((p.allow, p.for_value) for p in target_perms)

		for perm in source_perms:
			perm_key = (perm.allow, perm.for_value)
			if perm_key in target_perm_set:
				preview["user_permissions"]["existing"].append(perm)
			else:
				preview["user_permissions"]["add"].append(perm)

	# Preview role profile change
	if copy_role_profile:
		if source_doc.role_profile_name != target_doc.role_profile_name:
			preview["role_profile"]["change"] = {
				"from": target_doc.role_profile_name,
				"to": source_doc.role_profile_name,
			}

	# Preview module profile change
	if copy_module_profile:
		if source_doc.module_profile != target_doc.module_profile:
			preview["module_profile"]["change"] = {
				"from": target_doc.module_profile,
				"to": source_doc.module_profile,
			}

	# Summary
	preview["summary"] = {
		"roles_to_add": len(preview["roles"]["add"]),
		"user_permissions_to_add": len(preview["user_permissions"]["add"]),
		"role_profile_change": preview["role_profile"]["change"] is not None,
		"module_profile_change": preview["module_profile"]["change"] is not None,
	}

	return preview


@frappe.whitelist()
def execute_copy(source_user, target_user, copy_roles=True, copy_user_permissions=True, copy_role_profile=True, copy_module_profile=True, create_backup=True, selected_roles=None):
	"""Execute the copy operation from source to target user.

	Args:
	    source_user: User to copy from
	    target_user: User to copy to
	    copy_roles: Whether to copy role assignments
	    copy_user_permissions: Whether to copy user permission records
	    copy_role_profile: Whether to copy role profile
	    copy_module_profile: Whether to copy module profile
	    create_backup: Whether to create a backup snapshot before copying
	    selected_roles: List of specific roles to copy (if None, copies all)

	Returns:
	    dict: Results of the copy operation
	"""
	import json

	# Validate users exist
	if not frappe.db.exists("User", source_user):
		frappe.throw(_("Source user {0} does not exist").format(source_user))
	if not frappe.db.exists("User", target_user):
		frappe.throw(_("Target user {0} does not exist").format(target_user))

	# Convert string booleans to actual booleans
	copy_roles = _to_bool(copy_roles)
	copy_user_permissions = _to_bool(copy_user_permissions)
	copy_role_profile = _to_bool(copy_role_profile)
	copy_module_profile = _to_bool(copy_module_profile)
	create_backup = _to_bool(create_backup)

	# Parse selected_roles if it's a string
	if selected_roles and isinstance(selected_roles, str):
		selected_roles = json.loads(selected_roles)

	# Create operation log
	log = create_operation_log(
		"Copy User Permissions",
		{
			"source_user": source_user,
			"target_user": target_user,
			"copy_roles": copy_roles,
			"copy_user_permissions": copy_user_permissions,
			"copy_role_profile": copy_role_profile,
			"copy_module_profile": copy_module_profile,
			"selected_roles": selected_roles,
		},
	)
	log.mark_started()

	results = {"roles_added": 0, "user_permissions_added": 0, "role_profile_updated": False, "module_profile_updated": False, "errors": []}

	try:
		# Create backup if requested
		if create_backup:
			_create_user_backup(target_user)

		source_doc = frappe.get_doc("User", source_user)
		target_doc = frappe.get_doc("User", target_user)

		# Copy roles
		if copy_roles:
			source_roles = set(r.role for r in source_doc.roles)
			target_roles = set(r.role for r in target_doc.roles)

			# If specific roles are selected, only copy those
			if selected_roles:
				roles_to_add = set(selected_roles) - target_roles
			else:
				roles_to_add = source_roles - target_roles

			for role in roles_to_add:
				target_doc.append("roles", {"role": role})
				results["roles_added"] += 1

		# Copy role profile
		if copy_role_profile and source_doc.role_profile_name != target_doc.role_profile_name:
			target_doc.role_profile_name = source_doc.role_profile_name
			results["role_profile_updated"] = True

		# Copy module profile
		if copy_module_profile and source_doc.module_profile != target_doc.module_profile:
			target_doc.module_profile = source_doc.module_profile
			results["module_profile_updated"] = True

		# Save user document
		target_doc.save(ignore_permissions=True)

		# Copy user permissions (separate documents)
		if copy_user_permissions:
			source_perms = frappe.get_all(
				"User Permission",
				filters={"user": source_user},
				fields=["allow", "for_value", "applicable_for", "apply_to_all_doctypes"],
			)

			for perm in source_perms:
				# Check if already exists
				exists = frappe.db.exists(
					"User Permission",
					{"user": target_user, "allow": perm.allow, "for_value": perm.for_value},
				)
				if not exists:
					new_perm = frappe.new_doc("User Permission")
					new_perm.user = target_user
					new_perm.allow = perm.allow
					new_perm.for_value = perm.for_value
					new_perm.applicable_for = perm.applicable_for
					new_perm.apply_to_all_doctypes = perm.apply_to_all_doctypes
					new_perm.insert(ignore_permissions=True)
					results["user_permissions_added"] += 1

		frappe.db.commit()

		# Update log
		log.mark_completed(
			success_count=results["roles_added"] + results["user_permissions_added"],
			failure_count=len(results["errors"]),
			details=results,
		)

		return {"status": "success", "results": results, "log": log.name}

	except Exception as e:
		frappe.db.rollback()
		error_msg = str(e)
		results["errors"].append(error_msg)
		log.mark_failed(error_msg)
		return {"status": "error", "message": error_msg, "log": log.name}


@frappe.whitelist()
def copy_to_multiple_users(source_user, target_users, copy_roles=True, copy_user_permissions=True, copy_role_profile=True, copy_module_profile=True):
	"""Copy permissions from source user to multiple target users.

	Args:
	    source_user: User to copy from
	    target_users: List of users to copy to (JSON string or list)
	    copy_roles: Whether to copy role assignments
	    copy_user_permissions: Whether to copy user permission records
	    copy_role_profile: Whether to copy role profile
	    copy_module_profile: Whether to copy module profile

	Returns:
	    dict: Results for each target user
	"""
	import json

	if isinstance(target_users, str):
		target_users = json.loads(target_users)

	results = {"total": len(target_users), "success": 0, "failed": 0, "details": []}

	for target_user in target_users:
		result = execute_copy(
			source_user=source_user,
			target_user=target_user,
			copy_roles=copy_roles,
			copy_user_permissions=copy_user_permissions,
			copy_role_profile=copy_role_profile,
			copy_module_profile=copy_module_profile,
			create_backup=True,
		)

		if result.get("status") == "success":
			results["success"] += 1
		else:
			results["failed"] += 1

		results["details"].append({"user": target_user, "result": result})

	return results


def _create_user_backup(user):
	"""Create a backup snapshot of user's current permissions."""
	import json

	user_doc = frappe.get_doc("User", user)

	# Collect current state
	backup_data = {
		"user": user,
		"roles": [r.role for r in user_doc.roles],
		"role_profile": user_doc.role_profile_name,
		"module_profile": user_doc.module_profile,
		"user_permissions": frappe.get_all(
			"User Permission",
			filters={"user": user},
			fields=["allow", "for_value", "applicable_for", "apply_to_all_doctypes"],
		),
	}

	# Create snapshot
	snapshot = frappe.new_doc("Permission Snapshot")
	snapshot.snapshot_type = "User Permissions"
	snapshot.description = f"Backup before copy operation for user {user}"
	snapshot.snapshot_data = json.dumps(backup_data)
	snapshot.user_filter = user
	snapshot.insert(ignore_permissions=True)

	return snapshot.name


@frappe.whitelist()
def get_user_roles_for_copy(source_user, target_user=None):
	"""Get source user's roles with info about whether target already has them.

	Args:
	    source_user: User to get roles from
	    target_user: Optional target user to compare against

	Returns:
	    dict: List of roles with copy status
	"""
	if not frappe.db.exists("User", source_user):
		frappe.throw(_("Source user {0} does not exist").format(source_user))

	source_doc = frappe.get_doc("User", source_user)
	source_roles = [r.role for r in source_doc.roles]

	target_roles = set()
	if target_user and frappe.db.exists("User", target_user):
		target_doc = frappe.get_doc("User", target_user)
		target_roles = set(r.role for r in target_doc.roles)

	roles_info = []
	for role in source_roles:
		roles_info.append({
			"role": role,
			"already_has": role in target_roles,
		})

	return {
		"source_user": source_user,
		"target_user": target_user,
		"roles": roles_info,
		"total": len(roles_info),
		"already_has_count": sum(1 for r in roles_info if r["already_has"]),
	}


@frappe.whitelist()
def get_role_doctype_permissions(role):
	"""Get all DocType permissions for a role.

	Args:
	    role: Role name

	Returns:
	    dict: DocType permissions grouped by DocType
	"""
	if not frappe.db.exists("Role", role):
		frappe.throw(_("Role {0} does not exist").format(role))

	docperms = frappe.get_all(
		"DocPerm",
		filters={"role": role, "permlevel": 0},
		fields=[
			"name",
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

	return {
		"role": role,
		"permissions": docperms,
		"doctype_count": len(docperms),
	}


@frappe.whitelist()
def get_user_roles_with_permissions(source_user, target_user=None):
	"""Get source user's roles with their DocType permissions.

	Args:
	    source_user: User to get roles from
	    target_user: Optional target user to compare against

	Returns:
	    dict: Roles with their DocType permissions
	"""
	if not frappe.db.exists("User", source_user):
		frappe.throw(_("Source user {0} does not exist").format(source_user))

	source_doc = frappe.get_doc("User", source_user)
	source_roles = [r.role for r in source_doc.roles]

	target_roles = set()
	if target_user and frappe.db.exists("User", target_user):
		target_doc = frappe.get_doc("User", target_user)
		target_roles = set(r.role for r in target_doc.roles)

	roles_info = []
	for role in source_roles:
		# Get DocType permissions for this role
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

		roles_info.append({
			"role": role,
			"already_has": role in target_roles,
			"permissions": docperms,
			"doctype_count": len(docperms),
		})

	return {
		"source_user": source_user,
		"target_user": target_user,
		"roles": roles_info,
		"total": len(roles_info),
	}


@frappe.whitelist()
def create_custom_role_with_permissions(role_name, permissions, desk_access=True):
	"""Create a new custom role with specific DocType permissions.

	Args:
	    role_name: Name for the new role
	    permissions: List of permission dicts [{doctype, read, write, create, ...}]
	    desk_access: Whether role has desk access

	Returns:
	    dict: Result with new role name
	"""
	import json

	if isinstance(permissions, str):
		permissions = json.loads(permissions)

	desk_access = _to_bool(desk_access)

	# Check if role already exists
	if frappe.db.exists("Role", role_name):
		frappe.throw(_("Role {0} already exists").format(role_name))

	# Create the role
	role_doc = frappe.new_doc("Role")
	role_doc.role_name = role_name
	role_doc.desk_access = desk_access
	role_doc.is_custom = 1
	role_doc.insert(ignore_permissions=True)

	# Add permissions to each DocType
	for perm in permissions:
		doctype = perm.get("doctype")
		if not doctype or not frappe.db.exists("DocType", doctype):
			continue

		# Get the DocType document to add permission
		dt_doc = frappe.get_doc("DocType", doctype)

		# Check if permission already exists for this role
		existing = [p for p in dt_doc.permissions if p.role == role_name and p.permlevel == 0]
		if existing:
			# Update existing permission
			for key in ["read", "write", "create", "delete", "submit", "cancel", "amend", "report", "export", "import", "share", "print", "email"]:
				if perm.get(key):
					existing[0].set(key, 1)
		else:
			# Add new permission
			dt_doc.append("permissions", {
				"role": role_name,
				"permlevel": 0,
				"read": perm.get("read", 0),
				"write": perm.get("write", 0),
				"create": perm.get("create", 0),
				"delete": perm.get("delete", 0),
				"submit": perm.get("submit", 0),
				"cancel": perm.get("cancel", 0),
				"amend": perm.get("amend", 0),
				"report": perm.get("report", 0),
				"export": perm.get("export", 0),
				"import": perm.get("import", 0),
				"share": perm.get("share", 0),
				"print": perm.get("print", 0),
				"email": perm.get("email", 0),
			})

		dt_doc.save(ignore_permissions=True)

	frappe.db.commit()

	return {
		"status": "success",
		"role": role_name,
		"permissions_added": len(permissions),
	}


@frappe.whitelist()
def copy_with_custom_permissions(source_user, target_user, selected_permissions, custom_role_name=None):
	"""Copy permissions with cherry-picked DocType permissions.

	Creates a custom role with only the selected permissions and assigns it to the target user.

	Args:
	    source_user: Source user
	    target_user: Target user
	    selected_permissions: JSON list of {role, doctype, read, write, create, ...}
	    custom_role_name: Optional name for the custom role (auto-generated if not provided)

	Returns:
	    dict: Result
	"""
	import json

	if isinstance(selected_permissions, str):
		selected_permissions = json.loads(selected_permissions)

	if not selected_permissions:
		frappe.throw(_("No permissions selected"))

	# Validate custom role name is provided (mandatory to prevent accidental permission overwrites)
	if not custom_role_name or not custom_role_name.strip():
		frappe.throw(_("Custom Role Name is required. Please provide a unique name for the new role."))

	custom_role_name = custom_role_name.strip()

	# Create operation log
	log = create_operation_log(
		"Copy Custom Permissions",
		{
			"source_user": source_user,
			"target_user": target_user,
			"custom_role_name": custom_role_name,
			"permissions_count": len(selected_permissions),
		},
	)
	log.mark_started()

	try:
		# Create the custom role with selected permissions
		result = create_custom_role_with_permissions(
			role_name=custom_role_name,
			permissions=selected_permissions,
			desk_access=True,
		)

		if result.get("status") != "success":
			raise Exception("Failed to create custom role")

		# Assign the custom role to target user
		target_doc = frappe.get_doc("User", target_user)
		target_doc.append("roles", {"role": custom_role_name})
		target_doc.save(ignore_permissions=True)

		frappe.db.commit()

		log.mark_completed(
			success_count=1,
			failure_count=0,
			details={"custom_role": custom_role_name, "permissions": len(selected_permissions)},
		)

		return {
			"status": "success",
			"custom_role": custom_role_name,
			"permissions_added": len(selected_permissions),
		}

	except Exception as e:
		frappe.db.rollback()
		log.mark_failed(str(e))
		return {"status": "error", "message": str(e)}


def _to_bool(value):
	"""Convert various truthy values to boolean."""
	if isinstance(value, bool):
		return value
	if isinstance(value, str):
		return value.lower() in ("true", "1", "yes")
	return bool(value)
