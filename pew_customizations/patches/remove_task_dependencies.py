"""PEW Tasks no longer depend on one another. Setup chained the template Tasks (each one depends_on
the one before), and Scope and Project Template generation copied that chain onto every real Task,
so ERPNext refused to complete a Task until the previous one was completed.

Rows ERPNext adds itself, linking a group Task to its child Tasks (Parent Task), are kept.
"""

import frappe


def execute():
	depends_on = frappe.qb.DocType("Task Depends On")
	dependency = frappe.qb.DocType("Task")
	rows = (
		frappe.qb.from_(depends_on)
		.left_join(dependency)
		.on(dependency.name == depends_on.task)
		.select(depends_on.name, depends_on.parent)
		.where(depends_on.parenttype == "Task")
		.where(dependency.parent_task.isnull() | (dependency.parent_task != depends_on.parent))
		.run(as_dict=True)
	)
	if not rows:
		return

	frappe.db.delete("Task Depends On", {"name": ("in", [row.name for row in rows])})

	# depends_on_tasks is the comma-joined copy of the table that Task.update_depends_on() keeps
	for task in {row.parent for row in rows}:
		remaining = frappe.get_all(
			"Task Depends On", filters={"parent": task, "parenttype": "Task"}, pluck="task", order_by="idx"
		)
		frappe.db.set_value(
			"Task", task, "depends_on_tasks", "".join(f"{name}," for name in remaining), update_modified=False
		)
