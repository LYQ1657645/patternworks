import * as THREE from 'three';

type Point = { x: number; y: number; z: number };

function random(seed: number) {
  return () => {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    return seed / 4294967296;
  };
}

/** The original three bright spiral arms identify a file without a visible boundary. */
export function createConstellationCloud(
  members: Point[], center: Point, radius: number, seed: number,
  particleBudget = 1800, familyIndex = 0,
) {
  const group = new THREE.Group();
  group.position.set(center.x, center.y, center.z);
  const rand = random(seed);
  const count = Math.min(particleBudget, Math.max(600, Math.min(1800, members.length * 240)));
  const positions = new Float32Array(count * 3), colors = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    const r = Math.sqrt(rand()) * radius;
    const arm = i % 3 * Math.PI * 2 / 3;
    const angle = arm + r / radius * 4 + (rand() - .5) * .8;
    positions.set([Math.cos(angle) * r, Math.sin(angle) * r * .8, -18 + (rand() - .5) * 26], i * 3);
    const color = new THREE.Color().setHSL(.60 + familyIndex * .07 + (rand() - .5) * .06, .3, .32 + rand() * .3);
    colors.set([color.r, color.g, color.b], i * 3);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  const material = new THREE.PointsMaterial({
    size: 1.2, vertexColors: true, transparent: true, opacity: .42,
    depthWrite: false, blending: THREE.AdditiveBlending,
  });
  const dust = new THREE.Points(geometry, material);
  dust.raycast = () => {};
  group.add(dust);
  return { group, resources: [geometry, material] };
}
