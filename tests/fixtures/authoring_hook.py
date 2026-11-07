# SPDX-License-Identifier: Apache-2.0
"""Synthetic counter fixture for authoring contracts, not the transaction plugin."""
from texstage.plugin_api.v1 import PluginV1, PreparedAuthoring, PreparedItem, Transition, latex_escape


def prepare_source(source, context):
    initial, increment = source["initial"], source["increment"]
    if type(initial) is not int or type(increment) is not int:
        raise ValueError("integer counter required")
    title = latex_escape(source.get("label", "Counter"))
    exercise = rf"\textbf{{{title}}}\par Initial value: {initial}.\par Add {increment}.\par Predict the final value."
    solution = exercise + rf"\par Worked answer: {initial + increment}."
    return PreparedAuthoring(PreparedItem(
        public={"initial": initial, "increment": increment},
        private={"answer": initial + increment},
        evaluations={"value": {"seed": "counter", "references": []}},
        diagnostics=["Prepared the counter example."]),
        {"exercise": exercise, "solutions": solution})


class Counter:
    def initial_state(self, item, context):
        return {}

    def transition(self, state, event, context):
        return Transition(state)

    def view(self, state, audience, context):
        return {}


def create_plugin():
    return PluginV1(authoring_hooks={"counter": prepare_source}, state_hooks={"plane": Counter()})
