<script lang="ts">
  // The NON-COLOUR half of a feedback mark (Jony; CLAUDE.md section 0a keeps
  // basic a11y in scope). Colour is never the only signal, so every marked
  // surface - board cell and keyboard key alike - carries a small corner shape
  // as well: a filled square for correct, the same square turned 45 degrees for
  // present, and a hollow ring for absent.
  //
  // It is one component rather than three copies of the same markup precisely
  // because the promise is that the cue is IDENTICAL everywhere: a shape that
  // meant "correct" on the board and something else on the keyboard would be
  // worse than no shape at all. The three branches are written out rather than
  // built from a lookup because Tailwind resolves class names by scanning the
  // source, and a concatenated class would emit no CSS at all.
  //
  // The shape is aria-hidden: the state is already in the cell's own label, and
  // announcing it twice would read every tile out as two facts.
  import type { Mark } from "./logic";

  interface Props {
    mark: Mark;
  }

  let { mark }: Props = $props();
</script>

{#if mark === "correct"}
  <span aria-hidden="true" class="absolute right-0.5 top-0.5 h-1.5 w-1.5 bg-current"></span>
{:else if mark === "present"}
  <span
    aria-hidden="true"
    class="absolute right-0.5 top-0.5 h-1.5 w-1.5 rotate-45 bg-current"
  ></span>
{:else}
  <span
    aria-hidden="true"
    class="absolute right-0.5 top-0.5 h-1.5 w-1.5 rounded-full border border-current"
  ></span>
{/if}
