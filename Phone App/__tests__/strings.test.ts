import { defaultLang, formatDuration, t } from "../src/strings";

describe("strings", () => {
  it("Norwegian is the default language", () => {
    expect(defaultLang).toBe("nb");
    expect(t("overview")).toBe("Oversikt");
    expect(t("overview", "en")).toBe("Overview");
  });

  it("fills in variables", () => {
    expect(t("connectedOk", "nb", { n: 5, v: "0.1.0" })).toBe("Koblet til. 5 matter, versjon 0.1.0.");
  });

  it("formats durations", () => {
    expect(formatDuration(45)).toBe("45 s");
    expect(formatDuration(11 * 60 + 58)).toBe("11 min");
    expect(formatDuration(77 * 60)).toBe("1 t 17 min");
    expect(formatDuration(3600)).toBe("1 t");
  });

  it("never uses clinical claims in the texts", () => {
    for (const lang of ["nb", "en"] as const) {
      const all = (["disclaimer", "riskNote", "risk_high"] as const).map((k) => t(k, lang)).join(" ").toLowerCase();
      expect(all).not.toMatch(/diagnos(is|e) (of|av)|ulcer probability|decubitus-sannsynlighet/);
    }
  });
});
