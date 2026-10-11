# SQLite Data Model

Use Alembic migrations, SQLAlchemy models and SQLite foreign_keys=ON/WAL.

## Core tables
- jira_connections(id, name, base_url, auth_method, credential_reference, created_at) — no raw token.
- jira_projects(id, jira_project_id UNIQUE, key, name, metadata_json, active, updated_at).
- jira_fields(id, jira_field_id UNIQUE, name, schema_json, is_custom, searchable, last_seen_at).
- jira_field_contexts(id, jira_field_id, context_id, project_id nullable, issue_type_id nullable, options_json, fetched_at) — only accessible metadata.
- jira_issue_types(id, jira_type_id, name, hierarchy_level nullable, metadata_json).
- jira_statuses(id, jira_status_id, name, category_key, metadata_json).
- issues(id, jira_issue_id UNIQUE, issue_key, project_id, issue_type_id, status_id, parent_jira_issue_id nullable, summary, assignee_account_id nullable, reporter_account_id nullable, created_at, updated_at, due_at nullable, resolved_at nullable, raw_fields_json, last_seen_sync_id, is_deleted_or_inaccessible, synced_at).
- issue_field_values(id, issue_id, jira_field_id, value_type, string_value nullable, number_value nullable, date_value nullable, boolean_value nullable, option_id nullable, user_account_id nullable, raw_value_json, UNIQUE(issue_id,jira_field_id,option_id,string_value) requires special handling for NULLs). Prefer a stable element_index and UNIQUE(issue_id,jira_field_id,element_index) for multivalued fields.
- issue_relationships(id, parent_issue_id nullable, child_issue_id, relationship_type, is_resolved, UNIQUE(child_issue_id,relationship_type)) for parent links; store missing external parent IDs separately.
- dashboard_configs(id, name, description, scope_json, layout_json, filters_json, owner_id, shared, version, updated_at).
- metric_definitions(id, name, metric_type, numerator_filter_json, denominator_filter_json, aggregation_json, field_id nullable, scope_json, updated_at).
- field_display_configs(id, dashboard_id, jira_field_id, label_override, format_json, visible, display_order).
- app_users(id, external_subject, display_name, role, active).
- project_permissions(id, user_or_role, jira_project_id, can_view, can_configure).
- sync_runs(id, started_at, finished_at, status, projects_json, fetched_count, upserted_count, missing_count, error_json, watermark_before, watermark_after).
- config_audit(id, actor_id, entity_type, entity_id, operation, before_json, after_json, occurred_at).
- report_snapshots(id, scope_hash, metric_id, value_json, as_of, sync_run_id) optional for trends.

## Invariants
Jira issue ID is stable identity; issue key is display and deep-link. Parent can be absent or out of project scope; never silently invent a parent. Use real Jira field IDs, not labels, as config keys. Preserve arrays and typed values. Missing vs null vs inaccessible values should be distinguishable where possible. Avoid recursive SQL cycles by detecting and flagging invalid chains. Ensure every aggregate uses distinct Jira issue IDs.
