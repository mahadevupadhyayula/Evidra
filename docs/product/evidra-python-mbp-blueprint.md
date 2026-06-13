# Evidra.ai Python MBP Blueprint

## 1. MBP Objective

Evidra.ai is a Python-based, evidence-first Interview Sprint MBP. The objective is to build the complete Evidra Interview Sprint value loop:

Resume → Profile → Opportunity Context → Approved Evidence → Reusable Stories → Contextual Matching → Free Preview → Payment → Prep Kit → Text Practice → Seven-Day Plan

The MBP must prove that a user will:

- Provide career data.
- Approve evidence.
- Receive reusable interview stories.
- See a role-specific preview.
- Pay for the Prep Kit.
- Practise answers.
- Follow a seven-day plan.

The MBP does not need production-scale architecture. It needs a complete, reliable, truthful user value loop.

## 2. Python-First Architecture

- **Framework:** Django modular monolith.
- **Frontend:** Django templates, HTMX, minimal Alpine.js only if necessary, and standard forms.
- **Backend:** Django views/class-based views, Django service modules, Django ORM, PostgreSQL, Pydantic, OpenAI Python SDK, httpx, and PDF/DOCX parsing libraries.
- **Storage:** Private object storage for uploaded resumes.
- **Payment:** Razorpay assumed for the first MBP.
- **Background processing:** No Redis or Celery. Use a `GenerationRun` database table and a Django management command.

## 3. Application Module Structure

The intended structure for later implementation is:

```text
evidra/
├── manage.py
├── config/
├── apps/
│   ├── accounts/
│   ├── documents/
│   ├── profiles/
│   ├── opportunities/
│   ├── evidence/
│   ├── stories/
│   ├── matching/
│   ├── previews/
│   ├── payments/
│   ├── prepkits/
│   ├── practice/
│   ├── plans/
│   ├── generations/
│   └── common/
├── ai/
│   ├── client.py
│   ├── schemas/
│   ├── prompts/
│   ├── services/
│   └── validators/
├── templates/
├── static/
├── tests/
└── docs/
```

This blueprint documents the intended structure only. This documentation task must not create the Django project or application code.

| Module | Responsibility |
| --- | --- |
| `accounts` | Authentication, user identity, and user ownership helpers. |
| `documents` | Resume upload, paste handling, parsing, storage metadata, and active resume replacement. |
| `profiles` | Career profile extraction, user correction, confirmation, and profile source-of-truth state. |
| `opportunities` | Job description intake, role family selection, company context capture, and opportunity confirmation. |
| `evidence` | Evidence extraction, manual highlights, review, approval, rejection, provenance, and evidence thresholds. |
| `stories` | Reusable story generation, scoring, preservation of user edits, and story status. |
| `matching` | Role-pack matching, contextual story ranking, gap detection, and user overrides. |
| `previews` | Free readiness preview and paid Prep Kit explanation. |
| `payments` | Razorpay order creation, webhook validation, payment state, idempotency, and Sprint entitlement. |
| `prepkits` | Paid Prep Kit generation, stored artifact, print-friendly HTML, and recoverable failures. |
| `practice` | Text answer practice, scoring, improved answer generation, and append-only attempts. |
| `plans` | Rule-based seven-day improvement plan and task completion. |
| `generations` | Database-backed AI/background operations using `GenerationRun`. |
| `common` | Shared constants, ownership checks, state helpers, validators, and utility functions. |
| `ai` | OpenAI client wrapper, Pydantic schemas, prompts, AI services, and grounding validators. |

## 4. Core Workflow State Machine

Approved Sprint states:

1. `DRAFT`
2. `RESUME_READY`
3. `PROFILE_CONFIRMED`
4. `OPPORTUNITY_CONFIRMED`
5. `EVIDENCE_REVIEW`
6. `EVIDENCE_APPROVED`
7. `STORIES_READY`
8. `MATCHING_READY`
9. `PREVIEW_READY`
10. `PAYMENT_PENDING`
11. `PAID`
12. `PREPKIT_READY`
13. `PRACTICE_ACTIVE`
14. `PLAN_READY`
15. `COMPLETED`

State-management rules:

