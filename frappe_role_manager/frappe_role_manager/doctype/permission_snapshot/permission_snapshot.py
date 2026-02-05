"""Permission Snapshot DocType Controller."""

import frappe
from frappe.model.document import Document


class PermissionSnapshot(Document):
	"""Stores permission snapshots for backup and restore operations."""

	def before_insert(self):
		"""Set the created_by field."""
		self.created_by = frappe.session.user

	def validate(self):
		"""Validate the snapshot data."""
		if self.snapshot_data:
			try:
				import json

				if isinstance(self.snapshot_data, str):
					json.loads(self.snapshot_data)
			except json.JSONDecodeError:
				frappe.throw("Invalid JSON in snapshot data")

	@frappe.whitelist()
	def apply_snapshot(self):
		"""Apply this snapshot to restore permissions."""
		if not self.snapshot_data:
			frappe.throw("No snapshot data to apply")

		import json

		data = json.loads(self.snapshot_data) if isinstance(self.snapshot_data, str) else self.snapshot_data

		results = {"roles_updated": 0, "user_permissions_updated": 0, "role_assignments_updated": 0}

		# Apply role permissions (DocPerm)
		if "role_permissions" in data:
			for perm in data["role_permissions"]:
				self._apply_role_permission(perm)
				results["roles_updated"] += 1

		# Apply user permissions
		if "user_permissions" in data:
			for up in data["user_permissions"]:
				self._apply_user_permission(up)
				results["user_permissions_updated"] += 1

		# Apply role assignments
		if "role_assignments" in data:
			for ra in data["role_assignments"]:
				self._apply_role_assignment(ra)
				results["role_assignments_updated"] += 1

		self.status = "Applied"
		self.save()

		frappe.db.commit()
		return results

	def _apply_role_permission(self, perm):
		"""Apply a single role permission."""
		existing = frappe.db.exists(
			"DocPerm", {"parent": perm.get("doctype"), "role": perm.get("role"), "permlevel": perm.get("permlevel", 0)}
		)

		if existing:
			doc = frappe.get_doc("DocPerm", existing)
			for key in ["read", "write", "create", "delete", "submit", "cancel", "amend", "report", "export", "import", "share", "print", "email"]:
				if key in perm:
					setattr(doc, key, perm.get(key))
			doc.save()
		else:
			# Create new DocPerm through DocType
			dt = frappe.get_doc("DocType", perm.get("doctype"))
			dt.append(
				"permissions",
				{
					"role": perm.get("role"),
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
				},
			)
			dt.save()

	def _apply_user_permission(self, up):
		"""Apply a single user permission."""
		existing = frappe.db.exists(
			"User Permission",
			{"user": up.get("user"), "allow": up.get("allow"), "for_value": up.get("for_value")},
		)

		if not existing:
			doc = frappe.new_doc("User Permission")
			doc.user = up.get("user")
			doc.allow = up.get("allow")
			doc.for_value = up.get("for_value")
			doc.apply_to_all_doctypes = up.get("apply_to_all_doctypes", 1)
			doc.insert(ignore_permissions=True)

	def _apply_role_assignment(self, ra):
		"""Apply role assignments to a user."""
		user = ra.get("user")
		roles = ra.get("roles", [])

		if not frappe.db.exists("User", user):
			return

		user_doc = frappe.get_doc("User", user)
		existing_roles = [r.role for r in user_doc.roles]

		for role in roles:
			if role not in existing_roles:
				user_doc.append("roles", {"role": role})

		user_doc.save(ignore_permissions=True)
