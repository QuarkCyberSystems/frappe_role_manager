"""CLONE API - Clone Roles with Modifications.

Allows:
- Clone an existing role with a new name
- Cherry-pick which DocType permissions to include
- Modify permissions during clone
- Create role from template
"""

import json

import frappe
from frappe import _

from frappe_role_manager.frappe_role_manager.doctype.bulk_operation_log.bulk_operation_log import (
	create_operation_log,
)


@frappe.whitelist()
def get_role_details(role):
	"""Get complete details of a role for cloning.

	Args:
	    role: Role name to get details for

	Returns:
	    dict: Role details with all permissions
	"""
	if not frappe.db.exists("Role", role):
		frappe.throw(_("Role {0} does not exist").format(role))

	role_doc = frappe.get_doc("Role", role)

	# Get all DocPerms for this role
	docperms = frappe.get_all(
		"DocPerm",
		filters={"role": role},
		fields=[
			"parent as doctype",
			"permlevel",
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
		order_by="parent, permlevel",
	)

	# Group by DocType
	permissions_by_doctype = {}
	for perm in docperms:
		doctype = perm.pop("doctype")
		if doctype not in permissions_by_doctype:
			permissions_by_doctype[doctype] = []
		permissions_by_doctype[doctype].append(perm)

	return {
		"role": role,
		"desk_access": role_doc.desk_access,
		"is_custom": role_doc.is_custom,
		"disabled": role_doc.disabled,
		"permissions": permissions_by_doctype,
		"doctype_count": len(permissions_by_doctype),
		"total_permissions": len(docperms),
	}


@frappe.whitelist()
def preview_clone(source_role, new_role_name, include_doctypes=None, exclude_doctypes=None, permission_overrides=None):
	"""Preview the clone operation before executing.

	Args:
	    source_role: Role to clone from
	    new_role_name: Name for the new role
	    include_doctypes: List of DocTypes to include (if None, include all)
	    exclude_doctypes: List of DocTypes to exclude
	    permission_overrides: Dict of DocType -> permission overrides

	Returns:
	    dict: Preview of the new role
	"""
	if not frappe.db.exists("Role", source_role):
		frappe.throw(_("Source role {0} does not exist").format(source_role))

	if frappe.db.exists("Role", new_role_name):
		frappe.throw(_("Role {0} already exists").format(new_role_name))

	# Parse JSON strings
	if isinstance(include_doctypes, str) and include_doctypes:
		include_doctypes = json.loads(include_doctypes)
	if isinstance(exclude_doctypes, str) and exclude_doctypes:
		exclude_doctypes = json.loads(exclude_doctypes)
	if isinstance(permission_overrides, str) and permission_overrides:
		permission_overrides = json.loads(permission_overrides)

	# Get source role details
	source_details = get_role_details(source_role)

	# Filter DocTypes
	final_doctypes = set(source_details["permissions"].keys())

	if include_doctypes:
		final_doctypes = final_doctypes & set(include_doctypes)

	if exclude_doctypes:
		final_doctypes = final_doctypes - set(exclude_doctypes)

	# Build preview
	preview_permissions = {}
	for doctype in final_doctypes:
		perms = source_details["permissions"][doctype]

		# Apply overrides if any
		if permission_overrides and doctype in permission_overrides:
			for perm in perms:
				for key, value in permission_overrides[doctype].items():
					if key in perm:
						perm[key] = value

		preview_permissions[doctype] = perms

	return {
		"source_role": source_role,
		"new_role_name": new_role_name,
		"permissions": preview_permissions,
		"summary": {
			"source_doctype_count": len(source_details["permissions"]),
			"final_doctype_count": len(preview_permissions),
			"excluded_count": len(source_details["permissions"]) - len(preview_permissions),
		},
	}


@frappe.whitelist()
def execute_clone(source_role, new_role_name, include_doctypes=None, exclude_doctypes=None, permission_overrides=None, desk_access=1):
	"""Execute the clone operation.

	Args:
	    source_role: Role to clone from
	    new_role_name: Name for the new role
	    include_doctypes: List of DocTypes to include (if None, include all)
	    exclude_doctypes: List of DocTypes to exclude
	    permission_overrides: Dict of DocType -> permission overrides
	    desk_access: Whether the new role has desk access

	Returns:
	    dict: Results of the clone operation
	"""
	if not frappe.db.exists("Role", source_role):
		frappe.throw(_("Source role {0} does not exist").format(source_role))

	if frappe.db.exists("Role", new_role_name):
		frappe.throw(_("Role {0} already exists").format(new_role_name))

	# Parse JSON strings
	if isinstance(include_doctypes, str) and include_doctypes:
		include_doctypes = json.loads(include_doctypes)
	if isinstance(exclude_doctypes, str) and exclude_doctypes:
		exclude_doctypes = json.loads(exclude_doctypes)
	if isinstance(permission_overrides, str) and permission_overrides:
		permission_overrides = json.loads(permission_overrides)

	desk_access = _to_bool(desk_access)

	# Create operation log
	log = create_operation_log(
		"Clone Role",
		{
			"source_role": source_role,
			"new_role_name": new_role_name,
			"include_doctypes": include_doctypes,
			"exclude_doctypes": exclude_doctypes,
		},
	)
	log.mark_started()

	results = {"role_created": False, "permissions_added": 0, "errors": []}

	try:
		# Create new role
		new_role = frappe.new_doc("Role")
		new_role.role_name = new_role_name
		new_role.desk_access = desk_access
		new_role.is_custom = 1
		new_role.insert(ignore_permissions=True)
		results["role_created"] = True

		# Get source permissions
		source_details = get_role_details(source_role)

		# Filter DocTypes
		final_doctypes = set(source_details["permissions"].keys())

		if include_doctypes:
			final_doctypes = final_doctypes & set(include_doctypes)

		if exclude_doctypes:
			final_doctypes = final_doctypes - set(exclude_doctypes)

		# Add permissions to DocTypes
		for doctype in final_doctypes:
			try:
				perms = source_details["permissions"][doctype]

				# Get DocType document
				dt_doc = frappe.get_doc("DocType", doctype)

				for perm in perms:
					# Apply overrides if any
					if permission_overrides and doctype in permission_overrides:
						for key, value in permission_overrides[doctype].items():
							if key in perm:
								perm[key] = value

					# Add permission
					dt_doc.append(
						"permissions",
						{
							"role": new_role_name,
							"permlevel": perm.get("permlevel", 0),
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
							"if_owner": perm.get("if_owner", 0),
						},
					)
					results["permissions_added"] += 1

				dt_doc.save(ignore_permissions=True)

			except Exception as e:
				error_msg = f"Error adding permissions for {doctype}: {e!s}"
				results["errors"].append(error_msg)

		frappe.db.commit()

		log.mark_completed(
			success_count=results["permissions_added"],
			failure_count=len(results["errors"]),
			details=results,
		)

		return {"status": "success", "results": results, "role": new_role_name, "log": log.name}

	except Exception as e:
		frappe.db.rollback()
		error_msg = str(e)
		results["errors"].append(error_msg)
		log.mark_failed(error_msg)
		return {"status": "error", "message": error_msg, "results": results, "log": log.name}


@frappe.whitelist()
def create_role_from_doctypes(role_name, doctypes, permissions=None, desk_access=1):
	"""Create a new role with permissions for specified DocTypes.

	Args:
	    role_name: Name for the new role
	    doctypes: List of DocTypes to include
	    permissions: Dict of default permissions or DocType-specific overrides
	    desk_access: Whether the role has desk access

	Returns:
	    dict: Results of the operation
	"""
	if frappe.db.exists("Role", role_name):
		frappe.throw(_("Role {0} already exists").format(role_name))

	# Parse JSON strings
	if isinstance(doctypes, str):
		doctypes = json.loads(doctypes)
	if isinstance(permissions, str) and permissions:
		permissions = json.loads(permissions)

	desk_access = _to_bool(desk_access)

	# Default permissions if not specified
	default_perms = permissions.get("_default", {}) if permissions else {}
	if not default_perms:
		default_perms = {"read": 1, "write": 0, "create": 0, "delete": 0}

	# Create operation log
	log = create_operation_log(
		"Clone Role",
		{"role_name": role_name, "doctypes": doctypes},
	)
	log.mark_started()

	results = {"role_created": False, "permissions_added": 0, "errors": []}

	try:
		# Create new role
		new_role = frappe.new_doc("Role")
		new_role.role_name = role_name
		new_role.desk_access = desk_access
		new_role.is_custom = 1
		new_role.insert(ignore_permissions=True)
		results["role_created"] = True

		# Add permissions to each DocType
		for doctype in doctypes:
			if not frappe.db.exists("DocType", doctype):
				results["errors"].append(f"DocType {doctype} does not exist")
				continue

			try:
				dt_doc = frappe.get_doc("DocType", doctype)

				# Get permissions for this DocType
				doctype_perms = default_perms.copy()
				if permissions and doctype in permissions:
					doctype_perms.update(permissions[doctype])

				dt_doc.append(
					"permissions",
					{
						"role": role_name,
						"permlevel": 0,
						"read": doctype_perms.get("read", 0),
						"write": doctype_perms.get("write", 0),
						"create": doctype_perms.get("create", 0),
						"delete": doctype_perms.get("delete", 0),
						"submit": doctype_perms.get("submit", 0),
						"cancel": doctype_perms.get("cancel", 0),
						"amend": doctype_perms.get("amend", 0),
						"report": doctype_perms.get("report", 1),
						"export": doctype_perms.get("export", 1),
						"import": doctype_perms.get("import", 0),
						"share": doctype_perms.get("share", 0),
						"print": doctype_perms.get("print", 1),
						"email": doctype_perms.get("email", 1),
					},
				)
				dt_doc.save(ignore_permissions=True)
				results["permissions_added"] += 1

			except Exception as e:
				error_msg = f"Error adding permissions for {doctype}: {e!s}"
				results["errors"].append(error_msg)

		frappe.db.commit()

		log.mark_completed(
			success_count=results["permissions_added"],
			failure_count=len(results["errors"]),
			details=results,
		)

		return {"status": "success", "results": results, "role": role_name, "log": log.name}

	except Exception as e:
		frappe.db.rollback()
		error_msg = str(e)
		results["errors"].append(error_msg)
		log.mark_failed(error_msg)
		return {"status": "error", "message": error_msg, "results": results, "log": log.name}


@frappe.whitelist()
def merge_roles(role_a, role_b, new_role_name, merge_strategy="union"):
	"""Merge two roles into a new role.

	Args:
	    role_a: First role
	    role_b: Second role
	    new_role_name: Name for the merged role
	    merge_strategy: 'union' (combine all) or 'intersection' (common only)

	Returns:
	    dict: Results of the merge operation
	"""
	if not frappe.db.exists("Role", role_a):
		frappe.throw(_("Role {0} does not exist").format(role_a))
	if not frappe.db.exists("Role", role_b):
		frappe.throw(_("Role {0} does not exist").format(role_b))
	if frappe.db.exists("Role", new_role_name):
		frappe.throw(_("Role {0} already exists").format(new_role_name))

	# Get permissions for both roles
	perms_a = get_role_details(role_a)["permissions"]
	perms_b = get_role_details(role_b)["permissions"]

	doctypes_a = set(perms_a.keys())
	doctypes_b = set(perms_b.keys())

	# Determine final DocTypes based on strategy
	if merge_strategy == "union":
		final_doctypes = doctypes_a | doctypes_b
	else:  # intersection
		final_doctypes = doctypes_a & doctypes_b

	# Merge permissions
	merged_permissions = {}
	for doctype in final_doctypes:
		perm_a = perms_a.get(doctype, [{}])[0] if doctype in perms_a else {}
		perm_b = perms_b.get(doctype, [{}])[0] if doctype in perms_b else {}

		# Merge with OR logic (if either role has permission, merged role has it)
		merged = {}
		for field in ["read", "write", "create", "delete", "submit", "cancel", "amend", "report", "export", "import", "share", "print", "email"]:
			merged[field] = max(perm_a.get(field, 0), perm_b.get(field, 0))

		merged_permissions[doctype] = merged

	# Create the merged role
	log = create_operation_log(
		"Clone Role",
		{"role_a": role_a, "role_b": role_b, "new_role_name": new_role_name, "strategy": merge_strategy},
	)
	log.mark_started()

	results = {"role_created": False, "permissions_added": 0, "errors": []}

	try:
		# Create new role
		new_role = frappe.new_doc("Role")
		new_role.role_name = new_role_name
		new_role.desk_access = 1
		new_role.is_custom = 1
		new_role.insert(ignore_permissions=True)
		results["role_created"] = True

		# Add merged permissions
		for doctype, perms in merged_permissions.items():
			try:
				dt_doc = frappe.get_doc("DocType", doctype)
				dt_doc.append(
					"permissions",
					{
						"role": new_role_name,
						"permlevel": 0,
						**perms,
					},
				)
				dt_doc.save(ignore_permissions=True)
				results["permissions_added"] += 1

			except Exception as e:
				results["errors"].append(f"Error for {doctype}: {e!s}")

		frappe.db.commit()

		log.mark_completed(
			success_count=results["permissions_added"],
			failure_count=len(results["errors"]),
			details=results,
		)

		return {
			"status": "success",
			"results": results,
			"role": new_role_name,
			"log": log.name,
			"merge_info": {
				"doctypes_from_a_only": list(doctypes_a - doctypes_b),
				"doctypes_from_b_only": list(doctypes_b - doctypes_a),
				"doctypes_common": list(doctypes_a & doctypes_b),
			},
		}

	except Exception as e:
		frappe.db.rollback()
		error_msg = str(e)
		log.mark_failed(error_msg)
		return {"status": "error", "message": error_msg, "results": results, "log": log.name}


def _to_bool(value):
	"""Convert various truthy values to boolean."""
	if isinstance(value, bool):
		return value
	if isinstance(value, str):
		return value.lower() in ("true", "1", "yes")
	return bool(value)
