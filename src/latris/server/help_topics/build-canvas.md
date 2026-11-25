---
title: Visualise Mode
category: build
summary: Edit the conceptual model directly on the graph canvas.
---

## What Visualise mode is for

Visualise mode is the main graph canvas for the conceptual model and selected formal view. It is best for direct editing and spatial reasoning.

## Common actions

- Add nodes.
- Connect nodes with edges.
- Rename nodes inline.
- Select nodes or edges to edit details in the inspector.
- Arrange the view.
- Open context actions on graph elements.

## Substrate versus views

The conceptual substrate is the shared model. Formal views such as CLD, DAG, and FCM add model-specific requirements. If an element is not ready for a selected view, use Analyse and Configure to complete the required attributes.

## Links

- To link two factors, drag from the dot on one factor's edge and let go anywhere on the other factor.
- Links meet each factor's border on the line between the two, so they stay attached sensibly when you move a factor.
- Causal maps draw curved links that bow outward around each feedback loop, as the report's figure does. Trees (fault tree, decision tree, theory of change, bow-tie) draw right-angle connectors.
- Select a curved link to show its bend handle. Drag it to reshape the curve; double-click it to go back to the automatic bow.
- Arrange → Links switches between Auto, Curved and Right-angle. The choice is remembered for this project on this device.

## Layout

Canvas positions are saved separately from semantic model data. Moving a node changes the layout, not the underlying claim.

Arrange → Re-layout All lays the whole map out again: maps with feedback loops are spread so each loop reads as a ring, and maps without loops are laid out top-down. Re-layout clears hand-made link bends.
