// Global reference for the Role Manager instance
var frappe_role_manager_instance = null;

frappe.pages["role-manager"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Role Manager",
		single_column: true,
	});

	wrapper.page = page;

	// Add custom buttons
	page.set_primary_action(__("Refresh"), () => {
		page.role_manager.refresh();
	});

	page.set_secondary_action(__("Export"), () => {
		page.role_manager.show_export_dialog();
	});

	// Add menu items
	page.add_menu_item(__("Import Permissions"), () => {
		page.role_manager.show_import_dialog();
	});

	page.add_menu_item(__("Download Template"), () => {
		page.role_manager.download_template();
	});

	page.add_menu_item(__("View Operation Logs"), () => {
		frappe.set_route("List", "Bulk Operation Log");
	});

	page.add_menu_item(__("View Snapshots"), () => {
		frappe.set_route("List", "Permission Snapshot");
	});

	// Initialize the Role Manager
	page.role_manager = new RoleManager(page);
	frappe_role_manager_instance = page.role_manager;
};

frappe.pages["role-manager"].on_page_show = function (wrapper) {
	// Refresh when page is shown
	if (wrapper.page && wrapper.page.role_manager) {
		wrapper.page.role_manager.refresh();
	}
};

class RoleManager {
	constructor(page) {
		this.page = page;
		this.wrapper = $(page.body);
		this.current_tab = "users";
		this.selected_user = null;
		this.selected_role = null;

		this.make();
	}

	make() {
		this.wrapper.html(`
			<div class="role-manager-container">
				<!-- Tabs -->
				<div class="role-manager-tabs">
					<button class="btn btn-tab active" data-tab="users">
						<i class="fa fa-users"></i> Users
					</button>
					<button class="btn btn-tab" data-tab="roles">
						<i class="fa fa-key"></i> Roles
					</button>
					<button class="btn btn-tab" data-tab="compare">
						<i class="fa fa-exchange"></i> Compare
					</button>
					<button class="btn btn-tab" data-tab="bulk">
						<i class="fa fa-tasks"></i> Bulk Operations
					</button>
				</div>

				<!-- Content Area -->
				<div class="role-manager-content">
					<!-- Users Tab -->
					<div class="tab-content" data-tab="users">
						<div class="row">
							<div class="col-md-4">
								<div class="panel panel-default">
									<div class="panel-heading">
										<h4>Select User</h4>
									</div>
									<div class="panel-body">
										<div class="user-search">
											<input type="text" class="form-control" id="user-search"
												placeholder="Search users...">
										</div>
										<div class="user-count text-muted" id="user-count" style="font-size: 12px; margin: 5px 0;"></div>
										<div class="user-list" id="user-list">
											<!-- User list will be populated here -->
										</div>
									</div>
								</div>
							</div>
							<div class="col-md-8">
								<div class="user-details-panel" id="user-details">
									<div class="text-center text-muted" style="padding: 50px;">
										<i class="fa fa-user fa-3x"></i>
										<p>Select a user to view their permissions</p>
									</div>
								</div>
							</div>
						</div>
					</div>

					<!-- Roles Tab -->
					<div class="tab-content hidden" data-tab="roles">
						<div class="row">
							<div class="col-md-4">
								<div class="panel panel-default">
									<div class="panel-heading">
										<h4>Select Role</h4>
										<button class="btn btn-xs btn-primary pull-right" id="btn-new-role">
											<i class="fa fa-plus"></i> New Role
										</button>
									</div>
									<div class="panel-body">
										<div class="role-search">
											<input type="text" class="form-control" id="role-search"
												placeholder="Search roles...">
										</div>
										<div class="role-list" id="role-list">
											<!-- Role list will be populated here -->
										</div>
									</div>
								</div>
							</div>
							<div class="col-md-8">
								<div class="role-details-panel" id="role-details">
									<div class="text-center text-muted" style="padding: 50px;">
										<i class="fa fa-key fa-3x"></i>
										<p>Select a role to view its permissions</p>
									</div>
								</div>
							</div>
						</div>
					</div>

					<!-- Compare Tab -->
					<div class="tab-content hidden" data-tab="compare">
						<div class="compare-panel">
							<div class="row">
								<div class="col-md-5">
									<div class="form-group">
										<label>User/Role A</label>
										<select class="form-control" id="compare-a"></select>
									</div>
								</div>
								<div class="col-md-2 text-center" style="padding-top: 25px;">
									<i class="fa fa-exchange fa-2x text-muted"></i>
								</div>
								<div class="col-md-5">
									<div class="form-group">
										<label>User/Role B</label>
										<select class="form-control" id="compare-b"></select>
									</div>
								</div>
							</div>
							<div class="row">
								<div class="col-md-12 text-center">
									<button class="btn btn-primary" id="btn-compare">
										<i class="fa fa-search"></i> Compare
									</button>
								</div>
							</div>
							<div class="compare-results" id="compare-results">
								<!-- Comparison results will be shown here -->
							</div>
						</div>
					</div>

					<!-- Bulk Operations Tab -->
					<div class="tab-content hidden" data-tab="bulk">
						<div class="bulk-panel">
							<div class="row">
								<div class="col-md-6">
									<div class="panel panel-default">
										<div class="panel-heading">
											<h4>Bulk Role Assignment</h4>
										</div>
										<div class="panel-body">
											<div class="form-group">
												<label>Action</label>
												<select class="form-control" id="bulk-action">
													<option value="add">Add Role</option>
													<option value="remove">Remove Role</option>
												</select>
											</div>
											<div class="form-group">
												<label>Role</label>
												<select class="form-control" id="bulk-role"></select>
											</div>
											<div class="form-group">
												<label>Filter Users By</label>
												<select class="form-control" id="bulk-filter-type">
													<option value="">Select Filter...</option>
													<option value="department">Department</option>
													<option value="company">Company</option>
													<option value="role">Existing Role</option>
												</select>
											</div>
											<div class="form-group" id="bulk-filter-value-group" style="display:none;">
												<label>Filter Value</label>
												<select class="form-control" id="bulk-filter-value"></select>
											</div>
											<div class="form-group">
												<button class="btn btn-info" id="btn-bulk-preview">
													<i class="fa fa-eye"></i> Preview
												</button>
												<button class="btn btn-primary" id="btn-bulk-execute" disabled>
													<i class="fa fa-play"></i> Execute
												</button>
											</div>
											<div class="bulk-preview" id="bulk-preview">
												<!-- Preview will be shown here -->
											</div>
										</div>
									</div>
								</div>
								<div class="col-md-6">
									<div class="panel panel-default">
										<div class="panel-heading">
											<h4>Copy User Permissions</h4>
										</div>
										<div class="panel-body">
											<div class="form-group">
												<label>Source User</label>
												<select class="form-control" id="copy-source"></select>
											</div>
											<div class="form-group">
												<label>Target User</label>
												<select class="form-control" id="copy-target"></select>
											</div>
											<div class="form-group">
												<label>What to Copy</label>
												<div class="checkbox">
													<label>
														<input type="checkbox" id="copy-roles" checked> Roles
													</label>
												</div>
												<div class="checkbox">
													<label>
														<input type="checkbox" id="copy-user-perms" checked> User Permissions
													</label>
												</div>
												<div class="checkbox">
													<label>
														<input type="checkbox" id="copy-role-profile" checked> Role Profile
													</label>
												</div>
											</div>
											<div class="form-group">
												<button class="btn btn-info" id="btn-copy-preview">
													<i class="fa fa-eye"></i> Preview
												</button>
												<button class="btn btn-primary" id="btn-copy-execute" disabled>
													<i class="fa fa-copy"></i> Copy
												</button>
											</div>
											<div class="copy-preview" id="copy-preview">
												<!-- Preview will be shown here -->
											</div>
										</div>
									</div>
								</div>
							</div>
						</div>
					</div>
				</div>
			</div>
		`);

		this.bind_events();
		this.refresh();
	}

