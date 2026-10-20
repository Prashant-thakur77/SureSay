/**
 * A hand-drawn curve from the "I heard" line to the first card. Decorative.
 *
 * It lives only in the stage's left padding (the gutter between the stage
 * edge and the content), so it can never cross text. When the gutter is too
 * narrow to draw it cleanly, it is not drawn at all.
 */

import { useLayoutEffect, useState, type RefObject } from "react";

interface Geometry {
  width: number;
  height: number;
  d: string;
  head: string;
  start: { x: number; y: number };
}

const MIN_GUTTER = 34;

export function Connector({ fromRef, watch }: { fromRef: RefObject<HTMLElement>; watch: string }) {
  const [geo, setGeo] = useState<Geometry | null>(null);

  useLayoutEffect(() => {
    const from = fromRef.current;
    const stage = from?.closest<HTMLElement>(".stage");
    if (!from || !stage) return;
    const measure = () => {
      const target = stage.querySelector<HTMLElement>("button.card, .final__card");
      if (!target) return setGeo(null);
      const s = stage.getBoundingClientRect();
      const a = from.getBoundingClientRect();
      const b = target.getBoundingClientRect();
      const gutter = Math.min(a.left, b.left) - s.left;
      if (gutter < MIN_GUTTER || b.top <= a.bottom) return setGeo(null);
      const x0 = a.left - s.left - 7;
      const y0 = a.top - s.top + a.height / 2;
      const x1 = b.left - s.left - 5;
      const y1 = b.top - s.top + Math.min(b.height / 2, 56);
      const out = Math.max(6, gutter * 0.22);
      // two slightly uneven bends read as drawn by hand
      const midY = y0 + (y1 - y0) * 0.55;
      const d = `M ${x0} ${y0} C ${out + 6} ${y0 + 4}, ${out - 2} ${midY - 30}, ${out + 1} ${midY} S ${x1 - 16} ${y1 + 2}, ${x1} ${y1}`;
      const angle = Math.atan2(2, 16);
      const rot = (dx: number, dy: number) =>
        `${(x1 + dx * Math.cos(angle) - dy * Math.sin(angle)).toFixed(1)} ${(y1 + dx * Math.sin(angle) + dy * Math.cos(angle)).toFixed(1)}`;
      const head = `M ${rot(-9, -5)} L ${x1} ${y1} L ${rot(-9, 5)}`;
      setGeo({ width: gutter, height: s.height, d, head, start: { x: x0, y: y0 } });
    };
    measure();
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measure) : null;
    ro?.observe(stage);
    window.addEventListener("resize", measure);
    return () => {
      ro?.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [fromRef, watch]);

  if (!geo) return null;
  return (
    <svg className="connector" width={geo.width} height={geo.height} viewBox={`0 0 ${geo.width} ${geo.height}`} aria-hidden="true" focusable="false">
      <circle className="connector__dot" cx={geo.start.x} cy={geo.start.y} r="2.6" />
      <path className="connector__line" d={geo.d} pathLength={1} />
      <path className="connector__head" d={geo.head} />
    </svg>
  );
}
