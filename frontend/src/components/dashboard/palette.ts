/**
 * Chart palette.
 *
 * Risk bands are ordered (Low Concern -> Review Recommended -> High Concern), so
 * in charts they are encoded as a validated **ordinal ramp** - one hue, light to
 * dark - rather than the green/amber/red triad used on badges. That is a
 * deliberate accessibility decision: a green-to-red triad fails deuteranopia
 * separation badly (measured CVD ΔE 4.2 between the green and the red, against a
 * floor of 8), which would make the two colours that matter most in this product
 * indistinguishable for a common form of colour blindness.
 *
 * The semantic triad is still used on badges and chips, where it is always
 * accompanied by the band's name - colour never carries the meaning alone.
 *
 * Both ramps below pass the full ordinal validation against this product's own
 * chart surfaces (#ffffff light, #171c27 dark): monotone lightness, adjacent
 * ΔL >= 0.06, light end clear of the surface, single hue.
 */
export interface ChartTheme {
  surface: string;
  grid: string;
  axis: string;
  ink: string;
  inkMuted: string;
  /** Single-series fill (magnitude, identity carried by the axis labels). */
  primary: string;
  /** Ordinal ramp, index 0 = least concern. */
  bands: [string, string, string];
  tooltipBg: string;
  tooltipBorder: string;
}

export const LIGHT_THEME: ChartTheme = {
  surface: "#ffffff",
  grid: "#e6e9ee",
  axis: "#c8cdd6",
  ink: "#1c2330",
  inkMuted: "#6b7280",
  primary: "#2a78d6",
  bands: ["#86b6ef", "#2a78d6", "#104281"],
  tooltipBg: "#ffffff",
  tooltipBorder: "#d8dde5",
};

export const DARK_THEME: ChartTheme = {
  surface: "#171c27",
  grid: "#242c3a",
  axis: "#333c4d",
  ink: "#e6eaf1",
  inkMuted: "#9aa3b2",
  primary: "#3987e5",
  bands: ["#9ec5f4", "#3987e5", "#184f95"],
  tooltipBg: "#1b2130",
  tooltipBorder: "#2c3547",
};

export const BAND_ORDER = ["low_concern", "review_recommended", "high_concern"] as const;

export const BAND_LABEL: Record<string, string> = {
  low_concern: "Low Concern",
  review_recommended: "Review Recommended",
  high_concern: "High Concern",
};