	bind_events() {
		const me = this;

		// Tab switching
		this.wrapper.find(".btn-tab").on("click", function () {
			me.switch_tab($(this).data("tab"));
		});

		// User search
		this.wrapper.find("#user-search").on("input", frappe.utils.debounce(() => {
			me.filter_users();
		}, 300));

		// Role search
		this.wrapper.find("#role-search").on("input", frappe.utils.debounce(() => {
			me.filter_roles();
		}, 300));

		// New role button
		this.wrapper.find("#btn-new-role").on("click", () => {
			me.show_new_role_dialog();
		});

		// Compare button
		this.wrapper.find("#btn-compare").on("click", () => {
			me.run_comparison();
		});

		// Bulk filter type change
		this.wrapper.find("#bulk-filter-type").on("change", function () {
			me.update_bulk_filter_values($(this).val());
		});

		// Bulk preview button
		this.wrapper.find("#btn-bulk-preview").on("click", () => {
			me.preview_bulk_operation();
		});

		// Bulk execute button
		this.wrapper.find("#btn-bulk-execute").on("click", () => {
			me.execute_bulk_operation();
		});

		// Copy preview button
		this.wrapper.find("#btn-copy-preview").on("click", () => {
			me.preview_copy_operation();
		});

		// Copy execute button
		this.wrapper.find("#btn-copy-execute").on("click", () => {
			me.execute_copy_operation();
		});
	}

	switch_tab(tab) {
		this.current_tab = tab;

		// Update tab buttons
		this.wrapper.find(".btn-tab").removeClass("active");
		this.wrapper.find(`.btn-tab[data-tab="${tab}"]`).addClass("active");

		// Show/hide content
		this.wrapper.find(".tab-content").addClass("hidden");
		this.wrapper.find(`.tab-content[data-tab="${tab}"]`).removeClass("hidden");
	}

	refresh() {
		this.load_users();
		this.load_roles();
		this.load_filter_options();
	}

	load_users() {
		const me = this;

		frappe.call({
			method: "frappe_role_manager.frappe_role_manager.api.view.get_all_users",
			callback: function (r) {
				if (r.message) {
					me.users = r.message;
					me.render_user_list();
					me.populate_user_selects();
				} else {
					me.users = [];
					me.render_user_list();
					console.warn("No users returned from API");
				}
			},
			error: function (r) {
				me.users = [];
				me.render_user_list();
				frappe.msgprint(__("Error loading users. Please check console for details."));
				console.error("Error loading users:", r);
			},
		});
	}

	render_user_list() {
		const me = this;
		const search = this.wrapper.find("#user-search").val().toLowerCase();

		let users = this.users || [];
		if (search) {
			users = users.filter(
				(u) =>
					u.name.toLowerCase().includes(search) ||
					(u.full_name && u.full_name.toLowerCase().includes(search)) ||
					(u.email && u.email.toLowerCase().includes(search)) ||
					(u.user_type && u.user_type.toLowerCase().includes(search))
			);
		}

		// Update user count
		const totalCount = this.users ? this.users.length : 0;
		this.wrapper.find("#user-count").text(
			search
				? `Showing ${users.length} of ${totalCount} users`
				: `${totalCount} users`
		);

		if (users.length === 0) {
			this.wrapper.find("#user-list").html(`
				<div class="text-center text-muted" style="padding: 20px;">
					${search ? "No users match your search" : "No users found"}
				</div>
			`);
			return;
		}

		const html = users
			.map(
				(u) => `
			<div class="user-item ${me.selected_user === u.name ? "selected" : ""}"
				 data-user="${u.name}">
				<div class="user-avatar">
					${frappe.avatar(u.name, "avatar-small")}
				</div>
				<div class="user-info">
					<div class="user-name">${u.full_name || u.name}</div>
					<div class="user-email text-muted">${u.name}</div>
					<div class="user-type text-muted" style="font-size: 10px;">${u.user_type || ""}</div>
				</div>
				<div class="user-badge">
					<span class="badge">${u.role_count} roles</span>
				</div>
			</div>
		`
			)
			.join("");

		this.wrapper.find("#user-list").html(html);

		// Bind click events
		this.wrapper.find(".user-item").on("click", function () {
			me.select_user($(this).data("user"));
		});
	}

	filter_users() {
		this.render_user_list();
	}

	select_user(user) {
		this.selected_user = user;
		this.render_user_list();
		this.load_user_details(user);
	}

	load_user_details(user) {
		const me = this;

		frappe.call({
			method: "frappe_role_manager.frappe_role_manager.api.view.get_user_permissions_view",
			args: { user: user },
			callback: function (r) {
				if (r.message) {
					me.render_user_details(r.message);
				}
			},
		});
	}

