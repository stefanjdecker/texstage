// SPDX-License-Identifier: Apache-2.0
// Built-in activity feedback can remain in state after its slide is left.
// A current plugin with phone input must take priority over that retained view.
export function activeContentType(state, types) {
  if (state.session.finished || ["get-ready", "open"].includes(state.round?.phase)) return undefined;
  if (types.plugins && state.plugins?.items.some(d => d.modules["participant-input"])) return "plugins";
  return Object.keys(types).find(name => name !== "plugins" && state[name]);
}
