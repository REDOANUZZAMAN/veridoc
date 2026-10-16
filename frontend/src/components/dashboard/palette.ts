/**
 * Chart palette.
 *
 * Risk bands are ordered (Low Concern -> Review Recommended -> High Concern), so
 * in charts they are encoded as a validated **ordinal ramp** - one hue, light to
 * dark - rather than the green/amber/red triad used on badges. That is a
 * deliberate accessibility decision: a green-to-red triad fails deuteranopia
 * separation far more easily than a single-hue ramp, which would make the two
 * colours that matter most in this product hard to tell apart for a common form
 * of colour blindness.
 *
 * The semantic triad is still used on badges and chips, where it is always
 * accompanied by the band's name - colour never carries the meaning alone.
 *
 * Both ramps below are the product's iris accent, stepped and then validated
 * against this product's own chart surfaces (#ffffff light, #191622 dark):
 * monotone lightness, adjacent OKLCH ΔL >= 0.06, single hue (spread <= 9°), and a
 * light end that clears the surface (2.12:1 light, 2.35:1 dark).
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
  grid: "#e8e6ef",
  axis: "#c7c3d5",
  ink: "#1a1726",
  inkMuted: "#6a6581",
  primary: "#5e31d8",
  bands: ["#bba7f1", "#683eda", "#381a89"],
  tooltipBg: "#ffffff",
  tooltipBorder: "#dddae7",
};

export const DARK_THEME: ChartTheme = {
  surface: "#191622",
  grid: "#2c2938",
  axis: "#464257",
  ink: "#ebeaf1",
  inkMuted: "#9c97af",
  primary: "#a582f7",
  bands: ["#c3affd", "#9e7cf4", "#5e2bd4"],
  tooltipBg: "#1d1a28",
  tooltipBorder: "#383546",
};

export const BAND_ORDER = ["low_concern", "review_recommended", "high_concern"] as const;

export const BAND_LABEL: Record<string, string> = {
  low_concern: "Low Concern",
  review_recommended: "Review Recommended",
  high_concern: "High Concern",
};