- AI may generate proposed output.
- AI may not update Sprint state directly.
- Application services validate output.
- Application services determine transitions.
- State changes are transactional.
- Users cannot skip approval stages.
- Repeated requests must not create duplicate records.
- Upstream edits mark downstream outputs stale.
- Stale outputs are not deleted automatically.
- Regeneration requires explicit user confirmation.

## 5. Resume Scope

Users can upload a PDF/DOCX resume, paste resume text, view extracted text, correct extraction errors, and replace the active resume.

Resume states:

- `UPLOADED`
- `VALIDATING`
- `PARSING`
- `READY_FOR_REVIEW`
- `CONFIRMED`

Failure states:

- `INVALID_FILE`
- `PARSING_FAILED`
- `REPLACED`

Document model fields:

- `id`
- `user_id`
- `document_type`
- `original_filename`
- `storage_key`
- `mime_type`
- `file_size`
- `raw_text`
- `cleaned_text`
- `parsing_status`
- `parsing_error`
- `is_active`
- `created_at`
- `updated_at`

Parser service methods:

- `validate_file`
- `extract_pdf_text`
- `extract_docx_text`
- `clean_text`
- `detect_sections`

Resume rules:

- Accept PDF, DOCX, or pasted text only.
- Enforce a file size limit.
- Validate both extension and MIME type.
- Store uploaded files in private object storage.
- Never send resume binaries to AI.
- Do not implement OCR in the MBP.
- Provide paste fallback when parsing fails or the user prefers paste.
- Allow one active resume per user.
- Resume replacement marks downstream outputs stale.
- Paid artifacts are not deleted automatically when a resume is replaced.

## 6. Profile Scope

Draft profile fields:

- Name.
- Current role.
- Current company.
- Years of experience.
- Functional areas.
- Industries.
- Skills.
- Tools.
- Education summary.
- Career summary.
- Positioning summary.

The user can correct and confirm the profile.

CareerProfile fields:

- `id`
- `user_id`
- `active_resume_id`
- `full_name`
- `current_role`
- `current_company`
- `years_experience`
- `industries`
- `functional_areas`
- `skills`
- `tools`
- `education_summary`
- `career_summary`
- `positioning_summary`
- `confirmation_status`
- `confirmed_at`
- `created_at`
- `updated_at`

AI input:

- Confirmed resume text only.
- No job description.
- No company context.
- No demographic inference.

AI output schema:

- `full_name`
- `current_role`
- `current_company`
- `years_experience`
- `industries`
- `functional_areas`
- `skills`
- `tools`
- `education_summary`
- `career_summary`
- `positioning_summary`
- `uncertain_fields`

Profile rules:

- Unknowns are `null`.
- Do not infer sensitive attributes.
- User-confirmed fields are the source of truth.
- AI cannot overwrite confirmed values.
- A confirmed profile is required before opportunity analysis.

## 7. Opportunity Context Scope

The user provides:

- Job description.
- Role title.
- Company name.
- Optional company/product URL.
- Target seniority.
- Interview stage and date.
- Concerns.
- Improvement goals.

Role families:

- Product Management.
- AI Product Management.
- Software Engineering.
- Data and Analytics.
- Sales and Business Development.
- Consulting/Strategy/Ops.
- Other.

Opportunity fields:

- `id`
- `sprint_id`
- `role_title`
- `role_family`
- `target_seniority`
- `company_name`
- `company_url`
- `job_description`
- `interview_stage`
- `interview_date`
- `concerns`
- `improvement_goals`
- `jd_analysis`
- `company_context`
- `confirmation_status`
- `created_at`
- `updated_at`

Role packs are fixed YAML or Python config.

Company context:

- Fetch at most one user-supplied safe public company/product page, or use pasted context.
- Extract company description, product/service, target users, business-model clues, product terminology, and strategic themes.

Opportunity rules:

- Job description is required.
- Role family is required.
- User-selected role family is authoritative.
- Do not perform broad web research.
- Do not integrate search engines for company context.
- Block localhost, private IP, file, and internal URLs.
- Limit redirects, download size, and request duration.
- User confirms opportunity and company context before downstream use.

