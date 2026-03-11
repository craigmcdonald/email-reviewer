# API Reference

All JSON API endpoints are prefixed with `/api`. HTML views are excluded from the OpenAPI schema.

## Reps

### GET /api/reps

List all reps with aggregated score averages, sorted by overall average descending.

**Response**: `list[RepTeamRow]`

Each object includes:

| Field | Type | Description |
|-------|------|-------------|
| email | string | Rep email address |
| display_name | string | Normalised display name |
| rep_type | string \| null | SDR, BizDev, AM, or null if untyped |
| avg_personalisation | float | Average personalisation score |
| avg_clarity | float | Average clarity score |
| avg_value_proposition | float | Average value_proposition score |
| avg_cta | float | Average cta score |
| avg_overall | float | Average overall score |
| chain_count | integer | Number of conversation chains involving this rep |
| avg_chain_score | float | Average chain-level conversation_quality score |

### PATCH /api/reps/{rep_email}

Update a rep's fields. Currently supports setting `rep_type`.

**Request body**: `RepUpdate` - any subset of updatable rep fields.

| Field | Type | Description |
|-------|------|-------------|
| rep_type | string | SDR, BizDev, or AM. Rejects invalid values with 422. |
| display_name | string | Updated display name |

**Response**: `RepResponse` (200) or 404 if rep not found.

### GET /api/reps/{rep_email}/emails

Scored emails for one rep, ordered by date descending.

**Query parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| type | string | (none) | Filter by email type. Accepted values: `outreach` (standalone or first-in-sequence emails), `follow_up` (subsequent sends to same recipient/subject with no reply), `unanswered` (chains where prospect replied but rep has not followed up), `chain` (back-and-forth conversation chains). When `unanswered` or `chain`, returns chain objects instead of email objects. |

**Response**: List of email objects (default, `outreach`, `follow_up`) or chain objects (`unanswered`, `chain`).

### GET /api/reps/{rep_email}/chains

Paginated chains where the rep is a sender.

**Query parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| page | integer | 1 | Page number (>= 1) |
| per_page | integer | 20 | Items per page (>= 1) |

**Response**: Paginated `{items, total, page, per_page}`

## Chains

### GET /api/chains/{chain_id}

Single chain with all emails in timestamp order and chain_score.

**Response**: Chain object with nested emails and chain_score. Returns 404 if not found.

## Emails

### GET /api/emails/{email_id}

Single email with its score detail.

**Response**: Email object with nested score.

## Stats

### GET /api/stats

Summary statistics.

**Response**: `StatsResponse`

| Field | Type | Description |
|-------|------|-------------|
| total_emails | integer | Total email count |
| total_scored | integer | Emails with scores |
| total_reps | integer | Distinct rep count |
| avg_overall | float | Average overall score |

## Settings

### GET /api/settings

Current application settings.

**Response**: `SettingsResponse`

| Field | Type | Description |
|-------|------|-------------|
| id | integer | Always 1 |
| global_start_date | date | Floor for all fetches |
| company_domains | string | Comma-separated domains |
| scoring_batch_size | integer | Claude API concurrency limit |
| auto_score_after_fetch | boolean | Auto-score after fetch |
| initial_email_prompt_blocks | object \| null | Structured prompt blocks for scoring initial cold outreach emails. Keys: `opening`, `value_proposition`, `personalisation`, `cta`, `clarity`, `closing` |
| follow_up_email_prompt_blocks | object \| null | Structured prompt blocks for scoring follow-up emails. Same keys as initial |
| classifier_prompt_blocks | object \| null | Structured prompt blocks for the Haiku email classifier. Keys: `opening`, `classification`, `quoted_extraction`, `closing` |
| chain_evaluation_prompt_blocks | object \| null | Structured prompt blocks for evaluating conversation chains. Keys: `opening`, `progression`, `responsiveness`, `persistence`, `conversation_quality`, `closing` |
| weight_value_proposition | float | Weight for value_proposition (default 0.35) |
| weight_personalisation | float | Weight for personalisation (default 0.30) |
| weight_cta | float | Weight for cta (default 0.20) |
| weight_clarity | float | Weight for clarity (default 0.15) |

### PATCH /api/settings

Partial update of application settings. Returns the updated settings.

**Request body**: Any subset of `SettingsResponse` fields. Validation rules:
- `global_start_date` cannot be in the future
- `company_domains` cannot be empty
- `scoring_batch_size` must be >= 1
- When any weight field is provided, all four must be present and sum to 1.0 (tolerance 0.001)
- When prompt block objects are provided, no block value can be empty or whitespace-only

**Response**: `SettingsResponse`

### GET /api/settings/defaults

Default prompt block objects for `initial_email_prompt_blocks`, `follow_up_email_prompt_blocks`, and `chain_evaluation_prompt_blocks`.

**Response**: Object with default prompt strings.

## Operations

### POST /api/operations/fetch

Start a fetch operation. Returns 202 with job record. Rejects 409 if a FETCH job is already RUNNING.

**Request body** (optional JSON):

| Field | Type | Description |
|-------|------|-------------|
| start_date | string (date) | Override fetch start date |
| end_date | string (date) | Override fetch end date |
| max_count | integer | Limit number of emails fetched |
| auto_score | boolean | Override auto_score_after_fetch setting for this fetch |

**Response**: `JobResponse` (202)

### POST /api/operations/score

Start a scoring operation. Returns 202 with job record. Rejects 409 if SCORE or RESCORE is RUNNING.

**Response**: `JobResponse` (202)

### POST /api/operations/rescore

Delete all scores and re-score every email and chain. Returns 202 with job record. Rejects 409 if SCORE or RESCORE is RUNNING.

**Response**: `JobResponse` (202)

### POST /api/operations/export

Start an Excel export operation.

**Response**: `JobResponse` (202)

### POST /api/operations/chain-build

Rebuild conversations. Runs a three-stage pipeline: (1) classify unclassified emails, (2) split email threads into individual messages, (3) build conversation chains. Returns 202 with job record. Rejects 409 if a CHAIN_BUILD job is already RUNNING.

**Response**: `JobResponse` (202)

### GET /api/operations/jobs

List all jobs ordered by created_at descending.

**Response**: `list[JobResponse]`

### GET /api/operations/jobs/{job_id}

Single job by ID.

**Response**: `JobResponse`

### GET /api/operations/last-run

Most recent completed job per type (or null for types that have never run).

**Response**: `LastRunResponse`