	render_user_details(data) {
		const me = this;
		me.current_user_data = data;

		const html = `
			<div class="user-details">
				<div class="user-header">
					<h3>${data.user_name}</h3>
					<span class="text-muted">${data.user}</span>
					<span class="label label-${data.enabled ? "success" : "danger"}">
						${data.enabled ? "Active" : "Inactive"}
					</span>
				</div>

				<!-- Summary Cards -->
				<div class="row summary-cards">
					<div class="col-md-3">
						<div class="summary-card">
							<div class="number">${data.permission_summary.total_roles}</div>
							<div class="label">Roles</div>
						</div>
					</div>
					<div class="col-md-3">
						<div class="summary-card">
							<div class="number">${data.permission_summary.can_read}</div>
							<div class="label">Can Read</div>
						</div>
					</div>
					<div class="col-md-3">
						<div class="summary-card">
							<div class="number">${data.permission_summary.can_write}</div>
							<div class="label">Can Write</div>
						</div>
					</div>
					<div class="col-md-3">
						<div class="summary-card">
							<div class="number">${data.permission_summary.user_permission_count}</div>
							<div class="label">Filters</div>
						</div>
					</div>
				</div>

				<!-- Action Buttons -->
				<div class="action-buttons">
					<button class="btn btn-default btn-sm btn-copy-to" data-user="${data.user}">
						<i class="fa fa-copy"></i> Copy To...
					</button>
					<button class="btn btn-default btn-sm btn-export-user" data-user="${data.user}">
						<i class="fa fa-download"></i> Export
					</button>
					<button class="btn btn-default btn-sm btn-edit-user" data-user="${data.user}">
						<i class="fa fa-edit"></i> Edit User
					</button>
				</div>

				<!-- Roles Section -->
				<div class="section">
					<h4><i class="fa fa-key"></i> Assigned Roles (${data.roles.length})</h4>
					<div class="roles-list">
						${data.roles.map((r) => `<span class="role-tag">${r} <i class="fa fa-times remove-role" data-role="${r}" data-user="${data.user}" style="cursor:pointer; margin-left:4px; opacity:0.6;"></i></span>`).join("")}
						<span class="role-tag add-role-btn" data-user="${data.user}" style="cursor:pointer; border-style:dashed; opacity:0.7;"><i class="fa fa-plus"></i> Add Role</span>
					</div>
				</div>

				<!-- Role Profile -->
				<div class="section">
					<h4><i class="fa fa-id-card"></i> Role Profile</h4>
					<div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
						<span class="role-profile-display">${data.role_profile ? data.role_profile.name : '<span class="text-muted">None</span>'}</span>
						<button class="btn btn-xs btn-default change-role-profile" data-user="${data.user}"><i class="fa fa-pencil"></i> Change</button>
						${data.role_profile ? `<button class="btn btn-xs btn-danger-light remove-role-profile" data-user="${data.user}"><i class="fa fa-times"></i> Remove</button>` : ""}
					</div>
					${data.role_profile ? `
					<div class="roles-list" style="margin-top: 8px;">
						${data.role_profile.roles.map((r) => `<span class="role-tag secondary">${r}</span>`).join("")}
					</div>
					` : ""}
				</div>

				<!-- User Permissions Section -->
				<div class="section">
					<h4 style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
						<span><i class="fa fa-filter"></i> User Permissions (Document Filters)</span>
						<div class="add-user-perm-doctype-inline" style="display: inline-block; width: 150px;"></div>
						<div class="add-user-perm-value-inline" style="display: inline-block; width: 180px;"></div>
					</h4>
					${
						Object.keys(data.user_permissions).length > 0
							? `
					<table class="table table-bordered table-sm">
						<thead>
							<tr>
								<th>DocType</th>
								<th>Allowed Values</th>
								<th style="width: 30px;"></th>
							</tr>
						</thead>
						<tbody>
							${Object.entries(data.user_permissions)
								.map(
									([doctype, perms]) => `
								<tr>
									<td><strong>${doctype}</strong></td>
									<td>${perms.map((p) => `<span class="badge" style="display: inline-flex; align-items: center; gap: 4px;">${p.for_value} <i class="fa fa-times remove-user-perm" data-name="${p.name}" style="cursor:pointer; opacity:0.6;"></i></span>`).join(" ")}</td>
									<td class="text-center">
										<i class="fa fa-plus add-user-perm-value" data-doctype="${doctype}" data-user="${data.user}" style="cursor:pointer; opacity:0.5;" title="Add value for ${doctype}"></i>
									</td>
								</tr>
							`
								)
								.join("")}
						</tbody>
					</table>
					`
							: '<p class="text-muted">No user permissions set</p>'
					}
				</div>

				<!-- Effective Permissions Section -->
				<div class="section">
					<h4 style="display: flex; align-items: center; gap: 10px;">
						<span><i class="fa fa-check-circle"></i> Effective Permissions (${Object.keys(data.effective_permissions).length} DocTypes)</span>
						<div class="add-doctype-inline" style="display: inline-block; width: 200px;"></div>
					</h4>
					<div class="permission-matrix" style="max-height: 500px; overflow-y: auto;">
						<table class="table table-bordered table-sm">
							<thead>
								<tr>
									<th>DocType</th>
									<th title="Select">Sel</th>
									<th title="Read">R</th>
									<th title="Write">W</th>
									<th title="Create">C</th>
									<th title="Delete">D</th>
									<th title="Submit">Sub</th>
									<th title="Cancel">Can</th>
									<th title="Print">Prt</th>
									<th title="Email">Eml</th>
									<th title="Report">Rep</th>
									<th title="Import">Imp</th>
									<th title="Export">Exp</th>
									<th title="Share">Shr</th>
									<th></th>
								</tr>
							</thead>
							<tbody>
								${Object.entries(data.effective_permissions)
									.map(
										([doctype, perm]) => `
									<tr>
										<td>${doctype}</td>
										${["select", "read", "write", "create", "delete", "submit", "cancel", "print", "email", "report", "import", "export", "share"].map(
											(p) => `<td class="text-center perm-toggle" style="cursor: pointer;"
												data-doctype="${doctype}"
												data-perm="${p}"
												data-value="${perm[p] ? 1 : 0}"
												data-roles='${JSON.stringify(perm.roles || [])}'
												title="Click to toggle ${p} — Roles: ${(perm.roles || []).join(", ")}">
												${me.perm_icon(perm[p])}</td>`
										).join("")}
										<td class="text-center">
											<i class="fa fa-trash text-danger remove-doctype-perm" style="cursor:pointer; opacity:0.5;"
												data-doctype="${doctype}"
												data-roles='${JSON.stringify(perm.roles || [])}'
												title="Remove all permissions for ${doctype}"></i>
										</td>
									</tr>
								`
									)
									.join("")}
							</tbody>
						</table>
					</div>
				</div>
			</div>
		`;

		this.wrapper.find("#user-details").html(html);

		// Bind button events after rendering
		this.wrapper.find(".btn-copy-to").on("click", function () {
			me.show_copy_dialog($(this).data("user"));
		});

		this.wrapper.find(".btn-export-user").on("click", function () {
			me.export_user_permissions($(this).data("user"));
		});

		this.wrapper.find(".btn-edit-user").on("click", function () {
			frappe.set_route("Form", "User", $(this).data("user"));
		});

		// Remove role
		this.wrapper.find(".remove-role").on("click", function (e) {
			e.stopPropagation();
			const role = $(this).data("role");
			const user = $(this).data("user");
			frappe.confirm(
				__("Remove role <b>{0}</b> from this user?", [role]),
				function () {
					frappe.call({
						method: "frappe_role_manager.frappe_role_manager.api.view.remove_user_role",
						args: { user: user, role: role },
						callback: function (r) {
							if (r.message && r.message.status === "success") {
								me.load_user_details(user);
							}
						},
					});
				}
			);
		});

		// Add role
		this.wrapper.find(".add-role-btn").on("click", function () {
			const user = $(this).data("user");
			frappe.call({
				method: "frappe_role_manager.frappe_role_manager.api.view.get_assignable_roles",
				callback: function (r) {
					if (r.message) {
						frappe.prompt(
							{
								fieldtype: "Autocomplete",
								fieldname: "role",
								label: __("Role"),
								options: r.message,
								reqd: 1,
							},
							function (values) {
								frappe.call({
									method: "frappe_role_manager.frappe_role_manager.api.view.add_user_role",
									args: { user: user, role: values.role },
									callback: function (r2) {
										if (r2.message && r2.message.status === "success") {
											me.load_user_details(user);
										}
									},
								});
							},
							__("Add Role"),
							__("Add")
						);
					}
				},
			});
		});

		// Change Role Profile
		this.wrapper.find(".change-role-profile").on("click", function () {
			const user = $(this).data("user");
			frappe.call({
				method: "frappe_role_manager.frappe_role_manager.api.view.get_all_role_profiles",
				callback: function (r) {
					if (r.message) {
						frappe.prompt(
							{
								fieldtype: "Autocomplete",
								fieldname: "role_profile",
								label: __("Role Profile"),
								options: r.message,
								reqd: 1,
							},
							function (values) {
								frappe.call({
									method: "frappe_role_manager.frappe_role_manager.api.view.change_role_profile",
									args: { user: user, role_profile_name: values.role_profile },
									callback: function (r2) {
										if (r2.message && r2.message.status === "success") {
											me.load_user_details(user);
										}
									},
								});
							},
							__("Change Role Profile"),
							__("Apply")
						);
					}
				},
			});
		});

		// Remove Role Profile
		this.wrapper.find(".remove-role-profile").on("click", function () {
			const user = $(this).data("user");
			frappe.confirm(
				__("Remove the Role Profile from this user? The user will keep their current roles."),
				function () {
					frappe.call({
						method: "frappe_role_manager.frappe_role_manager.api.view.change_role_profile",
						args: { user: user, role_profile_name: "" },
						callback: function (r) {
							if (r.message && r.message.status === "success") {
								me.load_user_details(user);
							}
						},
					});
				}
			);
		});

		// Remove a single User Permission value
		this.wrapper.find(".remove-user-perm").on("click", function () {
			const name = $(this).data("name");
			$(this).closest(".badge").fadeOut(200);
			frappe.call({
				method: "frappe_role_manager.frappe_role_manager.api.view.delete_user_permission",
				args: { name: name },
				callback: function () {
					me.load_user_details(me.selected_user);
				},
			});
		});

		// Add a new value to an existing User Permission DocType (inline + icon)
		this.wrapper.find(".add-user-perm-value").on("click", function () {
			const doctype = $(this).data("doctype");
			const user = $(this).data("user");
			const $td = $(this).closest("td");

			// Replace icon with inline Link field
			$td.html("");
			const valField = frappe.ui.form.make_control({
				df: {
					fieldtype: "Link",
					fieldname: "add_value_" + doctype,
					options: doctype,
					placeholder: __("Add {0}...", [doctype]),
				},
				parent: $td,
				render_input: true,
			});
			valField.$input.css({ height: "26px", "font-size": "11px", width: "140px" });
			valField.$input.focus();
			valField.$input.on("change", function () {
				const for_value = valField.get_value();
				if (!for_value) return;
				frappe.call({
					method: "frappe_role_manager.frappe_role_manager.api.view.add_user_permission",
					args: { user: user, allow: doctype, for_value: for_value },
					callback: function (r) {
						if (r.message && r.message.status === "success") {
							me.load_user_details(user);
						}
					},
				});
			});
		});

		// Inline DocType + Value fields for adding new User Permission
		let selectedPermDoctype = "";

		const userPermDoctype = frappe.ui.form.make_control({
			df: {
				fieldtype: "Link",
				fieldname: "user_perm_doctype",
				options: "DocType",
				placeholder: __("Select DocType..."),
				get_query: function () {
					return { filters: { istable: 0 } };
				},
			},
			parent: this.wrapper.find(".add-user-perm-doctype-inline"),
			render_input: true,
		});
		userPermDoctype.$input.css({ height: "28px", "font-size": "12px" });

		const $valueParent = this.wrapper.find(".add-user-perm-value-inline");

		function renderValueField(doctype) {
			$valueParent.empty();
			if (!doctype) {
				$valueParent.html('<input class="form-control" disabled placeholder="Select DocType first..." style="height:28px; font-size:12px;">');
				return;
			}
			const valCtrl = frappe.ui.form.make_control({
				df: {
					fieldtype: "Link",
					fieldname: "user_perm_value_" + doctype,
					options: doctype,
					placeholder: __("Select {0} & press Enter", [doctype]),
				},
				parent: $valueParent,
				render_input: true,
			});
			valCtrl.$input.css({ height: "28px", "font-size": "12px" });
			valCtrl.$input.focus();
			valCtrl.$input.on("change", function () {
				const val = valCtrl.get_value();
				if (!val) return;
				frappe.call({
					method: "frappe_role_manager.frappe_role_manager.api.view.add_user_permission",
					args: { user: me.selected_user, allow: doctype, for_value: val },
					callback: function (r) {
						if (r.message && r.message.status === "success") {
							frappe.show_alert({ message: __("✓ Added filter {0}: {1}", [doctype, val]), indicator: "green" });
							me.load_user_details(me.selected_user);
						}
					},
				});
			});
		}

		// Initialize with disabled value field
		renderValueField("");

		// When DocType is selected, recreate the value field with correct options
		userPermDoctype.$input.on("change", function () {
			selectedPermDoctype = userPermDoctype.get_value();
			renderValueField(selectedPermDoctype);
		});

		// Bind permission toggle clicks
		this.wrapper.find(".perm-toggle").on("click", function () {
			const $cell = $(this);
			const doctype = $cell.data("doctype");
			const permType = $cell.data("perm");
			const currentValue = parseInt($cell.data("value"));
			const roles = $cell.data("roles") || [];
			const newValue = currentValue ? 0 : 1;

			function doToggle(role) {
				// Optimistic UI update
				$cell.data("value", newValue);
				$cell.html(me.perm_icon(newValue));

				frappe.call({
					method: "frappe_role_manager.frappe_role_manager.api.view.toggle_doctype_permission",
					args: {
						doctype: doctype,
						role: role,
						permission_type: permType,
						enabled: newValue,
					},
					callback: function (r) {
						if (!r.message || r.message.status !== "success") {
							// Revert on failure
							$cell.data("value", currentValue);
							$cell.html(me.perm_icon(currentValue));
							frappe.msgprint(__("Failed to update permission"));
						}
					},
					error: function () {
						$cell.data("value", currentValue);
						$cell.html(me.perm_icon(currentValue));
					},
				});
			}

			if (roles.length === 0) {
				frappe.msgprint(__("No role found for this DocType"));
				return;
			}

			if (roles.length === 1) {
				doToggle(roles[0]);
			} else {
				// Multiple roles — ask which one to modify
				frappe.prompt(
					{
						fieldtype: "Select",
						fieldname: "role",
						label: __("Select Role to Modify"),
						options: roles.join("\n"),
						reqd: 1,
						default: roles[0],
						description: __("Multiple roles grant access to {0}. Select which role to modify.", [doctype]),
					},
					function (values) {
						doToggle(values.role);
					},
					__("Select Role"),
					__("Update")
				);
			}
		});

		// Remove DocType permissions (no confirmation)
		this.wrapper.find(".remove-doctype-perm").on("click", function () {
			const $row = $(this).closest("tr");
			const doctype = $(this).data("doctype");
			const roles = $(this).data("roles") || [];

			if (roles.length === 0) return;

			$row.fadeOut(200);
			roles.forEach(function (role) {
				frappe.call({
					method: "frappe_role_manager.frappe_role_manager.api.view.remove_doctype_permission",
					args: { doctype: doctype, role: role },
					async: false,
				});
			});
			frappe.show_alert({ message: __("Removed {0}", [doctype]), indicator: "green" });
			me.load_user_details(me.selected_user);
		});

		// Inline Add DocType field
		const addDoctypeField = frappe.ui.form.make_control({
			df: {
				fieldtype: "Link",
				fieldname: "add_doctype",
				options: "DocType",
				placeholder: __("Search DocType & press Enter"),
				get_query: function () {
					return { filters: { istable: 0 } };
				},
			},
			parent: this.wrapper.find(".add-doctype-inline"),
			render_input: true,
		});
		addDoctypeField.$input.css({ height: "28px", "font-size": "12px" });
		addDoctypeField.$input.on("change", function () {
			const doctype = addDoctypeField.get_value();
			if (!doctype) return;

			// Check if already exists
			const existingDoctypes = me.current_user_data ? Object.keys(me.current_user_data.effective_permissions || {}) : [];
			if (existingDoctypes.includes(doctype)) {
				frappe.show_alert({ message: __("{0} already exists in permissions", [doctype]), indicator: "orange" });
				addDoctypeField.set_value("");
				return;
			}

			const userRoles = me.current_user_data ? me.current_user_data.roles : [];
			const role = userRoles[0] || "";
			if (!role) {
				frappe.show_alert({ message: __("User has no roles. Add a role first."), indicator: "orange" });
				addDoctypeField.set_value("");
				return;
			}
			frappe.call({
				method: "frappe_role_manager.frappe_role_manager.api.view.add_doctype_permission",
				args: {
					doctype: doctype,
					role: role,
					permissions: JSON.stringify({ read: 1 }),
				},
				callback: function (r) {
					if (r.message && r.message.status === "success") {
						frappe.show_alert({ message: __("✓ Added {0} with Read permission on role {1}", [doctype, role]), indicator: "green" });
						me.load_user_details(me.selected_user);
					}
				},
			});
			addDoctypeField.set_value("");
		});
	}