## 8. Approved Evidence Scope

Evidence sources:

- Resume experience, projects, and achievements.
- Three to five manual highlights from the user.

Evidence card fields:

- Title.
- Situation/problem.
- Role.
- Action.
- Result.
- Metric.
- Skills.
- Competencies.
- Ownership.
- Constraints.
- Tradeoffs.
- Missing details.
- Source excerpt.

EvidenceCard fields:

- `id`
- `user_id`
- `profile_id`
- `source_document_id`
- `title`
- `problem`
- `role`
- `action`
- `result`
- `metric`
- `skills`
- `competencies`
- `ownership_signal`
- `constraints`
- `tradeoffs`
- `missing_details`
- `source_excerpt`
- `source_location`
- `confidentiality`
- `status`
- `ai_generated_data`
- `user_edited_data`
- `created_at`
- `updated_at`

Statuses:

- `DRAFT`
- `APPROVED`
- `REJECTED`
- `NEEDS_DETAIL`
- `STALE`

Evidence rules:

- AI may extract and structure candidates.
- AI cannot approve evidence.
- AI cannot invent metrics.
- AI cannot invent employers.
- AI cannot remove provenance.
- AI cannot destructively merge evidence cards.
- Every card needs a source excerpt.
- Metrics must appear in the source or in user correction.
- At least three approved evidence cards are required.
- At least two approved evidence cards must have clear results.

## 9. Reusable Stories Scope

Generate up to five to seven reusable stories, fewer if evidence is insufficient.

Each story contains:

- Title.
- Type.
- STAR/CAR structure.
- Short answer.
- Ninety-second answer.
- Detailed answer.
- Competency tags.
- Seniority signals.
- Evidence references.
- Missing details.
- Quality score.

Story fields:

- `id`
- `user_id`
- `profile_id`
- `title`
- `story_type`
- `situation`
- `task`
- `action`
- `result`
- `learning`
- `short_answer`
- `medium_answer`
- `detailed_answer`
- `competency_tags`
- `seniority_signals`
- `evidence_ids`
- `specificity_score`
- `impact_score`
- `ownership_score`
- `clarity_score`
- `missing_details`
- `status`
- `created_at`
- `updated_at`

Story rules:

- Use approved evidence only.
- Do not include unsupported metrics.
- Preserve user edits.
- Regeneration does not overwrite edited stories.
- Stories remain reusable across opportunities.

## 10. Contextual Matching Scope

Contextual matching compares stories against:

- Job description.
- Role pack.
- Target seniority.
- Company/product context.
- Interview stage.
- Evidence strength.

StoryMatch fields:

- `id`
- `sprint_id`
- `competency_key`
- `primary_story_id`
- `alternative_story_id`
- `competency_score`
- `role_relevance_score`
- `seniority_score`
- `evidence_strength_score`
- `company_context_score`
- `total_score`
- `explanation`
- `jd_excerpt`
- `evidence_ids`
- `missing_signal`
- `recommended_emphasis`
- `user_selected`
- `created_at`

Scoring:

- AI may return component scores from 0 to 5.
- Python calculates final total score:
  - 35% competency alignment.
  - 20% role relevance.
  - 15% seniority signal.
  - 15% evidence strength.
  - 10% company/product relevance.
  - 5% answer diversity.

Matching rules:

- Show gaps explicitly.
- Do not label low-fit stories as strong.
- Store user overrides.
- Do not use embeddings or a vector database in the MBP.

## 11. Free Preview Scope

The free preview shows:

- Role summary.
- Five competencies.
- Three strengths.
- Three gaps.
- Evidence completeness.
- Story coverage.
- One matched-story excerpt.
- Paid Prep Kit explanation.

Preview rules:

- The preview is useful but incomplete.
- Payment gates the Prep Kit, not user-owned profile, evidence, or stories.
- Do not show offer probability.

## 12. Payment Scope

The MBP sells one Interview Sprint product at one price with one payment button.

Payment states:

- `NOT_STARTED`
- `ORDER_CREATED`
- `PAYMENT_PENDING`
- `PAID`
- `FAILED`
- `REFUNDED`

Payment fields:

