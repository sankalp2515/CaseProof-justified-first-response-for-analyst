export function tourOutcome(workflow) {
  const delivered =
    workflow?.status === "completed" &&
    new Set(
      (workflow.deliveries || [])
        .filter((d) => d.status === "sent")
        .map((d) => d.kind),
    ).size >= 2;
  const owned =
    workflow?.followup?.version > 0 &&
    !!workflow.followup.owner &&
    !!workflow.followup.next_action &&
    workflow.followup.state === "awaiting_external";
  return { delivered, owned, complete: delivered && owned };
}
