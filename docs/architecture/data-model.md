# MBP Data Model

## Core Ownership Rule

Every entity is owned by an authenticated user either directly through `user_id` or indirectly through a parent such as `sprint_id`, `profile_id`, or `plan_id`. All reads and writes must verify ownership server-side. Browser-submitted IDs are untrusted until checked against authenticated ownership.

## InterviewSprint

- **Purpose:** Owns the end-to-end interview preparation workflow for one target opportunity.
- **Ownership:** Direct via `user_id`.
- **Fields:** `id`, `user_id`, `state`, `active_resume_id`, `active_profile_id`, `created_at`, `updated_at`, `completed_at`.
- **Status values:** `DRAFT`, `RESUME_READY`, `PROFILE_CONFIRMED`, `OPPORTUNITY_CONFIRMED`, `EVIDENCE_REVIEW`, `EVIDENCE_APPROVED`, `STORIES_READY`, `MATCHING_READY`, `PREVIEW_READY`, `PAYMENT_PENDING`, `PAID`, `PREPKIT_READY`, `PRACTICE_ACTIVE`, `PLAN_READY`, `COMPLETED`.

## Document

- **Purpose:** Stores uploaded or pasted resume metadata and extracted/confirmed text.
- **Ownership:** Direct via `user_id`.
- **Fields:** `id`, `user_id`, `document_type`, `original_filename`, `storage_key`, `mime_type`, `file_size`, `raw_text`, `cleaned_text`, `parsing_status`, `parsing_error`, `is_active`, `created_at`, `updated_at`.
- **Status values:** `UPLOADED`, `VALIDATING`, `PARSING`, `READY_FOR_REVIEW`, `CONFIRMED`, `INVALID_FILE`, `PARSING_FAILED`, `REPLACED`.

## CareerProfile

- **Purpose:** User-confirmed profile extracted from the active resume.
- **Ownership:** Direct via `user_id`; linked to `active_resume_id`.
- **Fields:** `id`, `user_id`, `active_resume_id`, `full_name`, `current_role`, `current_company`, `years_experience`, `industries`, `functional_areas`, `skills`, `tools`, `education_summary`, `career_summary`, `positioning_summary`, `confirmation_status`, `confirmed_at`, `created_at`, `updated_at`.
- **Status values:** `DRAFT`, `CONFIRMED`, `STALE`.

## Opportunity

- **Purpose:** Captures target role, JD, company context, interview metadata, concerns, and goals.
- **Ownership:** Inherited via `sprint_id`.
- **Fields:** `id`, `sprint_id`, `role_title`, `role_family`, `target_seniority`, `company_name`, `company_url`, `job_description`, `interview_stage`, `interview_date`, `concerns`, `improvement_goals`, `jd_analysis`, `company_context`, `confirmation_status`, `created_at`, `updated_at`.
- **Status values:** `DRAFT`, `CONFIRMED`, `STALE`.

## CareerHighlight

- **Purpose:** Stores user-supplied manual highlights used as additional evidence source material.
- **Ownership:** Direct via `user_id` and/or inherited through `profile_id`.
- **Fields:** `id`, `user_id`, `profile_id`, `title`, `description`, `metric`, `skills`, `source_note`, `created_at`, `updated_at`.
- **Status values:** `DRAFT`, `ACTIVE`, `STALE`.

## EvidenceCard

- **Purpose:** User-reviewed evidence unit with provenance for stories and Prep Kit content.
- **Ownership:** Direct via `user_id`; linked to `profile_id` and optionally `source_document_id`.
- **Fields:** `id`, `user_id`, `profile_id`, `source_document_id`, `title`, `problem`, `role`, `action`, `result`, `metric`, `skills`, `competencies`, `ownership_signal`, `constraints`, `tradeoffs`, `missing_details`, `source_excerpt`, `source_location`, `confidentiality`, `status`, `ai_generated_data`, `user_edited_data`, `created_at`, `updated_at`.
- **Status values:** `DRAFT`, `APPROVED`, `REJECTED`, `NEEDS_DETAIL`, `STALE`.

## Story

- **Purpose:** Reusable interview story generated from approved evidence.
- **Ownership:** Direct via `user_id`; linked to `profile_id` and evidence IDs.
- **Fields:** `id`, `user_id`, `profile_id`, `title`, `story_type`, `situation`, `task`, `action`, `result`, `learning`, `short_answer`, `medium_answer`, `detailed_answer`, `competency_tags`, `seniority_signals`, `evidence_ids`, `specificity_score`, `impact_score`, `ownership_score`, `clarity_score`, `missing_details`, `status`, `created_at`, `updated_at`.
- **Status values:** `DRAFT`, `READY`, `EDITED`, `STALE`, `ARCHIVED`.

