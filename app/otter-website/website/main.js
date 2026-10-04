// Otter Tutor: page-level behavior.

// Reduced motion: don't autoplay the 360 video; give the visitor play controls instead.
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const robotVideo = document.querySelector(".robot-video");

function applyMotionPreference() {
  if (!robotVideo) return;
  if (reduceMotion.matches) {
    robotVideo.pause();
    robotVideo.controls = true;
  } else {
    robotVideo.controls = false;
    robotVideo.play().catch(() => {}); // autoplay can be blocked; the poster stays visible
  }
}

applyMotionPreference();
reduceMotion.addEventListener("change", applyMotionPreference);

// Nameplate + footer wordmark: scale the text so it spans its tile edge to edge.
function fitText(el) {
  el.style.fontSize = "";
  const range = document.createRange();
  range.selectNodeContents(el);
  const textWidth = range.getBoundingClientRect().width;
  const style = getComputedStyle(el);
  const available = el.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
  if (textWidth > 0) el.style.fontSize = `${parseFloat(style.fontSize) * (available / textWidth) * 0.995}px`;
}
function fitAll() { document.querySelectorAll("[data-fit]").forEach(fitText); }

document.fonts.ready.then(fitAll);
let fitTimer;
window.addEventListener("resize", () => { clearTimeout(fitTimer); fitTimer = setTimeout(fitAll, 100); });

// Restart a one-shot CSS animation class (laser landing, red pen drawing).
function replay(el, cls) {
  el.classList.remove(cls);
  void el.offsetWidth; // force a reflow so the animation starts again
  el.classList.add(cls);
}
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Hero: a short loop of the official demo script.
// watching -> reading line 2 -> laser + first nudge -> second hint -> line fixed -> praise.
(function heroLoop() {
  const canvas = document.getElementById("hero-otter");
  if (!canvas || !window.Otter) return;
  const otter = new Otter(canvas, { still: reduceMotion.matches });
  const bubble = document.getElementById("hero-bubble");
  const wrong = document.getElementById("hero-wrong");
  const fixed = document.getElementById("hero-fixed");
  const circle = document.getElementById("hero-circle");
  const laser = document.getElementById("hero-laser");
  const flag = document.getElementById("hero-flag");

  // Like the robot (robot.py point_at): the laser lights for 4 s, then switches off.
  let laserTimer = null;
  function pointLaser() {
    clearTimeout(laserTimer);
    laser.classList.remove("is-hidden");
    replay(laser, "lands");
    laserTimer = setTimeout(() => laser.classList.add("is-hidden"), 4000);
  }
  function flagged(on) {
    circle.classList.toggle("is-hidden", !on);
    if (on) { replay(circle, "draws"); pointLaser(); }
    else { clearTimeout(laserTimer); laser.classList.add("is-hidden"); }
  }
  function showFlag(text, ok) {
    flag.textContent = text;
    flag.classList.toggle("is-hidden", !text);
    flag.classList.toggle("flag-ok", !!ok);
  }

  // Reduced motion: one still frame of the key moment, no loop.
  if (reduceMotion.matches) {
    otter.setMood("confused");
    return;
  }

  async function run() {
    for (;;) {
      wrong.hidden = false; fixed.hidden = true;
      flagged(false); showFlag("");
      otter.setMood("listening"); setBubble(bubble, "Watching the board…");
      await sleep(2400);
      otter.setMood("thinking"); setBubble(bubble, "Reading line 2…");
      await sleep(1800);
      flagged(true); showFlag("Line 2 · wrong_rule · first nudge");
      setBubble(bubble, "Hmm, take another look at which rule you picked when you took the derivative on line 2.");
      await otter.talk(3200, "confused");
      await sleep(2600);
      // the student keeps going with the mistake: the second hint, once
      showFlag("Line 2 · wrong_rule · second hint");
      pointLaser();
      setBubble(bubble, "Look at what ended up on the bottom of your answer on line 2.");
      await otter.talk(2600, "confused");
      await sleep(2600);

      flagged(false); showFlag("");
      wrong.hidden = true; fixed.hidden = false;
      otter.setMood("listening"); setBubble(bubble, "Watching the board…");
      await sleep(1500);
      otter.setMood("thinking"); setBubble(bubble, "Reading line 2…");
      await sleep(1400);
      showFlag("Line 2 · ok", true);
      setBubble(bubble, "Nice work, that all checks out.");
      await otter.talk(2000, "happy");
      await sleep(3200);
    }
  }
  run();
})();

// Team avatars: use the image in assets/avatars/ when it exists, otherwise keep the initial.
document.querySelectorAll("[data-avatar]").forEach((el) => {
  const img = new Image();
  img.alt = "";
  img.onload = () => { el.textContent = ""; el.appendChild(img); el.classList.add("has-img"); };
  img.src = el.dataset.avatar;
});

// =========================================================
// Round 3: smoother motion, photo lightbox, circuit hotspots
// =========================================================

// Speech bubbles crossfade instead of snapping to the new line.
// (A function declaration, so it is ready before the hero loop and demo.js call it.)
function setBubble(el, text) {
  if (!el) return;
  el._next = text;
  if (reduceMotion.matches) { el.textContent = text; return; }
  if (el._swapping || el.textContent === text) return;
  el._swapping = true;
  el.classList.add("is-swapping");
  setTimeout(() => {
    el.textContent = el._next;
    el.classList.remove("is-swapping");
    el._swapping = false;
  }, 200);
}