- `id`
- `user_id`
- `sprint_id`
- `provider`
- `provider_order_id`
- `provider_payment_id`
- `amount`
- `currency`
- `status`
- `webhook_event_id`
- `webhook_received_at`
- `paid_at`
- `created_at`
- `updated_at`

Payment rules:

- Razorpay is the first payment provider.
- Browser redirect does not unlock access.
- Verified webhook only unlocks paid access.
- Validate webhook signatures.
- Ensure idempotency.
- Validate amount and order.
- Failed payment preserves work.
- Paid access belongs to one Sprint.

## 13. Prep Kit Scope

Prep Kit sections:

- Role/company briefing.
- Fit summary.
- Competency coverage.
- Story map.
- Question bank.
- Recommended story per question.
- Concern map.
- Missing evidence.
- Practice priorities.
- Seven-day plan.
- Checklist.

PrepKit fields:

- `id`
- `sprint_id`
- `status`
- `role_briefing`
- `fit_summary`
- `competency_coverage`
- `story_map`
- `question_bank`
- `concern_map`
- `missing_evidence`
- `practice_priorities`
- `seven_day_plan`
- `interview_checklist`
- `input_revision`
- `generated_at`
- `created_at`
- `updated_at`

GenerationRun fields:

- `id`
- `sprint_id`
- `operation`
- `status`
- `attempt_count`
- `input_revision`
- `error_code`
- `error_message`
- `started_at`
- `completed_at`
- `created_at`

Generation statuses:

- `PENDING`
- `RUNNING`
- `SUCCEEDED`
- `FAILED`
- `STALE`

AI design:

- Operation 1: analytical synthesis.
- Operation 2: preparation artifact.

Prep Kit rules:

- Verified payment is required.
- Do not include unsupported metrics.
- Do not guarantee outcomes.
- Maintain one active Prep Kit.
- Allow one structural retry.
- Allow user retry after failure.
- Paid entitlement survives generation failure.
- HTML print is allowed.
- PDF generation is deferred.

## 14. Text Practice Scope

The user chooses a priority question and types an answer.

Practice output includes:

- Scores for relevance, structure, specificity, ownership, impact, and clarity.
- Strengths.
- Improvements.
- Improved answer.
- Follow-up question.
- Unsupported claims.

PracticeAttempt fields:

- `id`
- `sprint_id`
- `question_id`
- `linked_story_id`
- `answer_text`
- `relevance_score`
- `structure_score`
- `specificity_score`
- `ownership_score`
- `impact_score`
- `clarity_score`
- `feedback`
- `improved_answer`
- `follow_up_question`
- `attempt_number`
- `created_at`

Practice rules:

- Text only.
- Attempts are append-only.
- Improved answers cannot invent facts.
- Do not evaluate accent, appearance, or demographic attributes.
- Comparison is deterministic.

## 15. Seven-Day Plan Scope

Plan task categories:

- Evidence strengthening.
- Story improvement.
- Practice.
- Company research.
- Final review.

Task fields:

- Title.
- Reason.
- Estimated duration.
- Linked weakness.
- Linked story/evidence/question.
- Status.

ImprovementPlan fields:

- `id`
- `sprint_id`
- `interview_date`
- `plan_length_days`
- `generated_from_revision`
- `created_at`
- `updated_at`

PlanTask fields:

- `id`
- `plan_id`
- `day_number`
- `task_type`
- `title`
- `reason`
- `instructions`
- `estimated_minutes`
- `linked_evidence_id`
- `linked_story_id`
- `linked_question_id`
- `priority`
- `status`
- `completed_at`

Plan rules:

- Use a Python rule-based plan engine.
- AI may phrase tasks only.
- Do not create generic “be confident” tasks.
- Maximum two major tasks per day.
- Target 20–45 minutes per day.
- Preserve completed tasks.
- Final day is review-focused.

## 16. Minimal AI Architecture

EvidraAIService methods:

- `extract_profile`
- `analyze_jd`
- `extract_company_context`
- `extract_evidence`
- `generate_stories`
- `score_stories`
- `score_story_matches`
- `generate_preview`
- `generate_prepkit_analysis`
- `generate_prepkit_artifact`
- `evaluate_answer`
- `phrase_plan_tasks`

