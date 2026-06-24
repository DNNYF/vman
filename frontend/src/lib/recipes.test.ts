import { describe, it, expect } from "vitest";
import {
  coerceVarValue,
  defaultVarValue,
  describeVars,
  emptyRecipeRunForm,
  recipeRequiresApproval,
  recipeRiskTone,
  type RecipeVarSpec,
} from "@/lib/recipes";

describe("recipe risk tone", () => {
  it("maps low/medium to safe tones", () => {
    expect(recipeRiskTone("low")).toBe("info");
    expect(recipeRiskTone("medium")).toBe("warning");
  });

  it("maps high/critical to destructive", () => {
    expect(recipeRiskTone("high")).toBe("destructive");
    expect(recipeRiskTone("critical")).toBe("destructive");
  });
});

describe("default var value", () => {
  it("returns an empty string when there is no default", () => {
    const spec: RecipeVarSpec = {
      type: "string",
      default: null,
      description: "",
      required: true,
    };
    expect(defaultVarValue(spec)).toBe("");
  });

  it("stringifies booleans as 'true' / 'false'", () => {
    expect(
      defaultVarValue({
        type: "bool",
        default: true,
        description: "",
        required: false,
      }),
    ).toBe("true");
    expect(
      defaultVarValue({
        type: "bool",
        default: false,
        description: "",
        required: false,
      }),
    ).toBe("false");
  });

  it("keeps string defaults verbatim", () => {
    expect(
      defaultVarValue({
        type: "string",
        default: "hello",
        description: "",
        required: false,
      }),
    ).toBe("hello");
  });

  it("stringifies objects via JSON", () => {
    expect(
      defaultVarValue({
        type: "object",
        default: { a: 1 },
        description: "",
        required: false,
      }),
    ).toBe('{"a":1}');
  });
});

describe("coerce var value", () => {
  it("converts int values and truncates", () => {
    expect(
      coerceVarValue(
        { type: "int", default: 0, description: "", required: false },
        "42",
      ),
    ).toBe(42);
    expect(
      coerceVarValue(
        { type: "int", default: 0, description: "", required: false },
        "42.9",
      ),
    ).toBe(42);
  });

  it("converts number values to floats", () => {
    expect(
      coerceVarValue(
        { type: "number", default: 0, description: "", required: false },
        "3.14",
      ),
    ).toBe(3.14);
  });

  it("converts bool values when spelled exactly", () => {
    const spec: RecipeVarSpec = {
      type: "bool",
      default: false,
      description: "",
      required: false,
    };
    expect(coerceVarValue(spec, "true")).toBe(true);
    expect(coerceVarValue(spec, "false")).toBe(false);
  });

  it("falls back to the raw string when the value cannot be parsed", () => {
    expect(
      coerceVarValue(
        { type: "int", default: 0, description: "", required: false },
        "not-a-number",
      ),
    ).toBe("not-a-number");
  });

  it("returns an empty string for empty inputs", () => {
    expect(
      coerceVarValue(
        { type: "string", default: "", description: "", required: false },
        "",
      ),
    ).toBe("");
  });
});

describe("recipeRequiresApproval", () => {
  it("returns true when policy.requires_approval is set", () => {
    expect(recipeRequiresApproval({ requires_approval: true })).toBe(true);
  });

  it("returns false for an empty policy", () => {
    expect(recipeRequiresApproval({})).toBe(false);
  });

  it("returns false when explicitly disabled", () => {
    expect(recipeRequiresApproval({ requires_approval: false })).toBe(false);
  });
});

describe("describeVars", () => {
  it("returns 'no variables' for an empty schema", () => {
    expect(describeVars({})).toBe("no variables");
  });

  it("lists names with their declared type", () => {
    const vars: Record<string, RecipeVarSpec> = {
      port: { type: "int", default: 8080, description: "", required: false },
      name: { type: "string", default: "vman", description: "", required: false },
    };
    expect(describeVars(vars)).toBe("port:int, name:string");
  });

  it("truncates long schemas with a count", () => {
    const vars: Record<string, RecipeVarSpec> = {};
    for (let i = 0; i < 6; i += 1) {
      vars[`v${i}`] = {
        type: "string",
        default: "",
        description: "",
        required: false,
      };
    }
    const out = describeVars(vars);
    expect(out).toMatch(/^\w+:\w+, \w+:\w+, \w+:\w+, \w+:\w+, \+\d+ more$/);
  });
});

describe("emptyRecipeRunForm", () => {
  it("returns a blank form with sensible defaults", () => {
    const form = emptyRecipeRunForm("host-123");
    expect(form.host_id).toBe("host-123");
    expect(form.vars).toEqual({});
    expect(form.timeout_seconds).toBe(600);
    expect(form.acknowledged_approval).toBe(false);
  });
});
