// Chart colours. One data hue with tints: colour never encodes identity
// (outlet, group), only emphasis. Kept in JS because SVG presentation
// attributes cannot read CSS variables.
export const COLORS = {
  data: "#2B5C8A",
  dataMid: "#6E93B8",
  dataLight: "#A9C1D9",
  ink: "#1D2733",
  muted: "#5E6A78",
  grid: "#E6E9ED",
  background: "#FFFFFF",
};

export const AXIS_TICK = { fill: COLORS.muted, fontSize: 12 };