## StoryMatch

- **Purpose:** Stores contextual fit between reusable stories and the target opportunity.
- **Ownership:** Inherited via `sprint_id`.
- **Fields:** `id`, `sprint_id`, `competency_key`, `primary_story_id`, `alternative_story_id`, `competency_score`, `role_relevance_score`, `seniority_score`, `evidence_strength_score`, `company_context_score`, `total_score`, `explanation`, `jd_excerpt`, `evidence_ids`, `missing_signal`, `recommended_emphasis`, `user_selected`, `created_at`.
- **Status values:** Not required for MBP; regenerate by input revision and staleness rules.

## ReadinessPreview

- **Purpose:** Free preview that summarizes readiness and explains paid Prep Kit value.
- **Ownership:** Inherited via `sprint_id`.
- **Fields:** `id`, `sprint_id`, `role_summary`, `competencies`, `strengths`, `gaps`, `evidence_completeness`, `story_coverage`, `matched_story_excerpt`, `prepkit_explanation`, `input_revision`, `status`, `created_at`, `updated_at`.
- **Status values:** `DRAFT`, `READY`, `STALE`.

## Payment

- **Purpose:** Stores Razorpay order/payment state and paid entitlement for one Sprint.
- **Ownership:** Direct via `user_id`; linked to `sprint_id`.
- **Fields:** `id`, `user_id`, `sprint_id`, `provider`, `provider_order_id`, `provider_payment_id`, `amount`, `currency`, `status`, `webhook_event_id`, `webhook_received_at`, `paid_at`, `created_at`, `updated_at`.
- **Status values:** `NOT_STARTED`, `ORDER_CREATED`, `PAYMENT_PENDING`, `PAID`, `FAILED`, `REFUNDED`.

## GenerationRun

- **Purpose:** Database-backed background generation job and failure record.
- **Ownership:** Inherited via `sprint_id`.
- **Fields:** `id`, `sprint_id`, `operation`, `status`, `attempt_count`, `input_revision`, `error_code`, `error_message`, `started_at`, `completed_at`, `created_at`.
- **Status values:** `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `STALE`.

## PrepKit

- **Purpose:** Paid interview preparation artifact generated after verified payment.
- **Ownership:** Inherited via `sprint_id`.
- **Fields:** `id`, `sprint_id`, `status`, `role_briefing`, `fit_summary`, `competency_coverage`, `story_map`, `question_bank`, `concern_map`, `missing_evidence`, `practice_priorities`, `seven_day_plan`, `interview_checklist`, `input_revision`, `generated_at`, `created_at`, `updated_at`.
- **Status values:** `PENDING`, `READY`, `FAILED`, `STALE`.

## PracticeAttempt

- **Purpose:** Append-only typed answer practice record and feedback.
- **Ownership:** Inherited via `sprint_id`.
- **Fields:** `id`, `sprint_id`, `question_id`, `linked_story_id`, `answer_text`, `relevance_score`, `structure_score`, `specificity_score`, `ownership_score`, `impact_score`, `clarity_score`, `feedback`, `improved_answer`, `follow_up_question`, `attempt_number`, `created_at`.
- **Status values:** Append-only; status not required for MBP.

## ImprovementPlan

- **Purpose:** Owns the seven-day preparation plan for one Sprint.
- **Ownership:** Inherited via `sprint_id`.
- **Fields:** `id`, `sprint_id`, `interview_date`, `plan_length_days`, `generated_from_revision`, `created_at`, `updated_at`.
- **Status values:** `DRAFT`, `ACTIVE`, `COMPLETED`, `STALE`.

## PlanTask

- **Purpose:** Individual traceable task inside the seven-day plan.
- **Ownership:** Inherited via `plan_id` to `ImprovementPlan` and `sprint_id`.
- **Fields:** `id`, `plan_id`, `day_number`, `task_type`, `title`, `reason`, `instructions`, `estimated_minutes`, `linked_evidence_id`, `linked_story_id`, `linked_question_id`, `priority`, `status`, `completed_at`.
- **Status values:** `TODO`, `DONE`, `SKIPPED`.

## Avoid in MBP

Do not implement these entities during the MBP:

- `CareerGraph`
- `Organization`
- `Team`
- `Subscription`
- `CreditBalance`
- `CoachMarketplace`
- `NotificationSchedule`
- `CalendarIntegration`
- `VectorEmbedding`
- `PromptEvalRun`
- `AudioPracticeAttempt`
- `VideoPracticeAttempt`