	perm_icon(value) {
		return value
			? '<i class="fa fa-check text-success"></i>'
			: '<i class="fa fa-times text-muted"></i>';
	}

	load_roles() {
		const me = this;

		frappe.call({
			method: "frappe_role_manager.frappe_role_manager.api.view.get_all_roles",
			callback: function (r) {
				if (r.message) {
					me.roles = r.message;
					me.render_role_list();
					me.populate_role_selects();
				}
			},
		});
	}

	render_role_list() {
		const me = this;
		const search = this.wrapper.find("#role-search").val().toLowerCase();

		let roles = this.roles;
		if (search) {
			roles = roles.filter((r) => r.name.toLowerCase().includes(search));
		}

		const html = roles
			.map(
				(r) => `
			<div class="role-item ${me.selected_role === r.name ? "selected" : ""}"
				 data-role="${r.name}">
				<div class="role-info">
					<div class="role-name">${r.name}</div>
					<div class="role-meta text-muted">
						${r.is_custom ? '<span class="label label-info">Custom</span>' : ""}
						${r.desk_access ? '<span class="label label-default">Desk</span>' : ""}
					</div>
				</div>
			</div>
		`
			)
			.join("");

		this.wrapper.find("#role-list").html(html);

		// Bind click events
		this.wrapper.find(".role-item").on("click", function () {
			me.select_role($(this).data("role"));
		});
	}

	filter_roles() {
		this.render_role_list();
	}

	select_role(role) {
		this.selected_role = role;
		this.render_role_list();
		this.load_role_details(role);
	}

	load_role_details(role) {
		const me = this;

		frappe.call({
			method: "frappe_role_manager.frappe_role_manager.api.clone.get_role_details",
			args: { role: role },
			callback: function (r) {
				if (r.message) {
					me.render_role_details(r.message);
				}
			},
		});
	}

