// SPDX-FileCopyrightText: 2026 Stefan Decker
// SPDX-License-Identifier: Apache-2.0
// Answer identities: colour + shape, as texquiz.sty draws them on the slides
// (\definecolor{texquiz-1} ... and \texquiz@shape): 1 red triangle, 2 blue diamond,
// 3 yellow circle, 4 green square, 5 purple star, 6 teal hexagon. Past six both repeat, so a
// choice of seven or more options gives every option its letter, A to Z, inside its shape
// (LETTERED; texactivity.sty draws the same on the slide).

export const COLORS = ["#E21B3C", "#1368CE", "#D89E00", "#26890C", "#864CBF", "#0AA3A3"];
export const LETTERED = 7;                   // this many options or more: each carries its letter

const PATHS = {
  1: "M50 8 L94 88 L6 88 Z",
  2: "M50 4 L96 50 L50 96 L4 50 Z",
  3: "M50 6 A44 44 0 1 1 49.99 6 Z",
  4: "M12 12 H88 V88 H12 Z",
  5: "M50 4 L61 37 L96 37 L68 58 L78 92 L50 72 L22 92 L32 58 L4 37 L39 37 Z",
  6: "M27 8 H73 L96 50 L73 92 H27 L4 50 Z",
};
// where a letter sits in each shape, and how large: [the centre's y, the font size] (the triangle's
// and the star's room is lower down and smaller)
const LETTER_AT = { 1: [64, 40], 2: [51, 46], 3: [51, 54], 4: [51, 56], 5: [56, 32], 6: [51, 54] };

export function color(shape) {
  return COLORS[(shape - 1) % COLORS.length];
}

export function letter(i) {
  // the i-th option's letter (from 0): A, B, ... Z
  return String.fromCharCode(65 + i);
}

// an inline SVG of the shape, filled (default: white, for use on the shape's colour) - with a letter inside
// it in the shape's colour where one is given. Shapes past six repeat, as the colours do.
export function shapeSVG(shape, fill = "#fff", mark = "") {
  const s = ((((shape - 1) % 6) + 6) % 6) + 1;
  const [y, size] = LETTER_AT[s] || LETTER_AT[4];
  const text = mark ? `<text x="50" y="${y}" text-anchor="middle" dominant-baseline="central" font-family="Arial, Helvetica, sans-serif"
    font-weight="700" font-size="${size}" fill="${color(shape)}">${String(mark).replace(/[&<>"']/g, "")}</text>` : "";
  return `<svg viewBox="0 0 100 100" aria-hidden="true"><path d="${PATHS[s] || PATHS[4]}" fill="${fill}"/>${text}</svg>`;
}
