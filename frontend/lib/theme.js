// Chart colours. One data hue with tints: colour never encodes identity
// (outlet, group), only emphasis. Kept in JS because SVG presentation
// attributes cannot read CSS variables.
export const COLORS = {
  data: "#2F6B3C",
  dataMid: "#5A9366",
  dataLight: "#B9D4BE",
  ink: "#1A1A1A",
  muted: "#5B5346",
  grid: "#E8DFCB",
  background: "#FFFFFF",
};

export const AXIS_TICK = { fill: COLORS.muted, fontSize: 12 };
