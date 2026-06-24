import { describe, it, expect, afterEach } from "vitest";
import {
  RecipeApiError,
  buildRunPayload,
  getRecipe,
  listRecipes,
  runRecipe,
  validateRecipeYaml,
} from "@/lib/recipesApi";
import type { RecipeDetail, RecipeRunFormValues } from "@/lib/recipes";

const sampleSummary = {
  name: "healthcheck",
  version: "0.1.0",
  description: "Read-only summary",
  risk_level: "low" as const,
  step_count: 5,
  has_preflight: true,
  has_verify: true,
  has_rollback: false,
  vars: {
    port: { type: "int", default: 8080, description: "port", required: false },
  },
  supported_os: { families: ["debian"], names: ["ubuntu"] },
  policy: { requires_approval: false, forbidden_on_environments: [] },
  source: "builtin" as const,
};

const sampleDetail: RecipeDetail = {
  ...sampleSummary,
  yaml: "schema_version: 1\nname: healthcheck\nversion: 0.1.0\n",
};

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

function mockFetchObserve(
  responder: (url: string, init?: RequestInit) => Response,
): { getLast: () => { url: string; init?: RequestInit } } {
  let last: { url: string; init?: RequestInit } = { url: "" };
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : String(input);
    last = { url, init };
    return responder(url, init);
  }) as unknown as typeof fetch;
  return {
    getLast: () => last,
  };
}

function mockFetchOnce(body: unknown, status = 200): void {
  globalThis.fetch = (async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    })) as unknown as typeof fetch;
}

describe("recipesApi listRecipes", () => {
  it("GETs /api/recipes and returns the parsed list", async () => {
    const obs = mockFetchObserve(() =>
      new Response(JSON.stringify([sampleSummary]), { status: 200 }),
    );
    const rows = await listRecipes();
    expect(rows).toHaveLength(1);
    expect(rows[0].name).toBe("healthcheck");
    expect(obs.getLast().url).toBe("/api/recipes");
  });

  it("wraps ApiError into RecipeApiError", async () => {
    mockFetchOnce({ detail: "boom" }, 500);
    await expect(listRecipes()).rejects.toBeInstanceOf(RecipeApiError);
  });
});

describe("recipesApi getRecipe", () => {
  it("fetches /api/recipes/{name} and returns the detail", async () => {
    const obs = mockFetchObserve(() =>
      new Response(JSON.stringify(sampleDetail), { status: 200 }),
    );
    const detail = await getRecipe("healthcheck");
    expect(detail.name).toBe("healthcheck");
    expect(detail.yaml).toContain("name: healthcheck");
    expect(obs.getLast().url).toBe("/api/recipes/healthcheck");
  });

  it("encodes special characters in the recipe name", async () => {
    const obs = mockFetchObserve(() =>
      new Response(JSON.stringify(sampleDetail), { status: 200 }),
    );
    await getRecipe("a b/");
    expect(obs.getLast().url).toBe("/api/recipes/a%20b%2F");
  });

  it("propagates 404 as a RecipeApiError", async () => {
    mockFetchOnce({ detail: "not found" }, 404);
    await expect(getRecipe("missing")).rejects.toBeInstanceOf(RecipeApiError);
  });
});

describe("recipesApi runRecipe", () => {
  it("POSTs the payload to /api/recipes/run", async () => {
    const obs = mockFetchObserve(() =>
      new Response(
        JSON.stringify({ job_id: "j-1", status: "queued", exit_code: null }),
        { status: 200 },
      ),
    );
    const result = await runRecipe({
      host_id: "h-1",
      recipe_yaml: "name: foo",
      vars: { port: 8080 },
      timeout_seconds: 60,
    });
    expect(result.job_id).toBe("j-1");
    expect(obs.getLast().url).toBe("/api/recipes/run");
    expect(obs.getLast().init?.method).toBe("POST");
    const body = JSON.parse(String(obs.getLast().init?.body ?? "{}"));
    expect(body).toEqual({
      host_id: "h-1",
      recipe_yaml: "name: foo",
      vars: { port: 8080 },
      timeout_seconds: 60,
    });
  });

  it("wraps ApiError into RecipeApiError", async () => {
    mockFetchOnce({ detail: "forbidden" }, 403);
    await expect(
      runRecipe({
        host_id: "h-1",
        recipe_yaml: "name: foo",
        vars: {},
        timeout_seconds: 60,
      }),
    ).rejects.toBeInstanceOf(RecipeApiError);
  });
});

describe("recipesApi validateRecipeYaml", () => {
  it("POSTs the YAML and returns the validation summary", async () => {
    const obs = mockFetchObserve(() =>
      new Response(
        JSON.stringify({
          name: "foo",
          version: "0.1.0",
          risk_level: "low",
          step_count: 1,
          has_preflight: false,
          has_verify: false,
          has_rollback: false,
        }),
        { status: 200 },
      ),
    );
    const result = await validateRecipeYaml("name: foo");
    expect(result.name).toBe("foo");
    expect(obs.getLast().url).toBe("/api/recipes/validate");
  });
});

describe("buildRunPayload", () => {
  it("forwards the YAML body verbatim", () => {
    const form: RecipeRunFormValues = {
      host_id: "h-1",
      vars: { port: "8080" },
      timeout_seconds: 30,
      acknowledged_approval: false,
    };
    const payload = buildRunPayload(form, sampleDetail);
    expect(payload.recipe_yaml).toBe(sampleDetail.yaml);
  });

  it("coerces int vars from form strings", () => {
    const form: RecipeRunFormValues = {
      host_id: "h-1",
      vars: { port: "9000" },
      timeout_seconds: 30,
      acknowledged_approval: false,
    };
    const payload = buildRunPayload(form, sampleDetail);
    expect(payload.vars).toEqual({ port: 9000 });
  });

  it("drops optional vars when empty", () => {
    const form: RecipeRunFormValues = {
      host_id: "h-1",
      vars: { port: "" },
      timeout_seconds: 30,
      acknowledged_approval: false,
    };
    const payload = buildRunPayload(form, sampleDetail);
    expect(payload.vars).toEqual({});
  });

  it("keeps empty values for required vars", () => {
    const requiredDetail: RecipeDetail = {
      ...sampleDetail,
      vars: {
        token: { type: "string", default: null, description: "", required: true },
      },
    };
    const form: RecipeRunFormValues = {
      host_id: "h-1",
      vars: { token: "" },
      timeout_seconds: 30,
      acknowledged_approval: false,
    };
    const payload = buildRunPayload(form, requiredDetail);
    expect(payload.vars).toEqual({ token: "" });
  });
});
