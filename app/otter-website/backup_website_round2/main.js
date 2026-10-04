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
      otter.setMood("listening"); bubble.textContent = "Watching the board…";
      await sleep(2400);
      otter.setMood("thinking"); bubble.textContent = "Reading line 2…";
      await sleep(1800);
      flagged(true); showFlag("Line 2 · wrong_rule · first nudge");
      bubble.textContent = "Hmm, take another look at which rule you picked when you took the derivative on line 2.";
      await otter.talk(3200, "confused");
      await sleep(2600);
      // the student keeps going with the mistake: the second hint, once
      showFlag("Line 2 · wrong_rule · second hint");
      pointLaser();
      bubble.textContent = "Look at what ended up on the bottom of your answer on line 2.";
      await otter.talk(2600, "confused");
      await sleep(2600);

      flagged(false); showFlag("");
      wrong.hidden = true; fixed.hidden = false;
      otter.setMood("listening"); bubble.textContent = "Watching the board…";
      await sleep(1500);
      otter.setMood("thinking"); bubble.textContent = "Reading line 2…";
      await sleep(1400);
      showFlag("Line 2 · ok", true);
      bubble.textContent = "Nice work, that all checks out.";
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
