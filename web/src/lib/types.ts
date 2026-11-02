// Mirrors the FastAPI response models. Keep in sync with api/src/jobhunt/schemas.

export type User = { id: string; email: string; display_name: string | null; created_at: string };
export type TokenResponse = { access_token: string; token_type: string; expires_in: number };

export type Role = { title: string; company: string; location: string | null; start: string | null; end: string | null; bullets: string[] };
export type Project = { name: string; description: string; url: string | null; technologies: string[]; bullets: string[] };
export type Education = { institution: string; degree: string | null; field: string | null; start: string | null; end: string | null };
export type Link = { label: string; url: string };
export type ProfileDocument = {
  name: string | null; headline: string | null; location: string | null; country_code: string | null;
  email: string | null; phone: string | null; links: Link[]; summary: string | null;
  roles: Role[]; projects: Project[]; skills: string[]; education: Education[];
  certifications: string[]; languages: string[];
};
export type ProfileRead = { document: ProfileDocument; version: number; source_filename: string | null; evidence_count: number };

export type LocationEligibility = {
  scope: "worldwide" | "regions" | "countries" | "timezone" | "unspecified";
  countries: string[]; regions: string[]; timezone_min_utc_offset: number | null; timezone_max_utc_offset: number | null;
  excluded_countries: string[]; text: string | null;
};
export type Salary = { min: number | null; max: number | null; currency: string | null; period: string | null; text: string | null };
export type JobExtraction = {
  title: string; company: string | null; seniority: string; years_experience_min: number | null;
  must_have_skills: string[]; nice_to_have_skills: string[]; salary: Salary | null; location: LocationEligibility;
  remote: string; employment_type: string; visa_sponsorship: string; summary: string; confidence: "low" | "medium" | "high";
};
export type Job = {
  id: string; source: string; url: string; title: string; company: string; location_text: string | null; salary_text: string | null;
  tags: string[]; posted_at: string | null; fetched_at: string; extraction_status: "pending" | "done" | "failed";
  extraction: JobExtraction | null; dedup_group_id: string | null; is_duplicate: boolean;
};
export type JobDetail = Job & { description: string; extraction_model: string | null; extraction_cost_usd: number | null; extraction_latency_ms: number | null };
export type JobList = { items: Job[]; total: number; limit: number; offset: number };
export type SourceStatus = { name: string; attribution: string; last_fetched_at: string | null; last_status_code: number | null; last_items_seen: number | null; last_items_new: number | null; last_error: string | null };

export type Strength = { evidence_id: string | null; path: string | null; quote: string; requirement: string };
export type Judgement = {
  score: number; verdict: string; recommendation: "apply" | "maybe" | "skip"; strengths: Strength[]; gaps: string[]; risks: string[];
  model: string | null; cost_usd: number | null; latency_ms: number | null; judged_at: string | null; dropped_citations: number;
};
export type Match = {
  job: Job; profile_version: number; passed_filters: boolean; filter_reasons: string[]; similarity_score: number | null;
  skill_coverage: number | null; hybrid_score: number | null; judge_score: number | null; judgement: Judgement | null; scored_at: string;
};
export type MatchedEvidence = { evidence_id: string; path: string; text: string; similarity: number };
export type SkillCoverage = { required: string[]; matched: string[]; missing: string[]; ratio: number | null };
export type MatchDetail = Match & { matched_evidence: MatchedEvidence[]; skills: SkillCoverage | null };
export type MatchList = { items: Match[]; total: number; limit: number; offset: number };
export type ScoreSummary = { considered: number; filtered_out: number; scored: number; judged: number; judge_cost_usd: number; profile_version: number };

export type Preferences = {
  country: string | null; timezone: string | null; min_salary_usd: number | null; seniority_levels: string[];
  excluded_keywords: string[]; required_keywords: string[]; shortlist_size: number; judge_pool_size: number; digest_email_enabled: boolean;
};

export type Stage = "saved" | "applied" | "interviewing" | "offer" | "rejected";
export const STAGES: Stage[] = ["saved", "applied", "interviewing", "offer", "rejected"];
export type ApplicationEvent = { id: string; kind: "stage_change" | "note" | "reminder"; body: string | null; data: Record<string, unknown>; created_at: string; source: string };
export type Application = {
  id: string; job: Job; stage: Stage; applied_at: string | null; follow_up_at: string | null; follow_up_due: boolean;
  resume_document_id: string | null; cover_letter_document_id: string | null; judge_score: number | null;
  events: ApplicationEvent[]; created_at: string; updated_at: string;
};
export type Board = { columns: Record<Stage, Application[]>; reminders_due: number };
