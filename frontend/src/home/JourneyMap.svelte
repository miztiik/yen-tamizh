<script lang="ts">
  // The winding-path map (docs/concepts/journeys.md). It is Journey CHROME that
  // doubles as level-select: the path a player is walking, drawn as the nodes
  // they have cleared, the one they are on, and the ones still ahead.
  //
  // ONE component, two layouts. The meander swaps AXIS at the breakpoint rather
  // than swapping component: a phone reads a column, so alternate nodes step
  // sideways and the path runs down; a desktop reads a row, so alternate nodes
  // step up and the path runs across. Two components would be two places to fix
  // a state bug, and the states are the whole content here (Jony).
  //
  // Locked nodes are NOT disabled buttons. A dead control invites a tap and then
  // punishes it, so a locked node is plainly not a button - the same ruling the
  // Home makes about a Mode that is not built yet - while every reachable node
  // is a real button with a real name and a visible focus ring.
  import Glyph from "../designsystem/Glyph.svelte";
  import { copyText } from "../lib/config";
  import type { Journey } from "../contracts";
  import type { NodeState } from "../modes/JourneyMode";

  interface Props {
    journey: Journey;
    /** One state per node, in walking order (JourneyMode.nodeStates). */
    states: NodeState[];
    onPlay: (nodeId: string) => void;
  }

  let { journey, states, onPlay }: Props = $props();

  // The glyph each state wears. A cleared node shows what it earned; the node
  // the player is on wears the marker that says "you are here"; a locked node
  // wears nothing at all, because a glyph on a node you cannot open is
  // decoration pretending to be information.
  const GLYPHS: Record<NodeState, string | null> = {
    completed: "check",
    available: "star",
    locked: null,
  };

  const nodes = $derived(
    journey.nodes.map((node, index) => ({
      node,
      index,
      state: states[index] ?? "locked",
      title: copyText(`game-${node.gameId}-title`),
      stateLabel: copyText(`journey-node-${states[index] ?? "locked"}`),
    })),
  );

  const cleared = $derived(states.filter((state) => state === "completed").length);
</script>

<section class="flex flex-col gap-md" data-testid="journey-map">
  <p class="text-center font-tamil text-sm text-text-secondary" data-testid="journey-progress">
    {copyText("journey-progress")}
    <span class="font-mono text-text-primary">{cleared}/{journey.nodes.length}</span>
  </p>

  <ol
    class="flex flex-col items-center py-lg md:flex-row md:items-center md:justify-start md:overflow-x-auto md:py-2xl"
    aria-label={copyText("journey-map-label")}
  >
    {#each nodes as entry (entry.node.id)}
      <li class="flex flex-col items-center md:flex-row">
        {#if entry.index > 0}
          <!-- The path itself: a segment between two nodes, vertical on a
               phone and horizontal on a desktop. Decorative - the ORDER is
               already carried by the ordered list. -->
          <span
            class="h-8 w-0.5 shrink-0 rounded-full bg-border md:h-0.5 md:w-10"
            aria-hidden="true"
          ></span>
        {/if}
        <!-- The meander. Alternate nodes step off the axis, and which axis is
             the breakpoint's only job. -->
        <div
          class="flex w-24 shrink-0 flex-col items-center gap-xs {entry.index % 2 === 1
            ? 'translate-x-10 md:translate-x-0 md:-translate-y-10'
            : ''}"
        >
          {#if entry.state === "locked"}
            <div
              class="flex size-12 items-center justify-center rounded-full border border-dashed border-border text-text-tertiary"
              data-testid="journey-node"
              data-node-id={entry.node.id}
              data-state={entry.state}
            >
              <span class="font-mono text-sm">{entry.index + 1}</span>
              <span class="sr-only">{entry.title} - {entry.stateLabel}</span>
            </div>
          {:else}
            <button
              type="button"
              class="flex size-12 items-center justify-center gap-xs rounded-full border-2 shadow-sm transition-transform duration-fast ease-spring hover:-translate-y-px focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent {entry.state ===
              'completed'
                ? 'border-accent bg-accent text-bg'
                : 'border-accent bg-bg-elevated text-accent'}"
              data-testid="journey-node"
              data-node-id={entry.node.id}
              data-state={entry.state}
              aria-label={`${entry.index + 1}. ${entry.title} - ${entry.stateLabel}`}
              onclick={() => onPlay(entry.node.id)}
            >
              {#if GLYPHS[entry.state]}
                <Glyph id={GLYPHS[entry.state] ?? "star"} size="1.25rem" />
              {:else}
                <span class="font-mono text-sm">{entry.index + 1}</span>
              {/if}
            </button>
          {/if}
          <span
            class="text-center font-tamil text-xs leading-tight {entry.state === 'locked'
              ? 'text-text-tertiary'
              : 'text-text-secondary'}"
          >
            {entry.title}
          </span>
        </div>
      </li>
    {/each}
  </ol>
</section>
