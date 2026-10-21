import * as THREE from 'three';

export function createStarField() {
  let seed = 107;
  const rand = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; };
  const count = 2600;
  const positions = new Float32Array(count * 3), colors = new Float32Array(count * 3);
  const sizes = new Float32Array(count), phases = new Float32Array(count);
  for (let i = 0; i < count; i++) {
    const z = rand() * 2 - 1, angle = rand() * Math.PI * 2, r = Math.sqrt(1 - z * z);
    positions.set([r * Math.cos(angle), r * Math.sin(angle), z], i * 3);
    const color = new THREE.Color().setHSL(rand() < .15 ? .10 : .58, .12 + rand() * .22, .65 + rand() * .3);
    colors.set([color.r, color.g, color.b], i * 3);
    sizes[i] = rand() < .035 ? 3.2 + rand() * 2 : .8 + rand() * 1.6;
    phases[i] = rand() * Math.PI * 2;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geometry.setAttribute('starSize', new THREE.BufferAttribute(sizes, 1));
  geometry.setAttribute('phase', new THREE.BufferAttribute(phases, 1));
  const material = new THREE.ShaderMaterial({
    uniforms: { time: { value: 0 }, pixelRatio: { value: Math.min(window.devicePixelRatio, 1.75) } },
    vertexShader: `
      attribute vec3 color;
      attribute float starSize;
      attribute float phase;
      uniform float pixelRatio;
      uniform float time;
      varying vec3 tint;
      varying float shimmer;
      void main() {
        tint = color;
        shimmer = .62 + .10 * sin(time * .7 + phase);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        gl_PointSize = starSize * pixelRatio;
      }
    `,
    fragmentShader: `
      varying vec3 tint;
      varying float shimmer;
      void main() {
        float radius = length(gl_PointCoord - vec2(.5)) * 2.0;
        if (radius > 1.0) discard;
        float core = exp(-radius * radius * 5.0);
        gl_FragColor = vec4(tint, core * shimmer);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }
    `,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const stars = new THREE.Points(geometry, material);
  stars.frustumCulled = false;
  stars.raycast = () => {};
  return { stars, material, resources: [geometry, material] };
}
