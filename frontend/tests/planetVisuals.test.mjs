import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import * as THREE from 'three';

const document = {
  createElement() {
    const canvas = { width: 0, height: 0, pixels: null, getContext: () => ({
      createImageData: (width, height) => ({ data: new Uint8ClampedArray(width * height * 4) }),
      createRadialGradient: () => ({ addColorStop() {} }),
      putImageData(image) { canvas.pixels = image.data; }, fillRect() {}, fillText() {},
    }) };
    return canvas;
  },
};
function load(name, dependencies = {}) {
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(new URL(`../src/${name}.ts`, import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInNewContext(code, { exports, document, require: name => name === 'three' ? THREE : dependencies[name] });
  return exports;
}
const model = load('galaxyModel');
const { createPlanetVisual, planetAppearance } = load('planetVisuals', { './galaxyModel': model });
const { createConstellationCloud } = load('constellationCloud');
const planet = { id: 'test-planet', available: true, parent_id: null, status: 'READY', version: 1 };

test('file appearance survives new versions and operation changes', () => {
  const source = { ...planet, group_id: 'source-A', name: 'contacts.csv', sheet: '' };
  const result = { ...source, id: 'new-id', version: 4, parent_id: source.id, operation: 'regex_replace' };
  assert.deepEqual(planetAppearance(source), planetAppearance(result));
  const original = createPlanetVisual(source, true);
  const transformed = createPlanetVisual(result, true);
  assert.deepEqual(original.surface.material.bumpMap.image.pixels, transformed.surface.material.bumpMap.image.pixels);
  assert.notDeepEqual(original.surface.material.map.image.pixels, transformed.surface.material.map.image.pixels);
  assert.equal(original.surface.rotation.y, transformed.surface.rotation.y);
  assert.equal(original.body.rotation.z, transformed.body.rotation.z);
  original.resources.forEach(resource => resource.dispose());
  transformed.resources.forEach(resource => resource.dispose());
});

test('new files reuse four bounded terrain types without restyling existing files', () => {
  const first = planetAppearance({ ...planet, group_id: 'source-A' });
  const styles = new Set();
  const seeds = new Set();
  for (let i = 0; i < 1000; i++) {
    const profile = planetAppearance({ ...planet, group_id: `file-${i}` });
    styles.add(profile.kind); seeds.add(profile.seed);
    assert(profile.frequency >= 14 && profile.frequency <= 30);
    assert(Math.abs(profile.tilt) <= .3);
  }
  assert.equal(styles.size, 4);
  assert.equal(seeds.size, 1000);
  assert.deepEqual(first, planetAppearance({ ...planet, group_id: 'source-A' }));
});

test('planets rotate quietly without interaction glow and respect reduced motion', () => {
  const visual = createPlanetVisual(planet, true);
  const start = visual.body.rotation.y;
  for (let i = 0; i < 60; i++) visual.update(1 / 60, false);
  assert(Math.abs(visual.body.rotation.y - start - .072) < 1e-10);
  const stopped = visual.body.rotation.y;
  visual.update(.6, true);
  assert.equal(visual.body.rotation.y, stopped);
  assert.equal(visual.group.getObjectByName('click-glow'), undefined);
  assert.equal(visual.group.getObjectByName('selection'), undefined);
  visual.resources.forEach(resource => resource.dispose());
});

test('ornamental rings never enlarge the clickable planet', () => {
  const visual = createPlanetVisual(planet, true);
  visual.group.updateMatrixWorld(true);
  const ray = new THREE.Raycaster(new THREE.Vector3(0, 0, 200), new THREE.Vector3(0, 0, -1));
  const coreHits = ray.intersectObject(visual.group, true);
  assert(coreHits.length > 0);
  assert(coreHits.every(hit => hit.object === visual.surface));
  ray.ray.origin.x = 45;
  assert.equal(ray.intersectObject(visual.group, true).length, 0);
  visual.resources.forEach(resource => resource.dispose());
});

test('original spiral dust is repeatable, bounded and never intercepts clicks', () => {
  const members = [{ x: 30, y: 10, z: 0 }, { x: 110, y: -30, z: 14 }];
  const center = { x: 70, y: -10, z: 0 };
  const a = createConstellationCloud(members, center, 130, 107, 700);
  const b = createConstellationCloud(members, center, 130, 107, 700);
  const positions = a.group.children[0].geometry.attributes.position;
  assert.equal(positions.count, 600);
  assert.deepEqual(positions.array, b.group.children[0].geometry.attributes.position.array);
  const depths = Array.from({ length: positions.count }, (_, i) => positions.getZ(i));
  assert(depths.every(z => z >= -31 && z <= -5));
  assert([...positions.array].every(Number.isFinite));
  a.group.updateMatrixWorld(true);
  const ray = new THREE.Raycaster(new THREE.Vector3(70, -10, 400), new THREE.Vector3(0, 0, -1));
  assert.equal(ray.intersectObject(a.group, true).length, 0);
  a.resources.forEach(resource => resource.dispose());
  b.resources.forEach(resource => resource.dispose());
});

test('a large library stays inside the scene particle budget', () => {
  let dust = 0;
  for (let i = 0; i < 100; i++) {
    const cloud = createConstellationCloud([{ x: i * 260, y: 0, z: 0 }], { x: i * 260, y: 0, z: 0 }, 95, i, 70);
    dust += cloud.group.children[0].geometry.attributes.position.count;
    cloud.resources.forEach(resource => resource.dispose());
  }
  assert.equal(dust, 7000);
});
