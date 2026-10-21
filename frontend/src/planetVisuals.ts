import * as THREE from 'three';
import { planetColor, type Planet } from './galaxyModel';

type Disposable = { dispose(): void };
export type PlanetVisual = {
  group: THREE.Group;
  resources: Disposable[];
  body: THREE.Object3D;
  surface: THREE.Mesh;
  update: (seconds: number, reduced: boolean) => void;
};

function hashId(id: string) {
  let hash = 2166136261;
  for (let i = 0; i < id.length; i++) hash = Math.imul(hash ^ id.charCodeAt(i), 16777619);
  return hash >>> 0;
}

function random(seed: number) {
  return () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 4294967296;
  };
}

/** A source family keeps its appearance when versions, filters or page order change. */
export function planetAppearance(node: Planet) {
  const seed = hashId(node.group_id || JSON.stringify([node.name, node.sheet]));
  const rand = random(seed);
  const kind = (['bands', 'clouds', 'continents', 'craters'] as const)[Math.floor(rand() * 4)];
  return { seed, kind, frequency: 14 + rand() * 16, turbulence: 5 + rand() * 5,
    scale: 2.5 + rand() * 1.8, tilt: (rand() - .5) * .6, orientation: rand() * Math.PI * 2 };
}

// A seeded lattice makes terrain stable across a source family's versions. Sampling a sphere rather
// than a flat rectangle keeps the longitude seam and both poles continuous.
function noiseField(seed: number) {
  const rand = random(seed);
  const permutation = new Uint16Array(512);
  const indices = Array.from({ length: 256 }, (_, i) => i);
  for (let i = 255; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [indices[i], indices[j]] = [indices[j], indices[i]];
  }
  for (let i = 0; i < 512; i++) permutation[i] = indices[i & 255];
  const fade = (v: number) => v * v * (3 - 2 * v);
  const mix = (a: number, b: number, t: number) => a + (b - a) * t;
  const corner = (x: number, y: number, z: number) =>
    permutation[(permutation[(permutation[x & 255] + y) & 255] + z) & 255] / 255;
  const noise = (x: number, y: number, z: number) => {
    const ix = Math.floor(x), iy = Math.floor(y), iz = Math.floor(z);
    const u = fade(x - ix), v = fade(y - iy), w = fade(z - iz);
    return mix(
      mix(mix(corner(ix, iy, iz), corner(ix + 1, iy, iz), u),
        mix(corner(ix, iy + 1, iz), corner(ix + 1, iy + 1, iz), u), v),
      mix(mix(corner(ix, iy, iz + 1), corner(ix + 1, iy, iz + 1), u),
        mix(corner(ix, iy + 1, iz + 1), corner(ix + 1, iy + 1, iz + 1), u), v),
      w,
    );
  };
  return (x: number, y: number, z: number, octaves = 4) => {
    let amplitude = .55, total = 0, weight = 0;
    for (let octave = 0; octave < octaves; octave++) {
      total += noise(x, y, z) * amplitude;
      weight += amplitude;
      x = x * 2.07 + 13.8; y = y * 2.07 + 5.3; z = z * 2.07 + 9.1;
      amplitude *= .47;
    }
    return total / weight;
  };
}

function textureFrom(canvas: HTMLCanvasElement, color = true) {
  const texture = new THREE.CanvasTexture(canvas);
  if (color) texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = THREE.RepeatWrapping;
  texture.anisotropy = 4;
  return texture;
}

