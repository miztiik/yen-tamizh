<script lang="ts">
  // CountdownHeader - the Time Trial's clock, in the shell's header slot.
  //
  // It is a PURE READOUT. It owns no timer, schedules no frame and reads no
  // clock: the run's `Countdown` derives the remaining time and hands it down,
  // so there is exactly one clock in the Mode and this cannot disagree with it.
  //
  // WHAT IT IS PERCEIVED BY (v2 a11y): the DIGITS carry the value. `role="timer"`
  // names this region a live numeric readout whose implicit `aria-live` is off,
  // so an assistive technology can read it on demand instead of being shouted a
  // new number sixty times a second - and `aria-label` gives it the name the
  // digits alone cannot ("remaining time"). Colour is EMPHASIS ONLY: the last
  // ten seconds turn the readout to the danger token AND the numbers keep
  // counting down, so a player who cannot see that change still reads exactly
  // the same fact from the same place.
  //
  // Chrome is Row 10 tokens and a Glyph by id - no bespoke colour, no inline SVG
  // (Holy Law #10). The digits are tabular so a 2 does not shift the layout when
  // it becomes a 1 (nothing on this screen may move except the number).
  import Glyph from "../designsystem/Glyph.svelte";
  import { formatClock } from "../modes/TimeTrialMode";

  interface Props {
    /** Milliseconds left in the run, derived by the Mode's Countdown. */
    remainingMs: number;
    /** The whole run, so "running out" is a fraction rather than a constant. */
    durationMs: number;
    /** The readout's accessible name (Tamil copy, from the Mode). */
    label: string;
  }

  let { remainingMs, durationMs, label }: Props = $props();

  // The last tenth of the run, floored at five seconds and capped at ten, so a
  // short sprint still gets a warning and a long one does not spend a minute
  // looking urgent.
  const lowThresholdMs = $derived(Math.min(10_000, Math.max(5_000, durationMs / 10)));
  const low = $derived(remainingMs <= lowThresholdMs);
  const clock = $derived(formatClock(remainingMs));
</script>

<div
  class="flex items-center gap-xs rounded-md px-sm py-xs transition-colors duration-fast ease-smooth {low
    ? 'text-danger'
    : 'text-text-secondary'}"
  role="timer"
  aria-label={label}
  data-testid="countdown"
  data-low={low}
>
  <Glyph id="timer" class="shrink-0" />
  <span class="font-mono text-lg font-semibold tabular-nums" data-testid="countdown-clock">
    {clock}
  </span>
</div>