	render_role_details(data) {
		const me = this;

		const html = `
			<div class="role-details">
				<div class="role-header">
					<h3>${data.role}</h3>
					<span class="label label-${data.is_custom ? "info" : "default"}">
						${data.is_custom ? "Custom" : "Standard"}
					</span>
					<span class="label label-${data.desk_access ? "success" : "warning"}">
						${data.desk_access ? "Desk Access" : "No Desk Access"}
					</span>
				</div>

				<!-- Action Buttons -->
				<div class="action-buttons">
					<button class="btn btn-default btn-sm btn-clone-role" data-role="${data.role}">
						<i class="fa fa-clone"></i> Clone Role
					</button>
					<button class="btn btn-default btn-sm btn-view-users" data-role="${data.role}">
						<i class="fa fa-users"></i> View Users
					</button>
					<button class="btn btn-default btn-sm btn-perm-manager">
						<i class="fa fa-cog"></i> Permission Manager
					</button>
				</div>

				<!-- Summary -->
				<div class="row summary-cards">
					<div class="col-md-6">
						<div class="summary-card">
							<div class="number">${data.doctype_count}</div>
							<div class="label">DocTypes</div>
						</div>
					</div>
					<div class="col-md-6">
						<div class="summary-card">
							<div class="number">${data.total_permissions}</div>
							<div class="label">Permissions</div>
						</div>
					</div>
				</div>

				<!-- Permissions Matrix -->
				<div class="section">
					<h4><i class="fa fa-table"></i> Permission Matrix</h4>
					<table class="table table-bordered table-sm">
						<thead>
							<tr>
								<th>DocType</th>
								<th>R</th>
								<th>W</th>
								<th>C</th>
								<th>D</th>
								<th>Submit</th>
								<th>Cancel</th>
								<th>Export</th>
								<th>Import</th>
							</tr>
						</thead>
						<tbody>
							${Object.entries(data.permissions)
								.map(
									([doctype, perms]) => `
								<tr>
									<td>${doctype}</td>
									<td>${me.perm_icon(perms[0]?.read)}</td>
									<td>${me.perm_icon(perms[0]?.write)}</td>
									<td>${me.perm_icon(perms[0]?.create)}</td>
									<td>${me.perm_icon(perms[0]?.delete)}</td>
									<td>${me.perm_icon(perms[0]?.submit)}</td>
									<td>${me.perm_icon(perms[0]?.cancel)}</td>
									<td>${me.perm_icon(perms[0]?.export)}</td>
									<td>${me.perm_icon(perms[0]?.import)}</td>
								</tr>
							`
								)
								.join("")}
						</tbody>
					</table>
				</div>
			</div>
		`;

		this.wrapper.find("#role-details").html(html);

		// Bind button events after rendering
		this.wrapper.find(".btn-clone-role").on("click", function () {
			me.show_clone_dialog($(this).data("role"));
		});

		this.wrapper.find(".btn-view-users").on("click", function () {
			me.show_users_with_role($(this).data("role"));
		});

		this.wrapper.find(".btn-perm-manager").on("click", function () {
			frappe.set_route("permission-manager");
		});
	}

	populate_user_selects() {
		const options = this.users
			.map((u) => `<option value="${u.name}">${u.full_name || u.name}</option>`)
			.join("");

		this.wrapper.find("#compare-a, #compare-b, #copy-source, #copy-target").html(
			`<option value="">Select User...</option>${options}`
		);
	}

	populate_role_selects() {
		const options = this.roles.map((r) => `<option value="${r.name}">${r.name}</option>`).join("");

		this.wrapper.find("#bulk-role").html(`<option value="">Select Role...</option>${options}`);
	}

	load_filter_options() {
		const me = this;

		frappe.call({
			method: "frappe_role_manager.frappe_role_manager.api.bulk.get_filter_options",
			callback: function (r) {
				if (r.message) {
					me.filter_options = r.message;
				}
			},
		});
	}

	update_bulk_filter_values(filter_type) {
		const me = this;
		const $group = this.wrapper.find("#bulk-filter-value-group");
		const $select = this.wrapper.find("#bulk-filter-value");

		if (!filter_type) {
			$group.hide();
			return;
		}

		$group.show();

		let options = [];
		if (filter_type === "department") {
			options = me.filter_options.departments || [];
		} else if (filter_type === "company") {
			options = me.filter_options.companies || [];
		} else if (filter_type === "role") {
			options = me.filter_options.roles || [];
		}

		$select.html(
			`<option value="">Select...</option>` +
				options.map((o) => `<option value="${o}">${o}</option>`).join("")
		);
	}

	preview_bulk_operation() {
		const me = this;
		const role = this.wrapper.find("#bulk-role").val();
		const action = this.wrapper.find("#bulk-action").val();
		const filter_type = this.wrapper.find("#bulk-filter-type").val();
		const filter_value = this.wrapper.find("#bulk-filter-value").val();

		if (!role) {
			frappe.msgprint(__("Please select a role"));
			return;
		}

		const args = { role: role, action: action };
		if (filter_type && filter_value) {
			args[filter_type] = filter_value;
		}

		frappe.call({
			method: "frappe_role_manager.frappe_role_manager.api.bulk.preview_bulk_role_assignment",
			args: args,
			callback: function (r) {
				if (r.message) {
					me.render_bulk_preview(r.message);
					me.bulk_preview_data = { ...args };
				}
			},
		});
	}

	render_bulk_preview(data) {
		const html = `
			<div class="preview-results">
				<h5>Preview Results</h5>
				<p><strong>Action:</strong> ${data.action === "add" ? "Add" : "Remove"} role <strong>${data.role}</strong></p>
				<p><strong>Will Change:</strong> ${data.summary.will_change} users</p>
				<p><strong>Already Done:</strong> ${data.summary.already_done} users</p>
				${
					data.will_change.length > 0
						? `
				<div class="preview-list">
					<strong>Users to modify:</strong>
					<ul>
						${data.will_change.slice(0, 10).map((u) => `<li>${u.name} (${u.user})</li>`).join("")}
						${data.will_change.length > 10 ? `<li>... and ${data.will_change.length - 10} more</li>` : ""}
					</ul>
				</div>
				`
						: ""
				}
			</div>
		`;

		this.wrapper.find("#bulk-preview").html(html);
		this.wrapper.find("#btn-bulk-execute").prop("disabled", data.will_change.length === 0);
	}

	execute_bulk_operation() {
		const me = this;

		frappe.confirm(
			__("Are you sure you want to execute this bulk operation?"),
			function () {
				frappe.call({
					method: "frappe_role_manager.frappe_role_manager.api.bulk.execute_bulk_role_assignment",
					args: me.bulk_preview_data,
					callback: function (r) {
						if (r.message && r.message.status === "success") {
							frappe.msgprint(
								__("Operation completed. {0} users modified.", [r.message.results.success])
							);
							me.refresh();
							me.wrapper.find("#bulk-preview").html("");
							me.wrapper.find("#btn-bulk-execute").prop("disabled", true);
						}
					},
				});
			}
		);
	}

	preview_copy_operation() {
		const me = this;
		const source = this.wrapper.find("#copy-source").val();
		const target = this.wrapper.find("#copy-target").val();

		if (!source || !target) {
			frappe.msgprint(__("Please select both source and target users"));
			return;
		}

		if (source === target) {
			frappe.msgprint(__("Source and target users must be different"));
			return;
		}

		frappe.call({
			method: "frappe_role_manager.frappe_role_manager.api.copy.preview_copy",
			args: {
				source_user: source,
				target_user: target,
				copy_roles: this.wrapper.find("#copy-roles").is(":checked"),
				copy_user_permissions: this.wrapper.find("#copy-user-perms").is(":checked"),
				copy_role_profile: this.wrapper.find("#copy-role-profile").is(":checked"),
			},
			callback: function (r) {
				if (r.message) {
					me.render_copy_preview(r.message);
					me.copy_preview_data = r.message;
				}
			},
		});
	}

	render_copy_preview(data) {
		const html = `
			<div class="preview-results">
				<h5>Preview Results</h5>
				<p><strong>Source:</strong> ${data.source_user_name}</p>
				<p><strong>Target:</strong> ${data.target_user_name}</p>
				<hr>
				<p><strong>Roles to add:</strong> ${data.summary.roles_to_add}</p>
				<p><strong>User permissions to add:</strong> ${data.summary.user_permissions_to_add}</p>
				<p><strong>Role profile change:</strong> ${data.summary.role_profile_change ? "Yes" : "No"}</p>
				${
					data.roles.add.length > 0
						? `
				<div class="preview-list">
					<strong>Roles to add:</strong>
					${data.roles.add.map((r) => `<span class="badge">${r}</span>`).join(" ")}
				</div>
				`
						: ""
				}
			</div>
		`;

		this.wrapper.find("#copy-preview").html(html);
		this.wrapper.find("#btn-copy-execute").prop("disabled",
			data.summary.roles_to_add === 0 &&
			data.summary.user_permissions_to_add === 0 &&
			!data.summary.role_profile_change &&
			!data.summary.module_profile_change
		);
	}