Shared AI pattern:

1. Load approved inputs.
2. Construct the minimal prompt.
3. Call structured AI.
4. Validate with Pydantic.
5. Validate source references.
6. Validate unsupported numeric claims.
7. Retry once when the failure is structural or parseable.
8. Save output or failure.

## 17. Global Rules

### Truth and Grounding

- Outputs must be grounded in resume text, user-confirmed profile data, approved evidence, user-provided opportunity context, role packs, or user-approved company context.
- Unsupported metrics, employers, achievements, and claims must be rejected or marked as missing.
- Free and paid outputs must not guarantee interview outcomes.

### Ownership

- All data belongs to a single authenticated user, directly or through Sprint ownership.
- Queries must be user-filtered.
- Browser-submitted IDs are never trusted without ownership checks.

### Idempotency

- Repeated requests must not create duplicate active records.
- Webhooks must be idempotent.
- Generation job creation must be idempotent by Sprint, operation, and input revision.

### Staleness and Failure Handling

- Upstream edits mark downstream outputs stale.
- Stale outputs are retained unless the user explicitly regenerates.
- Failed AI calls preserve prior work.
- Recoverable failures are visible to the user and retryable.

## 18. Iterative Implementation Plan

- **Iteration 1:** Foundation, authentication, resume, and profile.
- **Iteration 2:** Opportunity and evidence.
- **Iteration 3:** Stories, matching, and preview.
- **Iteration 4:** Payment and Prep Kit.
- **Iteration 5:** Practice and seven-day plan.

## 19. MBP Definition of Done

The MBP is done when an authenticated individual professional can complete the full end-to-end flow:

- Create or access their own Interview Sprint.
- Upload or paste a resume.
- Review and confirm extracted resume text.
- Generate, correct, and confirm a career profile.
- Provide and confirm job description, role family, company details, and interview context.
- Optionally provide a safe single company/product URL or pasted company context.
- Review AI-proposed evidence cards.
- Approve at least three evidence cards, including at least two with clear results.
- Generate reusable stories from approved evidence only.
- Match stories to the opportunity with visible scores and gaps.
- View a useful but incomplete free preview with one matched-story excerpt.
- Create a Razorpay order and complete payment.
- Unlock paid access only after a verified webhook.
- Generate a Prep Kit from grounded inputs.
- Recover from Prep Kit generation failure without losing paid entitlement.
- Practise text answers and receive grounded feedback.
- Receive a seven-day rule-based plan with traceable tasks.
- Complete the flow without cross-user data access.
- Preserve prior work when AI calls fail.
- Avoid all deferred architecture and product features unless re-approved.

## 20. Deferred After MBP Validation

Deferred items include:

- **Architecture:** Next.js, FastAPI, separate frontend/backend, Redis, Celery, distributed workers, microservices, pgvector, embeddings, vector search, multi-agent orchestration, workflow engine, model router, prompt dashboard, LLM judge, production observability, and enterprise multi-tenancy.
- **Authentication:** Google OAuth, magic links, SSO, organization accounts, team accounts, and RBAC beyond single-user ownership.
- **Parsing:** OCR, advanced layout reconstruction, and multiple active resumes.
- **Company research:** Open-ended web search, multi-page crawlers, continuous monitoring, news scraping, and social scraping.
- **Evidence graph:** Long-term career graph, multi-source stitching, entity resolution, embedding duplicate detection, and auto-merge.
- **Advanced matching:** Vector matching, learned ranking, interviewer-persona matching, and offer probability.
- **Billing:** Subscriptions, tiers, credits, coupons, refund automation, provider-neutral billing, and team billing.
- **Practice:** Audio, video, transcription, filler words, pacing, accent analysis, facial analysis, and live interview copilot.
- **Plan:** Notifications, calendar integration, email reminders, mobile push, and habit tracking.
- **Admin/ops:** Admin recovery UI, full audit logs, data export, deletion workflows, backups, load tests, pentests, cost dashboard, and prompt benchmark suite.
- **B2B features:** Organization dashboards, team analytics, coach marketplace, and enterprise controls.
