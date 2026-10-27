// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// Answer identities: colour + shape, as texquiz.sty draws them on the slides
// (\definecolor{texquiz-1} ... and \texquiz@shape): 1 red triangle, 2 blue diamond,
// 3 yellow circle, 4 green square, 5 purple star, 6 teal hexagon.

export const COLORS = ["#E21B3C", "#1368CE", "#D89E00", "#26890C", "#864CBF", "#0AA3A3"];

const PATHS = {
  1: "M50 8 L94 88 L6 88 Z",
  2: "M50 4 L96 50 L50 96 L4 50 Z",
  3: "M50 6 A44 44 0 1 1 49.99 6 Z",
  4: "M12 12 H88 V88 H12 Z",
  5: "M50 4 L61 37 L96 37 L68 58 L78 92 L50 72 L22 92 L32 58 L4 37 L39 37 Z",
  6: "M27 8 H73 L96 50 L73 92 H27 L4 50 Z",
};

export function color(shape) {
  return COLORS[(shape - 1) % COLORS.length];
}

// an inline SVG of the shape, filled (default: white, for use on the shape's colour)
export function shapeSVG(shape, fill = "#fff") {
  return `<svg viewBox="0 0 100 100" aria-hidden="true"><path d="${PATHS[shape] || PATHS[4]}" fill="${fill}"/></svg>`;
}
