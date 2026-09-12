export type Page = "campaigns" | "campaign" | "sweeps" | "trajectories" | "residence" | "space-charge" | "reports";

export function setupNavigation(onChange: (page: Page) => void): void {
  const links = [...document.querySelectorAll<HTMLAnchorElement>("[data-page]")];
  function update(): void {
    const requested = location.hash.slice(1).split("/")[0];
    const page = requested === "campaign" ? "campaign" : links.find(link => link.dataset.page === requested)?.dataset.page as Page | undefined;
    const active = page ?? "campaigns";
    document.body.dataset.page = active;
    for (const link of links) {
      if (link.dataset.page === (active === "campaign" ? "campaigns" : active)) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
    document.title = `${active === "campaign" ? "Campaign report" : links.find(link => link.dataset.page === active)?.textContent} · Fusion`;
    onChange(active);
    window.scrollTo(0, 0);
  }
  window.addEventListener("hashchange", update);
  update();
}

export function setupSidebar(sidebar: HTMLElement, handle: HTMLElement): void {
  let width = 240;
  let dragging = false;
  const maximum = (): number => Math.min(440, Math.max(180, window.innerWidth - 420));
  function resize(next: number): void {
    width = Math.round(Math.max(180, Math.min(maximum(), next)));
    document.documentElement.style.setProperty("--sidebar-width", `${width}px`);
    handle.setAttribute("aria-valuenow", String(width));
    handle.setAttribute("aria-valuemax", String(maximum()));
  }
  function save(): void {
    try { localStorage.setItem("fusion-sidebar-width", String(width)); }
    catch { /* Layout still works when browser storage is unavailable. */ }
  }
  try {
    const saved = localStorage.getItem("fusion-sidebar-width");
    if (saved !== null && Number.isFinite(Number(saved))) width = Number(saved);
  } catch { /* Browser storage is optional. */ }
  resize(width);
  handle.onpointerdown = event => {
    if (event.button !== 0) return;
    event.preventDefault();
    dragging = true;
    handle.setPointerCapture(event.pointerId);
    document.body.classList.add("resizing-sidebar");
  };
  handle.onpointermove = event => {
    if (dragging) resize(event.clientX - sidebar.getBoundingClientRect().left);
  };
  handle.onlostpointercapture = () => {
    dragging = false;
    document.body.classList.remove("resizing-sidebar");
    save();
  };
  handle.onpointerup = event => {
    if (handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId);
  };
  handle.onkeydown = event => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    resize(event.key === "Home" ? 180 : event.key === "End" ? maximum() :
      width + (event.key === "ArrowRight" ? 16 : -16));
    save();
  };
  handle.ondblclick = () => { resize(240); save(); };
  window.addEventListener("resize", () => resize(width));
}
