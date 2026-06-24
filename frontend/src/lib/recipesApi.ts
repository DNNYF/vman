/**
 * Thin wrapper around the VMAN recipe HTTP API.
 *
 * The backend mounts recipe routes at ``/api/recipes`` (see
 * ``backend/vman/api/routes_recipes.py``).  The module exposes:
 *
 * - :func:`listRecipes` for the catalogue page
 * - :func:`getRecipe` for the detail / run form page
 * - :func:`runRecipe` for the run form submission
 * - :func:`validateRecipeYaml` for the inline lint button
 *
 * SECURITY: this module never carries secret material. The recipe
 * body is treated as text the user authored and is forwarded to
 * the backend verbatim. The redaction engine is responsible for
 * scrubbing any secret material that ends up in a recipe log; the
 * UI does not do its own scrubbing.
 */

import { ApiClient, ApiError } from "@/lib/api";
import type {
  RecipeDetail,
  RecipeRunFormValues,
  RecipeSummary,
} from "@/lib/recipes";
import { coerceVarValue } from "@/lib/recipes";

const RECIPES_BASE = "";

const client = new ApiClient({ baseUrl: RECIPES_BASE });

export class RecipeApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "RecipeApiError";
    this.status = status;
    this.detail = detail;
  }
}

function toRecipeError(err: unknown): never {
  if (err instanceof ApiError) {
    throw new RecipeApiError(err.status, err.message);
  }
  if (err instanceof Error) {
    throw new RecipeApiError(0, err.message);
  }
  throw new RecipeApiError(0, "Unknown recipe API error");
}

export interface ListRecipesResponse extends Array<RecipeSummary> {}

/**
 * Fetch every built-in recipe VMAN knows about. The list is
 * expected to be short (handful of recipes for the MVP) so we do
 * not paginate; if the catalogue grows past a few dozen entries
 * we will add paging in a later task.
 */
export async function listRecipes(): Promise<RecipeSummary[]> {
  try {
    return await client.get<RecipeSummary[]>("/api/recipes");
  } catch (err) {
    toRecipeError(err);
  }
}

/**
 * Fetch a single recipe by name.  The response includes the raw
 * YAML body, ready to POST back to ``/api/recipes/run``.
 */
export async function getRecipe(name: string): Promise<RecipeDetail> {
  try {
    return await client.get<RecipeDetail>(
      `/api/recipes/${encodeURIComponent(name)}`,
    );
  } catch (err) {
    toRecipeError(err);
  }
}

/**
 * Result of a successful recipe run: the new job id plus the job's
 * initial status. The detail page will navigate to the job and
 * let the user follow the SSE log stream from there.
 */
export interface RecipeRunResult {
  job_id: string;
  status: string;
  exit_code: number | null;
}

/**
 * Payload submitted to ``POST /api/recipes/run``.  The vars block is
 * the raw, un-coerced form value. The backend treats any var as a
 * string substitute; the run form does the type coercion up front
 * so the backend only has to worry about safe substitution.
 */
export interface RunRecipePayload {
  host_id: string;
  recipe_yaml: string;
  vars: Record<string, unknown>;
  timeout_seconds: number;
}

/**
 * Convert a :class:`RecipeRunFormValues` into a payload the
 * backend understands.  Numeric / boolean vars are coerced based on
 * the recipe's declared schema; the recipe body is forwarded
 * verbatim.
 */
export function buildRunPayload(
  form: RecipeRunFormValues,
  recipe: RecipeDetail,
): RunRecipePayload {
  const vars: Record<string, unknown> = {};
  for (const [name, spec] of Object.entries(recipe.vars)) {
    const raw = form.vars[name] ?? "";
    if (raw === "" && !spec.required) continue;
    vars[name] = coerceVarValue(spec, raw);
  }
  return {
    host_id: form.host_id,
    recipe_yaml: recipe.yaml,
    vars,
    timeout_seconds: form.timeout_seconds,
  };
}

export async function runRecipe(
  payload: RunRecipePayload,
): Promise<RecipeRunResult> {
  try {
    return await client.post<RecipeRunResult>("/api/recipes/run", {
      json: payload,
    });
  } catch (err) {
    toRecipeError(err);
  }
}

/**
 * Validate a YAML body without running it.  Used by the inline
 * lint button on the run form.  Throws :class:`RecipeApiError`
 * with status=422 if the body fails validation.
 */
export interface RecipeValidationResult {
  name: string;
  version: string;
  risk_level: string;
  step_count: number;
  has_preflight: boolean;
  has_verify: boolean;
  has_rollback: boolean;
}

export async function validateRecipeYaml(
  recipeYaml: string,
): Promise<RecipeValidationResult> {
  try {
    return await client.post<RecipeValidationResult>("/api/recipes/validate", {
      json: { recipe_yaml: recipeYaml },
    });
  } catch (err) {
    toRecipeError(err);
  }
}
