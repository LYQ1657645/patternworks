export type ScreenPoint = { x: number; y: number };
export type ProjectedEdge = { id: string; points: readonly ScreenPoint[] };

const finitePoint = (point: ScreenPoint) => Number.isFinite(point.x) && Number.isFinite(point.y);

/**
 * Find the closest visible edge within a CSS-pixel radius.
 * Invalid points break a path rather than creating an invisible shortcut.
 * Callers should exclude points behind the camera and give planet hits priority.
 */
export function nearestProjectedEdge(
  point: ScreenPoint,
  paths: readonly ProjectedEdge[],
  radius = 16,
): string | null {
  if (!finitePoint(point) || !Number.isFinite(radius) || radius < 0) return null;
  let closest: string | null = null;
  let closestDistance = radius;

  for (const path of paths) {
    for (let index = 1; index < path.points.length; index += 1) {
      const start = path.points[index - 1], end = path.points[index];
      if (!finitePoint(start) || !finitePoint(end)) continue;
      const dx = end.x - start.x, dy = end.y - start.y;
      const length = Math.hypot(dx, dy);
      if (!Number.isFinite(length)) continue;
      const along = length === 0 ? 0 : Math.max(0, Math.min(length,
        (point.x - start.x) * (dx / length) + (point.y - start.y) * (dy / length)));
      const ratio = length === 0 ? 0 : along / length;
      const distance = Math.hypot(point.x - (start.x + dx * ratio), point.y - (start.y + dy * ratio));
      if (!Number.isFinite(distance) || distance > radius) continue;
      if (distance < closestDistance || (distance === closestDistance && (closest === null || path.id < closest))) {
        closest = path.id;
        closestDistance = distance;
      }
    }
  }
  return closest;
}