function surfaceTextures(node: Planet, appearance: ReturnType<typeof planetAppearance>, compact: boolean) {
  const { seed, kind, frequency, turbulence, scale } = appearance;
  const canvas = document.createElement('canvas');
  const relief = document.createElement('canvas');
  const width = compact ? 128 : 256, height = width / 2;
  canvas.width = relief.width = width; canvas.height = relief.height = height;
  const context = canvas.getContext('2d')!;
  const reliefContext = relief.getContext('2d')!;
  const pixels = context.createImageData(width, height);
  const elevations = reliefContext.createImageData(width, height);
  const color = planetColor(node);
  const base = [1, 3, 5].map(start => parseInt(color.slice(start, start + 2), 16));
  const noise = noiseField(seed);
  const offset = (seed % 157) * .197;
  const clamp = (value: number) => Math.min(1, Math.max(0, value));
  const blend = (a: number, b: number, t: number) => a + (b - a) * t;
  const rand = random(seed + 41);
  const craters = Array.from({ length: 18 }, () => {
    const z = rand() * 2 - 1, angle = rand() * Math.PI * 2, r = Math.sqrt(1 - z * z);
    return { x: Math.cos(angle) * r, y: z, z: Math.sin(angle) * r, size: .045 + rand() * .085 };
  });

  for (let y = 0; y < height; y++) {
    const latitude = y / (height - 1) * Math.PI;
    const sy = Math.cos(latitude), longitudeScale = Math.sin(latitude);
    for (let x = 0; x < width; x++) {
      const longitude = x / width * Math.PI * 2;
      const sx = longitudeScale * Math.cos(longitude);
      const sz = longitudeScale * Math.sin(longitude);
      const warp = noise(sx * 2.2 + offset, sy * 2.2, sz * 2.2, 2);
      const detail = noise(sx * 8 + warp * 2.6, sy * 8 + offset, sz * 8 + warp, 4);
      const landscape = noise(sx * scale + warp * 1.7, sy * scale + offset, sz * scale, 3);
      let shade: number, cloud: number, reliefValue: number;
      if (kind === 'bands') {
        const belt = .5 + .5 * Math.sin(sy * frequency + (warp - .5) * turbulence + (detail - .5) * 4);
        shade = .50 + belt * .32 + (detail - .5) * .25;
        cloud = clamp((landscape - .47) * 2.3) * .38;
        reliefValue = .5;
      } else if (kind === 'continents') {
        const coast = clamp((landscape - .39) * 4.2);
        shade = .30 + coast * .47 + (detail - .5) * .48;
        cloud = clamp((detail - .63) * 5) * .26;
        reliefValue = clamp(.22 + coast * .45 + (detail - .5) * .7);
      } else if (kind === 'clouds') {
        const swirls = .5 + .5 * Math.sin(landscape * frequency + warp * turbulence);
        shade = .43 + swirls * .34 + (detail - .5) * .2;
        cloud = Math.pow(swirls, 3) * .24;
        reliefValue = .46 + (detail - .5) * .12;
      } else {
        let depression = 0, rim = 0;
        for (const crater of craters) {
          const distance = (1 - (sx * crater.x + sy * crater.y + sz * crater.z)) / crater.size;
          if (distance < 1.3) {
            depression = Math.max(depression, Math.max(0, 1 - distance) ** 2);
            rim = Math.max(rim, Math.exp(-(((distance - .9) * 9) ** 2)));
          }
        }
        shade = .61 + (detail - .5) * .32 - depression * .28 + rim * .18;
        cloud = rim * .12;
        reliefValue = clamp(.5 - depression * .4 + rim * .25 + (detail - .5) * .2);
      }
      const i = (y * width + x) * 4;
      for (let channel = 0; channel < 3; channel++) {
        // The same terrain survives every operation; only the existing operation hue changes.
        const highlight = blend(base[channel], 245, .32);
        pixels.data[i + channel] = blend(base[channel] * shade, highlight, cloud);
        elevations.data[i + channel] = reliefValue * 255;
      }
      pixels.data[i + 3] = elevations.data[i + 3] = 255;
    }
  }
  context.putImageData(pixels, 0, 0); reliefContext.putImageData(elevations, 0, 0);
  return { map: textureFrom(canvas), bump: textureFrom(relief, false) };
}

function atmosphereMaterial(color: string) {
  return new THREE.ShaderMaterial({
    uniforms: {
      tint: { value: new THREE.Color(color) },
      lightDirection: { value: new THREE.Vector3(120, 100, 160).normalize() },
    },
    vertexShader: `
      varying vec3 viewNormal;
      varying vec3 viewDirection;
      varying vec3 worldNormal;
      void main() {
        vec4 viewPosition = modelViewMatrix * vec4(position, 1.0);
        viewNormal = normalize(normalMatrix * normal);
        viewDirection = -viewPosition.xyz;
        worldNormal = normalize(mat3(modelMatrix) * normal);
        gl_Position = projectionMatrix * viewPosition;
      }
    `,
    fragmentShader: `
      uniform vec3 tint;
      uniform vec3 lightDirection;
      varying vec3 viewNormal;
      varying vec3 viewDirection;
      varying vec3 worldNormal;
      void main() {
        float facing = max(dot(normalize(viewNormal), normalize(viewDirection)), 0.0);
        float rim = pow(1.0 - facing, 3.6);
        float daylight = smoothstep(-0.35, 0.65,
          dot(normalize(worldNormal), lightDirection));
        gl_FragColor = vec4(tint, rim * (0.06 + daylight * 0.34));
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }
    `,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    side: THREE.FrontSide,
  });
}

function haloTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 64;
  const context = canvas.getContext('2d')!;
  const gradient = context.createRadialGradient(32, 32, 0, 32, 32, 32);
  gradient.addColorStop(0, 'rgba(255,255,255,0)');
  gradient.addColorStop(.48, 'rgba(255,255,255,.015)');
  gradient.addColorStop(.68, 'rgba(255,255,255,.08)');
  gradient.addColorStop(1, 'rgba(255,255,255,0)');
  context.fillStyle = gradient; context.fillRect(0, 0, 64, 64);
  return textureFrom(canvas);
}