// Reveal on scroll: tiles rise and fade in, staggered. Only sections that start
// below the fold are hidden, so the first screen is complete at rest.
(function reveal() {
  const root = document.documentElement;
  if (reduceMotion.matches || !("IntersectionObserver" in window)) { root.classList.remove("js-reveal"); return; }
  const groups = ".steps, .ladder, .team, .choices, .strip";
  const items = [];
  const vh = window.innerHeight;
  document.querySelectorAll("main > section, .site-footer").forEach((sec) => {
    if (sec.getBoundingClientRect().top < vh * 0.9) return;
    [...sec.children].forEach((child) => {
      (child.matches(groups) ? [...child.children] : [child]).forEach((el) => { el.classList.add("rv"); items.push(el); });
    });
  });
  const show = (el, k) => { el.style.setProperty("--i", Math.min(k, 8)); el.classList.add("is-in"); };
  const io = new IntersectionObserver((entries) => {
    entries.filter((e) => e.isIntersecting)
      .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top || a.boundingClientRect.left - b.boundingClientRect.left)
      .forEach((e, k) => { show(e.target, k); io.unobserve(e.target); });
  }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
  items.forEach((el) => io.observe(el));
  // Safety net: anything on screen that never got its turn shows up anyway.
  let sweepTimer;
  const sweep = () => items.forEach((el) => {
    if (!el.classList.contains("is-in") && el.getBoundingClientRect().top < window.innerHeight) { show(el, 0); io.unobserve(el); }
  });
  setTimeout(sweep, 2500);
  window.addEventListener("scroll", () => { clearTimeout(sweepTimer); sweepTimer = setTimeout(sweep, 450); }, { passive: true });
})();

// Photo lightbox: click or Enter opens, arrows move, Esc or click outside closes.
(function lightbox() {
  const dlg = document.getElementById("lightbox");
  if (!dlg || typeof dlg.showModal !== "function") return;
  const img = document.getElementById("lb-img");
  const cap = document.getElementById("lb-cap");
  const shots = [...document.querySelectorAll("img[data-lightbox]")];
  let idx = 0, opener = null;
  function show(i) {
    idx = (i + shots.length) % shots.length;
    const s = shots[idx];
    img.src = s.currentSrc || s.src;
    img.alt = s.alt;
    cap.textContent = s.dataset.caption || s.alt;
    if (img.animate && !reduceMotion.matches) {
      img.animate([{ opacity: 0, transform: "scale(.985)" }, { opacity: 1, transform: "none" }], { duration: 320, easing: "cubic-bezier(.2,.7,.2,1)" });
    }
  }
  function open(i) { opener = shots[i]; show(i); dlg.showModal(); }
  shots.forEach((s, i) => {
    s.tabIndex = 0;
    s.setAttribute("role", "button");
    s.setAttribute("aria-label", "Open photo: " + s.alt);
    s.addEventListener("click", () => open(i));
    s.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(i); } });
  });
  document.getElementById("lb-prev").addEventListener("click", () => show(idx - 1));
  document.getElementById("lb-next").addEventListener("click", () => show(idx + 1));
  document.getElementById("lb-close").addEventListener("click", () => dlg.close());
  dlg.addEventListener("click", (e) => { if (e.target === dlg || e.target.classList.contains("lb-figure")) dlg.close(); });
  dlg.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") { e.preventDefault(); show(idx + 1); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); show(idx - 1); }
  });
  dlg.addEventListener("close", () => { if (opener) opener.focus({ preventScroll: true }); });
})();

// Circuit: a number on the diagram and its row in the pin table light up together.
(function circuitHotspots() {
  const spots = [...document.querySelectorAll(".hotspot")];
  const rows = [...document.querySelectorAll(".pin-table tr[data-part]")];
  if (!spots.length) return;
  let locked = null;
  const mark = (part) => {
    spots.forEach((s) => s.classList.toggle("is-active", s.dataset.part === part));
    rows.forEach((r) => r.classList.toggle("is-active", r.dataset.part === part));
  };
  const back = () => mark(locked);
  spots.forEach((s) => {
    s.setAttribute("aria-pressed", "false");
    s.addEventListener("mouseenter", () => mark(s.dataset.part));
    s.addEventListener("mouseleave", back);
    s.addEventListener("focus", () => mark(s.dataset.part));
    s.addEventListener("blur", back);
    s.addEventListener("click", () => {
      locked = locked === s.dataset.part ? null : s.dataset.part;
      spots.forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.part === locked)));
      mark(locked || s.dataset.part);
    });
  });
  rows.forEach((r) => {
    r.addEventListener("mouseenter", () => mark(r.dataset.part));
    r.addEventListener("mouseleave", back);
  });
})();

// Demo verdict panel: changed rows fill in one after another.
(function verdictCells() {
  const table = document.querySelector(".verdict-table");
  if (!table || reduceMotion.matches) return;
  const cells = [...table.querySelectorAll("td")];
  const rowOf = (td) => [...table.rows].indexOf(td.parentElement);
  const mo = new MutationObserver((muts) => {
    const changed = new Set();
    muts.forEach((m) => {
      const node = m.target.nodeType === 1 ? m.target : m.target.parentElement;
      const td = node && node.closest("td");
      if (td && cells.includes(td)) changed.add(td);
    });
    [...changed].sort((a, b) => rowOf(a) - rowOf(b)).forEach((td, k) => { td.style.setProperty("--row", k); replay(td, "cell-in"); });
  });
  cells.forEach((td) => mo.observe(td, { childList: true, characterData: true, subtree: true }));
})();
