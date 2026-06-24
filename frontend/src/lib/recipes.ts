/**
 * Shared TypeScript types and small helpers for the recipe catalogue
 * and run form (Task 18).
 *
 * The shapes mirror the backend Pydantic schemas returned by
 * ``GET /api/recipes`` and ``GET /api/recipes/{name}``. The list
 * endpoint returns a narrow summary so the catalogue can render
 * without shipping every recipe body to every client; the detail
 * endpoint adds the full YAML body so the run form can submit it
 * back to the backend unchanged.
 *
 * SECURITY: this module never carries host credentials. The recipe
 * body is treated as text the user authored and is forwarded to
 * the backend verbatim. The redaction engine is responsible for
 * scrubbing any secret material that ends up in a recipe log; the
 * UI does not do its own scrubbing.
 */

export type RecipeRiskLevel = "low" | "medium" | "high" | "critical";

export type RecipeSource = "builtin" | "uploaded";

export interface RecipeVarSpec {
  /** Declared variable type. The form uses this to pick the right input. */
  type: "string" | "int" | "bool" | "number" | string;
  /** Default value declared by the recipe author (may be null/undefined). */
  default: unknown;
  /** Human-readable description shown as helper text under the input. */
  description: string;
  /** ``true`` when the recipe author did not declare a default value. */
  required: boolean;
}

export interface RecipeSupportedOs {
  families?: string[];
  names?: string[];
}

export interface RecipePolicy {
  requires_approval?: boolean;
  forbidden_on_environments?: string[];
}

export interface RecipeSummary {
  name: string;
  version: string;
  description: string;
  risk_level: RecipeRiskLevel;
  step_count: number;
  has_preflight: boolean;
  has_verify: boolean;
  has_rollback: boolean;
  vars: Record<string, RecipeVarSpec>;
  supported_os: RecipeSupportedOs;
  policy: RecipePolicy;
  source: RecipeSource;
}

export interface RecipeDetail extends RecipeSummary {
  /** Raw YAML body, ready to be POSTed to /api/recipes/run. */
  yaml: string;
}

export const RECIPE_RISK_LEVELS: RecipeRiskLevel[] = [
  "low",
  "medium",
  "high",
  "critical",
];

/**
 * UI tone for a recipe risk level.  Mirrors the badge tones used by
 * the jobs and hosts dashboards so the visual language stays
 * consistent across the app.
 */
export function recipeRiskTone(
  level: RecipeRiskLevel,
): "info" | "warning" | "destructive" | "outline" {
  if (level === "critical") return "destructive";
  if (level === "high") return "destructive";
  if (level === "medium") return "warning";
  return "info";
}

/**
 * Pick a sensible default form value for a variable.  We return a
 * string by default because every variable in the form is a string
 * input. Numeric / boolean vars are coerced on submit.
 */
export function defaultVarValue(spec: RecipeVarSpec): string {
  if (spec.default === null || spec.default === undefined) return "";
  if (typeof spec.default === "boolean") return spec.default ? "true" : "false";
  if (typeof spec.default === "object") return JSON.stringify(spec.default);
  return String(spec.default);
}

/**
 * Coerce a raw string form value into the type the recipe engine
 * expects.  Anything we cannot parse is forwarded as a string and
 * the backend will reject it with a 422 if the recipe truly
 * requires an int / bool.
 */
export function coerceVarValue(
  spec: RecipeVarSpec,
  raw: string,
): unknown {
  if (raw === "") return "";
  if (spec.type === "int" || spec.type === "number") {
    const n = Number(raw);
    if (Number.isNaN(n)) return raw;
    if (spec.type === "int") return Math.trunc(n);
    return n;
  }
  if (spec.type === "bool") {
    if (raw === "true") return true;
    if (raw === "false") return false;
    return raw;
  }
  return raw;
}

export interface RecipeRunFormValues {
  host_id: string;
  vars: Record<string, string>;
  timeout_seconds: number;
  acknowledged_approval: boolean;
}

export function emptyRecipeRunForm(hostId = ""): RecipeRunFormValues {
  return {
    host_id: hostId,
    vars: {},
    timeout_seconds: 600,
    acknowledged_approval: false,
  };
}

/**
 * The policy block can demand approval. The UI must surface this
 * clearly and refuse to submit until the user has explicitly
 * acknowledged the prompt.  This helper centralises the test so
 * the run form and any future callers agree on the rule.
 */
export function recipeRequiresApproval(policy: RecipePolicy): boolean {
  return Boolean(policy && policy.requires_approval);
}

/**
 * Pretty-print the variables for the catalogue card.  Returns a
 * short signature like ``port:int, name:string`` so the dashboard
 * can show users what knobs the recipe exposes without rendering
 * the full schema.
 */
export function describeVars(
  vars: Record<string, RecipeVarSpec>,
  max = 4,
): string {
  const names = Object.keys(vars);
  if (names.length === 0) return "no variables";
  const head = names
    .slice(0, max)
    .map((n) => `${n}:${vars[n].type}`)
    .join(", ");
  if (names.length <= max) return head;
  return `${head}, +${names.length - max} more`;
}
