// Interactive demo: "Your turn. Pick a line 2."
// Fully client-side. The lines follow the robot's real hint ladder (brain/policy.py):
// a first nudge built from SAFE_NUDGE ("...when you {act} on line {n}"), then, once, a more
// specific second hint if the student keeps going with the mistake. Confidence values are illustrative.

(function () {
  const CHOICES = [
    {
      kind: "wrong_rule",
      confidence: "0.86",
      num: "2x sin x − x² cos x", den: "sin² x",
      first: "Hmm, take another look at which rule you picked when you took the derivative on line 2.",
      second: "Look at what ended up on the bottom of your answer on line 2.",
      hidden: "x² · sin x is a product, not a quotient. The product rule gives 2x sin x + x² cos x.",
    },
    {
      kind: "misapplied",
      confidence: "0.81",
      line: "2x sin x + x² sin x",
      first: "Check how you took the derivative on line 2.",
      second: "Look at what happened to the sin x in the second term on line 2.",
      hidden: "Right rule, but the second term needs the derivative of sin x, which is cos x. It should read x² cos x.",
    },
    {
      kind: "arithmetic",
      confidence: "0.78",
      line: "2x sin x + x cos x",
      first: "Double-check the arithmetic when you took the derivative on line 2.",
      second: "Check the power on the x in the second term on line 2.",
      hidden: "The x² lost its power in the second term. It should be x² cos x, not x cos x.",
    },
    {
      kind: "ok",
      confidence: "0.92",
      line: "2x sin x + x² cos x",
      first: "Nice work, that all checks out.",
      second: null,
      hidden: "Nothing held back this time. Product rule, applied correctly.",
    },
  ];

  const AUTOPLAY_MS = 30000;
  const CHAR_MS = 45;     // handwriting speed for the write-in
  const THINK_MS = 1400;  // "thinking" face before the verdict
  const TALK_MS = 2400;
  const LASER_HOLD_MS = 4000; // robot.py point_at(hold_s=4.0): aim, light for 4 s, then off

  const $ = (id) => document.getElementById(id);
  const section = $("demo");
  const canvas = $("demo-otter");
  if (!section || !canvas || !window.Otter) return;

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const otter = new Otter(canvas, { still: reduceMotion.matches });
  otter.setMood("listening");

  const bubble = $("demo-bubble");
  const ghost = $("demo-ghost");
  const term = $("demo-term");
  const written = $("demo-written");
  const circle = $("demo-circle");
  const laser = $("demo-laser");
  const choicesBox = $("demo-choices");
  const buttons = [...choicesBox.querySelectorAll(".choice")];
  const status = $("verdict-status");
  const vVerdict = $("v-verdict"), vSaid = $("v-said"), vDid = $("v-did");
  const vHint = $("v-hint"), keepBtn = $("v-keep");
  const vHidden = $("v-hidden"), vHiddenSr = $("v-hidden-sr"), revealBtn = $("v-reveal");
  const resetBtn = $("demo-reset");

  let runId = 0;          // bumps on every pick/reset so stale async steps stop
  let interacted = false; // any click cancels the auto-play
  let autoTimer = null;
  let autoPending = false;
  let demoVisible = false;
  let current = null;     // the choice on the board, once the otter has judged it

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const muted = (text) => `<span class="mono muted">${text}</span>`;
  const HINT_WAITING = muted("Only if you keep going with the mistake");

  function replay(el, cls) {
    el.classList.remove(cls);
    void el.offsetWidth;
    el.classList.add(cls);
  }

  // Wrap every character in a span so the line can "write itself in".
  function inkSpans(text, startIndex) {
    const frag = document.createDocumentFragment();
    [...text].forEach((ch, i) => {
      const span = document.createElement("span");
      span.className = "ch";
      span.textContent = ch;
      span.style.animationDelay = `${(startIndex + i) * CHAR_MS}ms`;
      frag.appendChild(span);
    });
    return frag;
  }

  function writeLine(choice) {
    written.textContent = "";
    let count = 0;
    if (choice.num) {
      const frac = document.createElement("span");
      frac.className = "frac";
      const num = document.createElement("span");
      const den = document.createElement("span");
      num.appendChild(inkSpans(choice.num, 0));
      den.appendChild(inkSpans(choice.den, choice.num.length));
      frac.append(num, den);
      written.appendChild(frac);
      count = choice.num.length + choice.den.length;
    } else {
      written.appendChild(inkSpans(choice.line, 0));
      count = choice.line.length;
    }
    // Screen readers get the whole line at once instead of letter by letter.
    [...written.children].forEach((el) => el.setAttribute("aria-hidden", "true"));
    const sr = document.createElement("span");
    sr.className = "sr-only";
    sr.textContent = choice.num ? `(${choice.num}) over ${choice.den}` : choice.line;
    written.appendChild(sr);
    written.classList.toggle("writing", !reduceMotion.matches);
    return reduceMotion.matches ? 0 : count * CHAR_MS + 250;
  }

  function setHidden(text, revealed) {
    vHidden.textContent = text;
    vHidden.classList.toggle("is-revealed", revealed);
    vHidden.setAttribute("aria-hidden", String(!revealed));
    vHiddenSr.hidden = revealed;
    revealBtn.setAttribute("aria-pressed", String(revealed));
    revealBtn.textContent = revealed ? "Hide" : "Reveal";
  }

  let laserTimer = null;

  function clearMarks() {
    clearTimeout(laserTimer);
    circle.classList.add("is-hidden");
    laser.classList.add("is-hidden");
    circle.classList.remove("draws");
    laser.classList.remove("lands");
  }

  // Like the robot: the laser lights on line 2 for 4 s, then switches off.
  // The red-pen circle stays, so the visitor still sees which line was flagged.
  function pointLaser() {
    clearTimeout(laserTimer);
    laser.classList.remove("is-hidden");
    if (!reduceMotion.matches) replay(laser, "lands");
    laserTimer = setTimeout(() => laser.classList.add("is-hidden"), LASER_HOLD_MS);
  }

  function cancelAutoplay() {
    interacted = true;
    autoPending = false;
    clearTimeout(autoTimer);
  }

  async function pick(index, auto = false) {
    if (!auto) cancelAutoplay();
    const id = ++runId;
    const choice = CHOICES[index];
    const wrong = choice.kind !== "ok";

    otter.stopTalk();
    clearMarks();
    current = null;
    resetHintRow();
    buttons.forEach((b, i) => b.setAttribute("aria-pressed", String(i === index)));
    choicesBox.classList.add("is-revealed");

    status.textContent = auto
      ? "Auto-played after 30 s. Pick another line to try it yourself."
      : `You wrote option ${"ABCD"[index]}`;
    vVerdict.innerHTML = muted("Reading line 2…");
    vSaid.innerHTML = muted("Nothing yet");
    vDid.innerHTML = muted("Nothing yet");
    setHidden("The otter keeps the fix to itself until you find it.", false);
    revealBtn.disabled = true;

    // 1. line 2 writes itself in
    ghost.hidden = true;
    term.hidden = false;
    otter.setMood("listening");
    setBubble(bubble, "Watching the board…");
    await sleep(writeLine(choice));
    if (id !== runId) return;

    // 2. thinking
    otter.setMood("thinking");
    setBubble(bubble, "Reading line 2…");
    await sleep(reduceMotion.matches ? 0 : THINK_MS);
    if (id !== runId) return;

    // 3. verdict: laser + red pen on a mistake, then the real line
    if (wrong) {
      circle.classList.remove("is-hidden");
      if (!reduceMotion.matches) replay(circle, "draws");
      pointLaser();
    }
    const kindClass = wrong ? "kind-bad" : "kind-ok";
    vVerdict.innerHTML = `<span class="kind ${kindClass}">${choice.kind}</span><span class="mono">confidence ${choice.confidence}</span>`;
    vSaid.textContent = `“${choice.first}”`;
    vDid.textContent = wrong ? "Laser on line 2 for 4 s · face: confused" : "No laser · face: happy";
    if (wrong) {
      keepBtn.disabled = false;
    } else {
      vHint.innerHTML = muted("Not needed: nothing to fix");
    }
    setHidden(choice.hidden, false);
    revealBtn.disabled = false;
    setBubble(bubble, choice.first);
    current = choice;

    const after = wrong ? "confused" : "happy";
    if (reduceMotion.matches) otter.setMood(after);
    else await otter.talk(TALK_MS, after);
  }

  function reset() {
    cancelAutoplay();
    runId++;
    otter.stopTalk();
    otter.setMood("listening");
    setBubble(bubble, "Watching the board…");
    clearMarks();
    written.textContent = "";
    term.hidden = true;
    ghost.hidden = false;
    buttons.forEach((b) => b.setAttribute("aria-pressed", "false"));
    choicesBox.classList.remove("is-revealed");
    status.textContent = "Waiting for your line 2";
    vVerdict.innerHTML = muted("Pick a line 2 above");
    vSaid.innerHTML = muted("Nothing yet");
    vDid.innerHTML = muted("Nothing yet");
    setHidden("The otter keeps the fix to itself until you find it.", false);
    revealBtn.disabled = true;
    current = null;
    resetHintRow();
  }

  function resetHintRow() {
    vHint.innerHTML = HINT_WAITING;
    keepBtn.disabled = true;
    keepBtn.textContent = "Keep going with the mistake";
  }

  // Level 2 of the ladder: the student keeps going with the mistake still there,
  // so the otter gives its more specific hint, once, and points at line 2 again.
  async function keepGoing() {
    if (!current || !current.second || keepBtn.disabled) return;
    cancelAutoplay();
    keepBtn.disabled = true;
    keepBtn.textContent = "Said once";
    vHint.textContent = `“${current.second}”`;
    vDid.textContent = "Laser back on line 2 for 4 s · face: confused · second hint, said once";
    setBubble(bubble, current.second);
    pointLaser();
    if (reduceMotion.matches) otter.setMood("confused");
    else await otter.talk(TALK_MS, "confused");
  }

  buttons.forEach((b, i) => b.addEventListener("click", () => pick(i)));
  resetBtn.addEventListener("click", reset);
  keepBtn.addEventListener("click", keepGoing);
  revealBtn.addEventListener("click", () => {
    const revealed = revealBtn.getAttribute("aria-pressed") !== "true";
    setHidden(vHidden.textContent, revealed);
  });

  // Auto-play: 30 s after the demo first comes into view, if nobody clicked, pick option A.
  // If the visitor has scrolled away by then, it plays the next time the demo is on screen.
  function autoplayNow() {
    if (interacted) return;
    if (demoVisible) { interacted = true; pick(0, true); } else autoPending = true;
  }
  if ("IntersectionObserver" in window) {
    new IntersectionObserver((entries) => {
      demoVisible = entries[0].isIntersecting;
      if (!demoVisible || interacted) return;
      if (autoPending) { autoplayNow(); return; }
      if (!autoTimer) autoTimer = setTimeout(autoplayNow, AUTOPLAY_MS);
    }, { threshold: 0.25 }).observe(section);
  }
})();