	execute_copy_operation() {
		const me = this;
		const source = this.wrapper.find("#copy-source").val();
		const target = this.wrapper.find("#copy-target").val();

		frappe.confirm(
			__("Are you sure you want to copy permissions from {0} to {1}?", [source, target]),
			function () {
				frappe.call({
					method: "frappe_role_manager.frappe_role_manager.api.copy.execute_copy",
					args: {
						source_user: source,
						target_user: target,
						copy_roles: me.wrapper.find("#copy-roles").is(":checked"),
						copy_user_permissions: me.wrapper.find("#copy-user-perms").is(":checked"),
						copy_role_profile: me.wrapper.find("#copy-role-profile").is(":checked"),
					},
					callback: function (r) {
						if (r.message && r.message.status === "success") {
							frappe.msgprint(__("Permissions copied successfully!"));
							me.refresh();
							me.wrapper.find("#copy-preview").html("");
							me.wrapper.find("#btn-copy-execute").prop("disabled", true);
						}
					},
				});
			}
		);
	}

	run_comparison() {
		const me = this;
		const user_a = this.wrapper.find("#compare-a").val();
		const user_b = this.wrapper.find("#compare-b").val();

		if (!user_a || !user_b) {
			frappe.msgprint(__("Please select both users to compare"));
			return;
		}

		frappe.call({
			method: "frappe_role_manager.frappe_role_manager.api.compare.compare_users",
			args: { user_a: user_a, user_b: user_b },
			callback: function (r) {
				if (r.message) {
					me.render_comparison(r.message);
				}
			},
		});
	}

	render_comparison(data) {
		const html = `
			<div class="comparison-results">
				<h4>Comparison Results</h4>
				<div class="similarity-score">
					<div class="score">${data.similarity_score}%</div>
					<div class="label">Similarity</div>
				</div>

				<div class="row">
					<div class="col-md-6">
						<h5>${data.user_a.full_name}</h5>
					</div>
					<div class="col-md-6">
						<h5>${data.user_b.full_name}</h5>
					</div>
				</div>

				<!-- Roles Comparison -->
				<div class="comparison-section">
					<h5>Roles</h5>
					<div class="row">
						<div class="col-md-4">
							<strong>Only in ${data.user_a.full_name}:</strong>
							<div class="tag-list">
								${data.roles.only_a.map((r) => `<span class="badge badge-danger">${r}</span>`).join(" ") || "<em>None</em>"}
							</div>
						</div>
						<div class="col-md-4">
							<strong>Common:</strong>
							<div class="tag-list">
								${data.roles.common.map((r) => `<span class="badge badge-success">${r}</span>`).join(" ") || "<em>None</em>"}
							</div>
						</div>
						<div class="col-md-4">
							<strong>Only in ${data.user_b.full_name}:</strong>
							<div class="tag-list">
								${data.roles.only_b.map((r) => `<span class="badge badge-warning">${r}</span>`).join(" ") || "<em>None</em>"}
							</div>
						</div>
					</div>
				</div>

				<!-- User Permissions Comparison -->
				<div class="comparison-section">
					<h5>User Permissions</h5>
					<div class="row">
						<div class="col-md-4">
							<strong>Only in ${data.user_a.full_name}:</strong>
							<div class="tag-list">
								${data.user_permissions.only_a.map((p) => `<span class="badge">${p.allow}: ${p.for_value}</span>`).join(" ") || "<em>None</em>"}
							</div>
						</div>
						<div class="col-md-4">
							<strong>Common:</strong>
							<div class="tag-list">
								${data.user_permissions.common.map((p) => `<span class="badge badge-success">${p.allow}: ${p.for_value}</span>`).join(" ") || "<em>None</em>"}
							</div>
						</div>
						<div class="col-md-4">
							<strong>Only in ${data.user_b.full_name}:</strong>
							<div class="tag-list">
								${data.user_permissions.only_b.map((p) => `<span class="badge">${p.allow}: ${p.for_value}</span>`).join(" ") || "<em>None</em>"}
							</div>
						</div>
					</div>
				</div>
			</div>
		`;

		this.wrapper.find("#compare-results").html(html);
	}

	show_export_dialog() {
		const me = this;

		const d = new frappe.ui.Dialog({
			title: __("Export Permissions"),
			fields: [
				{
					fieldtype: "Check",
					fieldname: "export_roles",
					label: __("Export Role Permissions"),
					default: 1,
				},
				{
					fieldtype: "Check",
					fieldname: "export_user_permissions",
					label: __("Export User Permissions"),
					default: 1,
				},
				{
					fieldtype: "Check",
					fieldname: "export_role_assignments",
					label: __("Export Role Assignments"),
					default: 1,
				},
				{
					fieldtype: "Select",
					fieldname: "format",
					label: __("Format"),
					options: "JSON\nExcel",
					default: "JSON",
				},
				{
					fieldtype: "Link",
					fieldname: "user_filter",
					label: __("Filter by User (optional)"),
					options: "User",
				},
				{
					fieldtype: "Link",
					fieldname: "role_filter",
					label: __("Filter by Role (optional)"),
					options: "Role",
				},
			],
			primary_action_label: __("Export"),
			primary_action: function (values) {
				frappe.call({
					method: "frappe_role_manager.frappe_role_manager.api.export.export_permissions",
					args: {
						users: values.user_filter ? [values.user_filter] : null,
						roles: values.role_filter ? [values.role_filter] : null,
						export_roles: values.export_roles,
						export_user_permissions: values.export_user_permissions,
						export_role_assignments: values.export_role_assignments,
						format: values.format.toLowerCase(),
					},
					callback: function (r) {
						if (r.message) {
							if (r.message.format === "excel") {
								window.open(r.message.file_url);
							} else {
								// Download JSON
								const blob = new Blob([JSON.stringify(r.message.data, null, 2)], {
									type: "application/json",
								});
								const url = URL.createObjectURL(blob);
								const a = document.createElement("a");
								a.href = url;
								a.download = `permissions_export_${frappe.datetime.now_date()}.json`;
								a.click();
							}
							frappe.msgprint(__("Export completed. Snapshot saved: {0}", [r.message.snapshot]));
						}
					},
				});
				d.hide();
			},
		});

		d.show();
	}

	show_import_dialog() {
		const me = this;

		const d = new frappe.ui.Dialog({
			title: __("Import Permissions"),
			fields: [
				{
					fieldtype: "Attach",
					fieldname: "file",
					label: __("Upload File (JSON or Excel)"),
					reqd: 1,
				},
				{
					fieldtype: "Check",
					fieldname: "create_backup",
					label: __("Create backup before import"),
					default: 1,
				},
				{
					fieldtype: "Check",
					fieldname: "skip_errors",
					label: __("Skip errors and continue"),
					default: 0,
				},
			],
			primary_action_label: __("Preview"),
			primary_action: function (values) {
				frappe.call({
					method: "frappe_role_manager.frappe_role_manager.api.import_permissions.preview_import",
					args: { file_url: values.file },
					callback: function (r) {
						if (r.message) {
							me.show_import_preview_dialog(r.message, values);
						}
					},
				});
				d.hide();
			},
		});

		d.show();
	}

