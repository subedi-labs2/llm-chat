import { ShieldCheck } from "lucide-react";
import { animate } from "motion/react";
import { lazy, Suspense, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

// Three.js is only needed for the mascot, so keep it out of the main bundle.
const RobotHead = lazy(() => import("@/components/robot-head"));

const FLIGHT_SECONDS = 0.9;

type MascotHeadProps = {
  landingSlot: HTMLElement | null;
  siteSlot: HTMLElement | null;
  docked: boolean;
  nodding: boolean;
  reducedMotion: boolean;
};

// Renders a single WebGL canvas into a detached container that is moved
// between the landing slot, a fixed "flyer", and the site slot. Moving the
// DOM node (rather than remounting) keeps the WebGL context alive, so the
// head flies and shrinks into place as one continuous object.
export function MascotHead({
  landingSlot,
  siteSlot,
  docked,
  nodding,
  reducedMotion,
}: MascotHeadProps) {
  const [container] = useState(() => {
    const element = document.createElement("div");
    element.style.width = "100%";
    element.style.height = "100%";
    return element;
  });
  const flyerRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (!docked && landingSlot) landingSlot.appendChild(container);
  }, [container, docked, landingSlot]);

  useLayoutEffect(() => {
    const flyer = flyerRef.current;
    if (!docked || !siteSlot || !flyer) return;

    const from = container.getBoundingClientRect();
    if (reducedMotion || from.height === 0) {
      siteSlot.appendChild(container);
      return;
    }

    const to = siteSlot.getBoundingClientRect();
    flyer.style.left = `${from.left}px`;
    flyer.style.top = `${from.top}px`;
    flyer.style.width = `${from.width}px`;
    flyer.style.height = `${from.height}px`;
    flyer.style.transform = "none";
    flyer.style.display = "block";
    flyer.appendChild(container);

    // The camera frames the head by height, so matching heights lines the
    // flyer's final frame up exactly with the canvas in the site slot.
    const controls = animate(
      flyer,
      {
        x: to.left + to.width / 2 - (from.left + from.width / 2),
        y: to.top + to.height / 2 - (from.top + from.height / 2),
        scale: to.height / from.height,
      },
      { duration: FLIGHT_SECONDS, ease: [0.65, 0, 0.35, 1] },
    );
    void controls.then(() => {
      siteSlot.appendChild(container);
      flyer.style.display = "none";
    });
    return () => controls.stop();
  }, [container, docked, reducedMotion, siteSlot]);

  return (
    <>
      <div
        ref={flyerRef}
        aria-hidden="true"
        className="pointer-events-none fixed z-60 hidden origin-center"
      />
      {createPortal(
        <Suspense
          fallback={
            <div className="grid h-full place-items-center">
              <ShieldCheck
                className="size-1/3 max-h-16 animate-pulse text-teal-400"
                aria-hidden="true"
              />
            </div>
          }
        >
          <RobotHead entering={nodding} reducedMotion={reducedMotion} />
        </Suspense>,
        container,
      )}
    </>
  );
}