export function createPlanetVisual(node: Planet, compact = false): PlanetVisual {
  const resources: Disposable[] = [];
  const group = new THREE.Group();
  const body = new THREE.Group();
  group.add(body);
  const appearance = planetAppearance(node);
  const { seed } = appearance;
  const radius = node.parent_id ? 22 : 26;
  const color = planetColor(node);
  const incomplete = !node.available || (!!node.status && node.status !== 'READY');
  const { map, bump } = surfaceTextures(node, appearance, compact);
  const geometry = new THREE.SphereGeometry(radius, 48, 32);
  const material = new THREE.MeshStandardMaterial({
    map,
    bumpMap: bump,
    bumpScale: appearance.kind === 'craters' ? .45 : appearance.kind === 'continents' ? .34 : .08,
    roughness: .88,
    metalness: 0,
    wireframe: incomplete,
    transparent: incomplete,
    opacity: incomplete ? .32 : 1,
  });
  const sphere = new THREE.Mesh(geometry, material);
  sphere.rotation.y = appearance.orientation;
  body.rotation.z = appearance.tilt;
  body.add(sphere);
  resources.push(map, bump, geometry, material);

  if (!incomplete) {
    const atmosphereGeometry = new THREE.SphereGeometry(radius * 1.035, 40, 28);
    const atmosphere = atmosphereMaterial(color);
    body.add(new THREE.Mesh(atmosphereGeometry, atmosphere));
    const glow = haloTexture();
    const glowMaterial = new THREE.SpriteMaterial({
      map: glow, color, transparent: true, depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const glowSprite = new THREE.Sprite(glowMaterial);
    glowSprite.scale.setScalar(radius * 3.2);
    body.add(glowSprite);
    resources.push(atmosphereGeometry, atmosphere, glow, glowMaterial);
  }

  if (!node.parent_id && !incomplete) {
    const ringGeometry = new THREE.RingGeometry(radius * 1.31, radius * 1.68, 96);
    const positions = ringGeometry.attributes.position;
    const uv = ringGeometry.attributes.uv;
    for (let i = 0; i < positions.count; i++) {
      uv.setXY(i, (Math.hypot(positions.getX(i), positions.getY(i)) / radius - 1.31) / .37, .5);
    }
    const ringCanvas = document.createElement('canvas');
    ringCanvas.width = 256; ringCanvas.height = 1;
    const context = ringCanvas.getContext('2d')!;
    const rand = random(seed + 7);
    for (let x = 0; x < 256; x++) {
      const t = x / 255;
      const gap = t > .67 && t < .73 ? .08 : 1;
      const opacity = Math.sin(t * Math.PI) * (.34 + rand() * .30) * gap;
      context.fillStyle = `rgba(219,197,157,${opacity})`; context.fillRect(x, 0, 1, 1);
    }
    const ringTexture = textureFrom(ringCanvas);
    ringTexture.wrapS = THREE.ClampToEdgeWrapping;
    const ringMaterial = new THREE.MeshStandardMaterial({
      map: ringTexture, side: THREE.DoubleSide, transparent: true,
      depthWrite: false, roughness: 1,
    });
    const rings = new THREE.Mesh(ringGeometry, ringMaterial);
    rings.rotation.x = 1.12 + appearance.tilt; rings.rotation.y = .13; rings.position.z = -.7;
    group.add(rings);
    resources.push(ringGeometry, ringTexture, ringMaterial);
  }

  const update = (seconds: number, reduced: boolean) => {
    const elapsed = Math.max(0, seconds);
    const delta = Math.min(.05, elapsed);
    // Motion is frame-rate independent and stops completely with reduced motion.
    if (!reduced) body.rotation.y += delta * .072;
  };

  const labelCanvas = document.createElement('canvas');
  labelCanvas.width = 256; labelCanvas.height = 64;
  const context = labelCanvas.getContext('2d')!;
  const kind = node.status && node.status !== 'READY'
    ? node.status.toLowerCase()
    : !node.available ? 'unavailable' : !node.parent_id ? 'original' : 'result';
  context.font = '500 24px sans-serif'; context.textAlign = 'center';
  context.fillStyle = '#d8e1ee'; context.fillText(`V${node.version}  ${kind}`, 128, 38);
  const labelTexture = textureFrom(labelCanvas);
  const labelMaterial = new THREE.SpriteMaterial({
    map: labelTexture, depthWrite: false, transparent: true,
  });
  const label = new THREE.Sprite(labelMaterial);
  label.scale.set(80, 20, 1); label.position.y = -radius - 26;
  group.add(label); resources.push(labelTexture, labelMaterial);
  // Only the physical surface is interactive; transparent decoration must not steal edge hits.
  group.traverse(object=>{if(object!==sphere)object.raycast=()=>{};});
  return { group, resources, body, surface: sphere, update };
}