	show_import_preview_dialog(preview, import_options) {
		const me = this;

		const d = new frappe.ui.Dialog({
			title: __("Import Preview"),
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "preview_html",
				},
			],
			primary_action_label: __("Apply Import"),
			primary_action: function () {
				frappe.call({
					method: "frappe_role_manager.frappe_role_manager.api.import_permissions.execute_import",
					args: {
						file_url: import_options.file,
						create_backup: import_options.create_backup,
						skip_errors: import_options.skip_errors,
					},
					callback: function (r) {
						if (r.message && r.message.status === "success") {
							frappe.msgprint(__("Import completed successfully!"));
							me.refresh();
						} else if (r.message) {
							frappe.msgprint(__("Import failed: {0}", [r.message.message]));
						}
					},
				});
				d.hide();
			},
		});

		const html = `
			<div class="import-preview">
				<h5>Summary</h5>
				<table class="table table-bordered">
					<tr>
						<td>Role Permissions to Add</td>
						<td>${preview.summary.role_permissions_add}</td>
					</tr>
					<tr>
						<td>Role Permissions to Update</td>
						<td>${preview.summary.role_permissions_update}</td>
					</tr>
					<tr>
						<td>User Permissions to Add</td>
						<td>${preview.summary.user_permissions_add}</td>
					</tr>
					<tr>
						<td>Role Assignments to Add</td>
						<td>${preview.summary.role_assignments_add}</td>
					</tr>
					<tr>
						<td>Total Errors</td>
						<td class="${preview.summary.total_errors > 0 ? "text-danger" : ""}">${preview.summary.total_errors}</td>
					</tr>
				</table>
				${
					preview.validation.errors.length > 0
						? `
				<div class="alert alert-danger">
					<strong>Errors:</strong>
					<ul>
						${preview.validation.errors.slice(0, 10).map((e) => `<li>${e}</li>`).join("")}
					</ul>
				</div>
				`
						: ""
				}
				${!preview.can_proceed ? '<div class="alert alert-warning">Cannot proceed due to errors. Fix the file and try again.</div>' : ""}
			</div>
		`;

		d.fields_dict.preview_html.$wrapper.html(html);
		d.set_primary_action_enabled(preview.can_proceed);
		d.show();
	}

	download_template() {
		frappe.call({
			method: "frappe_role_manager.frappe_role_manager.api.export.download_template",
			args: { template_type: "full" },
			callback: function (r) {
				if (r.message && r.message.file_url) {
					window.open(r.message.file_url);
				}
			},
		});
	}

	show_copy_dialog(user) {
		const me = this;

		const d = new frappe.ui.Dialog({
			title: __("Copy Permissions to Another User"),
			size: "large",
			fields: [
				{
					fieldtype: "Link",
					fieldname: "target_user",
					label: __("Target User"),
					options: "User",
					reqd: 1,
					get_query: function () {
						return {
							filters: {
								enabled: 1,
								name: ["not in", ["Administrator", "Guest"]],
								user_type: ["in", ["System User", "Website User"]],
							},
						};
					},
					onchange: function () {
						const target = d.get_value("target_user");
						if (target) {
							me.load_roles_for_cherry_pick(d, user, target);
						}
					},
				},
				{
					fieldtype: "Section Break",
					fieldname: "roles_section",
					label: __("Cherry-Pick Roles"),
				},
				{
					fieldtype: "Check",
					fieldname: "copy_roles",
					label: __("Copy Roles"),
					default: 1,
					onchange: function () {
						const copy_roles = d.get_value("copy_roles");
						d.fields_dict.roles_html.$wrapper.toggle(copy_roles);
					},
				},
				{
					fieldtype: "HTML",
					fieldname: "roles_html",
				},
				{
					fieldtype: "Section Break",
					label: __("Other Permissions"),
				},
				{
					fieldtype: "Check",
					fieldname: "copy_user_permissions",
					label: __("Copy User Permissions (Document Filters)"),
					default: 1,
				},
				{
					fieldtype: "Check",
					fieldname: "create_role_profile",
					label: __("Create New Role Profile"),
					default: 1,
					description: __("Creates a new Role Profile containing the custom role and selected roles, then assigns it to the target user"),
				},
				{
					fieldtype: "Data",
					fieldname: "role_profile_name",
					label: __("Role Profile Name"),
					depends_on: "create_role_profile",
					mandatory_depends_on: "create_role_profile",
					description: __("A unique name for the new Role Profile"),
				},
				{
					fieldtype: "Section Break",
					label: __("Custom Role"),
				},
				{
					fieldtype: "Data",
					fieldname: "custom_role_name",
					label: __("Custom Role Name"),
					reqd: 1,
					description: __("A unique name for the new custom role that will be created with the selected DocType permissions"),
				},
			],
			primary_action_label: __("Copy Selected"),
			primary_action: function (values) {
				// Always create a new custom role with cherry-picked DocType permissions
				me.copy_with_custom_permissions(d, user, values);
			},
		});

		// Load source user roles immediately
		me.load_roles_for_cherry_pick(d, user, null);

		d.show();
	}

	load_roles_for_cherry_pick(dialog, source_user, target_user) {
		const me = this;

		// Use the new API that includes DocType permissions
		frappe.call({
			method: "frappe_role_manager.frappe_role_manager.api.copy.get_user_roles_with_permissions",
			args: {
				source_user: source_user,
				target_user: target_user,
			},
			callback: function (r) {
				if (r.message) {
					const data = r.message;
					me.cherry_pick_data = data; // Store for later use

					let html = `
						<div class="roles-cherry-pick" style="max-height: 400px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: 4px; padding: 10px;">
							<div style="margin-bottom: 10px;">
								<button type="button" class="btn btn-xs btn-default select-all-roles">${__("Select All Roles")}</button>
								<button type="button" class="btn btn-xs btn-default select-none-roles">${__("Select None")}</button>
								<span class="text-muted" style="margin-left: 10px;">${data.total} roles from source user</span>
							</div>
							<div class="text-muted" style="font-size: 11px; margin-bottom: 10px;">
								<i class="fa fa-info-circle"></i> Click on a role row to expand and cherry-pick specific DocType permissions
							</div>
					`;

					if (data.roles.length === 0) {
						html += `<div class="text-center text-muted" style="padding: 20px;">No roles assigned to source user</div>`;
					} else {
						data.roles.forEach((role, index) => {
							const disabled = role.already_has ? "disabled" : "";
							const checked = !role.already_has ? "checked" : "";
							const statusBadge = role.already_has
								? '<span class="label label-default">Already has</span>'
								: '<span class="label label-success">Will add</span>';
							const rowOpacity = role.already_has ? "opacity: 0.6;" : "";

							html += `
								<div class="role-card" style="border: 1px solid var(--border-color); border-radius: 4px; margin-bottom: 8px; ${rowOpacity}">
									<div class="role-header" style="padding: 8px 12px; background: var(--bg-light-gray); cursor: pointer; display: flex; align-items: center;" data-role-index="${index}">
										<input type="checkbox" class="role-checkbox" data-role="${role.role}" ${checked} ${disabled} style="margin-right: 10px;">
										<span style="flex: 1; font-weight: 500;">${role.role}</span>
										<span class="text-muted" style="margin-right: 10px;">${role.doctype_count} DocTypes</span>
										${statusBadge}
										<i class="fa fa-chevron-down toggle-icon" style="margin-left: 10px;"></i>
									</div>
									<div class="role-permissions" data-role="${role.role}" style="display: none; padding: 10px; border-top: 1px solid var(--border-color);">
										${me.render_doctype_permissions(role)}
									</div>
								</div>
							`;
						});
					}

					html += `</div>`;

					dialog.fields_dict.roles_html.$wrapper.html(html);

					// Bind events
					dialog.$wrapper.find(".select-all-roles").off("click").on("click", function (e) {
						e.preventDefault();
						dialog.$wrapper.find(".role-checkbox:not(:disabled)").prop("checked", true);
						dialog.$wrapper.find(".perm-checkbox:not(:disabled)").prop("checked", true);
					});

					dialog.$wrapper.find(".select-none-roles").off("click").on("click", function (e) {
						e.preventDefault();
						dialog.$wrapper.find(".role-checkbox:not(:disabled)").prop("checked", false);
						dialog.$wrapper.find(".perm-checkbox:not(:disabled)").prop("checked", false);
					});

					// Toggle role expansion
					dialog.$wrapper.find(".role-header").off("click").on("click", function (e) {
						if ($(e.target).hasClass("role-checkbox")) return; // Don't toggle when clicking checkbox

						const role = $(this).find(".role-checkbox").data("role");
						const $perms = dialog.$wrapper.find(`.role-permissions[data-role="${role}"]`);
						const $icon = $(this).find(".toggle-icon");

						$perms.slideToggle(200);
						$icon.toggleClass("fa-chevron-down fa-chevron-up");
					});

					// When role checkbox is toggled, toggle all its permission checkboxes
					dialog.$wrapper.find(".role-checkbox").off("change").on("change", function () {
						const role = $(this).data("role");
						const isChecked = $(this).is(":checked");
						dialog.$wrapper.find(`.role-permissions[data-role="${role}"] .perm-row-checkbox`).prop("checked", isChecked);
						dialog.$wrapper.find(`.role-permissions[data-role="${role}"] .perm-flag-checkbox`).prop("checked", isChecked);
					});
				}
			},
		});
	}

	copy_with_custom_permissions(dialog, source_user, values) {
		const me = this;

		// Gather selected DocType permissions with their individual flags
		const selected_permissions = [];
		const processedDoctypes = new Set();

		// Find all checked row checkboxes (selected DocTypes)
		dialog.$wrapper.find(".perm-row-checkbox:checked").each(function () {
			const $rowCheckbox = $(this);
			const role = $rowCheckbox.data("role");
			const doctype = $rowCheckbox.data("doctype");
			const permIndex = $rowCheckbox.data("perm-index");

			// Skip if already processed (same doctype from different roles)
			if (processedDoctypes.has(doctype)) return;
			processedDoctypes.add(doctype);

			// Read the individual permission flags from checkboxes
			const $row = $rowCheckbox.closest("tr");
			const permData = {
				doctype: doctype,
				read: $row.find('.perm-flag-checkbox[data-perm-type="read"]').is(":checked") ? 1 : 0,
				write: $row.find('.perm-flag-checkbox[data-perm-type="write"]').is(":checked") ? 1 : 0,
				create: $row.find('.perm-flag-checkbox[data-perm-type="create"]').is(":checked") ? 1 : 0,
				delete: $row.find('.perm-flag-checkbox[data-perm-type="delete"]').is(":checked") ? 1 : 0,
				submit: $row.find('.perm-flag-checkbox[data-perm-type="submit"]').is(":checked") ? 1 : 0,
				cancel: $row.find('.perm-flag-checkbox[data-perm-type="cancel"]').is(":checked") ? 1 : 0,
				export: $row.find('.perm-flag-checkbox[data-perm-type="export"]').is(":checked") ? 1 : 0,
				import: $row.find('.perm-flag-checkbox[data-perm-type="import"]').is(":checked") ? 1 : 0,
			};

			selected_permissions.push(permData);
		});

		if (selected_permissions.length === 0) {
			frappe.msgprint(__("Please expand roles and select at least one DocType"));
			return;
		}

		let custom_role_name = values.custom_role_name.trim();

		frappe.call({
			method: "frappe_role_manager.frappe_role_manager.api.copy.copy_with_custom_permissions",
			args: {
				source_user: source_user,
				target_user: values.target_user,
				selected_permissions: JSON.stringify(selected_permissions),
				custom_role_name: custom_role_name,
				copy_user_permissions: values.copy_user_permissions,
				create_role_profile: values.create_role_profile,
				role_profile_name: values.role_profile_name,
			},
			callback: function (r) {
				if (r.message && r.message.status === "success") {
					let msg = __("Created custom role '{0}' with {1} DocType permissions and assigned to {2}", [
						r.message.custom_role,
						r.message.permissions_added,
						values.target_user,
					]);
					if (r.message.role_profile) {
						msg += "<br>" + __("Created Role Profile: {0}", [r.message.role_profile]);
					}
					frappe.msgprint({
						title: __("Success"),
						message: msg,
						indicator: "green",
					});
					me.refresh();
				} else if (r.message) {
					frappe.msgprint({
						title: __("Error"),
						message: r.message.message,
						indicator: "red",
					});
				}
			},
		});

		dialog.hide();
	}

	render_doctype_permissions(role) {
		if (!role.permissions || role.permissions.length === 0) {
			return '<div class="text-muted text-center">No DocType permissions</div>';
		}

		const permTypes = [
			{ key: "read", label: "R" },
			{ key: "write", label: "W" },
			{ key: "create", label: "C" },
			{ key: "delete", label: "D" },
			{ key: "submit", label: "Sub" },
			{ key: "cancel", label: "Can" },
			{ key: "export", label: "Exp" },
			{ key: "import", label: "Imp" },
		];

		let html = `
			<div style="margin-bottom: 8px;">
				<button type="button" class="btn btn-xs btn-default select-all-perms" data-role="${role.role}">Select All DocTypes</button>
				<button type="button" class="btn btn-xs btn-default select-none-perms" data-role="${role.role}">Select None</button>
			</div>
			<div class="text-muted" style="font-size: 10px; margin-bottom: 5px;">
				<i class="fa fa-info-circle"></i> Click checkboxes to toggle individual permissions (R=Read, W=Write, C=Create, D=Delete)
			</div>
			<table class="table table-sm table-bordered" style="font-size: 11px; margin-bottom: 0;">
				<thead>
					<tr style="background: var(--bg-light-gray);">
						<th style="width: 25px;"></th>
						<th>DocType</th>
						${permTypes.map((p) => `<th style="width: 30px; text-align: center;" title="${p.key}">${p.label}</th>`).join("")}
					</tr>
				</thead>
				<tbody>
		`;

		role.permissions.forEach((perm, idx) => {
			html += `
				<tr data-role="${role.role}" data-doctype="${perm.doctype}" data-perm-index="${idx}">
					<td style="text-align: center;">
						<input type="checkbox" class="perm-row-checkbox" checked
							data-role="${role.role}"
							data-doctype="${perm.doctype}"
							data-perm-index="${idx}">
					</td>
					<td style="font-size: 10px; font-weight: 500;">${perm.doctype}</td>
			`;

			permTypes.forEach((p) => {
				const checked = perm[p.key] ? "checked" : "";
				html += `
					<td style="text-align: center; padding: 2px;">
						<input type="checkbox" class="perm-flag-checkbox" ${checked}
							data-role="${role.role}"
							data-doctype="${perm.doctype}"
							data-perm-index="${idx}"
							data-perm-type="${p.key}"
							style="cursor: pointer;">
					</td>
				`;
			});

			html += `</tr>`;
		});

		html += `
				</tbody>
			</table>
		`;

		return html;
	}

	show_clone_dialog(role) {
		const me = this;

		const d = new frappe.ui.Dialog({
			title: __("Clone Role"),
			fields: [
				{
					fieldtype: "Data",
					fieldname: "new_role_name",
					label: __("New Role Name"),
					reqd: 1,
				},
				{
					fieldtype: "Check",
					fieldname: "desk_access",
					label: __("Desk Access"),
					default: 1,
				},
			],
			primary_action_label: __("Clone"),
			primary_action: function (values) {
				frappe.call({
					method: "frappe_role_manager.frappe_role_manager.api.clone.execute_clone",
					args: {
						source_role: role,
						new_role_name: values.new_role_name,
						desk_access: values.desk_access,
					},
					callback: function (r) {
						if (r.message && r.message.status === "success") {
							frappe.msgprint(__("Role cloned successfully!"));
							me.refresh();
						}
					},
				});
				d.hide();
			},
		});

		d.show();
	}

	show_users_with_role(role) {
		frappe.call({
			method: "frappe_role_manager.frappe_role_manager.api.view.get_users_with_role",
			args: { role: role },
			callback: function (r) {
				if (r.message) {
					const users = r.message;
					const html =
						users.length > 0
							? `<ul>${users.map((u) => `<li>${u.full_name || u.name} (${u.name}) ${!u.enabled ? '<span class="text-muted">(Disabled)</span>' : ""}</li>`).join("")}</ul>`
							: "<p>No users have this role.</p>";

					frappe.msgprint({
						title: __("Users with role: {0}", [role]),
						message: html,
					});
				}
			},
		});
	}

	show_new_role_dialog() {
		const me = this;

		const d = new frappe.ui.Dialog({
			title: __("Create New Role"),
			fields: [
				{
					fieldtype: "Data",
					fieldname: "role_name",
					label: __("Role Name"),
					reqd: 1,
				},
				{
					fieldtype: "Check",
					fieldname: "desk_access",
					label: __("Desk Access"),
					default: 1,
				},
			],
			primary_action_label: __("Create"),
			primary_action: function (values) {
				frappe.call({
					method: "frappe.client.insert",
					args: {
						doc: {
							doctype: "Role",
							role_name: values.role_name,
							desk_access: values.desk_access,
							is_custom: 1,
						},
					},
					callback: function (r) {
						if (r.message) {
							frappe.msgprint(__("Role created successfully!"));
							d.hide();
							me.refresh();
						}
					},
				});
			},
		});

		d.show();
	}

	export_user_permissions(user) {
		frappe.call({
			method: "frappe_role_manager.frappe_role_manager.api.export.export_permissions",
			args: {
				users: [user],
				export_roles: true,
				export_user_permissions: true,
				export_role_assignments: true,
				format: "json",
			},
			callback: function (r) {
				if (r.message) {
					const blob = new Blob([JSON.stringify(r.message.data, null, 2)], {
						type: "application/json",
					});
					const url = URL.createObjectURL(blob);
					const a = document.createElement("a");
					a.href = url;
					a.download = `permissions_${user.replace("@", "_")}_${frappe.datetime.now_date()}.json`;
					a.click();
				}
			},
		});
	}
}
