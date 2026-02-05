"""Bulk Operation Log DocType Controller."""

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class BulkOperationLog(Document):
	"""Logs bulk permission operations for audit trail."""

	def before_insert(self):
		"""Set initial values."""
		self.executed_by = frappe.session.user
		self.started_at = now_datetime()

	def mark_started(self):
		"""Mark operation as started."""
		self.status = "In Progress"
		self.started_at = now_datetime()
		self.save()

	def mark_completed(self, success_count=0, failure_count=0, skipped_count=0, details=None):
		"""Mark operation as completed."""
		self.status = "Completed" if failure_count == 0 else "Partially Completed"
		self.completed_at = now_datetime()
		self.success_count = success_count
		self.failure_count = failure_count
		self.skipped_count = skipped_count
		self.total_records = success_count + failure_count + skipped_count

		if details:
			import json

			self.operation_details = json.dumps(details)

		self.save()

	def mark_failed(self, error_message):
		"""Mark operation as failed."""
		self.status = "Failed"
		self.completed_at = now_datetime()
		self.error_log = error_message
		self.save()

	def append_error(self, error_message):
		"""Append an error to the error log."""
		if self.error_log:
			self.error_log += f"\n{error_message}"
		else:
			self.error_log = error_message
		self.save()


def create_operation_log(operation_type, params):
	"""Create a new bulk operation log entry."""
	import json

	log = frappe.new_doc("Bulk Operation Log")
	log.operation_type = operation_type
	log.operation_params = json.dumps(params) if isinstance(params, dict) else params
	log.insert(ignore_permissions=True)
	return log
